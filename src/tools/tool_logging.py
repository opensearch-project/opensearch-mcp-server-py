# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Structured error logging for tool functions.

Provides a helper that extracts structured data from exceptions
(status codes, error types, root causes) before they are stringified,
and emits a structured log event for metric extraction.
"""

import json
import logging


logger = logging.getLogger(__name__)


def log_tool_error(
    tool_name: str,
    exception: Exception,
    operation: str = '',
    **context: object,
) -> list[dict]:
    """Log a structured tool error and return the MCP error response.

    Extracts status_code, exception type, and root cause from opensearchpy
    exceptions before they are lost to stringification.

    Args:
        tool_name: The registry key of the tool (e.g. 'SearchIndexTool').
        exception: The caught exception object.
        operation: Human-readable description of what failed
                   (e.g. 'searching index', 'getting mapping').
        **context: Additional context fields to include in the log
                   (e.g. index='my-index', method='GET').

    Returns:
        list[dict]: MCP-format error response
                    [{'type': 'text', 'text': 'Error ...'}].
    """
    error_text = f'Error {operation}: {exception}' if operation else f'Error: {exception}'
    exception_type = type(exception).__name__

    # Extract status_code from opensearchpy TransportError and subclasses.
    # ConnectionError sets status_code = "N/A" (a string), so only keep ints.
    raw_status = getattr(exception, 'status_code', None)
    status_code = raw_status if isinstance(raw_status, int) else None

    # Extract root cause from opensearchpy error info.
    # exception.info is a dict when opensearch-py parses the JSON response,
    # but can be a raw JSON string when the request goes through the fallback path.
    # The async library stores the response body in exception.error (2nd arg)
    # rather than exception.info (3rd arg), so fall back to that.
    error_info = getattr(exception, 'info', None)
    if error_info is None:
        error_info = getattr(exception, 'error', None)
    if isinstance(error_info, str):
        try:
            error_info = json.loads(error_info)
        except (json.JSONDecodeError, TypeError):
            error_info = None
    root_cause = None
    if isinstance(error_info, dict):
        error_detail = error_info.get('error', {})
        if isinstance(error_detail, dict):
            causes = error_detail.get('root_cause', [])
            if causes and isinstance(causes, list) and len(causes) > 0:
                root_cause = causes[0].get('type')

    log_extra: dict[str, object] = {
        'event_type': 'tool_error',
        'tool_name': tool_name,
        'exception_type': exception_type,
        'status': 'error',
    }
    if status_code is not None:
        log_extra['status_code'] = status_code
    if root_cause:
        log_extra['root_cause'] = root_cause

    # Merge caller-provided context (index, query, method, etc.)
    for key, value in context.items():
        if value is not None:
            log_extra[key] = value

    logger.error(
        f'Tool error: {tool_name} - {operation} ({exception_type})',
        extra=log_extra,
    )

    return [{'type': 'text', 'text': error_text, 'is_error': True}]
