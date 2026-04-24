# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import asyncio
import logging
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool
from mcp_server_opensearch.clusters_information import load_clusters_from_yaml
from mcp_server_opensearch.global_state import set_mode, set_profile, set_config_file_path
from tools.tool_filter import get_tools
from tools.tool_generator import generate_tools_from_openapi
from tools.tools import TOOL_REGISTRY
from tools.config import apply_custom_tool_config


# --- Server setup ---
async def serve(
    mode: str = 'single',
    profile: str = '',
    config_file_path: str = '',
    cli_tool_overrides: dict | None = None,
) -> None:
    # Set the global mode
    set_mode(mode)

    # Set the global profile if provided
    if profile:
        set_profile(profile)

    # Set the global config file path
    if config_file_path:
        set_config_file_path(config_file_path)

    server = Server('opensearch-mcp-server')
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

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        tools = []
        for tool_name, tool_info in enabled_tools.items():
            tools.append(
                Tool(
                    name=tool_info.get('display_name', tool_name),
                    description=tool_info['description'],
                    inputSchema=tool_info['input_schema'],
                )
            )
        return tools

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        from mcp_server_opensearch.tool_executor import execute_tool

        return await execute_tool(name, arguments, enabled_tools)

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
