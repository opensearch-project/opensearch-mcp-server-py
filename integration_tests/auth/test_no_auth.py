# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import os
import pytest
from integration_tests.framework.assertions import assert_tool_error
from integration_tests.framework.client import mcp_client
from integration_tests.framework.server import MCPServerProcess


@pytest.mark.auth
@pytest.mark.no_auth
class TestNoAuth:
    """Verify that OPENSEARCH_NO_AUTH=true sends no credentials.

    When aimed at a cluster that requires auth, the tool call should fail
    with an authentication error — proving that no credentials were sent.
    """

    async def test_no_auth_rejected_by_auth_cluster(self, seed_test_index):
        url = os.environ.get('IT_OPENSEARCH_URL')
        if not url:
            pytest.skip('IT_OPENSEARCH_URL not set')

        server = MCPServerProcess(
            env={
                'OPENSEARCH_URL': url,
                'OPENSEARCH_NO_AUTH': 'true',
            },
        )
        await server.start()
        try:
            async with mcp_client(server.url) as session:
                result = await session.call_tool('ClusterHealthTool', arguments={})
                # AWS returns AuthenticationException(401); self-managed returns security_exception
                assert_tool_error(result)
        finally:
            await server.stop()
