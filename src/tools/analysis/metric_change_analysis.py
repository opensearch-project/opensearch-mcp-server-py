# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import logging
import math
from .constants import (
    DATE_FIELD_TYPES,
    DEFAULT_TOP_N,
    EPSILON,
    GROUP_BY_TERMS_SIZE,
    GROUP_METRIC_KEY_SEP,
    LOG_RATIO_CAP,
    MAX_ANALYSIS_DOC_COUNT,
    MULTI_GROUP_KEY_SEP,
)
from .data_fetching_helper import (
    AnalysisParameters,
    format_time_string,
    get_field_types,
    get_number_fields,
)
from opensearchpy.exceptions import RequestError
from typing import Dict, List, Optional, Sequence, Set


logger = logging.getLogger(__name__)


async def execute_metric_change_analysis(
    client,
    params: AnalysisParameters,
    top_n: int = DEFAULT_TOP_N,
    group_by: Optional[Sequence[str]] = None,
) -> dict:
    """Compare percentile distributions (P50, P90) of numeric fields between two time ranges.

    When `group_by` is None, each numeric column gets one global percentile per
    window (the original behavior). When `group_by` is non-empty, percentiles are
    computed per (group, numeric_column) bucket so different services / hosts /
    KPIs aren't mixed together.
    """
    logger.debug('Starting metric change analysis: index=%s, group_by=%s', params.index, group_by)

    field_types = await get_field_types(client, params.index)
    number_fields = get_number_fields(field_types)

    if not number_fields:
        raise RuntimeError(
            'No numeric fields found in index. Percentile analysis requires numeric fields.'
        )

    group_by = list(group_by) if group_by else []

    # Guard against unbounded windows: percentile analysis over a huge window is
    # expensive for the cluster. Count each window first and, if either exceeds
    # the cap, ask the caller to narrow the offending time range instead.
    await _check_window_doc_counts(client, params)

    if group_by:
        fetch = _fetch_percentiles_grouped_via_agg
        fetch_kwargs = {'number_fields': number_fields, 'group_by': group_by}
    else:
        fetch = _fetch_percentiles_via_agg
        fetch_kwargs = {'number_fields': number_fields}

    selection_stats = await fetch(
        client,
        params.index,
        params.time_field,
        params.selection_time_range_start,
        params.selection_time_range_end,
        params,
        **fetch_kwargs,
    )
    baseline_stats = await fetch(
        client,
        params.index,
        params.time_field,
        params.baseline_time_range_start,
        params.baseline_time_range_end,
        params,
        **fetch_kwargs,
    )

    if not selection_stats:
        hint = _check_time_field(params.time_field, field_types)
        raise RuntimeError(f'No data found for selection time range.{hint}')
    if not baseline_stats:
        hint = _check_time_field(params.time_field, field_types)
        raise RuntimeError(f'No data found for baseline time range.{hint}')

    analyses = _calculate_metric_change_from_agg(selection_stats, baseline_stats)
    results = _format_results(analyses, top_n)
    return {'percentileAnalysis': results}


async def _fetch_percentiles_via_agg(
    client,
    index: str,
    time_field: str,
    time_range_start: str,
    time_range_end: str,
    params: AnalysisParameters,
    number_fields: Set[str],
) -> Dict[str, Dict[str, float]]:
    """Wide-format fetch: one percentiles agg per numeric column."""
    bool_query = _build_bool_query(time_field, time_range_start, time_range_end, params)

    aggs = {}
    for field in number_fields:
        safe_name = field.replace('.', '_DOT_')
        aggs[safe_name] = {'percentiles': {'field': field, 'percents': [50, 90]}}

    search_body = {'query': {'bool': bool_query}, 'size': 0, 'aggs': aggs}

    response = await _safe_search(client, index, search_body)
    if _hit_count(response) == 0:
        return {}

    aggregations = response.get('aggregations', {})
    stats: Dict[str, Dict[str, float]] = {}
    for field in number_fields:
        safe_name = field.replace('.', '_DOT_')
        values = aggregations.get(safe_name, {}).get('values', {})
        p50, p90 = values.get('50.0'), values.get('90.0')
        if p50 is None and p90 is None:
            continue
        stats[field] = {
            'p50': float(p50) if p50 is not None else 0.0,
            'p90': float(p90) if p90 is not None else 0.0,
        }
    return stats


async def _fetch_percentiles_grouped_via_agg(
    client,
    index: str,
    time_field: str,
    time_range_start: str,
    time_range_end: str,
    params: AnalysisParameters,
    number_fields: Set[str],
    group_by: Sequence[str],
) -> Dict[str, Dict[str, float]]:
    """Group-by fetch: bucket by `group_by` first, percentiles per numeric column inside.

    Returns `{<group_key><sep><numeric_field>: {p50, p90}}`. The composite
    keys are what the LLM sees back in the result, e.g.
    `ServiceTest6_response_rate` or `MySQL_3306|host01_value`.
    """
    bool_query = _build_bool_query(time_field, time_range_start, time_range_end, params)

    inner_aggs = {}
    for field in number_fields:
        safe_name = field.replace('.', '_DOT_')
        inner_aggs[safe_name] = {'percentiles': {'field': field, 'percents': [50, 90]}}

    if len(group_by) == 1:
        outer_agg = {'terms': {'field': group_by[0], 'size': GROUP_BY_TERMS_SIZE}}
    else:
        outer_agg = {
            'multi_terms': {
                'terms': [{'field': f} for f in group_by],
                'size': GROUP_BY_TERMS_SIZE,
            }
        }
    outer_agg['aggs'] = inner_aggs

    search_body = {
        'query': {'bool': bool_query},
        'size': 0,
        'aggs': {'groups': outer_agg},
    }

    response = await _safe_search(client, index, search_body)
    if _hit_count(response) == 0:
        return {}

    buckets = response.get('aggregations', {}).get('groups', {}).get('buckets', [])
    stats: Dict[str, Dict[str, float]] = {}
    for bucket in buckets:
        group_key = _bucket_group_key(bucket, len(group_by))
        for field in number_fields:
            safe_name = field.replace('.', '_DOT_')
            values = bucket.get(safe_name, {}).get('values', {})
            p50, p90 = values.get('50.0'), values.get('90.0')
            if p50 is None and p90 is None:
                continue
            composite_key = f'{group_key}{GROUP_METRIC_KEY_SEP}{field}'
            stats[composite_key] = {
                'p50': float(p50) if p50 is not None else 0.0,
                'p90': float(p90) if p90 is not None else 0.0,
            }
    return stats


def _bucket_group_key(bucket: dict, n_group_fields: int) -> str:
    """Pull the group-by key out of a terms / multi_terms bucket."""
    if n_group_fields == 1:
        return str(bucket.get('key'))
    # multi_terms: prefer pre-joined key_as_string, else join the list ourselves.
    key_str = bucket.get('key_as_string')
    if key_str:
        return key_str
    raw = bucket.get('key', [])
    if isinstance(raw, list):
        return MULTI_GROUP_KEY_SEP.join(str(part) for part in raw)
    return str(raw)


def _build_bool_query(
    time_field: str,
    time_range_start: str,
    time_range_end: str,
    params: AnalysisParameters,
) -> dict:
    import json

    bool_query: dict = {
        'must': [
            {
                'range': {
                    time_field: {
                        'gte': format_time_string(time_range_start),
                        'lte': format_time_string(time_range_end),
                        'format': 'strict_date_optional_time||epoch_millis',
                    }
                }
            }
        ]
    }

    if params.dsl:
        dsl_map = json.loads(params.dsl.replace("'", '"'))
        if 'query' in dsl_map:
            dsl_map = dsl_map['query']
        bool_query['must'].append(dsl_map)
    elif params.filter:
        for filter_item in params.filter:
            if isinstance(filter_item, dict):
                bool_query['must'].append(filter_item)
            else:
                filter_map = json.loads(str(filter_item).replace("'", '"'))
                bool_query['must'].append(filter_map)

    return bool_query


async def _safe_search(client, index: str, body: dict) -> dict:
    try:
        return await client.search(index=index, body=body)
    except RequestError as e:
        raise RuntimeError(_translate_filter_request_error(e)) from e


def _hit_count(response: dict) -> int:
    total = response.get('hits', {}).get('total', {})
    if isinstance(total, dict):
        return total.get('value', 0)
    return total or 0


async def _count_docs(
    client,
    index: str,
    time_field: str,
    time_range_start: str,
    time_range_end: str,
    params: AnalysisParameters,
) -> int:
    """Count documents matching a single time window (plus any filter)."""
    bool_query = _build_bool_query(time_field, time_range_start, time_range_end, params)
    try:
        response = await client.count(index=index, body={'query': {'bool': bool_query}})
    except RequestError as e:
        raise RuntimeError(_translate_filter_request_error(e)) from e
    return int(response.get('count', 0))


async def _check_window_doc_counts(client, params: AnalysisParameters) -> None:
    """Ensure neither window exceeds MAX_ANALYSIS_DOC_COUNT before analysis.

    Raises a RuntimeError naming the offending window(s) so the LLM knows which
    time range to narrow. When both windows are too large, both are reported.
    """
    selection_count = await _count_docs(
        client,
        params.index,
        params.time_field,
        params.selection_time_range_start,
        params.selection_time_range_end,
        params,
    )
    baseline_count = await _count_docs(
        client,
        params.index,
        params.time_field,
        params.baseline_time_range_start,
        params.baseline_time_range_end,
        params,
    )

    oversized = []
    if selection_count > MAX_ANALYSIS_DOC_COUNT:
        oversized.append(
            f'the selection range ({params.selection_time_range_start} to '
            f'{params.selection_time_range_end}) matches {selection_count} docs'
        )
    if baseline_count > MAX_ANALYSIS_DOC_COUNT:
        oversized.append(
            f'the baseline range ({params.baseline_time_range_start} to '
            f'{params.baseline_time_range_end}) matches {baseline_count} docs'
        )

    if oversized:
        raise RuntimeError(
            f'Too many documents to analyze: {" and ".join(oversized)}, '
            f'over the limit of {MAX_ANALYSIS_DOC_COUNT} per range. '
            'Narrow only the range(s) named above and retry, keeping the two '
            'ranges similar in duration for a fair percentile comparison.'
        )


def _calculate_metric_change_from_agg(
    selection_stats: Dict[str, Dict[str, float]],
    baseline_stats: Dict[str, Dict[str, float]],
) -> List[Dict]:
    """Calculate percentile changes for all numeric fields from aggregation results."""
    analyses = []
    common_fields = set(selection_stats.keys()) & set(baseline_stats.keys())

    for field in common_fields:
        sel = selection_stats[field]
        base = baseline_stats[field]
        variance = _calculate_percentile_variance(sel, base)
        analyses.append(
            {
                'field': field,
                'variance': variance,
                'selection_stats': sel,
                'baseline_stats': base,
            }
        )

    analyses.sort(key=lambda a: a['variance'], reverse=True)
    return analyses


def _calculate_percentile_variance(
    selection_stats: Dict[str, float], baseline_stats: Dict[str, float]
) -> float:
    """Calculate change score using weighted log-ratio on P50 and P90."""
    p50_valid = abs(baseline_stats['p50']) >= EPSILON
    p90_valid = abs(baseline_stats['p90']) >= EPSILON

    if not p50_valid and not p90_valid:
        return 0.0
    if p50_valid and p90_valid:
        return 0.5 * _safe_log_ratio(
            selection_stats['p50'], baseline_stats['p50']
        ) + 0.5 * _safe_log_ratio(selection_stats['p90'], baseline_stats['p90'])
    if p50_valid:
        return _safe_log_ratio(selection_stats['p50'], baseline_stats['p50'])
    return _safe_log_ratio(selection_stats['p90'], baseline_stats['p90'])


def _safe_log_ratio(selection: float, baseline: float) -> float:
    """Compute |log(selection / baseline)| with safe handling of near-zero values."""
    if abs(baseline) < EPSILON and abs(selection) < EPSILON:
        return 0.0
    if abs(baseline) < EPSILON:
        return LOG_RATIO_CAP
    ratio = selection / baseline
    if ratio <= 0:
        return 0.0
    return abs(math.log(ratio))


def _format_results(analyses: List[Dict], top_n: int) -> List[Dict]:
    """Format top N results for output."""
    results = []
    for analysis in analyses[:top_n]:
        sel = analysis['selection_stats']
        base = analysis['baseline_stats']
        results.append(
            {
                'field': analysis['field'],
                'changeScore': analysis['variance'],
                'selectionPercentiles': {'p50': sel['p50'], 'p90': sel['p90']},
                'baselinePercentiles': {'p50': base['p50'], 'p90': base['p90']},
                'logRatios': {
                    'p50': _safe_log_ratio(sel['p50'], base['p50']),
                    'p90': _safe_log_ratio(sel['p90'], base['p90']),
                },
            }
        )
    return results


def _translate_filter_request_error(error: RequestError) -> str:
    """Translate OpenSearch 400 errors caused by bad filter into LLM-actionable hints.

    The most common failures from LLM-generated filters are:
    - wildcard/prefix queries on metadata fields (_id, _field_names, etc.) — OpenSearch
      only allows these on keyword/text fields.
    - query_string without an explicit `fields` clause — expansion across all fields
      exceeds the index field-expansion limit (default 1024) on wide indices.
    """
    raw = str(error)
    metadata_field = None
    for meta in ('_id', '_field_names', '_index', '_type', '_routing'):
        if f'[{meta}]' in raw:
            metadata_field = meta
            break

    if metadata_field and ('wildcard queries on' in raw or 'prefix queries on' in raw):
        return (
            f'filter cannot use wildcard/prefix queries on the metadata field '
            f"'{metadata_field}' — these queries are only supported on keyword or text "
            f'fields. Rewrite the filter to target a business field, for example: '
            f'{{"wildcard": {{"serviceName": "ts-auth-service*"}}}} or '
            f'{{"term": {{"serviceName": "ts-auth-service"}}}}.'
        )

    if 'field expansion for [*] matches too many fields' in raw:
        return (
            'filter using query_string without an explicit `fields` list caused field '
            'expansion to exceed the index limit. Either restrict the query to specific '
            'fields, e.g. {"query_string": {"query": "ts-auth-service*", '
            '"fields": ["serviceName"]}}, or switch to a term/wildcard query on a '
            'specific business field.'
        )

    return f'filter rejected by OpenSearch: {raw}'


def _check_time_field(time_field: str, field_types: Dict[str, str]) -> str:
    """Return a hint explaining why a query returned no data.

    Distinguishes two root causes so the caller knows what to fix:
    - timeField is valid (exists in the mapping): the time range is likely the
      problem, so the hint points at the time range.
    - timeField does not exist in the mapping: the timeField itself is wrong,
      so the hint names the actual date fields available in the index.
    """
    if time_field in field_types:
        return (
            f" The timeField '{time_field}' exists in the index, so the time range is"
            ' likely the problem: no documents fall within the requested time range.'
            ' Try widening the time range.'
        )
    date_fields = [name for name, ftype in field_types.items() if ftype in DATE_FIELD_TYPES]
    return (
        f" The timeField '{time_field}' does not exist in this index, so no documents"
        ' could match (this is a timeField problem, not a time range problem).'
        f' Retry with one of the actual date fields in the index: {date_fields}'
    )
