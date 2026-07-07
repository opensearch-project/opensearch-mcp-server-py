# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import logging
from .analysis.data_distribution import execute_data_distribution
from .analysis.data_fetching_helper import AnalysisParameters
from .analysis.log_pattern_analysis import execute_log_pattern_analysis
from .analysis.metric_change_analysis import execute_metric_change_analysis
from .tool_logging import log_tool_error
from .tool_params import baseToolArgs
from .utils import format_json
from opensearch.client import get_opensearch_client
from pydantic import Field


logger = logging.getLogger(__name__)


class DataDistributionToolArgs(baseToolArgs):
    """Arguments for the DataDistributionTool."""

    index: str = Field(description='Target OpenSearch index name')
    selectionTimeRangeStart: str = Field(
        description='Start time for analysis period (format: yyyy-MM-dd HH:mm:ss)'
    )
    selectionTimeRangeEnd: str = Field(
        description='End time for analysis period (format: yyyy-MM-dd HH:mm:ss)'
    )
    timeField: str = Field(description='Date/time field for filtering(required)')
    baselineTimeRangeStart: str = Field(
        default='', description='Start time for baseline period (format: yyyy-MM-dd HH:mm:ss)'
    )
    baselineTimeRangeEnd: str = Field(
        default='', description='End time for baseline period (format: yyyy-MM-dd HH:mm:ss)'
    )
    size: int = Field(default=1000, description='Maximum number of documents to analyze')
    queryType: str = Field(default='dsl', description="Query type: 'dsl' (default) or 'ppl'")
    filter: str = Field(
        default='',
        description=(
            'Optional DSL filter clauses as JSON array. Target a business field '
            '(e.g. serviceName), NOT metadata fields like _id or _field_names. '
            'Example: [{"term":{"serviceName":"ts-auth-service"}}].'
        ),
    )
    dsl: str = Field(default='', description='Complete DSL query as JSON string')
    ppl: str = Field(
        default='', description='PPL query without time filtering (added automatically)'
    )


class MetricChangeAnalysisToolArgs(baseToolArgs):
    """Arguments for the MetricChangeAnalysisTool."""

    index: str = Field(description='Target OpenSearch index name')
    selectionTimeRangeStart: str = Field(
        description='Start of target period (format: yyyy-MM-dd HH:mm:ss)'
    )
    selectionTimeRangeEnd: str = Field(
        description='End of target period (format: yyyy-MM-dd HH:mm:ss)'
    )
    timeField: str = Field(description='Date/time field for filtering')
    baselineTimeRangeStart: str = Field(
        description='Start of baseline period (format: yyyy-MM-dd HH:mm:ss)'
    )
    baselineTimeRangeEnd: str = Field(
        description='End of baseline period (format: yyyy-MM-dd HH:mm:ss). Should be at or before selectionTimeRangeStart'
    )
    topN: int = Field(
        default=10,
        description='Number of top fields to return, ranked by change score (default: 10)',
    )
    queryType: str = Field(
        default='dsl', description="Query type: 'ppl' or 'dsl' (default: 'dsl')"
    )
    filter: str = Field(
        default='',
        description=(
            'Optional DSL filter, a single JSON object or a JSON array of clauses. '
            'Target a business field (e.g. serviceName), NOT metadata fields like _id. '
            'Example: {"term":{"serviceName":"ts-auth-service"}}.'
        ),
    )
    dsl: str = Field(default='', description='Complete raw DSL query as JSON string (optional)')
    ppl: str = Field(
        default='', description='Complete PPL statement without time information (optional)'
    )
    groupBy: list[str] = Field(
        default_factory=list,
        description=(
            'Optional categorical keyword fields to bucket by before computing percentiles. '
            'Leave empty when the index has many numeric columns (metric identity is in the '
            'column name); pass dimensions like service_name / cmdb_id / kpi_name when there '
            'are few numeric columns so distinct services / hosts / KPIs are not blended. '
            'Never pass time/date fields. '
            'Output `field` becomes "<group>_<column>" (or "<g1>|<g2>_<column>" for multiple).'
        ),
    )


class LogPatternAnalysisToolArgs(baseToolArgs):
    """Arguments for the LogPatternAnalysisTool."""

    index: str = Field(description='Target OpenSearch index name containing log data')
    logFieldName: str = Field(description='Field containing raw log messages to analyze')
    selectionTimeRangeStart: str = Field(
        description='Start time for analysis target period (format: yyyy-MM-dd HH:mm:ss)'
    )
    selectionTimeRangeEnd: str = Field(
        description='End time for analysis target period (format: yyyy-MM-dd HH:mm:ss)'
    )
    timeField: str = Field(description='Date/time field for time-based filtering(required)')
    traceFieldName: str = Field(
        default='', description='Field for trace/correlation ID (optional)'
    )
    baseTimeRangeStart: str = Field(
        default='',
        description='Start time for baseline comparison period (format: yyyy-MM-dd HH:mm:ss)',
    )
    baseTimeRangeEnd: str = Field(
        default='',
        description='End time for baseline comparison period (format: yyyy-MM-dd HH:mm:ss)',
    )
    filter: str = Field(
        default='',
        description="PPL boolean expression to filter logs (e.g. serviceName='ts-auth-service')",
    )


async def data_distribution_tool(args: DataDistributionToolArgs) -> list[dict]:
    """Analyze data distribution over time ranges."""
    try:
        params = AnalysisParameters(
            {
                'index': args.index,
                'timeField': args.timeField,
                'selectionTimeRangeStart': args.selectionTimeRangeStart,
                'selectionTimeRangeEnd': args.selectionTimeRangeEnd,
                'baselineTimeRangeStart': args.baselineTimeRangeStart,
                'baselineTimeRangeEnd': args.baselineTimeRangeEnd,
                'size': str(args.size),
                'queryType': args.queryType,
                'filter': args.filter,
                'dsl': args.dsl,
                'ppl': args.ppl,
            }
        )
        params.validate()

        async with get_opensearch_client(args) as client:
            result = await execute_data_distribution(client, params)

        formatted = format_json(result)
        return [{'type': 'text', 'text': f'DataDistributionTool result:\n{formatted}'}]

    except Exception as e:
        return log_tool_error('DataDistributionTool', e, 'executing DataDistributionTool')


async def metric_change_analysis_tool(args: MetricChangeAnalysisToolArgs) -> list[dict]:
    """Analyze metric changes by comparing percentile distributions between time periods."""
    try:
        if not args.index or not args.selectionTimeRangeStart or not args.selectionTimeRangeEnd:
            raise ValueError(
                'Missing required parameters: index, selectionTimeRangeStart, selectionTimeRangeEnd'
            )
        if not args.baselineTimeRangeStart or not args.baselineTimeRangeEnd:
            raise ValueError(
                'Missing required parameters: baselineTimeRangeStart, baselineTimeRangeEnd'
            )

        params = AnalysisParameters(
            {
                'index': args.index,
                'timeField': args.timeField,
                'selectionTimeRangeStart': args.selectionTimeRangeStart,
                'selectionTimeRangeEnd': args.selectionTimeRangeEnd,
                'baselineTimeRangeStart': args.baselineTimeRangeStart,
                'baselineTimeRangeEnd': args.baselineTimeRangeEnd,
                'queryType': args.queryType,
                'filter': args.filter,
                'dsl': args.dsl,
                'ppl': args.ppl,
            }
        )
        params.validate()

        top_n = args.topN if args.topN > 0 else 10

        async with get_opensearch_client(args) as client:
            result = await execute_metric_change_analysis(
                client, params, top_n, group_by=args.groupBy or None
            )

        formatted = format_json(result)
        return [{'type': 'text', 'text': f'MetricChangeAnalysisTool result:\n{formatted}'}]

    except Exception as e:
        return log_tool_error('MetricChangeAnalysisTool', e, 'executing MetricChangeAnalysisTool')


async def log_pattern_analysis_tool(args: LogPatternAnalysisToolArgs) -> list[dict]:
    """Analyze log patterns in the specified index."""
    try:
        if (
            not args.index
            or not args.logFieldName
            or not args.selectionTimeRangeStart
            or not args.selectionTimeRangeEnd
        ):
            raise ValueError(
                'Missing required parameters: index, logFieldName, selectionTimeRangeStart, selectionTimeRangeEnd'
            )

        async with get_opensearch_client(args) as client:
            result = await execute_log_pattern_analysis(
                client,
                index=args.index,
                time_field=args.timeField or '@timestamp',
                log_field_name=args.logFieldName,
                trace_field_name=args.traceFieldName or '',
                base_time_range_start=args.baseTimeRangeStart or '',
                base_time_range_end=args.baseTimeRangeEnd or '',
                selection_time_range_start=args.selectionTimeRangeStart,
                selection_time_range_end=args.selectionTimeRangeEnd,
                filter_expr=args.filter or '',
            )

        formatted = format_json(result)
        return [{'type': 'text', 'text': f'LogPatternAnalysisTool result:\n{formatted}'}]

    except Exception as e:
        return log_tool_error('LogPatternAnalysisTool', e, 'executing LogPatternAnalysisTool')


SKILLS_TOOLS_REGISTRY = {
    'DataDistributionTool': {
        'display_name': 'DataDistributionTool',
        'description': (
            'Analyzes the frequency distribution of categorical field values (e.g. service names, '
            'error codes, status values) and identifies which values shifted most between a baseline '
            'and an anomaly window. Provide a baseline time range to get a ranked list of field-value '
            'changes sorted by divergence score; omit baseline for a single-window frequency snapshot. '
            'Works on any index with keyword/boolean/numeric fields. '
            'Note: this tool measures value frequency changes, NOT latency or duration. '
            'A service appearing more frequently in traces does not necessarily mean it is the root cause '
            '— always cross-check with latency data (e.g. SearchIndexTool sorted by duration).'
        ),
        'input_schema': DataDistributionToolArgs.model_json_schema(),
        'function': data_distribution_tool,
        'args_model': DataDistributionToolArgs,
        'min_version': '1.0.0',
        'http_methods': 'POST',
    },
    'LogPatternAnalysisTool': {
        'display_name': 'LogPatternAnalysisTool',
        'description': (
            'Clusters raw log messages into patterns using ML, then highlights which patterns '
            'are new or surging compared to a baseline period. Supports three modes: '
            '(1) Insight mode (no baseline): extracts and ranks all patterns in the target window; '
            '(2) Diff mode (with baseline, no trace): shows patterns that appeared or surged; '
            '(3) Sequence mode (with baseline + traceFieldName): finds anomalous request sequences. '
            'Useful for discovering error patterns without knowing specific keywords upfront.'
        ),
        'input_schema': LogPatternAnalysisToolArgs.model_json_schema(),
        'function': log_pattern_analysis_tool,
        'args_model': LogPatternAnalysisToolArgs,
        'min_version': '2.19.0',
        'http_methods': 'POST',
    },
    'MetricChangeAnalysisTool': {
        'display_name': 'MetricChangeAnalysisTool',
        'description': (
            'Compares percentile distributions (P50, P90) of ALL numeric fields between a baseline '
            'and an anomaly window, then returns the top fields ranked by change score. '
            'Provide two short time windows of similar duration (e.g. 15-30 min each): '
            'one before the anomaly (baseline) and one during (selection). '
            'Returns changeScore, P50/P90 values, and log-ratios for each field. '
            'IMPORTANT: ALWAYS pass timeField. Discover the time field first, being sure to find '
            'the correct field. Omitting timeField, or passing a field that is '
            "absent from the index, causes a 'No data found' error and leads to a wrong "
            'conclusion.'
        ),
        'input_schema': MetricChangeAnalysisToolArgs.model_json_schema(),
        'function': metric_change_analysis_tool,
        'args_model': MetricChangeAnalysisToolArgs,
        'min_version': '1.0.0',
        'http_methods': 'POST',
    },
}
