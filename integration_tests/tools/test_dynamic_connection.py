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


def _build_inline_call_args() -> dict:
    """Build per-call connection args suitable for a zero-config server.

    A zero-config server has NO env vars set, so the inline params must be
    fully self-contained — they cannot rely on ambient AWS credentials or
    profiles on the server side.

    Prefers basic auth (username/password passed directly as tool params)
    over AWS auth, because AWS auth requires the server process to have
    credentials in its environment (which zero-config servers don't have).
    Falls back to opensearch_no_auth=True if neither is available.

    Calls pytest.skip if IT_OPENSEARCH_URL is not set.
    """
    url = os.environ.get('IT_OPENSEARCH_URL')
    if not url:
        pytest.skip('IT_OPENSEARCH_URL not set')

    basic_user = os.environ.get('IT_BASIC_AUTH_USERNAME')
    basic_pass = os.environ.get('IT_BASIC_AUTH_PASSWORD')

    if basic_user and basic_pass:
        return {
            'opensearch_url': url,
            'opensearch_username': basic_user,
            'opensearch_password': basic_pass,
        }

    # No basic auth — try no-auth (works for local/dev clusters)
    return {
        'opensearch_url': url,
        'opensearch_no_auth': True,
    }


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
async def wrong_url_server(seed_test_index):
    """MCP server started with a deliberately wrong OPENSEARCH_URL.

    Used to verify that per-call opensearch_url overrides the server's
    pre-configured URL: if the inline param takes precedence the call
    succeeds; if the server uses its own URL the call fails.

    No auth is configured on the server — auth comes entirely from the
    inline call params, which also proves per-call auth overrides work.
    """
    server = MCPServerProcess(env={'OPENSEARCH_URL': 'http://does-not-exist.invalid:9200'})
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
        call_args = _build_inline_call_args()
        async with mcp_client(zero_config_server.url) as session:
            result = await session.call_tool('ListIndexTool', arguments=call_args)
            response = assert_tool_success(result)
            assert TEST_INDEX in response

    async def test_inline_params_take_precedence_over_server_config(self, wrong_url_server):
        """Per-call opensearch_url overrides the server's pre-configured URL.

        The wrong_url_server has OPENSEARCH_URL pointing to a non-existent host.
        Passing the correct URL inline must override it — if the server used its
        own URL the call would fail with a connection error.
        """
        call_args = _build_inline_call_args()
        async with mcp_client(wrong_url_server.url) as session:
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
                    f'Tool {tool.name!r} should not expose opensearch_cluster_name in single mode'
                )
