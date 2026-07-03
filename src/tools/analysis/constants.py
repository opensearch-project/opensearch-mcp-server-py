# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Shared constants for the analysis (skills) tools."""

import re


# ---------------------------------------------------------------------------
# Query / time defaults
# ---------------------------------------------------------------------------

# Time format accepted from callers, e.g. "2025-01-02 00:00:00".
DATE_FORMAT_PATTERN = '%Y-%m-%d %H:%M:%S'

# Supported queryType values.
QUERY_TYPE_PPL = 'ppl'
QUERY_TYPE_DSL = 'dsl'

# Fallback time field when `timeField` is not provided.
DEFAULT_TIME_FIELD = '@timestamp'

# Default and hard upper bound for `size` (source documents per analysis).
DEFAULT_SIZE = 1000
MAX_SIZE_LIMIT = 10000

# OpenSearch numeric field types.
NUMBER_FIELD_TYPES = {
    'byte',
    'short',
    'integer',
    'long',
    'float',
    'double',
    'half_float',
    'scaled_float',
    'unsigned_long',
}

# OpenSearch date field types treated as valid time fields.
DATE_FIELD_TYPES = {'date', 'date_nanos'}


# ---------------------------------------------------------------------------
# Data distribution analysis
# ---------------------------------------------------------------------------

# Field types analyzed for value-frequency distribution.
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

# Max fields returned in comparison vs single-window mode.
DEFAULT_COMPARISON_RESULT_LIMIT = 10
DEFAULT_SINGLE_ANALYSIS_RESULT_LIMIT = 30

# Categorical-field cardinality cap: max(MIN_BASE, len(data) // MIN_DIVISOR).
# Fields above the cap are skipped (treated as effectively unique).
MIN_CARDINALITY_DIVISOR = 4
MIN_CARDINALITY_BASE = 5

# Looser cap for fields whose name ends in `id`.
ID_FIELD_MAX_CARDINALITY = 30

# Fallback caps when index mapping is unavailable:
# threshold = max(DATA_FIELD_MAX, len(data) // DATA_FIELD_DIVISOR).
DATA_FIELD_MAX_CARDINALITY = 10
DATA_FIELD_CARDINALITY_DIVISOR = 2

# Numeric fields with more distinct values than this get bucketed into 5 bins.
NUMERIC_GROUPING_THRESHOLD = 10

# Round fractions to 2 decimal percent: round(fraction * 100) / 100.
PERCENTAGE_MULTIPLIER = 100.0

# Max value-level changes returned per field.
TOP_CHANGES_LIMIT = 10


# ---------------------------------------------------------------------------
# Metric change analysis
# ---------------------------------------------------------------------------

# Default top fields returned, ranked by changeScore.
DEFAULT_TOP_N = 10

# Cap on |log(selection/baseline)| when baseline is ~0.
LOG_RATIO_CAP = 10.0

# Below this, a percentile value is treated as zero (avoids divide-by-zero).
EPSILON = 1e-10

# Max documents allowed in a single window before the tool refuses to run and
# asks the caller to narrow the time range. Bounding the window keeps the
# percentile analysis cheap for the cluster. Tune as needed.
MAX_ANALYSIS_DOC_COUNT = 100000


# ---------------------------------------------------------------------------
# Log pattern analysis
# ---------------------------------------------------------------------------

# Cosine-distance threshold for clustering log vectors.
LOG_VECTORS_CLUSTERING_THRESHOLD = 0.5

# Pattern-similarity threshold for grouping raw logs into patterns.
LOG_PATTERN_THRESHOLD = 0.75

# Lift threshold for a "surging" pattern: selection_freq / baseline_freq.
LOG_PATTERN_LIFT = 3

# Cap on log lines fetched per window.
MAX_LOG_SAMPLE_SIZE = 10000

# Collapse runs of placeholder tokens like '<*> <*> <*>' into a single '<*>'.
REPEATED_WILDCARDS_PATTERN = re.compile(r'(<\*>)(\s+<\*>)+')

# Lowercase keywords used to filter "interesting" log lines in insight mode.
ERROR_KEYWORDS = {
    'error',
    'err',
    'exception',
    'failed',
    'failure',
    'timeout',
    'panic',
    'fatal',
    'critical',
    'severe',
    'abort',
    'aborted',
    'aborting',
    'crash',
    'crashed',
    'broken',
    'corrupt',
    'corrupted',
    'invalid',
    'malformed',
    'unprocessable',
    'denied',
    'forbidden',
    'unauthorized',
    'conflict',
    'deadlock',
    'overflow',
    'underflow',
    'throttled',
    'disk_full',
    'insufficient',
    'retrying',
    'backpressure',
    'degraded',
    'unexpected',
    'unusual',
    'missing',
    'stale',
    'expired',
    'mismatch',
    'violation',
}


# ---------------------------------------------------------------------------
# Metric change analysis — groupBy
# ---------------------------------------------------------------------------

# Cap on group buckets returned by terms / multi_terms agg.
GROUP_BY_TERMS_SIZE = 1000

# Separator between multiple groupBy field values inside a composite key.
MULTI_GROUP_KEY_SEP = '|'

# Separator between group key and numeric metric column in the final output key.
GROUP_METRIC_KEY_SEP = '_'
