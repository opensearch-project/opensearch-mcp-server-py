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

import os
import pytest
from integration_tests.framework.assertions import assert_tool_error
from integration_tests.framework.client import mcp_client
from integration_tests.framework.server import MCPServerProcess


UNREACHED_URL = 'https://caller-chosen.us-east-1.es.amazonaws.com'

# Substrings unique to each guard. These are what make the tests non-vacuous.
NO_CALLER_CREDS = 'No caller-supplied credentials for the requested URL'
NO_BASE_CREDS_FOR_ROLE = 'No caller-supplied base credentials to assume the requested IAM role'
BAD_PROFILE = 'Failed to create boto3 session with the requested profile'

# The test host may have usable AWS credentials in ~/.aws or an instance role, which
# would let the opt-in succeed where a test means to leave the server nothing to fall
# back to. Point boto3 at empty files and switch the metadata service off.
NO_AWS_CREDENTIALS = {
    'AWS_SHARED_CREDENTIALS_FILE': os.devnull,
    'AWS_CONFIG_FILE': os.devnull,
    'AWS_EC2_METADATA_DISABLED': 'true',
}


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
    # Every case here supplies overrides against a configured URL, which the operator
    # opts into; without it the override gate would refuse before the guard under test.
    server = MCPServerProcess(env={'OPENSEARCH_DYNAMIC_CONNECTION': 'true', **server_env})
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


@pytest.mark.errors
class TestAmbientAwsFallbackOptIn:
    """OPENSEARCH_ALLOW_AMBIENT_AWS_FALLBACK shares AWS credentials, nothing else.

    The refusal above is a deliberate default rather than a fixed rule: one IAM
    identity often covers many clusters, so an operator may let callers send only a
    URL. That relaxation is limited to AWS, since SigV4 hands the caller nothing
    replayable, while basic auth and bearer tokens are sent to whichever host the
    caller named.
    """

    ENABLED = {'OPENSEARCH_ALLOW_AMBIENT_AWS_FALLBACK': 'true'}

    async def test_enabled_accepts_caller_url_without_credentials(self):
        """With the opt-in on, a bare caller URL must get past the refusal.

        The host is unreachable, so the call still fails. What matters is that it
        reaches the connection attempt instead of being refused for missing
        credentials.
        """
        result = await _call_list_indices(
            self.ENABLED
            | {
                'OPENSEARCH_URL': 'https://server-configured.example.com',
                'AWS_ACCESS_KEY_ID': 'AKIAIOSFODNN7EXAMPLE',
                'AWS_SECRET_ACCESS_KEY': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
                'AWS_REGION': 'us-east-1',
            },
            {'opensearch_url': 'https://unreachable.invalid:9200'},
        )
        text = assert_tool_error(result)
        assert NO_CALLER_CREDS.lower() not in text.lower(), (
            f'The opt-in did not take effect: {text[:300]}'
        )

    async def test_enabled_never_shares_basic_auth(self):
        """The opt-in covers AWS only.

        Basic auth travels to whichever host the URL names, so a caller who chose
        that host would receive the password. With no AWS credentials reachable the
        server has nothing left to offer, so it must fail on the AWS path rather
        than fall through to the password it holds.
        """
        result = await _call_list_indices(
            self.ENABLED
            | NO_AWS_CREDENTIALS
            | {
                'OPENSEARCH_URL': 'https://server-configured.example.com',
                'OPENSEARCH_USERNAME': 'server-admin',
                'OPENSEARCH_PASSWORD': 'server-secret',
            },
            {'opensearch_url': UNREACHED_URL},
        )
        text = assert_tool_error(result, 'AWS credentials')
        assert 'server-secret' not in text

    async def test_disabled_by_default(self):
        """Absent the variable, the refusal stands. Guards the default, not the opt-in."""
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

    async def test_non_true_value_does_not_enable(self):
        """Only "true" enables it, so a typo fails closed rather than opening up."""
        result = await _call_list_indices(
            {
                'OPENSEARCH_ALLOW_AMBIENT_AWS_FALLBACK': 'yes',
                'OPENSEARCH_URL': 'https://server-configured.example.com',
                'AWS_ACCESS_KEY_ID': 'AKIAIOSFODNN7EXAMPLE',
                'AWS_SECRET_ACCESS_KEY': 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
                'AWS_REGION': 'us-east-1',
            },
            {'opensearch_url': UNREACHED_URL},
        )
        assert_tool_error(result, NO_CALLER_CREDS)

    async def test_enabled_keeps_failed_profile_fatal(self):
        """A profile that cannot build must not degrade to the default identity.

        The default identity may be broader than the profile that was chosen, so
        signing the caller's URL with it would widen what the caller reaches.
        """
        result = await _call_list_indices(
            self.ENABLED
            | {
                'OPENSEARCH_URL': 'https://server-configured.example.com',
                'AWS_PROFILE': 'definitely-does-not-exist-xyz',
                'AWS_REGION': 'us-east-1',
            },
            {'opensearch_url': UNREACHED_URL},
        )
        assert_tool_error(result, BAD_PROFILE)
