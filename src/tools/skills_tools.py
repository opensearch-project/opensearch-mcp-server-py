# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import json
import logging
from typing import Dict, Any
from .tool_logging import log_tool_error
from .utils import format_json
from .tool_params import baseToolArgs
from pydantic import Field
from opensearch.client import get_opensearch_client

logger = logging.getLogger(__name__)


class DataDistributionToolArgs(baseToolArgs):
    index: str = Field(description='Target OpenSearch index name')
    selectionTimeRangeStart: str = Field(description='Start time for analysis period')
    selectionTimeRangeEnd: str = Field(description='End time for analysis period')
    timeField: str = Field(description='Date/time field for filtering(requied)')
    baselineTimeRangeStart: str = Field(
        default='', description='Start time for baseline period (optional)'
    )
    baselineTimeRangeEnd: str = Field(
        default='', description='End time for baseline period (optional)'
    )
    size: int = Field(default=1000, description='Maximum number of documents to analyze')


class LogPatternAnalysisToolArgs(baseToolArgs):
    index: str = Field(description='Target OpenSearch index name containing log data')
    logFieldName: str = Field(description='Field containing raw log messages to analyze')
    selectionTimeRangeStart: str = Field(description='Start time for analysis target period')
    selectionTimeRangeEnd: str = Field(description='End time for analysis target period')
    timeField: str = Field(description='Date/time field for time-based filtering(requied)')
    traceFieldName: str = Field(
        default='', description='Field for trace/correlation ID (optional)'
    )
    baseTimeRangeStart: str = Field(
        default='', description='Start time for baseline comparison period (optional)'
    )
    baseTimeRangeEnd: str = Field(
        default='', description='End time for baseline comparison period (optional)'
    )


async def call_opensearch_tool(
    tool_name: str, parameters: Dict[str, Any], args: baseToolArgs
) -> list[dict]:
    """Call OpenSearch ML tools API"""
    try:
        async with get_opensearch_client(args) as client:
            # Call OpenSearch ML tools execute API
            response = await client.transport.perform_request(
                'POST',
                f'/_plugins/_ml/tools/_execute/{tool_name}',
                body={'parameters': parameters},
            )

        logger.info(f'Tool {tool_name} result: {format_json(response)}')
        formatted_result = format_json(response)
        return [{'type': 'text', 'text': f'{tool_name} result:\n{formatted_result}'}]

    except Exception as e:
        return log_tool_error(tool_name, e, f'executing {tool_name}')


async def data_distribution_tool(args: DataDistributionToolArgs) -> list[dict]:
    params = {
        'index': args.index,
        'timeField': args.timeField,
        'selectionTimeRangeStart': args.selectionTimeRangeStart,
        'selectionTimeRangeEnd': args.selectionTimeRangeEnd,
        'size': args.size,
    }
    if args.baselineTimeRangeStart:
        params['baselineTimeRangeStart'] = args.baselineTimeRangeStart
    if args.baselineTimeRangeEnd:
        params['baselineTimeRangeEnd'] = args.baselineTimeRangeEnd

    result = await call_opensearch_tool('DataDistributionTool', params, args)
    return result


async def log_pattern_analysis_tool(args: LogPatternAnalysisToolArgs) -> list[dict]:
    params = {
        'index': args.index,
        'timeField': args.timeField,
        'logFieldName': args.logFieldName,
        'selectionTimeRangeStart': args.selectionTimeRangeStart,
        'selectionTimeRangeEnd': args.selectionTimeRangeEnd,
    }
    if args.traceFieldName:
        params['traceFieldName'] = args.traceFieldName
    if args.baseTimeRangeStart:
        params['baseTimeRangeStart'] = args.baseTimeRangeStart
    if args.baseTimeRangeEnd:
        params['baseTimeRangeEnd'] = args.baseTimeRangeEnd

    result = await call_opensearch_tool('LogPatternAnalysisTool', params, args)
    return result


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
}
