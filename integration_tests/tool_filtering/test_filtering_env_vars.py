# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import os
import pytest
from integration_tests.framework.client import mcp_client
from integration_tests.framework.server import MCPServerProcess


def _basic_auth_env():
    url = os.environ.get('IT_OPENSEARCH_URL')
    user = os.environ.get('IT_BASIC_AUTH_USERNAME')
    pwd = os.environ.get('IT_BASIC_AUTH_PASSWORD')
    if not all([url, user, pwd]):
        pytest.skip('Basic auth env vars not set')
    return {
        'OPENSEARCH_URL': url,
        'OPENSEARCH_USERNAME': user,
        'OPENSEARCH_PASSWORD': pwd,
    }


@pytest.mark.tools
class TestFilteringEnvVars:
    """Verify tool filtering via environment variables."""

    async def test_enabled_tools_env(self, seed_test_index):
        """OPENSEARCH_ENABLED_TOOLS adds tools to the enabled set (core_tools is always included)."""
        env = {
            **_basic_auth_env(),
            'OPENSEARCH_ENABLED_TOOLS': 'ListIndexTool,ClusterHealthTool',
        }
        server = MCPServerProcess(env=env)
        await server.start()
        try:
            async with mcp_client(server.url) as session:
                tools = await session.list_tools()
                tool_names = {t.name for t in tools.tools}
                assert 'ListIndexTool' in tool_names
                assert 'ClusterHealthTool' in tool_names
                # Non-core tools that weren't explicitly enabled should be absent
                assert 'GetClusterStateTool' not in tool_names
                assert 'CatNodesTool' not in tool_names
        finally:
            await server.stop()

    async def test_disabled_tools_env(self, seed_test_index):
        """Tools in OPENSEARCH_DISABLED_TOOLS are hidden."""
        env = {
            **_basic_auth_env(),
            'OPENSEARCH_DISABLED_TOOLS': 'SearchIndexTool,GenericOpenSearchApiTool',
        }
        server = MCPServerProcess(env=env)
        await server.start()
        try:
            async with mcp_client(server.url) as session:
                tools = await session.list_tools()
                tool_names = {t.name for t in tools.tools}
                assert 'SearchIndexTool' not in tool_names
                assert 'GenericOpenSearchApiTool' not in tool_names
                # Other tools should still be present
                assert 'ListIndexTool' in tool_names
        finally:
            await server.stop()

    async def test_regex_filtering_env(self, seed_test_index):
        """OPENSEARCH_ENABLED_TOOLS_REGEX adds matching tools (core_tools also included)."""
        env = {
            **_basic_auth_env(),
            'OPENSEARCH_ENABLED_TOOLS_REGEX': '.*Index.*',
        }
        server = MCPServerProcess(env=env)
        await server.start()
        try:
            async with mcp_client(server.url) as session:
                tools = await session.list_tools()
                tool_names = {t.name for t in tools.tools}
                # Regex-matched tools should be present
                assert 'ListIndexTool' in tool_names
                assert 'IndexMappingTool' in tool_names
                assert 'SearchIndexTool' in tool_names
                # Non-core tools NOT matching the regex should be absent
                assert 'GetClusterStateTool' not in tool_names
                assert 'CatNodesTool' not in tool_names
        finally:
            await server.stop()

    async def test_category_filtering_env(self, seed_test_index):
        """OPENSEARCH_ENABLED_CATEGORIES shows only that category."""
        env = {
            **_basic_auth_env(),
            'OPENSEARCH_ENABLED_CATEGORIES': 'core_tools',
        }
        server = MCPServerProcess(env=env)
        await server.start()
        try:
            async with mcp_client(server.url) as session:
                tools = await session.list_tools()
                tool_names = {t.name for t in tools.tools}
                # core_tools category should include ListIndexTool, SearchIndexTool, etc.
                assert 'ListIndexTool' in tool_names
                assert len(tool_names) > 0
        finally:
            await server.stop()
