# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import logging
import math
from .data_fetching_helper import (
    AnalysisParameters,
    format_time_string,
    get_field_types,
    get_number_fields,
)
from typing import Dict, List, Set


logger = logging.getLogger(__name__)

DEFAULT_TOP_N = 10
LOG_RATIO_CAP = 10.0
EPSILON = 1e-10


async def execute_metric_change_analysis(
    client, params: AnalysisParameters, top_n: int = DEFAULT_TOP_N
) -> dict:
    """Compare percentile distributions (P50, P90) of numeric fields between two time ranges.

    Uses OpenSearch percentiles aggregation for server-side computation instead of
    fetching raw documents.
    """
    logger.debug('Starting metric change analysis with parameters: index=%s', params.index)

    field_types = await get_field_types(client, params.index)
    number_fields = get_number_fields(field_types)

    if not number_fields:
        raise RuntimeError(
            'No numeric fields found in index. Percentile analysis requires numeric fields.'
        )

    selection_stats = await _fetch_percentiles_via_agg(
        client,
        params.index,
        params.time_field,
        params.selection_time_range_start,
        params.selection_time_range_end,
        number_fields,
        params,
    )
    baseline_stats = await _fetch_percentiles_via_agg(
        client,
        params.index,
        params.time_field,
        params.baseline_time_range_start,
        params.baseline_time_range_end,
        number_fields,
        params,
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
    number_fields: Set[str],
    params: AnalysisParameters,
) -> Dict[str, Dict[str, float]]:
    """Fetch P50 and P90 for all numeric fields using a single aggregation request."""
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

    aggs = {}
    for field in number_fields:
        safe_name = field.replace('.', '_DOT_')
        aggs[safe_name] = {'percentiles': {'field': field, 'percents': [50, 90]}}

    search_body = {
        'query': {'bool': bool_query},
        'size': 0,
        'aggs': aggs,
    }

    response = await client.search(index=index, body=search_body)

    total_hits = response.get('hits', {}).get('total', {})
    if isinstance(total_hits, dict):
        count = total_hits.get('value', 0)
    else:
        count = total_hits
    if count == 0:
        return {}

    aggregations = response.get('aggregations', {})
    stats: Dict[str, Dict[str, float]] = {}

    for field in number_fields:
        safe_name = field.replace('.', '_DOT_')
        agg_result = aggregations.get(safe_name, {})
        values = agg_result.get('values', {})
        p50 = values.get('50.0')
        p90 = values.get('90.0')
        if p50 is None and p90 is None:
            continue
        stats[field] = {
            'p50': float(p50) if p50 is not None else 0.0,
            'p90': float(p90) if p90 is not None else 0.0,
        }

    return stats


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


def _extract_numeric_values(data: List[Dict], field: str) -> List[float]:
    """Extract numeric values from dataset for a specific field."""
    from .data_fetching_helper import get_flattened_value

    values = []
    for doc in data:
        value = get_flattened_value(doc, field)
        if value is not None:
            try:
                if isinstance(value, (int, float)):
                    values.append(float(value))
                else:
                    values.append(float(str(value)))
            except (ValueError, TypeError):
                pass
    return values


def _calculate_percentiles(values: List[float]) -> Dict[str, float]:
    """Calculate P50 and P90 for a list of values."""
    if not values:
        return {'p50': 0.0, 'p90': 0.0}

    import numpy as np

    arr = np.asarray(values, dtype=np.float64)
    p50, p90 = np.percentile(arr, [50, 90], method='linear')
    return {'p50': float(p50), 'p90': float(p90)}


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


def _check_time_field(time_field: str, field_types: Dict[str, str]) -> str:
    """Check if timeField exists in mapping, return hint if not."""
    if time_field in field_types:
        return ''
    date_fields = [name for name, ftype in field_types.items() if ftype == 'date']
    suggested = date_fields[0] if date_fields else 'unknown'
    return (
        f"\n\nERROR: Invalid parameter 'timeField'.\n"
        f'Current value: {time_field}\n'
        f'Valid values: {", ".join(date_fields)}\n'
        f"REQUIRED ACTION: Retry this tool call with timeField='{suggested}'"
    )
