# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""End-to-end checks on the gates around a caller-supplied OpenSearch URL.

Three separate gates are covered: the optional SSRF guard, the operator switch
that disables per-call connection overrides entirely, and the rule that a URL
arriving in request headers may only use credentials from those same headers.

Every test asserts the specific refusal message. Asserting merely that "an
error happened" would pass even with the gates removed, since an unreachable
host or absent credentials also errors.

No cluster and no AWS credentials are needed. Each case is refused before any
network call, and the addresses used resolve locally, so nothing is contacted.
"""

import pytest
from integration_tests.framework.assertions import assert_tool_error
from integration_tests.framework.client import mcp_client
from integration_tests.framework.server import MCPServerProcess


SERVER_URL = 'https://server-configured.example.com'
UNREACHED_URL = 'https://caller-chosen.us-east-1.es.amazonaws.com'

# Substrings unique to each gate. These are what make the tests non-vacuous.
NON_PUBLIC_ADDRESS = 'resolves to a non-public address'
SSRF_REQUIRES_HTTPS = 'must use https when OPENSEARCH_SSRF_GUARD is enabled'
OVERRIDES_DISABLED = 'Per-call connection overrides are disabled'
NO_CALLER_CREDS = 'No caller-supplied credentials for the requested URL'


@pytest.fixture(scope='session')
def ml_tool_availability():
    """Override the cluster-probing fixture that an autouse fixture pulls in.

    Nothing here talks to a cluster, so probing one would skip these tests for a
    reason unrelated to what they verify.
    """
    return {}


async def _call_list_indices(server_env: dict, arguments: dict, headers: dict | None = None):
    # Overrides against a configured URL are an opt-in, so default it on here and let
    # the tests that disable it say so. Otherwise that gate refuses first and the gate
    # under test never runs.
    server = MCPServerProcess(env={'OPENSEARCH_DYNAMIC_CONNECTION': 'true', **server_env})
    await server.start(timeout=30.0)
    try:
        async with mcp_client(server.url, headers=headers) as session:
            return await session.call_tool('ListIndexTool', arguments=arguments)
    finally:
        await server.stop()


@pytest.mark.errors
class TestSSRFGuard:
    """With OPENSEARCH_SSRF_GUARD on, a caller may only name a public https host."""

    async def test_refuses_loopback_address(self):
        result = await _call_list_indices(
            {
                'OPENSEARCH_URL': SERVER_URL,
                'OPENSEARCH_SSRF_GUARD': 'true',
            },
            {'opensearch_url': 'https://127.0.0.1:9200', 'opensearch_no_auth': True},
        )
        text = assert_tool_error(result, NON_PUBLIC_ADDRESS)
        assert '127.0.0.1' in text

    async def test_refuses_private_address(self):
        result = await _call_list_indices(
            {
                'OPENSEARCH_URL': SERVER_URL,
                'OPENSEARCH_SSRF_GUARD': 'true',
            },
            {'opensearch_url': 'https://10.0.0.5:9200', 'opensearch_no_auth': True},
        )
        assert_tool_error(result, NON_PUBLIC_ADDRESS)

    async def test_refuses_link_local_address(self):
        """The cloud instance metadata endpoint is the classic SSRF target."""
        result = await _call_list_indices(
            {
                'OPENSEARCH_URL': SERVER_URL,
                'OPENSEARCH_SSRF_GUARD': 'true',
            },
            {'opensearch_url': 'https://169.254.169.254', 'opensearch_no_auth': True},
        )
        assert_tool_error(result, NON_PUBLIC_ADDRESS)

    async def test_refuses_plain_http(self):
        result = await _call_list_indices(
            {
                'OPENSEARCH_URL': SERVER_URL,
                'OPENSEARCH_SSRF_GUARD': 'true',
            },
            {'opensearch_url': 'http://198.51.100.7:9200', 'opensearch_no_auth': True},
        )
        assert_tool_error(result, SSRF_REQUIRES_HTTPS)

    async def test_guard_off_by_default_does_not_block_private_address(self):
        """Localhost and private-VPC clusters stay usable unless the operator opts in.

        The call still fails, because a caller URL with no caller credentials is
        refused for a different reason. That message proves the request got past
        the address check.
        """
        result = await _call_list_indices(
            {'OPENSEARCH_URL': SERVER_URL, 'AWS_REGION': 'us-east-1'},
            {'opensearch_url': 'https://127.0.0.1:9200'},
        )
        text = assert_tool_error(result, NO_CALLER_CREDS)
        assert NON_PUBLIC_ADDRESS.lower() not in text.lower()
        assert 'ssrf' not in text.lower()


@pytest.mark.errors
class TestDynamicConnectionDisabled:
    """OPENSEARCH_DYNAMIC_CONNECTION=false must be enforced, not just advertised."""

    async def test_refuses_url_override(self):
        """The fields are hidden from the schema, but a raw client can still send them."""
        result = await _call_list_indices(
            {
                'OPENSEARCH_URL': SERVER_URL,
                'OPENSEARCH_DYNAMIC_CONNECTION': 'false',
            },
            {'opensearch_url': UNREACHED_URL},
        )
        text = assert_tool_error(result, OVERRIDES_DISABLED)
        assert 'opensearch_url' in text

    async def test_names_every_supplied_override_field(self):
        result = await _call_list_indices(
            {
                'OPENSEARCH_URL': SERVER_URL,
                'OPENSEARCH_DYNAMIC_CONNECTION': 'false',
            },
            {
                'opensearch_url': UNREACHED_URL,
                'opensearch_username': 'caller',
                'opensearch_password': 'caller-secret',
                'aws_region': 'us-east-1',
            },
        )
        text = assert_tool_error(result, OVERRIDES_DISABLED)
        for field in (
            'aws_region',
            'opensearch_password',
            'opensearch_url',
            'opensearch_username',
        ):
            assert field in text, (
                f'{field} was supplied but not named in the refusal: {text[:300]}'
            )
        assert 'caller-secret' not in text

    async def test_refuses_auth_override_without_url(self):
        """Any override field counts, not only the URL."""
        result = await _call_list_indices(
            {
                'OPENSEARCH_URL': SERVER_URL,
                'OPENSEARCH_DYNAMIC_CONNECTION': 'false',
            },
            {'aws_profile': 'some-profile'},
        )
        text = assert_tool_error(result, OVERRIDES_DISABLED)
        assert 'aws_profile' in text


@pytest.mark.errors
class TestHeaderSuppliedUrlIsolation:
    """A URL from request headers may only use credentials from those same headers."""

    async def test_refuses_header_url_with_no_header_credentials(self):
        """The server's env basic auth belongs to the server's cluster, not this one."""
        result = await _call_list_indices(
            {
                'OPENSEARCH_HEADER_AUTH': 'true',
                'OPENSEARCH_URL': SERVER_URL,
                'OPENSEARCH_USERNAME': 'server-admin',
                'OPENSEARCH_PASSWORD': 'server-secret',
                'AWS_REGION': 'us-east-1',
            },
            {},
            headers={'opensearch-url': UNREACHED_URL},
        )
        text = assert_tool_error(result, NO_CALLER_CREDS)
        assert 'server-admin' not in text
        assert 'server-secret' not in text

    async def test_refuses_header_url_when_server_has_env_aws_keys(self):
        """The server's own AWS keys are likewise not the header caller's identity."""
        result = await _call_list_indices(
            {
                'OPENSEARCH_HEADER_AUTH': 'true',
                'OPENSEARCH_URL': SERVER_URL,
                'AWS_ACCESS_KEY_ID': 'AKIAIOSFODNN7EXAMPLE',
                'AWS_SECRET_ACCESS_KEY': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
                'AWS_REGION': 'us-east-1',
            },
            {},
            headers={'opensearch-url': UNREACHED_URL},
        )
        assert_tool_error(result, NO_CALLER_CREDS)

    async def test_header_url_with_header_credentials_is_not_refused(self):
        """Credentials from the same headers are legitimate and must be accepted.

        The target is unreachable, so this still errors. What matters is that it
        fails while connecting rather than being refused up front.
        """
        result = await _call_list_indices(
            {
                'OPENSEARCH_HEADER_AUTH': 'true',
                'OPENSEARCH_URL': SERVER_URL,
                'OPENSEARCH_USERNAME': 'server-admin',
                'OPENSEARCH_PASSWORD': 'server-secret',
            },
            {},
            headers={
                'opensearch-url': 'https://unreachable.invalid:9200',
                'aws-region': 'us-east-1',
                'aws-access-key-id': 'AKIAIOSFODNN7EXAMPLE',
                'aws-secret-access-key': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
            },
        )
        text = assert_tool_error(result)
        assert NO_CALLER_CREDS.lower() not in text.lower()
