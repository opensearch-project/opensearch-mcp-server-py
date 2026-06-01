# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import logging
import math
from typing import Any, Dict, List, Set

from .data_fetching_helper import (
    AnalysisParameters,
    fetch_index_data_dsl,
    get_field_types,
    get_flattened_value,
    get_number_fields,
)

logger = logging.getLogger(__name__)

DEFAULT_TOP_N = 10
LOG_RATIO_CAP = 10.0
EPSILON = 1e-10


async def execute_metric_change_analysis(
    client, params: AnalysisParameters, top_n: int = DEFAULT_TOP_N
) -> dict:
    """Compare percentile distributions (P50, P90) of numeric fields between two time ranges."""
    logger.debug('Starting metric change analysis with parameters: index=%s', params.index)

    field_types = await get_field_types(client, params.index)
    number_fields = get_number_fields(field_types)

    if not number_fields:
        raise RuntimeError(
            'No numeric fields found in index. Percentile analysis requires numeric fields.'
        )

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

    analyses = _calculate_metric_change_analysis(selection_data, baseline_data, number_fields)
    results = _format_results(analyses, top_n)
    return {'percentileAnalysis': results}


def _calculate_metric_change_analysis(
    selection_data: List[Dict[str, Any]],
    baseline_data: List[Dict[str, Any]],
    number_fields: Set[str],
) -> List[Dict]:
    """Calculate percentile changes for all numeric fields, sorted by change score."""
    analyses = []

    for field in number_fields:
        selection_values = _extract_numeric_values(selection_data, field)
        baseline_values = _extract_numeric_values(baseline_data, field)

        if not selection_values or not baseline_values:
            continue

        selection_stats = _calculate_percentiles(selection_values)
        baseline_stats = _calculate_percentiles(baseline_values)
        variance = _calculate_percentile_variance(selection_stats, baseline_stats)

        analyses.append(
            {
                'field': field,
                'variance': variance,
                'selection_stats': selection_stats,
                'baseline_stats': baseline_stats,
            }
        )

    analyses.sort(key=lambda a: a['variance'], reverse=True)
    return analyses


def _extract_numeric_values(data: List[Dict[str, Any]], field: str) -> List[float]:
    """Extract numeric values from dataset for a specific field."""
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

    sorted_values = sorted(values)
    p50 = _percentile(sorted_values, 50)
    p90 = _percentile(sorted_values, 90)
    return {'p50': p50, 'p90': p90}


def _percentile(sorted_values: List[float], percentile: int) -> float:
    """Calculate a specific percentile from sorted values using linear interpolation."""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]

    index = (percentile / 100.0) * (len(sorted_values) - 1)
    lower_index = int(math.floor(index))
    upper_index = int(math.ceil(index))

    if lower_index == upper_index:
        return sorted_values[lower_index]

    lower_value = sorted_values[lower_index]
    upper_value = sorted_values[upper_index]
    fraction = index - lower_index
    return lower_value + (upper_value - lower_value) * fraction


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
