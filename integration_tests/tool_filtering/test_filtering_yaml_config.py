# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import os
import pytest
import tempfile
import yaml
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
class TestFilteringYAMLConfig:
    """Verify tool filtering via YAML configuration file."""

    async def test_enabled_tools_yaml(self, seed_test_index):
        """Enabled tools adds to the enabled set (core_tools is always included)."""
        config = {
            'version': '1.0',
            'tool_filters': {
                'enabled_tools': ['ListIndexTool', 'ClusterHealthTool'],
            },
        }

        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.yml', delete=False, prefix='mcp-it-filter-'
        ) as f:
            yaml.dump(config, f)
            config_path = f.name

        env = _basic_auth_env()
        server = MCPServerProcess(env=env, config_file=config_path)
        await server.start()
        try:
            async with mcp_client(server.url) as session:
                tools = await session.list_tools()
                tool_names = {t.name for t in tools.tools}
                assert 'ListIndexTool' in tool_names
                assert 'ClusterHealthTool' in tool_names
                # Non-core tools not in enabled list should be absent
                assert 'GetClusterStateTool' not in tool_names
                assert 'CatNodesTool' not in tool_names
        finally:
            await server.stop()
            os.unlink(config_path)

    async def test_disabled_tools_yaml(self, seed_test_index):
        """Tools in tool_filters.disabled_tools are hidden."""
        config = {
            'version': '1.0',
            'tool_filters': {
                'disabled_tools': ['SearchIndexTool'],
            },
        }

        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.yml', delete=False, prefix='mcp-it-filter-'
        ) as f:
            yaml.dump(config, f)
            config_path = f.name

        env = _basic_auth_env()
        server = MCPServerProcess(env=env, config_file=config_path)
        await server.start()
        try:
            async with mcp_client(server.url) as session:
                tools = await session.list_tools()
                tool_names = {t.name for t in tools.tools}
                assert 'SearchIndexTool' not in tool_names
                assert 'ListIndexTool' in tool_names
        finally:
            await server.stop()
            os.unlink(config_path)
