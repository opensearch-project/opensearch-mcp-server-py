# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for per-call connection parameter overrides.

When optional connection fields are provided in tool args, they should
take precedence over environment variables, allowing agents to
dynamically target different clusters without reconfiguring the server.
"""

import os
import pytest
from opensearch.client import (
    ConfigurationError,
    initialize_client,
)
from tools.tool_params import ListIndicesArgs, baseToolArgs
from unittest.mock import Mock, patch


class TestConnectionOverrides:
    """Tests for optional connection parameter overrides in single mode."""

    def setup_method(self):
        """Clear env vars and set single-cluster mode before each test."""
        self.original_env = {}
        self._env_keys = [
            'OPENSEARCH_USERNAME',
            'OPENSEARCH_PASSWORD',
            'AWS_REGION',
            'OPENSEARCH_URL',
            'OPENSEARCH_NO_AUTH',
            'OPENSEARCH_SSL_VERIFY',
            'OPENSEARCH_TIMEOUT',
            'AWS_IAM_ARN',
            'AWS_PROFILE',
            'AWS_OPENSEARCH_SERVERLESS',
            'OPENSEARCH_HEADER_AUTH',
            'OPENSEARCH_MAX_RESPONSE_SIZE',
        ]
        for key in self._env_keys:
            if key in os.environ:
                self.original_env[key] = os.environ[key]
                del os.environ[key]

        from mcp_server_opensearch.global_state import set_mode

        set_mode('single')

    def teardown_method(self):
        """Restore original environment variables."""
        # Remove any keys we set during the test
        for key in self._env_keys:
            os.environ.pop(key, None)
        # Restore originals
        for key, value in self.original_env.items():
            os.environ[key] = value

    # --- URL override ---

    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_single_mode')
    def test_url_override_takes_precedence_over_env(self, mock_get_region, mock_opensearch):
        """Tool-level opensearch_url overrides OPENSEARCH_URL env var."""
        os.environ['OPENSEARCH_URL'] = 'https://env-cluster.example.com'
        os.environ['OPENSEARCH_NO_AUTH'] = 'true'
        mock_get_region.return_value = 'us-east-1'
        mock_opensearch.return_value = Mock()

        args = baseToolArgs(
            opensearch_cluster_name='',
            opensearch_url='https://override-cluster.example.com',
            opensearch_no_auth=True,
        )
        initialize_client(args)

        call_kwargs = mock_opensearch.call_args[1]
        assert 'override-cluster.example.com' in call_kwargs['hosts'][0]

    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_single_mode')
    def test_url_override_without_env_var(self, mock_get_region, mock_opensearch):
        """Tool-level opensearch_url works even when OPENSEARCH_URL is not set."""
        # No OPENSEARCH_URL in env
        mock_get_region.return_value = 'us-east-1'
        mock_opensearch.return_value = Mock()

        args = baseToolArgs(
            opensearch_cluster_name='',
            opensearch_url='https://dynamic-cluster.example.com',
            opensearch_no_auth=True,
        )
        initialize_client(args)

        call_kwargs = mock_opensearch.call_args[1]
        assert 'dynamic-cluster.example.com' in call_kwargs['hosts'][0]

    # --- Basic auth overrides ---

    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_single_mode')
    def test_basic_auth_override(self, mock_get_region, mock_opensearch):
        """Tool-level username/password override env vars."""
        os.environ['OPENSEARCH_URL'] = 'https://cluster.example.com'
        os.environ['OPENSEARCH_USERNAME'] = 'env-user'
        os.environ['OPENSEARCH_PASSWORD'] = 'env-pass'
        mock_get_region.return_value = 'us-east-1'
        mock_opensearch.return_value = Mock()

        args = baseToolArgs(
            opensearch_cluster_name='',
            opensearch_username='override-user',
            opensearch_password='override-pass',
        )
        initialize_client(args)

        call_kwargs = mock_opensearch.call_args[1]
        assert call_kwargs['http_auth'] == ('override-user', 'override-pass')

    # --- No-auth override ---

    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_single_mode')
    def test_no_auth_override(self, mock_get_region, mock_opensearch):
        """Tool-level opensearch_no_auth=True overrides env-based auth."""
        os.environ['OPENSEARCH_URL'] = 'https://cluster.example.com'
        os.environ['OPENSEARCH_USERNAME'] = 'env-user'
        os.environ['OPENSEARCH_PASSWORD'] = 'env-pass'
        mock_get_region.return_value = 'us-east-1'
        mock_opensearch.return_value = Mock()

        args = baseToolArgs(
            opensearch_cluster_name='',
            opensearch_no_auth=True,
        )
        initialize_client(args)

        call_kwargs = mock_opensearch.call_args[1]
        assert 'http_auth' not in call_kwargs

    # --- SSL verify override ---

    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_single_mode')
    def test_ssl_verify_false_override(self, mock_get_region, mock_opensearch):
        """Tool-level opensearch_ssl_verify=False overrides default True."""
        os.environ['OPENSEARCH_URL'] = 'https://cluster.example.com'
        os.environ['OPENSEARCH_NO_AUTH'] = 'true'
        mock_get_region.return_value = 'us-east-1'
        mock_opensearch.return_value = Mock()

        args = baseToolArgs(
            opensearch_cluster_name='',
            opensearch_ssl_verify=False,
        )
        initialize_client(args)

        call_kwargs = mock_opensearch.call_args[1]
        assert call_kwargs['verify_certs'] is False

    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_single_mode')
    def test_ssl_verify_override_env_false_to_true(self, mock_get_region, mock_opensearch):
        """Tool-level opensearch_ssl_verify=True overrides env OPENSEARCH_SSL_VERIFY=false."""
        os.environ['OPENSEARCH_URL'] = 'https://cluster.example.com'
        os.environ['OPENSEARCH_NO_AUTH'] = 'true'
        os.environ['OPENSEARCH_SSL_VERIFY'] = 'false'
        mock_get_region.return_value = 'us-east-1'
        mock_opensearch.return_value = Mock()

        args = baseToolArgs(
            opensearch_cluster_name='',
            opensearch_ssl_verify=True,
        )
        initialize_client(args)

        call_kwargs = mock_opensearch.call_args[1]
        assert call_kwargs['verify_certs'] is True

    # --- Timeout override ---

    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_single_mode')
    def test_timeout_override(self, mock_get_region, mock_opensearch):
        """Tool-level opensearch_timeout overrides OPENSEARCH_TIMEOUT env var."""
        os.environ['OPENSEARCH_URL'] = 'https://cluster.example.com'
        os.environ['OPENSEARCH_NO_AUTH'] = 'true'
        os.environ['OPENSEARCH_TIMEOUT'] = '30'
        mock_get_region.return_value = 'us-east-1'
        mock_opensearch.return_value = Mock()

        args = baseToolArgs(
            opensearch_cluster_name='',
            opensearch_timeout=120,
        )
        initialize_client(args)

        call_kwargs = mock_opensearch.call_args[1]
        assert call_kwargs['timeout'] == 120

    # --- AWS region override ---

    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.AWSV4SignerAsyncAuth')
    @patch('opensearch.client.boto3.Session')
    def test_aws_region_override(self, mock_session, mock_signer, mock_opensearch):
        """Tool-level aws_region overrides AWS_REGION env var."""
        os.environ['OPENSEARCH_URL'] = 'https://cluster.example.com'
        os.environ['AWS_REGION'] = 'us-east-1'
        mock_opensearch.return_value = Mock()

        # Mock AWS credentials
        mock_credentials = Mock()
        mock_credentials.access_key = 'test-key'
        mock_credentials.secret_key = 'test-secret'
        mock_credentials.token = 'test-token'
        mock_session_instance = Mock()
        mock_session_instance.get_credentials.return_value = mock_credentials
        mock_session.return_value = mock_session_instance

        args = baseToolArgs(
            opensearch_cluster_name='',
            aws_region='eu-west-1',
        )
        initialize_client(args)

        # Verify AWSV4SignerAsyncAuth was called with the overridden region
        mock_signer.assert_called_once()
        call_kwargs = mock_signer.call_args[1]
        assert call_kwargs['region'] == 'eu-west-1'

    # --- AWS profile override ---

    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.boto3.Session')
    def test_aws_profile_override(self, mock_session, mock_opensearch):
        """Tool-level aws_profile overrides AWS_PROFILE env var."""
        os.environ['OPENSEARCH_URL'] = 'https://cluster.example.com'
        os.environ['AWS_REGION'] = 'us-east-1'
        os.environ['AWS_PROFILE'] = 'env-profile'
        mock_opensearch.return_value = Mock()

        # Mock AWS credentials
        mock_credentials = Mock()
        mock_credentials.access_key = 'test-key'
        mock_credentials.secret_key = 'test-secret'
        mock_credentials.token = 'test-token'
        mock_session_instance = Mock()
        mock_session_instance.get_credentials.return_value = mock_credentials
        mock_session.return_value = mock_session_instance

        args = baseToolArgs(
            opensearch_cluster_name='',
            aws_profile='override-profile',
        )
        initialize_client(args)

        # Verify boto3.Session was called with the overridden profile
        mock_session.assert_called_with(profile_name='override-profile')

    # --- IAM ARN override ---

    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.boto3.Session')
    def test_iam_arn_override(self, mock_session, mock_opensearch):
        """Tool-level aws_iam_arn overrides AWS_IAM_ARN env var."""
        os.environ['OPENSEARCH_URL'] = 'https://cluster.example.com'
        os.environ['AWS_REGION'] = 'us-east-1'
        os.environ['AWS_IAM_ARN'] = 'arn:aws:iam::111111111111:role/EnvRole'
        mock_opensearch.return_value = Mock()

        # Mock STS assume_role
        mock_sts_client = Mock()
        mock_sts_client.assume_role.return_value = {
            'Credentials': {
                'AccessKeyId': 'assumed-key',
                'SecretAccessKey': 'assumed-secret',
                'SessionToken': 'assumed-token',
            }
        }
        mock_session_instance = Mock()
        mock_session_instance.client.return_value = mock_sts_client
        mock_session.return_value = mock_session_instance

        args = baseToolArgs(
            opensearch_cluster_name='',
            aws_iam_arn='arn:aws:iam::222222222222:role/OverrideRole',
        )
        initialize_client(args)

        # Verify assume_role was called with the overridden ARN
        mock_sts_client.assume_role.assert_called_once()
        call_args = mock_sts_client.assume_role.call_args[1]
        assert call_args['RoleArn'] == 'arn:aws:iam::222222222222:role/OverrideRole'

    # --- Serverless override ---

    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.AWSV4SignerAsyncAuth')
    @patch('opensearch.client.boto3.Session')
    def test_serverless_override(self, mock_session, mock_signer, mock_opensearch):
        """Tool-level aws_opensearch_serverless overrides env var."""
        os.environ['OPENSEARCH_URL'] = 'https://collection.aoss.amazonaws.com'
        os.environ['AWS_REGION'] = 'us-east-1'
        mock_opensearch.return_value = Mock()

        # Mock AWS credentials
        mock_credentials = Mock()
        mock_credentials.access_key = 'test-key'
        mock_credentials.secret_key = 'test-secret'
        mock_credentials.token = 'test-token'
        mock_session_instance = Mock()
        mock_session_instance.get_credentials.return_value = mock_credentials
        mock_session.return_value = mock_session_instance

        args = baseToolArgs(
            opensearch_cluster_name='',
            aws_opensearch_serverless=True,
        )
        initialize_client(args)

        # Verify AWSV4SignerAsyncAuth was called with 'aoss' service name
        mock_signer.assert_called_once()
        call_kwargs = mock_signer.call_args[1]
        assert call_kwargs['service'] == 'aoss'

    # --- Fallback behavior ---

    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_single_mode')
    def test_none_overrides_fall_back_to_env(self, mock_get_region, mock_opensearch):
        """When override fields are None (default), env vars are used."""
        os.environ['OPENSEARCH_URL'] = 'https://env-cluster.example.com'
        os.environ['OPENSEARCH_USERNAME'] = 'env-user'
        os.environ['OPENSEARCH_PASSWORD'] = 'env-pass'
        os.environ['OPENSEARCH_TIMEOUT'] = '45'
        mock_get_region.return_value = 'us-east-1'
        mock_opensearch.return_value = Mock()

        # All override fields are None by default
        args = baseToolArgs(opensearch_cluster_name='')
        initialize_client(args)

        call_kwargs = mock_opensearch.call_args[1]
        assert 'env-cluster.example.com' in call_kwargs['hosts'][0]
        assert call_kwargs['http_auth'] == ('env-user', 'env-pass')
        assert call_kwargs['timeout'] == 45

    # --- Combined overrides ---

    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_single_mode')
    def test_full_dynamic_connection(self, mock_get_region, mock_opensearch):
        """Agent provides all connection params with no env vars set at all."""
        mock_get_region.return_value = None
        mock_opensearch.return_value = Mock()

        args = baseToolArgs(
            opensearch_cluster_name='',
            opensearch_url='https://dynamic.example.com',
            opensearch_username='dynamic-user',
            opensearch_password='dynamic-pass',
            opensearch_ssl_verify=True,
            opensearch_timeout=60,
        )
        initialize_client(args)

        call_kwargs = mock_opensearch.call_args[1]
        assert 'dynamic.example.com' in call_kwargs['hosts'][0]
        assert call_kwargs['http_auth'] == ('dynamic-user', 'dynamic-pass')
        assert call_kwargs['verify_certs'] is True
        assert call_kwargs['timeout'] == 60

    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_single_mode')
    def test_partial_override_mixes_with_env(self, mock_get_region, mock_opensearch):
        """Override only URL; username/password still come from env."""
        os.environ['OPENSEARCH_URL'] = 'https://env-cluster.example.com'
        os.environ['OPENSEARCH_USERNAME'] = 'env-user'
        os.environ['OPENSEARCH_PASSWORD'] = 'env-pass'
        mock_get_region.return_value = 'us-east-1'
        mock_opensearch.return_value = Mock()

        args = baseToolArgs(
            opensearch_cluster_name='',
            opensearch_url='https://other-cluster.example.com',
        )
        initialize_client(args)

        call_kwargs = mock_opensearch.call_args[1]
        assert 'other-cluster.example.com' in call_kwargs['hosts'][0]
        assert call_kwargs['http_auth'] == ('env-user', 'env-pass')

    # --- Error cases ---

    def test_no_url_from_env_or_override_raises(self):
        """ConfigurationError when neither env var nor override provides a URL."""
        args = baseToolArgs(opensearch_cluster_name='')
        with pytest.raises(ConfigurationError):
            initialize_client(args)


class TestConnectionOverrideSchema:
    """Tests that connection override fields appear correctly in tool schemas."""

    def test_override_fields_present_in_base_schema(self):
        """All connection override fields exist in baseToolArgs schema."""
        from mcp_server_opensearch.server_instructions import CONNECTION_OVERRIDE_FIELDS

        schema = baseToolArgs.model_json_schema()
        for field in CONNECTION_OVERRIDE_FIELDS:
            assert field in schema['properties'], f'{field} missing from schema'

    def test_override_fields_are_optional(self):
        """Connection override fields are not in the required list."""
        from mcp_server_opensearch.server_instructions import CONNECTION_OVERRIDE_FIELDS

        schema = baseToolArgs.model_json_schema()
        required = schema.get('required', [])
        for field in CONNECTION_OVERRIDE_FIELDS:
            assert field not in required, f'{field} should not be required'

    def test_override_fields_default_to_none(self):
        """Connection override fields default to None when not provided."""
        args = baseToolArgs(opensearch_cluster_name='test')
        assert args.opensearch_url is None
        assert args.opensearch_username is None
        assert args.opensearch_password is None
        assert args.opensearch_no_auth is None
        assert args.aws_region is None
        assert args.aws_iam_arn is None
        assert args.aws_profile is None
        assert args.aws_opensearch_serverless is None
        assert args.opensearch_ssl_verify is None
        assert args.opensearch_timeout is None

    def test_override_fields_inherited_by_subclass(self):
        """Subclasses of baseToolArgs inherit connection override fields."""
        args = ListIndicesArgs(opensearch_cluster_name='test', index='my-index')
        assert args.opensearch_url is None
        assert args.opensearch_username is None

        # Can also set them
        args2 = ListIndicesArgs(
            opensearch_cluster_name='test',
            index='my-index',
            opensearch_url='https://dynamic.example.com',
        )
        assert args2.opensearch_url == 'https://dynamic.example.com'

    def test_single_mode_schema_keeps_override_fields(self):
        """In single mode without OPENSEARCH_URL, get_tools keeps overrides."""
        schema = ListIndicesArgs.model_json_schema()
        props = schema['properties']

        # Simulate what get_tools does in single mode without OPENSEARCH_URL
        _always_hidden = {'opensearch_cluster_name'}
        for field in _always_hidden:
            props.pop(field, None)

        # Override fields should still be present (no OPENSEARCH_URL configured)
        assert 'opensearch_url' in props
        assert 'opensearch_username' in props
        assert 'opensearch_password' in props
        # Tool-specific fields should also be present
        assert 'index' in props
        assert 'include_detail' in props
        # opensearch_cluster_name should be gone
        assert 'opensearch_cluster_name' not in props

    def test_single_mode_schema_strips_override_fields_when_url_configured(self):
        """In single mode with OPENSEARCH_URL set, get_tools strips overrides."""
        from mcp_server_opensearch.server_instructions import CONNECTION_OVERRIDE_FIELDS

        schema = ListIndicesArgs.model_json_schema()
        props = schema['properties']

        # Simulate what get_tools does when OPENSEARCH_URL is pre-configured
        _always_hidden = {'opensearch_cluster_name'}
        for field in _always_hidden | CONNECTION_OVERRIDE_FIELDS:
            props.pop(field, None)

        # Override fields should be gone
        for field in CONNECTION_OVERRIDE_FIELDS:
            assert field not in props
        # Tool-specific fields should still be present
        assert 'index' in props
        assert 'include_detail' in props


class TestConnectionOverrideValidation:
    """Tests for validate_args_for_mode with connection override fields."""

    def setup_method(self):
        """Set single mode."""
        from mcp_server_opensearch.global_state import set_mode

        set_mode('single')

    def test_validate_args_single_mode_with_overrides(self):
        """validate_args_for_mode accepts connection overrides in single mode."""
        from tools.tool_params import validate_args_for_mode

        args_dict = {
            'index': 'my-index',
            'opensearch_url': 'https://dynamic.example.com',
            'opensearch_username': 'user',
            'opensearch_password': 'pass',
        }
        result = validate_args_for_mode(args_dict, ListIndicesArgs)
        assert result.opensearch_url == 'https://dynamic.example.com'
        assert result.opensearch_username == 'user'
        assert result.opensearch_password == 'pass'
        assert result.opensearch_cluster_name == ''  # defaulted in single mode

    def test_validate_args_single_mode_without_overrides(self):
        """validate_args_for_mode works without connection overrides (backward compat)."""
        from tools.tool_params import validate_args_for_mode

        args_dict = {'index': 'my-index'}
        result = validate_args_for_mode(args_dict, ListIndicesArgs)
        assert result.opensearch_url is None
        assert result.opensearch_username is None
        assert result.index == 'my-index'

    def test_validate_args_multi_mode_with_overrides(self):
        """validate_args_for_mode accepts connection overrides in multi mode too."""
        from mcp_server_opensearch.global_state import set_mode
        from tools.tool_params import validate_args_for_mode

        set_mode('multi')
        args_dict = {
            'opensearch_cluster_name': 'my-cluster',
            'index': 'my-index',
            'opensearch_url': 'https://dynamic.example.com',
        }
        result = validate_args_for_mode(args_dict, ListIndicesArgs)
        assert result.opensearch_url == 'https://dynamic.example.com'
        assert result.opensearch_cluster_name == 'my-cluster'
