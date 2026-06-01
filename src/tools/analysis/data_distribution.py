# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import json
import logging
import math
from typing import Any, Dict, List, Set, Tuple

from .data_fetching_helper import (
    QUERY_TYPE_PPL,
    AnalysisParameters,
    execute_ppl_and_parse_docs,
    fetch_index_data_dsl,
    get_field_types,
    get_flattened_value,
    get_number_fields,
    NUMBER_FIELD_TYPES,
)

logger = logging.getLogger(__name__)

USEFUL_FIELD_TYPES = {
    'keyword',
    'boolean',
    'text',
    'byte',
    'short',
    'integer',
    'long',
    'float',
    'double',
    'half_float',
    'scaled_float',
}
DEFAULT_COMPARISON_RESULT_LIMIT = 10
DEFAULT_SINGLE_ANALYSIS_RESULT_LIMIT = 30
MIN_CARDINALITY_DIVISOR = 4
MIN_CARDINALITY_BASE = 5
ID_FIELD_MAX_CARDINALITY = 30
DATA_FIELD_MAX_CARDINALITY = 10
DATA_FIELD_CARDINALITY_DIVISOR = 2
NUMERIC_GROUPING_THRESHOLD = 10
PERCENTAGE_MULTIPLIER = 100.0
TOP_CHANGES_LIMIT = 10


async def execute_data_distribution(client, params: AnalysisParameters) -> dict:
    """Main entry point for data distribution analysis."""
    logger.debug('Starting data distribution analysis with parameters: index=%s', params.index)
    if params.query_type == QUERY_TYPE_PPL:
        return await _execute_ppl_analysis(client, params)
    else:
        return await _execute_dsl_analysis(client, params)


async def _execute_dsl_analysis(client, params: AnalysisParameters) -> dict:
    """Fetch data via DSL queries and perform distribution analysis."""
    if params.has_baseline_time_range():
        selection_data = await fetch_index_data_dsl(
            client, params.selection_time_range_start, params.selection_time_range_end, params
        )
        baseline_data = await fetch_index_data_dsl(
            client, params.baseline_time_range_start, params.baseline_time_range_end, params
        )
        if not selection_data:
            raise RuntimeError('No data found for selection time range')
        if not baseline_data:
            raise RuntimeError('No data found for baseline time range')
        result = await _get_comparison_distribution(
            client, selection_data, baseline_data, params.index
        )
        return {'comparisonAnalysis': result}
    else:
        selection_data = await fetch_index_data_dsl(
            client, params.selection_time_range_start, params.selection_time_range_end, params
        )
        if not selection_data:
            raise RuntimeError('No data found for selection time range')
        result = await _analyze_single_dataset(client, selection_data, params.index)
        return {'singleAnalysis': result}


async def _execute_ppl_analysis(client, params: AnalysisParameters) -> dict:
    """Fetch data via PPL queries and perform distribution analysis."""
    if params.has_baseline_time_range():
        selection_query = _build_ppl_query(
            params.index,
            params.time_field,
            params.selection_time_range_start,
            params.selection_time_range_end,
            params.size,
            params.ppl,
        )
        baseline_query = _build_ppl_query(
            params.index,
            params.time_field,
            params.baseline_time_range_start,
            params.baseline_time_range_end,
            params.size,
            params.ppl,
        )
        selection_data = await execute_ppl_and_parse_docs(client, selection_query)
        baseline_data = await execute_ppl_and_parse_docs(client, baseline_query)
        if not selection_data:
            raise RuntimeError('No data found for selection time range')
        if not baseline_data:
            raise RuntimeError('No data found for baseline time range')
        result = await _get_comparison_distribution(
            client, selection_data, baseline_data, params.index
        )
        return {'comparisonAnalysis': result}
    else:
        selection_query = _build_ppl_query(
            params.index,
            params.time_field,
            params.selection_time_range_start,
            params.selection_time_range_end,
            params.size,
            params.ppl,
        )
        selection_data = await execute_ppl_and_parse_docs(client, selection_query)
        if not selection_data:
            raise RuntimeError('No data found for selection time range')
        result = await _analyze_single_dataset(client, selection_data, params.index)
        return {'singleAnalysis': result}


def _build_ppl_query(
    index: str, time_field: str, start_time: str, end_time: str, size: int, custom_ppl: str
) -> str:
    if custom_ppl:
        base_query = _get_ppl_query_with_time_range(custom_ppl, start_time, end_time, time_field)
    else:
        base_query = _get_ppl_query_with_time_range(
            f'source={index}', start_time, end_time, time_field
        )
    return f'{base_query} | head {size}'


def _format_time_for_ppl(time_string: str) -> str:
    from datetime import datetime as dt

    # Normalize trailing 'Z' to '+00:00' for fromisoformat (Python 3.10 compat)
    normalized = time_string.replace('Z', '+00:00') if time_string.endswith('Z') else time_string
    try:
        zdt = dt.fromisoformat(normalized)
        return zdt.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    except (ValueError, TypeError):
        pass
    try:
        local_dt = dt.strptime(time_string, '%Y-%m-%d %H:%M:%S')
        return local_dt.strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        pass
    return time_string


def _get_ppl_query_with_time_range(
    query: str, start_time: str, end_time: str, time_field: str
) -> str:
    if not query:
        raise ValueError('PPL query cannot be empty')
    if not time_field:
        return query

    formatted_start = _format_time_for_ppl(start_time)
    formatted_end = _format_time_for_ppl(end_time)
    time_predicate = (
        f"`{time_field}` >= '{formatted_start}' AND `{time_field}` <= '{formatted_end}'"
    )

    commands = query.split('|')
    command_list = [commands[0].strip(), f'WHERE {time_predicate}']
    for cmd in commands[1:]:
        cmd = cmd.strip()
        if cmd:
            command_list.append(cmd)
    return ' | '.join(command_list)


async def _get_comparison_distribution(
    client, selection_data: List[Dict], baseline_data: List[Dict], index: str
) -> List[Dict]:
    """Compare field distributions between selection and baseline, ranked by divergence."""
    field_types = await get_field_types(client, index)
    useful_fields = _get_useful_fields(selection_data, field_types)
    number_fields = get_number_fields(field_types)
    analyses = []

    for field in useful_fields:
        selection_dist = _calculate_field_distribution(selection_data, field)
        baseline_dist = _calculate_field_distribution(baseline_data, field)

        if field in number_fields:
            selection_dist, baseline_dist = _group_numeric_keys(selection_dist, baseline_dist)

        divergence = _calculate_max_difference(selection_dist, baseline_dist)
        analyses.append(
            {
                'field': field,
                'divergence': divergence,
                'selection_dist': selection_dist,
                'baseline_dist': baseline_dist,
            }
        )

    analyses.sort(key=lambda a: a['divergence'], reverse=True)
    return _format_comparison_summary(analyses, DEFAULT_COMPARISON_RESULT_LIMIT)


async def _analyze_single_dataset(client, data: List[Dict], index: str) -> List[Dict]:
    """Analyze field distributions within a single dataset, ranked by divergence."""
    field_types = await get_field_types(client, index)
    useful_fields = _get_useful_fields(data, field_types)
    number_fields = get_number_fields(field_types)
    analyses = []

    for field in useful_fields:
        selection_dist = _calculate_field_distribution(data, field)
        baseline_dist: Dict[str, float] = {}

        if field in number_fields:
            selection_dist, _ = _group_numeric_keys(selection_dist, baseline_dist)

        divergence = _calculate_max_difference(selection_dist, baseline_dist)
        analyses.append(
            {
                'field': field,
                'divergence': divergence,
                'selection_dist': selection_dist,
                'baseline_dist': baseline_dist,
            }
        )

    analyses.sort(key=lambda a: a['divergence'], reverse=True)
    return _format_comparison_summary(analyses, DEFAULT_SINGLE_ANALYSIS_RESULT_LIMIT)


def _get_useful_fields(data: List[Dict], field_types: Dict[str, str]) -> List[str]:
    """Filter fields suitable for distribution analysis based on type and cardinality."""
    if not field_types:
        logger.warning('No field types available, using data-based field detection')
        return _get_fields_from_data(data)

    keyword_fields: Set[str] = set()
    number_fields_set: Set[str] = set()

    for field_name, field_type in field_types.items():
        if field_type in USEFUL_FIELD_TYPES:
            keyword_fields.add(field_name)
        if field_type in NUMBER_FIELD_TYPES:
            number_fields_set.add(field_name)

    normalized_fields = set()
    for field in keyword_fields:
        if field.endswith('.keyword'):
            normalized_fields.add(field.replace('.keyword', ''))
        else:
            normalized_fields.add(field)

    field_value_sets: Dict[str, Set[str]] = {field: set() for field in normalized_fields}
    max_cardinality = max(MIN_CARDINALITY_BASE, len(data) // MIN_CARDINALITY_DIVISOR)

    for doc in data:
        for field in normalized_fields:
            value = get_flattened_value(doc, field)
            if value is not None:
                field_value_sets[field].add(str(value))

    result = []
    for field in normalized_fields:
        cardinality = len(field_value_sets[field])
        if field.lower().endswith('id'):
            if 0 < cardinality <= ID_FIELD_MAX_CARDINALITY:
                result.append(field)
        elif field in number_fields_set:
            # if cardinality > 0:
            result.append(field)
        else:
            if 0 < cardinality <= max_cardinality:
                result.append(field)
    return result


def _get_fields_from_data(data: List[Dict]) -> List[str]:
    """Extract analyzable fields directly from data when index mapping is unavailable."""
    if not data:
        return []

    all_fields: Set[str] = set()
    for doc in data:
        all_fields.update(doc.keys())

    result = []
    excluded = {'@timestamp', '_id', '_index'}
    for field in all_fields:
        if field in excluded:
            continue
        values: Set[str] = set()
        for doc in data:
            value = doc.get(field)
            if value is not None:
                values.add(str(value))
        cardinality = len(values)
        threshold = max(DATA_FIELD_MAX_CARDINALITY, len(data) // DATA_FIELD_CARDINALITY_DIVISOR)
        if 0 < cardinality <= threshold:
            result.append(field)
    return result


def _calculate_field_distribution(data: List[Dict], field: str) -> Dict[str, float]:
    """Calculate relative frequency of each value for a given field."""
    if not data:
        return {}

    counts: Dict[str, int] = {}
    for doc in data:
        value = get_flattened_value(doc, field)
        if value is not None:
            str_value = str(value)
            counts[str_value] = counts.get(str_value, 0) + 1

    return {k: v / len(data) for k, v in counts.items()}


def _calculate_max_difference(
    selection_dist: Dict[str, float], baseline_dist: Dict[str, float]
) -> float:
    """Compute the maximum absolute difference across all values between two distributions."""
    all_keys = set(selection_dist.keys()) | set(baseline_dist.keys())
    if not all_keys:
        return float('-inf')
    return max(abs(selection_dist.get(key, 0.0) - baseline_dist.get(key, 0.0)) for key in all_keys)


def _group_numeric_keys(
    selection_dist: Dict[str, float], baseline_dist: Dict[str, float]
) -> Tuple[Dict[str, float], Dict[str, float]]:
    """Group numeric field values into 5 equal-width bins when cardinality exceeds threshold."""
    all_keys = set(selection_dist.keys()) | set(baseline_dist.keys())

    if len(all_keys) <= NUMERIC_GROUPING_THRESHOLD:
        return selection_dist, baseline_dist

    numeric_keys = []
    for key in all_keys:
        try:
            numeric_keys.append(float(key))
        except (ValueError, TypeError):
            return selection_dist, baseline_dist

    numeric_keys.sort()
    min_val = numeric_keys[0]
    max_val = numeric_keys[-1]
    range_val = max_val - min_val
    if range_val == 0:
        return selection_dist, baseline_dist

    num_groups = 5
    group_size = range_val / num_groups

    def get_group_label(num_key: float) -> str:
        group_index = (
            num_groups - 1 if num_key == max_val else int((num_key - min_val) / group_size)
        )
        lower_bound = min_val + group_index * group_size
        upper_bound = (
            max_val if group_index == num_groups - 1 else min_val + (group_index + 1) * group_size
        )
        return f'{lower_bound:.1f}-{upper_bound:.1f}'

    grouped_selection: Dict[str, float] = {}
    grouped_baseline: Dict[str, float] = {}

    for num_key in numeric_keys:
        label = get_group_label(num_key)
        str_key = str(num_key)
        grouped_selection[label] = grouped_selection.get(label, 0.0) + selection_dist.get(
            str_key, 0.0
        )
        grouped_baseline[label] = grouped_baseline.get(label, 0.0) + baseline_dist.get(
            str_key, 0.0
        )

    all_groups = set(grouped_selection.keys()) | set(grouped_baseline.keys())
    for group in all_groups:
        grouped_selection.setdefault(group, 0.0)
        grouped_baseline.setdefault(group, 0.0)

    return grouped_selection, grouped_baseline


def _format_comparison_summary(analyses: List[Dict], max_results: int) -> List[Dict]:
    """Format analysis results into summary with top value changes per field."""
    result = []
    for diff in analyses:
        if diff['divergence'] <= 0:
            continue
        if len(result) >= max_results:
            break

        selection_dist = diff['selection_dist']
        baseline_dist = diff['baseline_dist']
        has_baseline = bool(baseline_dist)

        all_keys = set(selection_dist.keys()) | set(baseline_dist.keys())
        changes = []
        for value in all_keys:
            sel_pct = (
                round(selection_dist.get(value, 0.0) * PERCENTAGE_MULTIPLIER)
                / PERCENTAGE_MULTIPLIER
            )
            base_pct = (
                round(baseline_dist.get(value, 0.0) * PERCENTAGE_MULTIPLIER)
                / PERCENTAGE_MULTIPLIER
                if has_baseline
                else None
            )
            changes.append(
                {
                    'value': value,
                    'selectionPercentage': sel_pct,
                    'baselinePercentage': base_pct,
                }
            )

        if has_baseline:
            changes.sort(
                key=lambda c: max(c.get('baselinePercentage') or 0.0, c['selectionPercentage']),
                reverse=True,
            )
        else:
            changes.sort(key=lambda c: c['selectionPercentage'], reverse=True)

        top_changes = changes[:TOP_CHANGES_LIMIT]
        result.append(
            {
                'field': diff['field'],
                'divergence': diff['divergence'],
                'topChanges': top_changes,
            }
        )
    return result
