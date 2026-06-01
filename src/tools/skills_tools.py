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
    selectionTimeRangeStart: str = Field(description='Start time for analysis period')
    selectionTimeRangeEnd: str = Field(description='End time for analysis period')
    timeField: str = Field(description='Date/time field for filtering(required)')
    baselineTimeRangeStart: str = Field(
        default='', description='Start time for baseline period (optional)'
    )
    baselineTimeRangeEnd: str = Field(
        default='', description='End time for baseline period (optional)'
    )
    size: int = Field(default=1000, description='Maximum number of documents to analyze')
    queryType: str = Field(default='dsl', description="Query type: 'dsl' (default) or 'ppl'")
    filter: str = Field(
        default='', description='Additional DSL filter clauses as JSON array of strings'
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
    size: int = Field(
        default=1000,
        description='Maximum number of documents to analyze (default: 1000, max: 10000)',
    )
    topN: int = Field(
        default=10,
        description='Number of top fields to return, ranked by change score (default: 10)',
    )
    queryType: str = Field(
        default='dsl', description="Query type: 'ppl' or 'dsl' (default: 'dsl')"
    )
    filter: str = Field(default='', description='Additional DSL query conditions (optional)')
    dsl: str = Field(default='', description='Complete raw DSL query as JSON string (optional)')
    ppl: str = Field(
        default='', description='Complete PPL statement without time information (optional)'
    )


class LogPatternAnalysisToolArgs(baseToolArgs):
    """Arguments for the LogPatternAnalysisTool."""

    index: str = Field(description='Target OpenSearch index name containing log data')
    logFieldName: str = Field(description='Field containing raw log messages to analyze')
    selectionTimeRangeStart: str = Field(description='Start time for analysis target period')
    selectionTimeRangeEnd: str = Field(description='End time for analysis target period')
    timeField: str = Field(description='Date/time field for time-based filtering(required)')
    traceFieldName: str = Field(
        default='', description='Field for trace/correlation ID (optional)'
    )
    baseTimeRangeStart: str = Field(
        default='', description='Start time for baseline comparison period (optional)'
    )
    baseTimeRangeEnd: str = Field(
        default='', description='End time for baseline comparison period (optional)'
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
                'size': str(args.size),
                'queryType': args.queryType,
                'filter': args.filter,
                'dsl': args.dsl,
                'ppl': args.ppl,
            }
        )
        params.validate()

        top_n = args.topN if args.topN > 0 else 10

        async with get_opensearch_client(args) as client:
            result = await execute_metric_change_analysis(client, params, top_n)

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
        'description': 'Analyzes data distribution patterns and field value frequencies within OpenSearch indices. Supports both single dataset analysis for understanding data characteristics and comparative analysis between two time periods to identify distribution changes. Automatically detects useful fields, calculates value distributions, groups numeric data, and computes divergence metrics. Useful for anomaly detection, data quality assessment, and trend analysis. We can use this tool to analyze the distribution of failures over time',
        'input_schema': DataDistributionToolArgs.model_json_schema(),
        'function': data_distribution_tool,
        'args_model': DataDistributionToolArgs,
        'min_version': '3.3.0',
        'http_methods': 'POST',
    },
    'LogPatternAnalysisTool': {
        'display_name': 'LogPatternAnalysisTool',
        'description': 'Intelligent log pattern analysis tool for troubleshooting and anomaly detection in application logs. Use this tool when you need to: analyze error patterns in logs, identify unusual log sequences, compare log patterns between time periods, find root causes of system issues, detect anomalous behavior in application traces, or investigate performance problems. The tool automatically extracts meaningful patterns from raw log messages, groups similar patterns, identifies outliers, and provides insights for debugging. Essential for log-based troubleshooting, incident analysis, and proactive monitoring of system health.',
        'input_schema': LogPatternAnalysisToolArgs.model_json_schema(),
        'function': log_pattern_analysis_tool,
        'args_model': LogPatternAnalysisToolArgs,
        'min_version': '3.3.0',
        'http_methods': 'POST',
    },
    'MetricChangeAnalysisTool': {
        'display_name': 'MetricChangeAnalysisTool',
        'description': 'Compares percentile distributions (P50, P90) of numeric fields between two time ranges. Returns top fields ranked by change score. Use for root cause analysis when investigating metric anomalies. Keep both time ranges short (e.g. 15-30 minutes) and similar in duration for accurate comparison.',
        'input_schema': MetricChangeAnalysisToolArgs.model_json_schema(),
        'function': metric_change_analysis_tool,
        'args_model': MetricChangeAnalysisToolArgs,
        'min_version': '3.3.0',
        'http_methods': 'POST',
    },
}
