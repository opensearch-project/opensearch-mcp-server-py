# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import pytest
from integration_tests.framework.assertions import assert_tool_error
from integration_tests.framework.client import mcp_client
from integration_tests.framework.server import MCPServerProcess


@pytest.mark.errors
class TestBadURLs:
    """Verify graceful error handling when the OpenSearch URL is unreachable."""

    async def test_dns_failure(self, seed_test_index):
        """Server with bad DNS may fail to start or return errors on tool calls."""
        server = MCPServerProcess(
            env={
                'OPENSEARCH_URL': 'https://nonexistent-cluster-xxxxx.us-east-2.es.amazonaws.com',
                'OPENSEARCH_USERNAME': 'admin',
                'OPENSEARCH_PASSWORD': 'admin',
            },
        )
        try:
            await server.start(timeout=10.0)
        except (TimeoutError, RuntimeError):
            await server.stop()
            return
        try:
            async with mcp_client(server.url) as session:
                result = await session.call_tool('ClusterHealthTool', arguments={})
                assert_tool_error(result)
        finally:
            await server.stop()

    async def test_unreachable_host(self, seed_test_index):
        """Server with unreachable URL may fail to start or return errors on tool calls."""
        server = MCPServerProcess(
            env={
                'OPENSEARCH_URL': 'https://192.0.2.1:9200',  # RFC 5737 TEST-NET
                'OPENSEARCH_USERNAME': 'admin',
                'OPENSEARCH_PASSWORD': 'admin',
            },
        )
        try:
            await server.start(timeout=10.0)
        except (TimeoutError, RuntimeError):
            # Server may fail to start with an unreachable URL — that's the expected behavior
            await server.stop()
            return
        try:
            async with mcp_client(server.url, timeout=10.0) as session:
                result = await session.call_tool('ClusterHealthTool', arguments={})
                assert_tool_error(result)
        finally:
            await server.stop()
