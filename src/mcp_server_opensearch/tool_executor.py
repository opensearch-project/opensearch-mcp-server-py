# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Shared tool execution with structured logging for metrics.

Extracts the duplicated call_tool() logic from stdio_server.py and
streaming_server.py into a single function that wraps tool invocation
with timing, error detection, and structured metric event logging.

Emits a structured log event (event_type="tool_execution") for every
tool invocation, enabling metric filters for:
- Tool execution failure alarms
- Invocation counts by tool name
- Execution latency by tool name
- Error rates by error type and tool
"""

import logging
import time
from mcp.types import CallToolResult, ContentBlock, TextContent
from mcp_server_opensearch.client_context import client_name_var


logger = logging.getLogger(__name__)


def _build_call_tool_result(result: list, is_error: bool) -> CallToolResult:
    # Convert a tool's raw content list into a CallToolResult.

    # Only the first non-None json_data in the result list is used.
    # All current tools return exactly one content block, so this is not a limitation in practice.
    # If a future tool needs to return multiple structured blocks it
    # should merge them into a single dict before returning.

    content: list[ContentBlock] = []
    structured_content = None
    for item in result or []:
        if isinstance(item, dict):
            content.append(
                TextContent(
                    type=item.get('type', 'text'),
                    text=item.get('text', ''),
                )
            )
            if (
                'json_data' in item
                and item['json_data'] is not None
                and structured_content is None
            ):
                data = item['json_data']
                structured_content = data if isinstance(data, dict) else {'result': data}
        else:
            content.append(item)

    return CallToolResult(
        content=content, is_error=is_error, structured_content=structured_content
    )


async def execute_tool(
    name: str,
    arguments: dict,
    enabled_tools: dict,
) -> CallToolResult:
    """Execute an MCP tool with structured logging for metrics.

    Resolves the tool by display name, validates arguments, executes,
    and emits a structured log event with timing and status information.

    Args:
        name: The display name of the tool as seen by the MCP client.
        arguments: The raw argument dict from the MCP protocol.
        enabled_tools: The enabled tools registry dict.

    Returns:
        list[TextContent]: The tool's result (success or error text).

    Raises:
        ValueError: If the tool name is unknown or disabled.
    """
    start_time = time.monotonic()
    status = 'success'
    error_type = None
    found_tool_key = None
    is_error = False

    try:
        # Resolve tool by display name
        for key, tool_info in enabled_tools.items():
            if tool_info.get('display_name', key) == name:
                found_tool_key = key
                break

        if not found_tool_key:
            status = 'error'
            error_type = 'UnknownToolError'
            raise ValueError(f'Unknown or disabled tool: {name}')

        tool = enabled_tools[found_tool_key]
        from tools.tool_params import validate_args_for_mode

        parsed = validate_args_for_mode(arguments, tool['args_model'])

        # Reject tools OpenSearch Serverless cannot serve when this call resolves to
        # a serverless connection. Returns immediately with a clear error instead of
        # letting the request fail downstream (404 / long timeout).
        from opensearch.client import is_serverless_connection
        from tools.tool_filter import SERVERLESS_COMPATIBLE_TOOLS

        if found_tool_key not in SERVERLESS_COMPATIBLE_TOOLS and is_serverless_connection(parsed):
            status = 'error'
            error_type = 'ServerlessUnsupportedToolError'
            is_error = True
            return _build_call_tool_result(
                [
                    TextContent(
                        type='text',
                        text=(
                            f"'{name}' is not supported on OpenSearch Serverless, which does "
                            'not implement cluster, node, or monitoring APIs.'
                        ),
                    )
                ],
                is_error=True,
            )

        result = await tool['function'](parsed)

        # Detect soft errors: tools catch exceptions internally and
        # return errors via log_tool_error(), which sets is_error=True
        # on the response dict as an explicit status indicator.
        if result and len(result) > 0:
            if isinstance(result[0], dict) and result[0].get('is_error'):
                status = 'error'
                is_error = True

        return _build_call_tool_result(result, is_error)

    except ValueError:
        # For unknown tool, status/error_type were already set above.
        # For validation errors (from validate_args_for_mode), set them now.
        if status != 'error':
            status = 'error'
            error_type = 'ValidationError'
        raise

    except Exception as e:
        status = 'error'
        error_type = type(e).__name__
        raise

    finally:
        duration_ms = round((time.monotonic() - start_time) * 1000, 2)
        log_extra: dict[str, object] = {
            'event_type': 'tool_execution',
            'tool_name': name,
            'status': status,
            'duration_ms': duration_ms,
            'client_name': client_name_var.get('unknown'),
        }
        if found_tool_key:
            log_extra['tool_key'] = found_tool_key
        if error_type:
            log_extra['error_type'] = error_type

        if status == 'success':
            logger.info(
                f'Tool executed: {name} ({duration_ms}ms)',
                extra=log_extra,
            )
        else:
            logger.error(
                f'Tool execution failed: {name} ({duration_ms}ms)',
                extra=log_extra,
            )
