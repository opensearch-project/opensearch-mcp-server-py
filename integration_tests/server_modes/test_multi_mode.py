# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import os
import pytest
import tempfile
import yaml
from integration_tests.framework.assertions import assert_tool_error, assert_tool_success
from integration_tests.framework.client import mcp_client
from integration_tests.framework.constants import TEST_INDEX
from integration_tests.framework.server import MCPServerProcess


def _build_multi_config():
    """Build a multi-mode YAML config using the best available auth."""
    url = os.environ.get('IT_OPENSEARCH_URL')
    if not url:
        pytest.skip('IT_OPENSEARCH_URL not set')

    # Build cluster config using the available auth method
    basic_user = os.environ.get('IT_BASIC_AUTH_USERNAME')
    basic_pass = os.environ.get('IT_BASIC_AUTH_PASSWORD')
    aws_region = os.environ.get('IT_AWS_REGION')

    cluster_config = {'opensearch_url': url}

    if basic_user and basic_pass:
        cluster_config['opensearch_username'] = basic_user
        cluster_config['opensearch_password'] = basic_pass
    elif aws_region:
        cluster_config['aws_region'] = aws_region
    else:
        pytest.skip('No auth credentials for multi-mode test')

    return {
        'version': '1.0',
        'clusters': {
            'cluster1': dict(cluster_config),
            'cluster2': dict(cluster_config),
        },
    }


def _build_server_env():
    """Return env vars the server process needs for AWS auth (if applicable)."""
    env = {}
    aws_key = os.environ.get('IT_AWS_ACCESS_KEY_ID')
    aws_secret = os.environ.get('IT_AWS_SECRET_ACCESS_KEY')
    if aws_key and aws_secret:
        env['AWS_ACCESS_KEY_ID'] = aws_key
        env['AWS_SECRET_ACCESS_KEY'] = aws_secret
        session_token = os.environ.get('IT_AWS_SESSION_TOKEN', '')
        if session_token:
            env['AWS_SESSION_TOKEN'] = session_token
        region = os.environ.get('IT_AWS_REGION')
        if region:
            env['AWS_REGION'] = region
    return env


@pytest.mark.server_modes
class TestMultiMode:
    """Verify multi-cluster mode behavior."""

    @pytest.fixture
    async def multi_mode_setup(self, seed_test_index):
        """Start a server in multi mode with a YAML config defining two cluster aliases."""
        config = _build_multi_config()

        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.yml', delete=False, prefix='mcp-it-multi-'
        ) as f:
            yaml.dump(config, f)
            config_path = f.name

        server = MCPServerProcess(
            env=_build_server_env(),
            mode='multi',
            config_file=config_path,
        )
        await server.start()
        try:
            yield server
        finally:
            try:
                await server.stop()
            finally:
                if os.path.exists(config_path):
                    os.unlink(config_path)

    async def test_tools_include_cluster_name_param(self, multi_mode_setup):
        async with mcp_client(multi_mode_setup.url) as session:
            tools = await session.list_tools()
            for tool in tools.tools:
                if tool.name == 'ListClustersTool':
                    continue
                props = tool.inputSchema.get('properties', {})
                assert 'opensearch_cluster_name' in props, (
                    f'Tool {tool.name} should expose opensearch_cluster_name in multi mode'
                )

    async def test_call_tool_with_cluster_name(self, multi_mode_setup):
        async with mcp_client(multi_mode_setup.url) as session:
            result = await session.call_tool(
                'ListIndexTool',
                arguments={'opensearch_cluster_name': 'cluster1'},
            )
            response = assert_tool_success(result)
            assert TEST_INDEX in response

    async def test_call_tool_with_second_cluster(self, multi_mode_setup):
        async with mcp_client(multi_mode_setup.url) as session:
            result = await session.call_tool(
                'ListIndexTool',
                arguments={'opensearch_cluster_name': 'cluster2'},
            )
            assert_tool_success(result, TEST_INDEX)

    async def test_call_tool_without_cluster_name_errors(self, multi_mode_setup):
        async with mcp_client(multi_mode_setup.url) as session:
            result = await session.call_tool('ListIndexTool', arguments={})
            assert_tool_error(result, 'opensearch_cluster_name')

    async def test_call_tool_with_nonexistent_cluster_errors(self, multi_mode_setup):
        async with mcp_client(multi_mode_setup.url) as session:
            result = await session.call_tool(
                'ListIndexTool',
                arguments={'opensearch_cluster_name': 'nonexistent_cluster'},
            )
            assert_tool_error(result, 'nonexistent_cluster')
