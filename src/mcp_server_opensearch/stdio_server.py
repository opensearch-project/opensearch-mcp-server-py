# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import asyncio
import logging
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.shared.exceptions import MCPError
from mcp.types import CallToolRequestParams, CallToolResult, ListToolsResult, TextContent, Tool
from mcp_server_opensearch.clusters_information import load_clusters_from_yaml
from mcp_server_opensearch.global_state import set_config_file_path, set_mode, set_profile
from mcp_server_opensearch.server_instructions import get_server_instructions
from tools.config import apply_custom_tool_config
from tools.tool_filter import get_tools
from tools.tool_generator import generate_tools_from_openapi
from tools.tools import TOOL_REGISTRY


# --- Server setup ---
async def serve(
    mode: str = 'single',
    profile: str = '',
    config_file_path: str = '',
    cli_tool_overrides: dict | None = None,
) -> None:
    """Start the MCP server in stdio mode."""
    # Set the global mode
    set_mode(mode)

    # Set the global profile if provided
    if profile:
        set_profile(profile)

    # Set the global config file path
    if config_file_path:
        set_config_file_path(config_file_path)

    # Load clusters from YAML file
    if mode == 'multi':
        await load_clusters_from_yaml(config_file_path)

    # Call tool generator
    await generate_tools_from_openapi()
    # Apply custom tool config (custom name and description)
    customized_registry = apply_custom_tool_config(
        TOOL_REGISTRY, config_file_path, cli_tool_overrides or {}
    )
    # Get enabled tools (tool filter)
    enabled_tools = await get_tools(
        tool_registry=customized_registry, config_file_path=config_file_path
    )
    logging.info(f'Enabled tools: {list(enabled_tools.keys())}')

    async def _list_tools(ctx, params) -> ListToolsResult:
        tools = []
        for tool_name, tool_info in enabled_tools.items():
            tools.append(
                Tool(
                    name=tool_info.get('display_name', tool_name),
                    description=tool_info['description'],
                    input_schema=tool_info['input_schema'],
                    meta={'category': tool_info['category']}
                    if tool_info.get('category')
                    else None,  # type: ignore[call-arg]
                )
            )
        return ListToolsResult(tools=tools)

    async def _call_tool(ctx, params: CallToolRequestParams) -> CallToolResult:
        from mcp_server_opensearch.client_context import request_context_var
        from mcp_server_opensearch.tool_executor import _build_call_tool_result, execute_tool

        token = request_context_var.set(ctx.request)
        try:
            return await execute_tool(params.name, params.arguments or {}, enabled_tools)
        except MCPError:
            raise
        except Exception as e:
            return _build_call_tool_result(
                [
                    TextContent(
                        type='text',
                        text=str(e),
                    )
                ],
                is_error=True,
            )
        finally:
            request_context_var.reset(token)

    # Server instructions guide the LLM on dynamic connection params (single mode only)
    server = Server(
        'opensearch-mcp-server',
        instructions=get_server_instructions(),
        on_list_tools=_list_tools,
        on_call_tool=_call_tool,
    )

    # Start stdio-based MCP server
    from mcp_server_opensearch.logging_config import start_memory_monitor

    options = server.create_initialization_options()
    async with stdio_server() as (reader, writer):
        monitor_task = start_memory_monitor()
        try:
            await server.run(reader, writer, options, raise_exceptions=True)
        finally:
            monitor_task.cancel()
            try:
                await monitor_task
            except (asyncio.CancelledError, Exception):
                pass
