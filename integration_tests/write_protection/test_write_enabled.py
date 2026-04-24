# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import pytest
import pytest_asyncio
import uuid
from integration_tests.framework.assertions import assert_tool_success
from integration_tests.framework.aws_helpers import get_default_server_env
from integration_tests.framework.client import mcp_client
from integration_tests.framework.constants import TEST_INDEX
from integration_tests.framework.server import MCPServerProcess


@pytest.mark.tools
class TestWriteEnabled:
    """Verify write operations work when OPENSEARCH_SETTINGS_ALLOW_WRITE=true."""

    @pytest_asyncio.fixture
    async def write_enabled_client(self, seed_test_index):
        env = {**get_default_server_env(), 'OPENSEARCH_SETTINGS_ALLOW_WRITE': 'true'}
        server = MCPServerProcess(env=env)
        await server.start()
        try:
            async with mcp_client(server.url) as session:
                yield session
        finally:
            await server.stop()

    async def test_generic_api_post_succeeds(self, write_enabled_client):
        """POST a document — use a unique ID to avoid polluting seed data."""
        doc_id = f'it-write-test-{uuid.uuid4().hex[:8]}'
        result = await write_enabled_client.call_tool(
            'GenericOpenSearchApiTool',
            arguments={
                'path': f'/{TEST_INDEX}/_doc/{doc_id}',
                'method': 'PUT',
                'body': {'title': 'write test', 'category': 'test', 'value': 0},
            },
        )
        assert_tool_success(result, 'OpenSearch API Response')

        # Clean up the doc we just created
        await write_enabled_client.call_tool(
            'GenericOpenSearchApiTool',
            arguments={
                'path': f'/{TEST_INDEX}/_doc/{doc_id}',
                'method': 'DELETE',
            },
        )
