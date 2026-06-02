# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import pytest
import pytest_asyncio
from integration_tests.framework.assertions import assert_tool_error, assert_tool_success
from integration_tests.framework.aws_helpers import get_default_server_env
from integration_tests.framework.client import mcp_client
from integration_tests.framework.constants import TEST_INDEX
from integration_tests.framework.server import MCPServerProcess


@pytest.mark.tools
class TestWriteCategories:
    """Verify allow_write_categories exempts specific categories from write protection."""

    @pytest_asyncio.fixture
    async def write_categories_client(self, seed_test_index):
        env = {
            **get_default_server_env(),
            'OPENSEARCH_SETTINGS_ALLOW_WRITE': 'false',
            'OPENSEARCH_SETTINGS_ALLOW_WRITE_CATEGORIES': 'search_relevance',
            'OPENSEARCH_ENABLED_CATEGORIES': 'core_tools,search_relevance',
        }
        server = MCPServerProcess(env=env)
        await server.start()
        try:
            async with mcp_client(server.url) as session:
                yield session
        finally:
            await server.stop()

    async def test_search_relevance_write_tools_available(self, write_categories_client):
        """search_relevance write tools should be listed when exempted via allow_write_categories."""
        tools = await write_categories_client.list_tools()
        tool_names = {t.name for t in tools.tools}
        assert 'CreateQuerySetTool' in tool_names
        assert 'CreateSearchConfigurationTool' in tool_names
        assert 'DeleteQuerySetTool' in tool_names
        assert 'CreateExperimentTool' in tool_names

    async def test_generic_api_write_still_blocked(self, write_categories_client):
        """GenericOpenSearchApiTool write operations should still be blocked at runtime."""
        result = await write_categories_client.call_tool(
            'GenericOpenSearchApiTool',
            arguments={
                'path': f'/{TEST_INDEX}/_doc',
                'method': 'POST',
                'body': {'test': 'data'},
            },
        )
        assert_tool_error(result, 'Write operations are disabled')

    async def test_generic_api_read_still_works(self, write_categories_client):
        """GenericOpenSearchApiTool GET operations should still work."""
        result = await write_categories_client.call_tool(
            'GenericOpenSearchApiTool',
            arguments={'path': '/_cluster/health', 'method': 'GET'},
        )
        assert_tool_success(result, 'OpenSearch API Response')

    async def test_core_tools_read_still_works(self, write_categories_client):
        """Core read tools should still be available and functional."""
        result = await write_categories_client.call_tool(
            'ClusterHealthTool',
            arguments={},
        )
        assert_tool_success(result)
