# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import logging
import math
import re
from typing import Any, Dict, List, Optional, Set

from .clustering_helper import ClusteringHelper
from .hierarchical_agglomerative_clustering import calculate_cosine_similarity
from .data_fetching_helper import execute_ppl_and_parse_datarows

logger = logging.getLogger(__name__)

LOG_VECTORS_CLUSTERING_THRESHOLD = 0.5
LOG_PATTERN_THRESHOLD = 0.75
LOG_PATTERN_LIFT = 3
DEFAULT_TIME_FIELD = '@timestamp'
MAX_LOG_SAMPLE_SIZE = 10000

REPEATED_WILDCARDS_PATTERN = re.compile(r'(<\*>)(\s+<\*>)+')

ERROR_KEYWORDS = {
    'error', 'err', 'exception', 'failed', 'failure', 'timeout', 'panic',
    'fatal', 'critical', 'severe', 'abort', 'aborted', 'aborting', 'crash',
    'crashed', 'broken', 'corrupt', 'corrupted', 'invalid', 'malformed',
    'unprocessable', 'denied', 'forbidden', 'unauthorized', 'conflict',
    'deadlock', 'overflow', 'underflow', 'throttled', 'disk_full',
    'insufficient', 'retrying', 'backpressure', 'degraded', 'unexpected',
    'unusual', 'missing', 'stale', 'expired', 'mismatch', 'violation',
}


async def execute_log_pattern_analysis(
    client,
    index: str,
    time_field: str,
    log_field_name: str,
    trace_field_name: str,
    base_time_range_start: str,
    base_time_range_end: str,
    selection_time_range_start: str,
    selection_time_range_end: str,
    filter_expr: str,
) -> dict:
    """Main entry point: dispatches to sequence analysis, pattern diff, or log insight."""
    logger.debug("Starting log pattern analysis with parameters: index=%s", index)
    has_base_time = bool(base_time_range_start) and bool(base_time_range_end)
    has_trace_field = bool(trace_field_name)

    if has_trace_field and has_base_time:
        if filter_expr:
            logger.warning("Filter parameter is ignored for sequence analysis mode as it requires all logs within a trace")
        logger.debug("Performing log sequence analysis for index: %s", index)
        return await _log_sequence_analysis(
            client, index, time_field, log_field_name, trace_field_name,
            base_time_range_start, base_time_range_end,
            selection_time_range_start, selection_time_range_end,
        )
    elif has_base_time:
        logger.debug("Performing log pattern analysis for index: %s", index)
        return await _log_pattern_diff_analysis(
            client, index, time_field, log_field_name,
            base_time_range_start, base_time_range_end,
            selection_time_range_start, selection_time_range_end,
            filter_expr,
        )
    else:
        return await _log_insight(
            client, index, time_field, log_field_name,
            selection_time_range_start, selection_time_range_end,
            filter_expr,
        )


# ==============================================================================
# Sequence Analysis
# ==============================================================================

async def _log_sequence_analysis(
    client, index: str, time_field: str, log_field_name: str, trace_field_name: str,
    base_start: str, base_end: str, selection_start: str, selection_end: str,
) -> dict:
    """Identify exceptional trace sequences by comparing selection vs baseline."""
    selection_ppl = _build_log_pattern_ppl_with_trace(
        index, time_field, log_field_name, trace_field_name,
        selection_start, selection_end, '',
    )
    selection_result = await _execute_sequence_ppl(client, selection_ppl)
    logger.debug(
        "Selection time range analysis completed, found %d traces",
        len(selection_result['trace_pattern_map']),
    )

    if not selection_result['trace_pattern_map']:
        return {'BASE': {}, 'EXCEPTIONAL': {}}

    base_ppl = _build_log_pattern_ppl_with_trace(
        index, time_field, log_field_name, trace_field_name,
        base_start, base_end, '',
    )
    base_result = await _execute_sequence_ppl(client, base_ppl)
    logger.debug(
        "Base time range analysis completed, found %d traces",
        len(base_result['trace_pattern_map']),
    )

    return _generate_sequence_comparison_result(base_result, selection_result)


async def _execute_sequence_ppl(client, ppl: str) -> dict:
    """Execute PPL and build trace_pattern_map, pattern_count_map, and pattern_weights."""
    datarows = await execute_ppl_and_parse_datarows(client, ppl)

    trace_pattern_map: Dict[str, List[str]] = {}
    pattern_count_map: Dict[str, Set[str]] = {}
    raw_pattern_cache: Dict[str, str] = {}

    for row in datarows:
        if len(row) < 2:
            continue
        trace_id = str(row[0])
        raw_pattern = str(row[1])

        if raw_pattern not in raw_pattern_cache:
            raw_pattern_cache[raw_pattern] = _post_process_pattern(raw_pattern)
        simplified_pattern = raw_pattern_cache[raw_pattern]

        if trace_id not in trace_pattern_map:
            trace_pattern_map[trace_id] = []
        if simplified_pattern not in trace_pattern_map[trace_id]:
            trace_pattern_map[trace_id].append(simplified_pattern)

        if simplified_pattern not in pattern_count_map:
            pattern_count_map[simplified_pattern] = set()
        pattern_count_map[simplified_pattern].add(trace_id)

    pattern_weights = _vectorize_pattern(pattern_count_map, len(trace_pattern_map))

    return {
        'trace_pattern_map': trace_pattern_map,
        'pattern_count_map': pattern_count_map,
        'pattern_weights': pattern_weights,
    }


def _vectorize_pattern(pattern_count_map: Dict[str, Set[str]], total_trace_count: int) -> Dict[str, float]:
    """Compute IDF-based weights: weight = sigmoid(log(total_traces / doc_freq))."""
    pattern_values: Dict[str, float] = {}
    for pattern, trace_ids in pattern_count_map.items():
        if trace_ids:
            idf = math.log(total_trace_count / len(trace_ids))
            value = 1.0 / (1.0 + math.exp(-idf))
            pattern_values[pattern] = value
        else:
            pattern_values[pattern] = 0.0
    return pattern_values


def _generate_sequence_comparison_result(base_result: dict, selection_result: dict) -> dict:
    """Build vectors, cluster, and filter to find exceptional selection traces."""
    all_patterns = set(base_result['pattern_count_map'].keys()) | set(selection_result['pattern_count_map'].keys())
    sorted_patterns = sorted(all_patterns)
    pattern_index_map = {p: i for i, p in enumerate(sorted_patterns)}
    logger.debug("vector dimension is %d", len(sorted_patterns))

    base_vector_map = _build_vector_map(
        base_result['trace_pattern_map'],
        base_result['pattern_weights'],
        pattern_index_map,
        is_selection=False,
    )

    clustering_helper = ClusteringHelper(LOG_VECTORS_CLUSTERING_THRESHOLD)
    base_representative = clustering_helper.cluster_log_vectors_and_get_representative(base_vector_map)

    selection_vector_map = _build_vector_map(
        selection_result['trace_pattern_map'],
        selection_result['pattern_weights'],
        pattern_index_map,
        is_selection=True,
        base_pattern_count_map=base_result['pattern_count_map'],
        selection_pattern_count_map=selection_result['pattern_count_map'],
    )

    selection_representative = clustering_helper.cluster_log_vectors_and_get_representative(
        selection_vector_map
    )

    trace_need_to_examine = _filter_selection_centroids(
        base_representative, selection_representative, base_vector_map, selection_vector_map
    )
    logger.info(
        "Identified %d traceNeedToExamine centroids from %d candidates",
        len(trace_need_to_examine), len(selection_representative),
    )

    return _build_final_result(
        base_representative, trace_need_to_examine,
        base_result['trace_pattern_map'], selection_result['trace_pattern_map'],
    )


def _build_vector_map(
    trace_pattern_map: Dict[str, List[str]],
    pattern_weights: Dict[str, float],
    pattern_index_map: Dict[str, int],
    is_selection: bool = False,
    base_pattern_count_map: Optional[Dict[str, Set[str]]] = None,
    selection_pattern_count_map: Optional[Dict[str, Set[str]]] = None,
) -> Dict[str, List[float]]:
    """Build a weighted vector per trace. Selection vectors get extra weight for novel patterns."""
    dimension = len(pattern_index_map)
    vector_map: Dict[str, List[float]] = {}

    for trace_id, patterns in trace_pattern_map.items():
        vector = [0.0] * dimension
        for pattern in patterns:
            index = pattern_index_map.get(pattern)
            if index is not None:
                base_value = 0.5 * pattern_weights.get(pattern, 0.0)
                if is_selection and base_pattern_count_map is not None and selection_pattern_count_map is not None:
                    existence_weight = 0 if pattern in base_pattern_count_map else 1
                    vector[index] = base_value + 0.5 * existence_weight
                else:
                    vector[index] = base_value
        vector_map[trace_id] = vector

    return vector_map


def _filter_selection_centroids(
    base_centroids: List[str],
    selection_candidates: List[str],
    base_vector_map: Dict[str, List[float]],
    selection_vector_map: Dict[str, List[float]],
) -> List[str]:
    """Keep only selection centroids dissimilar to all base centroids."""
    selection_centroids = []
    for candidate in selection_candidates:
        candidate_vector = selection_vector_map.get(candidate)
        if candidate_vector is None:
            logger.warning("No vector found for selection candidate: %s", candidate)
            continue

        is_exceptional = True
        for base_centroid in base_centroids:
            base_vector = base_vector_map.get(base_centroid)
            if base_vector is not None:
                sim = calculate_cosine_similarity(base_vector, candidate_vector)
                if sim > LOG_VECTORS_CLUSTERING_THRESHOLD:
                    is_exceptional = False
                    break

        if is_exceptional:
            selection_centroids.append(candidate)

    return selection_centroids


def _build_final_result(
    base_centroids: List[str],
    selection_centroids: List[str],
    base_trace_pattern_map: Dict[str, List[str]],
    selection_trace_pattern_map: Dict[str, List[str]],
) -> dict:
    """Map centroid trace IDs to "pat1 -> pat2 -> ..." sequences."""
    base_sequences = {}
    for centroid in base_centroids:
        patterns = base_trace_pattern_map.get(centroid)
        if patterns:
            base_sequences[centroid] = ' -> '.join(patterns)

    selection_sequences = {}
    for centroid in selection_centroids:
        patterns = selection_trace_pattern_map.get(centroid)
        if patterns:
            selection_sequences[centroid] = ' -> '.join(patterns)

    return {'BASE': base_sequences, 'EXCEPTIONAL': selection_sequences}


# ==============================================================================
# Pattern Diff Analysis
# ==============================================================================

async def _log_pattern_diff_analysis(
    client, index: str, time_field: str, log_field_name: str,
    base_start: str, base_end: str, selection_start: str, selection_end: str,
    filter_expr: str,
) -> dict:
    """Compare pattern frequencies between baseline and selection, return top by lift."""
    base_ppl = _build_log_pattern_ppl_aggregation(
        index, time_field, log_field_name, base_start, base_end, filter_expr
    )
    logger.debug("Executing base time range pattern PPL: %s", base_ppl)
    base_datarows = await execute_ppl_and_parse_datarows(client, base_ppl)
    base_patterns: Dict[str, float] = {}
    for row in base_datarows:
        if len(row) == 2:
            pattern = str(row[1])
            count = float(row[0])
            base_patterns[pattern] = count
    _merge_similar_patterns(base_patterns)
    logger.debug("Base patterns processed: %d patterns", len(base_patterns))

    selection_ppl = _build_log_pattern_ppl_aggregation(
        index, time_field, log_field_name, selection_start, selection_end, filter_expr
    )
    logger.debug("Executing selection time range pattern PPL: %s", selection_ppl)
    selection_datarows = await execute_ppl_and_parse_datarows(client, selection_ppl)
    selection_patterns: Dict[str, float] = {}
    for row in selection_datarows:
        if len(row) == 2:
            pattern = str(row[1])
            count = float(row[0])
            selection_patterns[pattern] = count
    _merge_similar_patterns(selection_patterns)
    logger.debug("Selection patterns processed: %d patterns", len(selection_patterns))

    differences = _calculate_pattern_differences(base_patterns, selection_patterns)
    logger.debug("Pattern analysis completed: %d differences found", len(differences))

    with_lift = sorted(
        [d for d in differences if d['lift'] is not None],
        key=lambda d: (d['lift'], d['selection'] or 0),
        reverse=True,
    )[:10]
    without_lift = sorted(
        [d for d in differences if d['lift'] is None],
        key=lambda d: d['selection'] or 0,
        reverse=True,
    )[:10]

    return {'patternMapDifference': with_lift + without_lift}


# ==============================================================================
# Log Insight
# ==============================================================================

async def _log_insight(
    client, index: str, time_field: str, log_field_name: str,
    selection_start: str, selection_end: str, filter_expr: str,
) -> dict:
    """Find top error/warning patterns with sample logs in the selection time range."""
    filter_clause = f" | where {filter_expr}" if filter_expr else ''
    error_keywords_str = ' '.join(ERROR_KEYWORDS)

    ppl = (
        f"source={index} | where {time_field}>'{selection_start}' and {time_field}<'{selection_end}'"
        f"{filter_clause}"
        f" | where match({log_field_name}, '{error_keywords_str}') | head {MAX_LOG_SAMPLE_SIZE}"
        f" | fields {log_field_name} | patterns {log_field_name} method=brain"
        f" mode=aggregation max_sample_count=5 variable_count_threshold=3"
        f" | fields patterns_field, pattern_count, sample_logs | sort -pattern_count | head 5"
    )

    datarows = await execute_ppl_and_parse_datarows(client, ppl)
    log_insights = []
    for row in datarows:
        if len(row) == 3:
            log_insights.append({
                'pattern': row[0],
                'count': row[1],
                'sampleLogs': row[2],
            })

    return {'logInsights': log_insights}


# ==============================================================================
# Helpers
# ==============================================================================

def _build_log_pattern_ppl_with_trace(
    index: str, time_field: str, log_field_name: str, trace_field_name: str,
    start_time: str, end_time: str, filter_expr: str,
) -> str:
    """Build PPL for sequence analysis: patterns grouped by trace, sorted by time."""
    filter_clause = f" | where {filter_expr}" if filter_expr else ''
    return (
        f"source={index} | where {trace_field_name}!='' "
        f"| where {time_field}>'{start_time}' and {time_field}<'{end_time}'{filter_clause} "
        f"| fields {trace_field_name}, {log_field_name}, {time_field} "
        f"| patterns {log_field_name} method=brain variable_count_threshold=3 "
        f"| fields {trace_field_name}, patterns_field, {time_field} | sort {time_field}"
    )


def _build_log_pattern_ppl_aggregation(
    index: str, time_field: str, log_field_name: str,
    start_time: str, end_time: str, filter_expr: str,
) -> str:
    """Build PPL for pattern diff: aggregate patterns with counts."""
    filter_clause = f" | where {filter_expr}" if filter_expr else ''
    return (
        f"source={index} | where {time_field}>'{start_time}' and {time_field}<'{end_time}'{filter_clause} "
        f"| fields {log_field_name} | patterns {log_field_name} method=brain mode=aggregation variable_count_threshold=3 "
        f"| fields pattern_count, patterns_field"
    )


def _post_process_pattern(pattern: str) -> str:
    """Collapse consecutive wildcards into a single <*>."""
    if not pattern:
        return pattern
    return REPEATED_WILDCARDS_PATTERN.sub('<*>', pattern)


def _jaccard_similarity(pattern1: str, pattern2: str) -> float:
    if not pattern1 and not pattern2:
        return 1.0
    if not pattern1 or not pattern2:
        return 0.0
    set1 = set(pattern1.split())
    set2 = set(pattern2.split())
    union = set1 | set2
    intersection_size = len(set1) + len(set2) - len(union)
    return intersection_size / len(union) if union else 0.0


def _merge_similar_patterns(pattern_map: Dict[str, float]):
    if not pattern_map:
        return

    patterns = sorted(pattern_map.keys())
    removed: Set[str] = set()

    for i in range(len(patterns)):
        p1 = patterns[i]
        if p1 in removed:
            continue
        for j in range(i + 1, len(patterns)):
            p2 = patterns[j]
            if p2 in removed:
                continue
            if _jaccard_similarity(p1, p2) > LOG_PATTERN_THRESHOLD:
                count1 = pattern_map.get(p1, 0.0)
                count2 = pattern_map.get(p2, 0.0)
                pattern_map[p1] = count1 + count2
                del pattern_map[p2]
                removed.add(p2)
                logger.debug("Merged similar patterns: '%s' + '%s' -> '%s'", p1, p2, p1)

    to_replace: Dict[str, str] = {}
    for pattern in list(pattern_map.keys()):
        processed = _post_process_pattern(pattern)
        if processed != pattern:
            to_replace[pattern] = processed

    for original, processed in to_replace.items():
        count = pattern_map.pop(original)
        pattern_map[processed] = pattern_map.get(processed, 0.0) + count

    logger.debug("Pattern merging completed: %d patterns remaining", len(pattern_map))


def _calculate_pattern_differences(
    base_patterns: Dict[str, float], selection_patterns: Dict[str, float]
) -> List[Dict]:
    differences = []
    selection_total = sum(selection_patterns.values())
    base_total = sum(base_patterns.values())

    if selection_total == 0:
        return differences

    for pattern, selection_count in selection_patterns.items():
        if pattern in base_patterns:
            base_count = base_patterns[pattern]
            if base_total == 0:
                continue
            lift = (selection_count / selection_total) / (base_count / base_total)
            if lift < 1:
                lift = 1.0 / lift
            if lift > LOG_PATTERN_LIFT:
                differences.append({
                    'pattern': pattern,
                    'base': base_count / base_total,
                    'selection': selection_count / selection_total,
                    'lift': lift,
                })
        else:
            differences.append({
                'pattern': pattern,
                'base': 0.0,
                'selection': selection_count / selection_total,
                'lift': None,
            })
            logger.debug("New selection pattern detected: %s (count: %s)", pattern, selection_count)

    return differences
