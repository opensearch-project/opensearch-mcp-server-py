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
class TestWriteDisabled:
    """Verify write protection when OPENSEARCH_SETTINGS_ALLOW_WRITE=false."""

    @pytest_asyncio.fixture
    async def write_disabled_client(self, seed_test_index):
        env = {**get_default_server_env(), 'OPENSEARCH_SETTINGS_ALLOW_WRITE': 'false'}
        server = MCPServerProcess(env=env)
        await server.start()
        try:
            async with mcp_client(server.url) as session:
                yield session
        finally:
            await server.stop()

    async def test_generic_api_post_blocked(self, write_disabled_client):
        result = await write_disabled_client.call_tool(
            'GenericOpenSearchApiTool',
            arguments={
                'path': f'/{TEST_INDEX}/_doc',
                'method': 'POST',
                'body': {'test': 'data'},
            },
        )
        assert_tool_error(result, 'Write operations are disabled')

    async def test_generic_api_put_blocked(self, write_disabled_client):
        result = await write_disabled_client.call_tool(
            'GenericOpenSearchApiTool',
            arguments={
                'path': f'/{TEST_INDEX}/_doc/999',
                'method': 'PUT',
                'body': {'test': 'data'},
            },
        )
        assert_tool_error(result, 'Write operations are disabled')

    async def test_generic_api_delete_blocked(self, write_disabled_client):
        result = await write_disabled_client.call_tool(
            'GenericOpenSearchApiTool',
            arguments={
                'path': f'/{TEST_INDEX}/_doc/999',
                'method': 'DELETE',
            },
        )
        assert_tool_error(result, 'Write operations are disabled')

    async def test_generic_api_get_still_works(self, write_disabled_client):
        result = await write_disabled_client.call_tool(
            'GenericOpenSearchApiTool',
            arguments={'path': '/_cluster/health', 'method': 'GET'},
        )
        assert_tool_success(result, 'OpenSearch API Response')
