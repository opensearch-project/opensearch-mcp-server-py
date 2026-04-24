# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import os
import pytest
from integration_tests.framework.assertions import assert_tool_success
from integration_tests.framework.aws_helpers import build_header_auth_headers
from integration_tests.framework.client import mcp_client
from integration_tests.framework.constants import TEST_INDEX
from integration_tests.framework.server import MCPServerProcess


@pytest.mark.auth
@pytest.mark.header_auth
class TestHeaderAuth:
    """Verify that header-based auth works (creds sent per-request in headers)."""

    async def test_list_index(self, header_auth_client):
        result = await header_auth_client.call_tool('ListIndexTool', arguments={})
        assert_tool_success(result, 'All indices information:', TEST_INDEX)

    async def test_search_index(self, header_auth_client):
        result = await header_auth_client.call_tool(
            'SearchIndexTool',
            arguments={
                'index': TEST_INDEX,
                'query_dsl': '{"query": {"match_all": {}}}',
            },
        )
        assert_tool_success(result, 'Test document')

    async def test_generic_api(self, header_auth_client):
        result = await header_auth_client.call_tool(
            'GenericOpenSearchApiTool',
            arguments={'path': '/_cluster/health', 'method': 'GET'},
        )
        assert_tool_success(result, 'OpenSearch API Response')


@pytest.mark.auth
@pytest.mark.header_auth
class TestHeaderAuthPriority:
    """Verify header auth takes precedence over server-side credentials.

    This test starts its own server configured with BOTH basic auth creds AND
    header auth enabled. It then sends AWS header creds, proving the header
    creds are used instead of the server-side basic auth creds.
    This requires a separate server because the shared fixtures only configure
    one auth mode at a time.
    """

    async def test_header_auth_overrides_basic_auth(self, seed_test_index):
        env_vars = {
            'IT_OPENSEARCH_URL': '',
            'IT_BASIC_AUTH_USERNAME': '',
            'IT_BASIC_AUTH_PASSWORD': '',
        }
        for key in env_vars:
            val = os.environ.get(key)
            if not val:
                pytest.skip(f'{key} not set')
            env_vars[key] = val

        server = MCPServerProcess(
            env={
                'OPENSEARCH_URL': env_vars['IT_OPENSEARCH_URL'],
                'OPENSEARCH_USERNAME': env_vars['IT_BASIC_AUTH_USERNAME'],
                'OPENSEARCH_PASSWORD': env_vars['IT_BASIC_AUTH_PASSWORD'],
                'OPENSEARCH_HEADER_AUTH': 'true',
            },
        )
        await server.start()
        try:
            headers = build_header_auth_headers()
            async with mcp_client(server.url, headers=headers) as session:
                result = await session.call_tool('ListIndexTool', arguments={})
                assert_tool_success(result, 'All indices information:', seed_test_index)
        finally:
            await server.stop()
