# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import logging
import os
import pytest
import pytest_asyncio
from integration_tests.framework.aws_helpers import (
    AWSProfileManager,
    build_header_auth_headers,
    get_default_server_env,
)
from integration_tests.framework.client import mcp_client
from integration_tests.framework.constants import METRIC_TEST_INDEX, TEST_INDEX
from integration_tests.framework.server import MCPServerProcess


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_env(*names: str) -> dict[str, str]:
    """Return env values for the given names, or pytest.skip if any are missing."""
    result = {}
    for name in names:
        val = os.environ.get(name)
        if not val:
            pytest.skip(f'Required env var {name} not set')
        result[name] = val
    return result


def _create_os_client():
    """Create a synchronous OpenSearch client using the best available auth.

    Returns a client or calls pytest.skip.
    """
    from opensearchpy import OpenSearch

    url = os.environ.get('IT_OPENSEARCH_URL')
    if not url:
        pytest.skip('IT_OPENSEARCH_URL not set')

    use_ssl = url.startswith('https')
    verify_certs = os.environ.get('OPENSEARCH_SSL_VERIFY', 'true').lower() != 'false'

    aws_key = os.environ.get('IT_AWS_ACCESS_KEY_ID')
    aws_secret = os.environ.get('IT_AWS_SECRET_ACCESS_KEY')
    aws_region = os.environ.get('IT_AWS_REGION', 'us-west-2')
    basic_user = os.environ.get('IT_BASIC_AUTH_USERNAME')
    basic_pass = os.environ.get('IT_BASIC_AUTH_PASSWORD')

    if aws_key and aws_secret:
        from opensearchpy import RequestsHttpConnection
        from requests_aws4auth import AWS4Auth

        session_token = os.environ.get('IT_AWS_SESSION_TOKEN', '')
        aws_auth = AWS4Auth(aws_key, aws_secret, aws_region, 'es', session_token=session_token)
        client = OpenSearch(
            hosts=[url],
            http_auth=aws_auth,
            use_ssl=use_ssl,
            verify_certs=verify_certs,
            connection_class=RequestsHttpConnection,
        )
    elif basic_user and basic_pass:
        client = OpenSearch(
            hosts=[url],
            http_auth=(basic_user, basic_pass),
            use_ssl=use_ssl,
            verify_certs=verify_certs,
        )
    else:
        pytest.skip('No auth credentials available for seed_test_index')

    return client


# ---------------------------------------------------------------------------
# Test index setup / teardown (session-scoped, runs once for all IT)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope='session')
async def seed_test_index():
    """Create and seed a test index before any IT runs, delete it after."""
    client = _create_os_client()

    # Create index with known mapping (let cluster decide shard/replica settings)
    if not client.indices.exists(index=TEST_INDEX):
        client.indices.create(
            index=TEST_INDEX,
            body={
                'mappings': {
                    'properties': {
                        'title': {'type': 'text'},
                        'category': {'type': 'keyword'},
                        'timestamp': {'type': 'date'},
                        'value': {'type': 'integer'},
                    }
                },
            },
        )

    # Seed with known documents
    docs = [
        {'title': 'Test document 1', 'category': 'A', 'timestamp': '2025-01-01', 'value': 10},
        {'title': 'Test document 2', 'category': 'B', 'timestamp': '2025-01-02', 'value': 20},
        {'title': 'Test document 3', 'category': 'A', 'timestamp': '2025-01-03', 'value': 30},
    ]
    for i, doc in enumerate(docs):
        client.index(index=TEST_INDEX, id=str(i + 1), body=doc, refresh=True)  # type: ignore[call-arg]
    client.close()

    yield TEST_INDEX

    # Teardown — create a fresh client to ensure the connection isn't stale
    try:
        teardown_client = _create_os_client()
        try:
            teardown_client.indices.delete(index=TEST_INDEX)
        except Exception:
            pass  # Index may already be gone
        teardown_client.close()
        logger.info(f'Deleted test index: {TEST_INDEX}')
    except Exception as e:
        logger.warning(f'Failed to delete test index {TEST_INDEX}: {e}')


# ---------------------------------------------------------------------------
# Metric test index (numeric fields with baseline vs selection distributions)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope='session')
async def seed_metric_test_index():
    """Create and seed a separate index with multiple numeric fields.

    Used by MetricChangeAnalysisTool tests, which need:
    - several numeric fields (to verify topN ranking),
    - enough docs per window for P50/P90 to be meaningful,
    - distinct baseline vs selection distributions on some fields and
      stable distributions on others (to verify changeScore ordering).
    """
    client = _create_os_client()

    if not client.indices.exists(index=METRIC_TEST_INDEX):
        client.indices.create(
            index=METRIC_TEST_INDEX,
            body={
                'mappings': {
                    'properties': {
                        'service': {'type': 'keyword'},
                        'timestamp': {'type': 'date'},
                        'latency': {'type': 'float'},
                        'cpu': {'type': 'float'},
                        'memory': {'type': 'integer'},
                    }
                },
            },
        )

    # Baseline window: 2025-01-01 — low latency, low cpu, stable memory
    baseline_docs = [
        {
            'service': 'svc-a',
            'timestamp': '2025-01-01T00:30:00Z',
            'latency': 30,
            'cpu': 0.20,
            'memory': 110,
        },
        {
            'service': 'svc-a',
            'timestamp': '2025-01-01T02:00:00Z',
            'latency': 45,
            'cpu': 0.22,
            'memory': 120,
        },
        {
            'service': 'svc-a',
            'timestamp': '2025-01-01T04:00:00Z',
            'latency': 50,
            'cpu': 0.25,
            'memory': 130,
        },
        {
            'service': 'svc-a',
            'timestamp': '2025-01-01T06:00:00Z',
            'latency': 60,
            'cpu': 0.27,
            'memory': 140,
        },
        {
            'service': 'svc-b',
            'timestamp': '2025-01-01T08:00:00Z',
            'latency': 70,
            'cpu': 0.30,
            'memory': 150,
        },
        {
            'service': 'svc-b',
            'timestamp': '2025-01-01T10:00:00Z',
            'latency': 80,
            'cpu': 0.32,
            'memory': 160,
        },
        {
            'service': 'svc-b',
            'timestamp': '2025-01-01T12:00:00Z',
            'latency': 90,
            'cpu': 0.35,
            'memory': 170,
        },
        {
            'service': 'svc-b',
            'timestamp': '2025-01-01T14:00:00Z',
            'latency': 100,
            'cpu': 0.37,
            'memory': 180,
        },
        {
            'service': 'svc-c',
            'timestamp': '2025-01-01T16:00:00Z',
            'latency': 110,
            'cpu': 0.40,
            'memory': 190,
        },
        {
            'service': 'svc-c',
            'timestamp': '2025-01-01T20:00:00Z',
            'latency': 120,
            'cpu': 0.42,
            'memory': 200,
        },
    ]

    # Selection window: 2025-01-02..04 — latency and cpu surge, memory stays stable
    selection_docs = [
        {
            'service': 'svc-a',
            'timestamp': '2025-01-02T01:00:00Z',
            'latency': 220,
            'cpu': 0.72,
            'memory': 115,
        },
        {
            'service': 'svc-a',
            'timestamp': '2025-01-02T05:00:00Z',
            'latency': 280,
            'cpu': 0.75,
            'memory': 125,
        },
        {
            'service': 'svc-a',
            'timestamp': '2025-01-02T10:00:00Z',
            'latency': 350,
            'cpu': 0.78,
            'memory': 135,
        },
        {
            'service': 'svc-a',
            'timestamp': '2025-01-02T15:00:00Z',
            'latency': 420,
            'cpu': 0.82,
            'memory': 145,
        },
        {
            'service': 'svc-b',
            'timestamp': '2025-01-02T20:00:00Z',
            'latency': 500,
            'cpu': 0.85,
            'memory': 155,
        },
        {
            'service': 'svc-b',
            'timestamp': '2025-01-03T02:00:00Z',
            'latency': 600,
            'cpu': 0.88,
            'memory': 165,
        },
        {
            'service': 'svc-b',
            'timestamp': '2025-01-03T08:00:00Z',
            'latency': 720,
            'cpu': 0.90,
            'memory': 175,
        },
        {
            'service': 'svc-b',
            'timestamp': '2025-01-03T14:00:00Z',
            'latency': 820,
            'cpu': 0.92,
            'memory': 185,
        },
        {
            'service': 'svc-c',
            'timestamp': '2025-01-03T20:00:00Z',
            'latency': 900,
            'cpu': 0.93,
            'memory': 195,
        },
        {
            'service': 'svc-c',
            'timestamp': '2025-01-04T01:00:00Z',
            'latency': 1000,
            'cpu': 0.95,
            'memory': 205,
        },
    ]

    for i, doc in enumerate(baseline_docs + selection_docs, start=1):
        client.index(index=METRIC_TEST_INDEX, id=str(i), body=doc, refresh=True)  # type: ignore[call-arg]
    client.close()

    yield METRIC_TEST_INDEX

    try:
        teardown_client = _create_os_client()
        try:
            teardown_client.indices.delete(index=METRIC_TEST_INDEX)
        except Exception:
            pass
        teardown_client.close()
        logger.info(f'Deleted metric test index: {METRIC_TEST_INDEX}')
    except Exception as e:
        logger.warning(f'Failed to delete metric test index {METRIC_TEST_INDEX}: {e}')


# ---------------------------------------------------------------------------
# ML tool availability detection & requires_ml_tool marker
# ---------------------------------------------------------------------------

_ml_tool_availability_cache: dict = {}


@pytest.fixture(scope='session')
def ml_tool_availability():
    """Probe cluster to detect which ML tools are registered (session-scoped)."""
    if _ml_tool_availability_cache:
        return _ml_tool_availability_cache

    client = _create_os_client()
    try:
        for tool_name in ('DataDistributionTool', 'LogPatternAnalysisTool'):
            try:
                client.transport.perform_request(
                    'POST',
                    f'/_plugins/_ml/tools/_execute/{tool_name}',
                    body={'parameters': {}},
                )
                _ml_tool_availability_cache[tool_name] = True
            except Exception as e:
                error_repr = repr(e)
                if 'Tool not found' in error_repr or 'Tool not found' in str(
                    getattr(e, 'info', '')
                ):
                    _ml_tool_availability_cache[tool_name] = False
                else:
                    # Tool exists but request failed for other reasons (e.g. bad params)
                    _ml_tool_availability_cache[tool_name] = True
    finally:
        client.close()

    return _ml_tool_availability_cache


@pytest.fixture(autouse=True)
def _check_requires_ml_tool(request, ml_tool_availability):
    """Skip tests marked with @pytest.mark.requires_ml_tool if tool is not available."""
    marker = request.node.get_closest_marker('requires_ml_tool')
    if marker is None:
        return
    tool_name = marker.args[0]
    if not ml_tool_availability.get(tool_name, False):
        pytest.skip(f'ML tool {tool_name} not registered on this cluster')


# ---------------------------------------------------------------------------
# AWS profile manager (session-scoped)
# ---------------------------------------------------------------------------


@pytest.fixture(scope='session')
def aws_profile_manager():
    """Create and manage a temporary AWS profile from IT_AWS_* env vars."""
    manager = AWSProfileManager()
    try:
        manager.setup()
    except ValueError:
        pytest.skip('AWS credentials not available for profile tests')
    yield manager
    manager.teardown()


# ---------------------------------------------------------------------------
# Server fixtures — one per auth mode, session-scoped
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope='session')
async def basic_auth_server(seed_test_index):
    """MCP server using basic auth."""
    env = _require_env('IT_OPENSEARCH_URL', 'IT_BASIC_AUTH_USERNAME', 'IT_BASIC_AUTH_PASSWORD')
    server = MCPServerProcess(
        env={
            'OPENSEARCH_URL': env['IT_OPENSEARCH_URL'],
            'OPENSEARCH_USERNAME': env['IT_BASIC_AUTH_USERNAME'],
            'OPENSEARCH_PASSWORD': env['IT_BASIC_AUTH_PASSWORD'],
        },
    )
    await server.start()
    yield server
    await server.stop()


@pytest_asyncio.fixture(scope='session')
async def aws_creds_server(seed_test_index):
    """MCP server using direct AWS credentials."""
    env = _require_env(
        'IT_OPENSEARCH_URL', 'IT_AWS_REGION', 'IT_AWS_ACCESS_KEY_ID', 'IT_AWS_SECRET_ACCESS_KEY'
    )
    server = MCPServerProcess(
        env={
            'OPENSEARCH_URL': env['IT_OPENSEARCH_URL'],
            'AWS_REGION': env['IT_AWS_REGION'],
            'AWS_ACCESS_KEY_ID': env['IT_AWS_ACCESS_KEY_ID'],
            'AWS_SECRET_ACCESS_KEY': env['IT_AWS_SECRET_ACCESS_KEY'],
            'AWS_SESSION_TOKEN': os.environ.get('IT_AWS_SESSION_TOKEN', ''),
        },
    )
    await server.start()
    yield server
    await server.stop()


@pytest_asyncio.fixture(scope='session')
async def iam_role_server(seed_test_index):
    """MCP server using IAM role assumption."""
    env = _require_env(
        'IT_OPENSEARCH_URL',
        'IT_AWS_REGION',
        'IT_IAM_ROLE_ARN',
        'IT_AWS_ACCESS_KEY_ID',
        'IT_AWS_SECRET_ACCESS_KEY',
    )
    server = MCPServerProcess(
        env={
            'OPENSEARCH_URL': env['IT_OPENSEARCH_URL'],
            'AWS_REGION': env['IT_AWS_REGION'],
            'AWS_IAM_ARN': env['IT_IAM_ROLE_ARN'],
            'AWS_ACCESS_KEY_ID': env['IT_AWS_ACCESS_KEY_ID'],
            'AWS_SECRET_ACCESS_KEY': env['IT_AWS_SECRET_ACCESS_KEY'],
            'AWS_SESSION_TOKEN': os.environ.get('IT_AWS_SESSION_TOKEN', ''),
        },
    )
    await server.start()
    yield server
    await server.stop()


@pytest_asyncio.fixture(scope='session')
async def header_auth_server(seed_test_index):
    """MCP server with header-based auth (no creds on server side)."""
    server = MCPServerProcess(
        env={'OPENSEARCH_HEADER_AUTH': 'true'},
    )
    await server.start()
    yield server
    await server.stop()


@pytest_asyncio.fixture(scope='session')
async def profile_cli_server(seed_test_index, aws_profile_manager):
    """MCP server using --profile CLI arg."""
    env = _require_env('IT_OPENSEARCH_URL', 'IT_AWS_REGION')
    server_env = {
        'OPENSEARCH_URL': env['IT_OPENSEARCH_URL'],
        'AWS_REGION': env['IT_AWS_REGION'],
        **aws_profile_manager.get_env_for_profile_cli(),
    }
    server = MCPServerProcess(
        env=server_env,
        profile=aws_profile_manager.profile_name,
    )
    await server.start()
    yield server
    await server.stop()


@pytest_asyncio.fixture(scope='session')
async def profile_env_server(seed_test_index, aws_profile_manager):
    """MCP server using AWS_PROFILE env var."""
    env = _require_env('IT_OPENSEARCH_URL', 'IT_AWS_REGION')
    server_env = {
        'OPENSEARCH_URL': env['IT_OPENSEARCH_URL'],
        'AWS_REGION': env['IT_AWS_REGION'],
        **aws_profile_manager.get_env_for_profile_env(),
    }
    server = MCPServerProcess(env=server_env)
    await server.start()
    yield server
    await server.stop()


# ---------------------------------------------------------------------------
# Default server/client — uses best available auth for tool tests
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope='session')
async def default_server(seed_test_index, seed_metric_test_index):
    """MCP server using whichever auth is available (AWS creds preferred, then basic).

    Tool tests use this fixture so they work regardless of which auth the
    cluster supports.  All tools are enabled (not just core_tools) so
    non-core tool tests can exercise their targets.
    """
    env = get_default_server_env()
    # Enable ALL tools, not just the default core_tools category
    env['OPENSEARCH_ENABLED_TOOLS_REGEX'] = '.*'
    server = MCPServerProcess(env=env)
    await server.start()
    yield server
    await server.stop()


@pytest_asyncio.fixture(scope='session')
async def default_client(default_server):
    """MCP client session against the default server (session-scoped to avoid connection exhaustion)."""
    async with mcp_client(default_server.url) as session:
        yield session


# ---------------------------------------------------------------------------
# Client fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def basic_auth_client(basic_auth_server):
    """MCP client session against the basic auth server."""
    async with mcp_client(basic_auth_server.url) as session:
        yield session


@pytest_asyncio.fixture
async def aws_creds_client(aws_creds_server):
    """MCP client session against the AWS creds server."""
    async with mcp_client(aws_creds_server.url) as session:
        yield session


@pytest_asyncio.fixture
async def iam_role_client(iam_role_server):
    """MCP client session against the IAM role server."""
    async with mcp_client(iam_role_server.url) as session:
        yield session


@pytest_asyncio.fixture
async def header_auth_client(header_auth_server):
    """MCP client session against the header auth server with AWS creds in headers."""
    headers = build_header_auth_headers()
    async with mcp_client(header_auth_server.url, headers=headers) as session:
        yield session


@pytest_asyncio.fixture
async def profile_cli_client(profile_cli_server):
    """MCP client session against the AWS profile CLI server."""
    async with mcp_client(profile_cli_server.url) as session:
        yield session


@pytest_asyncio.fixture
async def profile_env_client(profile_env_server):
    """MCP client session against the AWS profile env server."""
    async with mcp_client(profile_env_server.url) as session:
        yield session
