# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""End-to-end checks on refusing server credentials against a caller's URL.

Unit tests cover which auth branch runs. These cover what unit tests cannot:
that the refusal reaches the MCP caller as a tool error, rather than crashing
the server, hanging, or returning a success.

Every test asserts the specific refusal message. Asserting merely that "an
error happened" would pass even with the guards deleted, since an unreachable
host or absent credentials also errors.

No cluster and no AWS credentials are needed. Each case is refused before any
network call, so the caller's URL is never contacted.
"""

import pytest
from integration_tests.framework.assertions import assert_tool_error
from integration_tests.framework.client import mcp_client
from integration_tests.framework.server import MCPServerProcess


UNREACHED_URL = 'https://caller-chosen.us-east-1.es.amazonaws.com'

# Substrings unique to each guard. These are what make the tests non-vacuous.
NO_CALLER_CREDS = 'No caller-supplied credentials for the requested URL'
NO_BASE_CREDS_FOR_ROLE = 'No caller-supplied base credentials to assume the requested IAM role'
BAD_PROFILE = 'Failed to create boto3 session with the requested profile'


@pytest.fixture(scope='session')
def ml_tool_availability():
    """Override the cluster-probing fixture that an autouse fixture pulls in.

    Nothing here talks to a cluster, so probing one would skip these tests for a
    reason unrelated to what they verify.
    """
    return {}


async def _call_list_indices(server_env: dict, arguments: dict):
    # Not one of the OpenAPI-generated tools: those retype the inherited connection
    # fields as strings, so a boolean like opensearch_no_auth fails validation.
    server = MCPServerProcess(env=server_env)
    await server.start(timeout=30.0)
    try:
        async with mcp_client(server.url) as session:
            return await session.call_tool('ListIndexTool', arguments=arguments)
    finally:
        await server.stop()


@pytest.mark.errors
class TestCredentialIsolation:
    """A caller-supplied URL must never be paired with the server's own credentials."""

    async def test_refuses_when_server_has_env_basic_auth(self):
        """Env basic auth belongs to the server's cluster, not the caller's."""
        result = await _call_list_indices(
            {
                'OPENSEARCH_URL': 'https://server-configured.example.com',
                'OPENSEARCH_USERNAME': 'server-admin',
                'OPENSEARCH_PASSWORD': 'server-secret',
            },
            {'opensearch_url': UNREACHED_URL},
        )
        assert_tool_error(result, NO_CALLER_CREDS)

    async def test_refuses_when_server_has_env_aws_credentials(self):
        """Env AWS keys must not sign a request to a host the caller picked."""
        result = await _call_list_indices(
            {
                'OPENSEARCH_URL': 'https://server-configured.example.com',
                'AWS_ACCESS_KEY_ID': 'AKIAIOSFODNN7EXAMPLE',
                'AWS_SECRET_ACCESS_KEY': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
                'AWS_REGION': 'us-east-1',
            },
            {'opensearch_url': UNREACHED_URL},
        )
        assert_tool_error(result, NO_CALLER_CREDS)

    async def test_refuses_iam_role_without_caller_profile(self):
        """Assuming a role with the server's own identity is the same borrow."""
        result = await _call_list_indices(
            {
                'OPENSEARCH_URL': 'https://server-configured.example.com',
                'AWS_ACCESS_KEY_ID': 'AKIAIOSFODNN7EXAMPLE',
                'AWS_SECRET_ACCESS_KEY': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
                'AWS_REGION': 'us-east-1',
            },
            {
                'opensearch_url': UNREACHED_URL,
                'aws_iam_arn': 'arn:aws:iam::123456789012:role/SomeRole',
                'aws_region': 'us-east-1',
            },
        )
        assert_tool_error(result, NO_BASE_CREDS_FOR_ROLE)

    async def test_named_profile_that_fails_to_build_is_fatal(self):
        """A caller-named profile must not quietly degrade to the server's identity."""
        result = await _call_list_indices(
            {'OPENSEARCH_URL': 'https://server-configured.example.com', 'AWS_REGION': 'us-east-1'},
            {
                'opensearch_url': UNREACHED_URL,
                'aws_profile': 'definitely-does-not-exist-xyz',
                'aws_region': 'us-east-1',
            },
        )
        assert_tool_error(result, BAD_PROFILE)

    async def test_caller_with_own_credentials_is_not_refused(self):
        """A complete caller bundle is legitimate and must reach the connection attempt.

        The target is unreachable, so this still errors. What matters is that it
        fails while connecting rather than being refused up front, so neither
        guard message may appear.
        """
        result = await _call_list_indices(
            {
                'OPENSEARCH_URL': 'https://server-configured.example.com',
                'OPENSEARCH_USERNAME': 'server-admin',
                'OPENSEARCH_PASSWORD': 'server-secret',
            },
            {'opensearch_url': 'https://unreachable.invalid:9200', 'opensearch_no_auth': True},
        )
        text = assert_tool_error(result)
        for guard in (NO_CALLER_CREDS, NO_BASE_CREDS_FOR_ROLE, BAD_PROFILE):
            assert guard.lower() not in text.lower(), (
                f'A complete caller bundle was refused by a guard: {text[:300]}'
            )
