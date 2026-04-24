# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import os
import pytest
from integration_tests.framework.assertions import assert_tool_error
from integration_tests.framework.client import mcp_client
from integration_tests.framework.server import MCPServerProcess


@pytest.mark.errors
class TestBadCredentials:
    """Verify graceful error handling when credentials are wrong."""

    async def test_wrong_password_basic_auth(self, seed_test_index):
        url = os.environ.get('IT_OPENSEARCH_URL')
        username = os.environ.get('IT_BASIC_AUTH_USERNAME')
        if not url:
            pytest.skip('IT_OPENSEARCH_URL not set')
        if not username:
            pytest.skip('IT_BASIC_AUTH_USERNAME not set (basic auth not available)')

        server = MCPServerProcess(
            env={
                'OPENSEARCH_URL': url,
                'OPENSEARCH_USERNAME': username,
                'OPENSEARCH_PASSWORD': 'wrong_password_xxxxx',
            },
        )
        await server.start()
        try:
            async with mcp_client(server.url) as session:
                result = await session.call_tool('ListIndexTool', arguments={})
                assert_tool_error(result)
        finally:
            await server.stop()

    async def test_expired_aws_token_header_auth(self, header_auth_server):
        bad_headers = {
            'opensearch-url': os.environ.get('IT_OPENSEARCH_URL', ''),
            'aws-region': os.environ.get('IT_AWS_REGION', 'us-west-2'),
            'aws-access-key-id': 'ASIAINVALIDKEY12345XX',
            'aws-secret-access-key': 'invalid-secret-xxxxxxxxxx',
            'aws-session-token': 'invalid-token',
            'aws-service-name': 'es',
        }
        if not bad_headers['opensearch-url']:
            pytest.skip('IT_OPENSEARCH_URL not set')

        async with mcp_client(header_auth_server.url, headers=bad_headers) as session:
            result = await session.call_tool('ListIndexTool', arguments={})
            assert_tool_error(result)
