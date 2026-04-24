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
class TestFilteringCLIArgs:
    """Verify tool customization via CLI arguments."""

    async def test_custom_display_name_via_cli(self, seed_test_index):
        """Server started with --tool.ListIndexTool.display_name=MyCustomList."""
        env = _basic_auth_env()
        server = MCPServerProcess(
            env=env,
            extra_args=['--tool.ListIndexTool.display_name=MyCustomList'],
        )
        await server.start()
        try:
            async with mcp_client(server.url) as session:
                tools = await session.list_tools()
                tool_names = {t.name for t in tools.tools}
                assert 'MyCustomList' in tool_names
                assert 'ListIndexTool' not in tool_names
        finally:
            await server.stop()
