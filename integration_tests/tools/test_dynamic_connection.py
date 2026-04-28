# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for dynamic (zero-config) connection parameter mode.

Tests two scenarios:
1. Zero-config mode: no OPENSEARCH_URL set → override fields exposed in schemas,
   and tool calls succeed when the agent supplies connection params directly.
2. Pre-configured mode: OPENSEARCH_URL set → override fields hidden from schemas.
"""

import os
import pytest
import pytest_asyncio
from integration_tests.framework.assertions import assert_tool_success
from integration_tests.framework.aws_helpers import get_default_server_env
from integration_tests.framework.client import mcp_client
from integration_tests.framework.constants import TEST_INDEX
from integration_tests.framework.server import MCPServerProcess
from mcp_server_opensearch.server_instructions import CONNECTION_OVERRIDE_FIELDS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope='module')
async def zero_config_server(seed_test_index):
    """MCP server started with NO pre-configured connection (zero-config mode).

    No OPENSEARCH_URL or any auth env vars are set, so the server exposes
    connection override fields in every tool's schema.
    """
    server = MCPServerProcess(env={})
    await server.start()
    yield server
    await server.stop()


@pytest_asyncio.fixture(scope='module')
async def preconfigured_server(seed_test_index):
    """MCP server started with OPENSEARCH_URL set (pre-configured mode).

    Override fields should be hidden from tool schemas.
    """
    env = get_default_server_env()
    server = MCPServerProcess(env=env)
    await server.start()
    yield server
    await server.stop()


# ---------------------------------------------------------------------------
# Tests: zero-config mode
# ---------------------------------------------------------------------------


@pytest.mark.dynamic_connection
class TestZeroConfigMode:
    """Verify behavior when no connection is pre-configured on the server."""

    async def test_override_fields_exposed_in_schemas(self, zero_config_server):
        """All connection override fields must appear in every tool's input schema."""
        async with mcp_client(zero_config_server.url) as session:
            tools = await session.list_tools()
            assert tools.tools, 'Expected at least one tool to be listed'

            for tool in tools.tools:
                props = tool.inputSchema.get('properties', {})
                for field in CONNECTION_OVERRIDE_FIELDS:
                    assert field in props, (
                        f'Tool {tool.name!r} is missing override field {field!r} '
                        f'in zero-config mode'
                    )

    async def test_tool_call_with_inline_connection_params(self, zero_config_server):
        """A tool call that supplies opensearch_url inline should succeed."""
        env = get_default_server_env()
        opensearch_url = env.get('OPENSEARCH_URL')
        if not opensearch_url:
            pytest.skip('IT_OPENSEARCH_URL not set')

        # Build per-call auth params from whatever auth is available
        call_args: dict = {'opensearch_url': opensearch_url}

        aws_key = os.environ.get('IT_AWS_ACCESS_KEY_ID')
        aws_secret = os.environ.get('IT_AWS_SECRET_ACCESS_KEY')
        aws_region = os.environ.get('IT_AWS_REGION', 'us-west-2')
        basic_user = os.environ.get('IT_BASIC_AUTH_USERNAME')
        basic_pass = os.environ.get('IT_BASIC_AUTH_PASSWORD')

        if aws_key and aws_secret:
            call_args['aws_region'] = aws_region
        elif basic_user and basic_pass:
            call_args['opensearch_username'] = basic_user
            call_args['opensearch_password'] = basic_pass
        else:
            pytest.skip('No auth credentials available for inline connection test')

        async with mcp_client(zero_config_server.url) as session:
            result = await session.call_tool('ListIndexTool', arguments=call_args)
            response = assert_tool_success(result)
            assert TEST_INDEX in response

    async def test_inline_params_take_precedence_over_env_vars(self, zero_config_server):
        """Per-call opensearch_url must override any env var that might be set."""
        env = get_default_server_env()
        opensearch_url = env.get('OPENSEARCH_URL')
        if not opensearch_url:
            pytest.skip('IT_OPENSEARCH_URL not set')

        call_args: dict = {'opensearch_url': opensearch_url}

        aws_key = os.environ.get('IT_AWS_ACCESS_KEY_ID')
        aws_secret = os.environ.get('IT_AWS_SECRET_ACCESS_KEY')
        aws_region = os.environ.get('IT_AWS_REGION', 'us-west-2')
        basic_user = os.environ.get('IT_BASIC_AUTH_USERNAME')
        basic_pass = os.environ.get('IT_BASIC_AUTH_PASSWORD')

        if aws_key and aws_secret:
            call_args['aws_region'] = aws_region
        elif basic_user and basic_pass:
            call_args['opensearch_username'] = basic_user
            call_args['opensearch_password'] = basic_pass
        else:
            pytest.skip('No auth credentials available')

        # The zero_config_server has no env vars set, so the only way this
        # succeeds is if the per-call params are actually used.
        async with mcp_client(zero_config_server.url) as session:
            result = await session.call_tool('ClusterHealthTool', arguments=call_args)
            assert_tool_success(result)


# ---------------------------------------------------------------------------
# Tests: pre-configured mode (negative — override fields hidden)
# ---------------------------------------------------------------------------


@pytest.mark.dynamic_connection
class TestPreconfiguredMode:
    """Verify that override fields are hidden when OPENSEARCH_URL is set."""

    async def test_override_fields_hidden_when_url_configured(self, preconfigured_server):
        """Connection override fields must NOT appear in tool schemas when URL is set."""
        async with mcp_client(preconfigured_server.url) as session:
            tools = await session.list_tools()
            assert tools.tools, 'Expected at least one tool to be listed'

            for tool in tools.tools:
                props = tool.inputSchema.get('properties', {})
                for field in CONNECTION_OVERRIDE_FIELDS:
                    assert field not in props, (
                        f'Tool {tool.name!r} should NOT expose override field {field!r} '
                        f'when OPENSEARCH_URL is pre-configured'
                    )

    async def test_cluster_name_not_exposed_in_single_mode(self, preconfigured_server):
        """opensearch_cluster_name must never appear in single-mode tool schemas."""
        async with mcp_client(preconfigured_server.url) as session:
            tools = await session.list_tools()
            for tool in tools.tools:
                props = tool.inputSchema.get('properties', {})
                assert 'opensearch_cluster_name' not in props, (
                    f'Tool {tool.name!r} should not expose opensearch_cluster_name '
                    f'in single mode'
                )
