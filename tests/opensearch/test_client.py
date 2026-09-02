# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import boto3
import logging
import os
import pytest
import tempfile
from opensearch.client import (
    AuthenticationError,
    BufferedAsyncHttpConnection,
    ConfigurationError,
    _parsed_with_default_ports,
    initialize_client,
)
from opensearchpy import AWSV4SignerAsyncAuth
from tools.tool_params import baseToolArgs
from unittest.mock import Mock, patch
from urllib.parse import urlparse, urlunparse


class TestOpenSearchClient:
    """Tests for OpenSearch client initialization."""

    def setup_method(self):
        """Clear env vars and set single-cluster mode before each test."""
        self.original_env = {}
        for key in [
            'OPENSEARCH_USERNAME',
            'OPENSEARCH_PASSWORD',
            'AWS_REGION',
            'OPENSEARCH_URL',
            'OPENSEARCH_NO_AUTH',
            'OPENSEARCH_SSL_VERIFY',
            'OPENSEARCH_CA_CERT_PATH',
            'OPENSEARCH_CLIENT_CERT_PATH',
            'OPENSEARCH_CLIENT_KEY_PATH',
            'OPENSEARCH_TIMEOUT',
            'AWS_IAM_ARN',
            'AWS_ACCESS_KEY_ID',
            'AWS_SECRET_ACCESS_KEY',
            'AWS_SESSION_TOKEN',
        ]:
            if key in os.environ:
                self.original_env[key] = os.environ[key]
                del os.environ[key]

        from mcp_server_opensearch.global_state import set_mode

        set_mode('single')

    def teardown_method(self):
        """Cleanup after each test method."""
        # Restore original environment variables
        if hasattr(self, 'original_env'):
            for key, value in self.original_env.items():
                os.environ[key] = value

    def test_initialize_client_empty_url(self):
        """Test that initialize_client raises ConfigurationError when opensearch_url is empty."""
        with pytest.raises(ConfigurationError) as exc_info:
            initialize_client(baseToolArgs(opensearch_cluster_name=''))

        assert 'OPENSEARCH_URL environment variable is required but not set' in str(exc_info.value)

    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_single_mode')
    def test_initialize_client_basic_auth(self, mock_get_region, mock_opensearch):
        """Test client initialization with basic authentication."""
        # Set environment variables
        os.environ['OPENSEARCH_USERNAME'] = 'test-user'
        os.environ['OPENSEARCH_PASSWORD'] = 'test-password'
        os.environ['OPENSEARCH_URL'] = 'https://test-opensearch-domain.com'

        # Mock AWS region (not needed for basic auth, but called anyway)
        mock_get_region.return_value = 'us-east-1'

        # Mock OpenSearch client
        mock_client = Mock()
        mock_opensearch.return_value = mock_client

        # Execute
        client = initialize_client(baseToolArgs(opensearch_cluster_name=''))

        # Assert
        assert client == mock_client
        mock_opensearch.assert_called_once()
        call_kwargs = mock_opensearch.call_args[1]
        assert call_kwargs['hosts'] == ['https://test-opensearch-domain.com:443']
        assert call_kwargs['use_ssl'] is True
        assert call_kwargs['verify_certs'] is True
        assert call_kwargs['connection_class'] == BufferedAsyncHttpConnection
        assert call_kwargs['timeout'] == 30
        assert call_kwargs['max_response_size'] is None  # No limit by default
        assert call_kwargs['headers']['user-agent'].startswith('opensearch-mcp-server-py/')
        assert call_kwargs['http_auth'] == ('test-user', 'test-password')

    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.boto3.Session')
    def test_initialize_client_aws_auth(self, mock_session, mock_opensearch):
        """Test client initialization with AWS IAM authentication."""
        # Set environment variables (no basic auth to allow AWS auth)
        os.environ['AWS_REGION'] = 'us-west-2'
        os.environ['OPENSEARCH_URL'] = 'https://test-opensearch-domain.com'
        # Clear any basic auth env vars
        if 'OPENSEARCH_USERNAME' in os.environ:
            del os.environ['OPENSEARCH_USERNAME']
        if 'OPENSEARCH_PASSWORD' in os.environ:
            del os.environ['OPENSEARCH_PASSWORD']

        # Mock AWS credentials
        mock_credentials = Mock()
        mock_credentials.access_key = 'test-access-key'
        mock_credentials.secret_key = 'test-secret-key'
        mock_credentials.token = 'test-token'

        mock_session_instance = Mock()
        mock_session_instance.get_credentials.return_value = mock_credentials
        mock_session.return_value = mock_session_instance

        # Mock OpenSearch client
        mock_client = Mock()
        mock_opensearch.return_value = mock_client

        # Execute
        client = initialize_client(baseToolArgs(opensearch_cluster_name=''))

        # Assert
        assert client == mock_client
        mock_opensearch.assert_called_once()
        call_kwargs = mock_opensearch.call_args[1]
        assert call_kwargs['hosts'] == ['https://test-opensearch-domain.com:443']
        assert call_kwargs['use_ssl'] is True
        assert call_kwargs['verify_certs'] is True
        assert call_kwargs['connection_class'] == BufferedAsyncHttpConnection
        assert call_kwargs['max_response_size'] is None  # No limit by default
        assert isinstance(call_kwargs['http_auth'], AWSV4SignerAsyncAuth)

    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.boto3.Session')
    def test_initialize_client_aws_auth_error(self, mock_session, mock_opensearch):
        """Test client initialization when AWS authentication fails."""
        # Set environment variables
        os.environ['AWS_REGION'] = 'us-west-2'
        os.environ['OPENSEARCH_URL'] = 'https://test-opensearch-domain.com'

        # Mock AWS session to raise an error
        mock_session_instance = Mock()
        mock_session_instance.get_credentials.side_effect = boto3.exceptions.Boto3Error(
            'AWS credentials error'
        )
        mock_session.return_value = mock_session_instance

        # Execute and assert
        with pytest.raises(AuthenticationError) as exc_info:
            initialize_client(baseToolArgs(opensearch_cluster_name=''))
        assert 'Failed to authenticate with AWS credentials' in str(exc_info.value)

    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.boto3.Session')
    def test_initialize_client_no_auth(self, mock_session, mock_opensearch):
        """Test client initialization when no authentication is available."""
        # Set environment variable
        os.environ['OPENSEARCH_URL'] = 'https://test-opensearch-domain.com'

        # Mock AWS session to return no credentials
        mock_session_instance = Mock()
        mock_session_instance.get_credentials.return_value = None
        mock_session.return_value = mock_session_instance

        # Execute and assert
        with pytest.raises(AuthenticationError) as exc_info:
            initialize_client(baseToolArgs(opensearch_cluster_name=''))
        assert 'No AWS credentials found in session' in str(exc_info.value)

    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_single_mode')
    def test_initialize_client_no_auth_enabled(self, mock_get_region, mock_opensearch):
        """Test client initialization with OPENSEARCH_NO_AUTH=true."""
        # Set environment variables
        os.environ['OPENSEARCH_URL'] = 'https://test-opensearch-domain.com'
        os.environ['OPENSEARCH_NO_AUTH'] = 'true'

        # Mock AWS region (not needed for no auth, but called anyway)
        mock_get_region.return_value = 'us-east-1'

        # Mock OpenSearch client
        mock_client = Mock()
        mock_opensearch.return_value = mock_client

        # Execute
        client = initialize_client(baseToolArgs(opensearch_cluster_name=''))

        # Assert
        assert client == mock_client
        mock_opensearch.assert_called_once()
        call_kwargs = mock_opensearch.call_args[1]
        assert call_kwargs['hosts'] == ['https://test-opensearch-domain.com:443']
        assert call_kwargs['use_ssl'] is True
        assert call_kwargs['verify_certs'] is True
        assert call_kwargs['connection_class'] == BufferedAsyncHttpConnection
        assert call_kwargs['timeout'] == 30
        assert call_kwargs['max_response_size'] is None  # No limit by default
        assert call_kwargs['headers']['user-agent'].startswith('opensearch-mcp-server-py/')
        assert 'http_auth' not in call_kwargs

    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_single_mode')
    def test_initialize_client_basic_auth_with_mtls(self, mock_get_region, mock_opensearch):
        """Test client initialization with CA, client cert, and client key."""
        with (
            tempfile.NamedTemporaryFile() as ca_file,
            tempfile.NamedTemporaryFile() as cert_file,
            tempfile.NamedTemporaryFile() as key_file,
        ):
            os.environ['OPENSEARCH_USERNAME'] = 'test-user'
            os.environ['OPENSEARCH_PASSWORD'] = 'test-password'
            os.environ['OPENSEARCH_URL'] = 'https://test-opensearch-domain.com'
            os.environ['OPENSEARCH_CA_CERT_PATH'] = ca_file.name
            os.environ['OPENSEARCH_CLIENT_CERT_PATH'] = cert_file.name
            os.environ['OPENSEARCH_CLIENT_KEY_PATH'] = key_file.name

            mock_get_region.return_value = 'us-east-1'
            mock_client = Mock()
            mock_opensearch.return_value = mock_client

            client = initialize_client(baseToolArgs(opensearch_cluster_name=''))

            assert client == mock_client
            call_kwargs = mock_opensearch.call_args[1]
            assert call_kwargs['ca_certs'] == ca_file.name
            assert call_kwargs['client_cert'] == cert_file.name
            assert call_kwargs['client_key'] == key_file.name
            assert call_kwargs['http_auth'] == ('test-user', 'test-password')

    def test_initialize_client_rejects_partial_mtls_env_config(self):
        """Test that partial mTLS configuration is rejected in single mode."""
        with tempfile.NamedTemporaryFile() as cert_file:
            os.environ['OPENSEARCH_URL'] = 'https://test-opensearch-domain.com'
            os.environ['OPENSEARCH_NO_AUTH'] = 'true'
            os.environ['OPENSEARCH_CLIENT_CERT_PATH'] = cert_file.name

            with pytest.raises(ConfigurationError) as exc_info:
                initialize_client(baseToolArgs(opensearch_cluster_name=''))

        assert 'requires both client certificate and client key paths' in str(exc_info.value)

    @patch('opensearch.client._initialize_client_single_mode')
    def test_initialize_client_with_timeout_env(self, mock_init):
        """Test client initialization with timeout from environment."""
        os.environ['OPENSEARCH_TIMEOUT'] = '30'
        os.environ['OPENSEARCH_URL'] = 'https://test-opensearch-domain.com'
        os.environ['OPENSEARCH_USERNAME'] = 'admin'
        os.environ['OPENSEARCH_PASSWORD'] = 'password'

        mock_client = Mock()
        mock_init.return_value = mock_client

        client = initialize_client(baseToolArgs(opensearch_cluster_name=''))
        assert client == mock_client

    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_multi_mode')
    def test__initialize_client_multi_mode_timeout(self, mock_get_region, mock_opensearch):
        """Test client initialization with cluster timeout."""
        from mcp_server_opensearch.clusters_information import ClusterInfo
        from opensearch.client import _initialize_client_multi_mode

        cluster_info = ClusterInfo(
            opensearch_url='https://localhost:9200',
            opensearch_username='admin',
            opensearch_password='password',
            timeout=60,
        )

        # Mock AWS region (not needed for basic auth, but called anyway)
        mock_get_region.return_value = 'us-east-1'

        mock_client = Mock()
        mock_opensearch.return_value = mock_client

        client = _initialize_client_multi_mode(cluster_info)

        assert client == mock_client
        call_kwargs = mock_opensearch.call_args[1]
        assert call_kwargs['timeout'] == 60

    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_multi_mode')
    def test__initialize_client_multi_mode_no_auth(self, mock_get_region, mock_opensearch):
        """Test client initialization with no-auth from cluster config."""
        from mcp_server_opensearch.clusters_information import ClusterInfo
        from opensearch.client import _initialize_client_multi_mode

        cluster_info = ClusterInfo(
            opensearch_url='http://localhost:9200',
            opensearch_no_auth=True,
        )

        # Mock AWS region (not needed for no auth, but called anyway)
        mock_get_region.return_value = 'us-east-1'

        mock_client = Mock()
        mock_opensearch.return_value = mock_client

        client = _initialize_client_multi_mode(cluster_info)

        assert client == mock_client
        call_kwargs = mock_opensearch.call_args[1]
        assert call_kwargs['hosts'] == ['http://localhost:9200']
        assert call_kwargs['use_ssl'] is False  # http:// URL
        assert call_kwargs['verify_certs'] is True
        assert call_kwargs['connection_class'] == BufferedAsyncHttpConnection
        assert call_kwargs['max_response_size'] is None  # No limit by default
        # Should not have http_auth when no-auth is True
        assert 'http_auth' not in call_kwargs

    @patch('opensearch.client.request_context_var')
    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_multi_mode')
    def test__initialize_client_multi_mode_ignores_header_url(
        self, mock_get_region, mock_opensearch, mock_request_ctx
    ):
        """A header opensearch-url must not override the registered cluster URL."""
        from mcp_server_opensearch.clusters_information import ClusterInfo
        from opensearch.client import _initialize_client_multi_mode
        from starlette.requests import Request

        cluster_info = ClusterInfo(
            opensearch_url='https://registered-cluster.example.com',
            opensearch_no_auth=True,
            opensearch_header_auth=True,
        )
        mock_get_region.return_value = 'us-east-1'
        mock_opensearch.return_value = Mock()

        mock_request = Mock(spec=Request)
        mock_request.headers = {'opensearch-url': 'https://attacker.example.com'}
        mock_request_ctx.get.return_value = mock_request

        _initialize_client_multi_mode(cluster_info)

        call_kwargs = mock_opensearch.call_args[1]
        assert call_kwargs['hosts'][0].startswith('https://registered-cluster.example.com')
        assert 'attacker.example.com' not in call_kwargs['hosts'][0]

    @patch('opensearch.client.request_context_var')
    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_multi_mode')
    def test__initialize_client_multi_mode_no_auth_wins_over_unusable_credential(
        self, mock_get_region, mock_opensearch, mock_request_ctx
    ):
        """Multi mode: a configured no_auth attaches nothing, so nothing to fail over."""
        import base64
        from mcp_server_opensearch.clusters_information import ClusterInfo
        from opensearch.client import _initialize_client_multi_mode
        from starlette.requests import Request

        cluster_info = ClusterInfo(
            opensearch_url='https://registered-cluster.example.com',
            opensearch_no_auth=True,
            opensearch_header_auth=True,
        )
        mock_get_region.return_value = 'us-east-1'
        mock_opensearch.return_value = Mock()

        token = base64.b64encode(b'alice:').decode()
        mock_request = Mock(spec=Request)
        mock_request.headers = {'authorization': f'Basic {token}'}
        mock_request_ctx.get.return_value = mock_request

        _initialize_client_multi_mode(cluster_info)

        assert 'http_auth' not in mock_opensearch.call_args[1]

    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_multi_mode')
    def test__initialize_client_multi_mode_with_mtls(self, mock_get_region, mock_opensearch):
        """Test client initialization with mTLS paths from cluster config."""
        from mcp_server_opensearch.clusters_information import ClusterInfo
        from opensearch.client import _initialize_client_multi_mode

        with (
            tempfile.NamedTemporaryFile() as ca_file,
            tempfile.NamedTemporaryFile() as cert_file,
            tempfile.NamedTemporaryFile() as key_file,
        ):
            cluster_info = ClusterInfo(
                opensearch_url='https://localhost:9200',
                opensearch_username='admin',
                opensearch_password='password',
                opensearch_ca_cert_path=ca_file.name,
                opensearch_client_cert_path=cert_file.name,
                opensearch_client_key_path=key_file.name,
            )

            mock_get_region.return_value = 'us-east-1'
            mock_client = Mock()
            mock_opensearch.return_value = mock_client

            client = _initialize_client_multi_mode(cluster_info)

            assert client == mock_client
            call_kwargs = mock_opensearch.call_args[1]
            assert call_kwargs['ca_certs'] == ca_file.name
            assert call_kwargs['client_cert'] == cert_file.name
            assert call_kwargs['client_key'] == key_file.name
            assert call_kwargs['http_auth'] == ('admin', 'password')

    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_multi_mode')
    def test_initialize_client_no_auth_priority_cluster_over_env(
        self, mock_get_region, mock_opensearch
    ):
        """Test that cluster config opensearch_no_auth takes priority over environment variable."""
        from mcp_server_opensearch.clusters_information import ClusterInfo
        from opensearch.client import _initialize_client_multi_mode

        # Set environment variable to false
        os.environ['OPENSEARCH_NO_AUTH'] = 'false'

        cluster_info = ClusterInfo(
            opensearch_url='http://localhost:9200',
            opensearch_no_auth=True,  # Cluster config says no auth
        )

        # Mock AWS region (not needed for no auth, but called anyway)
        mock_get_region.return_value = 'us-east-1'

        mock_client = Mock()
        mock_opensearch.return_value = mock_client

        client = _initialize_client_multi_mode(cluster_info)

        assert client == mock_client
        call_kwargs = mock_opensearch.call_args[1]
        # Should use no auth because cluster config takes priority
        assert 'http_auth' not in call_kwargs

    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_cluster')
    @patch('opensearch.client.get_aws_region_multi_mode')
    def test_initialize_client_multi_cluster_no_auth(
        self, mock_get_region, mock_get_cluster, mock_opensearch
    ):
        """Test client initialization in multi-cluster mode with no-auth cluster."""
        from mcp_server_opensearch.clusters_information import ClusterInfo
        from mcp_server_opensearch.global_state import set_mode

        # Set mode to multi for this test
        set_mode('multi')

        # Mock cluster info with no-auth
        cluster_info = ClusterInfo(
            opensearch_url='http://localhost:9200',
            opensearch_no_auth=True,
        )
        mock_get_cluster.return_value = cluster_info

        # Mock AWS region (not needed for no auth, but called anyway)
        mock_get_region.return_value = 'us-east-1'

        # Mock OpenSearch client
        mock_client = Mock()
        mock_opensearch.return_value = mock_client

        # Create args with cluster name
        args = baseToolArgs(opensearch_cluster_name='')
        args.opensearch_cluster_name = 'no-auth-cluster'

        client = initialize_client(args)

        assert client == mock_client
        mock_get_cluster.assert_called_once_with('no-auth-cluster')
        call_kwargs = mock_opensearch.call_args[1]
        assert call_kwargs['hosts'] == ['http://localhost:9200']
        assert call_kwargs['use_ssl'] is False
        assert 'http_auth' not in call_kwargs


class TestOpenSearchClientContextManager:
    """Tests for the get_opensearch_client() async context manager."""

    def setup_method(self):
        """Setup before each test method."""
        # Clear environment variables to ensure clean test state
        for key in [
            'OPENSEARCH_USERNAME',
            'OPENSEARCH_PASSWORD',
            'AWS_REGION',
            'OPENSEARCH_URL',
            'OPENSEARCH_NO_AUTH',
            'OPENSEARCH_SSL_VERIFY',
            'OPENSEARCH_CA_CERT_PATH',
            'OPENSEARCH_CLIENT_CERT_PATH',
            'OPENSEARCH_CLIENT_KEY_PATH',
            'OPENSEARCH_TIMEOUT',
            'AWS_IAM_ARN',
            'AWS_ACCESS_KEY_ID',
            'AWS_SECRET_ACCESS_KEY',
            'AWS_SESSION_TOKEN',
        ]:
            if key in os.environ:
                del os.environ[key]

        # Set global mode for tests
        from mcp_server_opensearch.global_state import set_mode

        set_mode('single')

    @pytest.mark.asyncio
    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_single_mode')
    async def test_context_manager_successful_creation_and_cleanup(
        self, mock_get_region, mock_opensearch
    ):
        """Test that context manager creates client and calls close() on exit."""
        from opensearch.client import get_opensearch_client

        # Set environment variables
        os.environ['OPENSEARCH_URL'] = 'https://test-opensearch-domain.com'
        os.environ['OPENSEARCH_USERNAME'] = 'test-user'
        os.environ['OPENSEARCH_PASSWORD'] = 'test-password'

        # Mock AWS region
        mock_get_region.return_value = 'us-east-1'

        # Mock OpenSearch client with close method
        mock_client = Mock()
        mock_client.close = Mock(return_value=None)
        mock_opensearch.return_value = mock_client

        # Use context manager
        async with get_opensearch_client(baseToolArgs(opensearch_cluster_name='')) as client:
            assert client == mock_client

        # Verify close was called
        mock_client.close.assert_called_once()

    @pytest.mark.asyncio
    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_single_mode')
    async def test_context_manager_cleanup_on_exception(self, mock_get_region, mock_opensearch):
        """Test that context manager calls close() even when exception occurs."""
        from opensearch.client import get_opensearch_client

        # Set environment variables
        os.environ['OPENSEARCH_URL'] = 'https://test-opensearch-domain.com'
        os.environ['OPENSEARCH_USERNAME'] = 'test-user'
        os.environ['OPENSEARCH_PASSWORD'] = 'test-password'

        # Mock AWS region
        mock_get_region.return_value = 'us-east-1'

        # Mock OpenSearch client with close method
        mock_client = Mock()
        mock_client.close = Mock(return_value=None)
        mock_opensearch.return_value = mock_client

        # Use context manager and raise exception
        with pytest.raises(RuntimeError):
            async with get_opensearch_client(baseToolArgs(opensearch_cluster_name='')) as client:
                assert client == mock_client
                raise RuntimeError('Test exception')

        # Verify close was still called
        mock_client.close.assert_called_once()

    @pytest.mark.asyncio
    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_single_mode')
    async def test_context_manager_cleanup_error_logged_not_propagated(
        self, mock_get_region, mock_opensearch
    ):
        """Test that cleanup errors are logged but not propagated."""
        from opensearch.client import get_opensearch_client

        # Set environment variables
        os.environ['OPENSEARCH_URL'] = 'https://test-opensearch-domain.com'
        os.environ['OPENSEARCH_USERNAME'] = 'test-user'
        os.environ['OPENSEARCH_PASSWORD'] = 'test-password'

        # Mock AWS region
        mock_get_region.return_value = 'us-east-1'

        # Mock OpenSearch client with close method that raises exception
        mock_client = Mock()
        mock_client.close = Mock(side_effect=Exception('Cleanup error'))
        mock_opensearch.return_value = mock_client

        # Use context manager - should not raise cleanup exception
        async with get_opensearch_client(baseToolArgs(opensearch_cluster_name='')) as client:
            assert client == mock_client

        # Verify close was called
        mock_client.close.assert_called_once()

    @pytest.mark.asyncio
    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_single_mode')
    async def test_context_manager_cleanup_error_does_not_mask_original_exception(
        self, mock_get_region, mock_opensearch
    ):
        """Test that cleanup errors don't mask the original exception."""
        from opensearch.client import get_opensearch_client

        # Set environment variables
        os.environ['OPENSEARCH_URL'] = 'https://test-opensearch-domain.com'
        os.environ['OPENSEARCH_USERNAME'] = 'test-user'
        os.environ['OPENSEARCH_PASSWORD'] = 'test-password'

        # Mock AWS region
        mock_get_region.return_value = 'us-east-1'

        # Mock OpenSearch client with close method that raises exception
        mock_client = Mock()
        mock_client.close = Mock(side_effect=Exception('Cleanup error'))
        mock_opensearch.return_value = mock_client

        # Use context manager and raise exception - should get original exception
        with pytest.raises(RuntimeError, match='Original exception'):
            async with get_opensearch_client(baseToolArgs(opensearch_cluster_name='')) as client:
                assert client == mock_client
                raise RuntimeError('Original exception')

        # Verify close was still called
        mock_client.close.assert_called_once()

    @pytest.mark.asyncio
    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_single_mode')
    async def test_context_manager_multiple_sequential_calls(
        self, mock_get_region, mock_opensearch
    ):
        """Test that multiple sequential context manager calls each create and close clients."""
        from opensearch.client import get_opensearch_client

        # Set environment variables
        os.environ['OPENSEARCH_URL'] = 'https://test-opensearch-domain.com'
        os.environ['OPENSEARCH_USERNAME'] = 'test-user'
        os.environ['OPENSEARCH_PASSWORD'] = 'test-password'

        # Mock AWS region
        mock_get_region.return_value = 'us-east-1'

        # Mock OpenSearch clients
        mock_client1 = Mock()
        mock_client1.close = Mock(return_value=None)
        mock_client2 = Mock()
        mock_client2.close = Mock(return_value=None)
        mock_client3 = Mock()
        mock_client3.close = Mock(return_value=None)

        mock_opensearch.side_effect = [mock_client1, mock_client2, mock_client3]

        # First call
        async with get_opensearch_client(baseToolArgs(opensearch_cluster_name='')) as client:
            assert client == mock_client1
        mock_client1.close.assert_called_once()

        # Second call
        async with get_opensearch_client(baseToolArgs(opensearch_cluster_name='')) as client:
            assert client == mock_client2
        mock_client2.close.assert_called_once()

        # Third call
        async with get_opensearch_client(baseToolArgs(opensearch_cluster_name='')) as client:
            assert client == mock_client3
        mock_client3.close.assert_called_once()

        # Verify all three clients were created
        assert mock_opensearch.call_count == 3


class TestHeaderBasedBasicAuth:
    """Tests for Basic authentication via Authorization header."""

    def setup_method(self):
        """Setup before each test method."""
        # Clear environment variables
        for key in [
            'OPENSEARCH_USERNAME',
            'OPENSEARCH_PASSWORD',
            'AWS_REGION',
            'OPENSEARCH_URL',
            'OPENSEARCH_NO_AUTH',
            'OPENSEARCH_HEADER_AUTH',
        ]:
            if key in os.environ:
                del os.environ[key]

        # Set global mode for tests
        from mcp_server_opensearch.global_state import set_mode

        set_mode('single')

    @patch('opensearch.client.boto3.Session')
    @patch('opensearch.client.request_context_var')
    @patch('opensearch.client.AsyncOpenSearch')
    def test_basic_auth_from_authorization_header(
        self, mock_opensearch, mock_request_ctx, mock_boto_session
    ):
        """Test Basic auth extraction from Authorization header."""
        import base64
        from starlette.requests import Request

        # Set required environment variables
        os.environ['OPENSEARCH_URL'] = 'https://test-opensearch-domain.com'
        os.environ['OPENSEARCH_HEADER_AUTH'] = 'true'

        # Mock boto3 Session to return None for credentials
        mock_session = Mock()
        mock_session.Session().return_value = None
        mock_boto_session.return_value = mock_session

        # Create mock request with Authorization header
        username = 'header-user'
        password = 'header-password'
        credentials = f'{username}:{password}'
        encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')

        mock_request = Mock(spec=Request)
        mock_request.headers = {'authorization': f'Basic {encoded_credentials}'}

        # Mock request context var to return the request directly
        mock_request_ctx.get.return_value = mock_request

        # Mock OpenSearch client
        mock_client = Mock()
        mock_opensearch.return_value = mock_client

        # Execute
        client = initialize_client(baseToolArgs(opensearch_cluster_name=''))

        # Assert
        assert client == mock_client
        # Verify Basic auth was used from header
        call_kwargs = mock_opensearch.call_args[1]
        assert call_kwargs['http_auth'] == (username, password)

    @patch('opensearch.client.boto3.Session')
    @patch('opensearch.client.request_context_var')
    @patch('opensearch.client.AsyncOpenSearch')
    def test_basic_auth_header_overrides_env_vars(
        self, mock_opensearch, mock_request_ctx, mock_boto_session
    ):
        """Test that Authorization header overrides environment variables."""
        import base64
        from starlette.requests import Request

        # Set environment variables with different credentials
        os.environ['OPENSEARCH_URL'] = 'https://test-opensearch-domain.com'
        os.environ['OPENSEARCH_USERNAME'] = 'env-user'
        os.environ['OPENSEARCH_PASSWORD'] = 'env-password'
        os.environ['OPENSEARCH_HEADER_AUTH'] = 'true'

        # Mock boto3 Session to return None for credentials
        mock_session = Mock()
        mock_session.get_credentials.return_value = None
        mock_boto_session.return_value = mock_session

        # Create mock request with Authorization header (different credentials)
        header_username = 'header-user'
        header_password = 'header-password'
        credentials = f'{header_username}:{header_password}'
        encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')

        mock_request = Mock(spec=Request)
        mock_request.headers = {'authorization': f'Basic {encoded_credentials}'}

        # Mock request context var to return the request directly
        mock_request_ctx.get.return_value = mock_request

        # Mock OpenSearch client
        mock_client = Mock()
        mock_opensearch.return_value = mock_client

        # Execute
        client = initialize_client(baseToolArgs(opensearch_cluster_name=''))

        # Assert - header credentials should be used, not env var credentials
        assert client == mock_client
        call_kwargs = mock_opensearch.call_args[1]
        assert call_kwargs['http_auth'] == (header_username, header_password)

    @patch('opensearch.client.request_context_var')
    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_single_mode')
    def test_basic_auth_falls_back_to_env_when_no_header(
        self, mock_get_region, mock_opensearch, mock_request_ctx
    ):
        """Test that env vars are used when Authorization header is not present."""
        # Set environment variables
        os.environ['OPENSEARCH_URL'] = 'https://test-opensearch-domain.com'
        os.environ['OPENSEARCH_USERNAME'] = 'env-user'
        os.environ['OPENSEARCH_PASSWORD'] = 'env-password'
        os.environ['OPENSEARCH_HEADER_AUTH'] = 'true'

        # Mock AWS region
        mock_get_region.return_value = 'us-east-1'

        # Create mock request without Authorization header
        mock_request = Mock()
        mock_request.headers = {}

        # Mock request context var to return the request directly
        mock_request_ctx.get.return_value = mock_request

        # Mock OpenSearch client
        mock_client = Mock()
        mock_opensearch.return_value = mock_client

        # Execute
        client = initialize_client(baseToolArgs(opensearch_cluster_name=''))

        # Assert - env var credentials should be used
        assert client == mock_client
        call_kwargs = mock_opensearch.call_args[1]
        assert call_kwargs['http_auth'] == ('env-user', 'env-password')


class TestHeaderBasedBearerAuth:
    """Tests for Bearer authentication via Authorization header."""

    def setup_method(self):
        """Setup before each test method."""
        # Clear environment variables
        for key in [
            'OPENSEARCH_USERNAME',
            'OPENSEARCH_PASSWORD',
            'AWS_REGION',
            'OPENSEARCH_URL',
            'OPENSEARCH_NO_AUTH',
            'OPENSEARCH_HEADER_AUTH',
        ]:
            if key in os.environ:
                del os.environ[key]

        # Set global mode for tests
        from mcp_server_opensearch.global_state import set_mode

        set_mode('single')

    @patch('opensearch.client.request_context_var')
    @patch('opensearch.client.AsyncOpenSearch')
    def test_bearer_auth_from_authorization_header(self, mock_opensearch, mock_request_ctx):
        """Test Bearer auth passthrough from Authorization header."""
        from starlette.requests import Request

        # Set required environment variables
        os.environ['OPENSEARCH_URL'] = 'https://test-opensearch-domain.com'
        os.environ['OPENSEARCH_HEADER_AUTH'] = 'true'

        # Create mock request with Authorization Bearer header
        bearer_token = 'test-bearer-token'
        mock_request = Mock(spec=Request)
        mock_request.headers = {'authorization': f'Bearer {bearer_token}'}

        # Mock request context var to return the request directly
        mock_request_ctx.get.return_value = mock_request

        # Mock OpenSearch client
        mock_client = Mock()
        mock_opensearch.return_value = mock_client

        # Execute
        client = initialize_client(baseToolArgs(opensearch_cluster_name=''))

        # Assert
        assert client == mock_client
        call_kwargs = mock_opensearch.call_args[1]
        assert call_kwargs['headers'] == {'Authorization': f'Bearer {bearer_token}'}
        assert 'http_auth' not in call_kwargs

    @patch('opensearch.client.request_context_var')
    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_single_mode')
    def test_malformed_authorization_header(
        self, mock_get_region, mock_opensearch, mock_request_ctx
    ):
        """Test that malformed Authorization header is gracefully ignored."""
        # Set environment variables
        os.environ['OPENSEARCH_URL'] = 'https://test-opensearch-domain.com'
        os.environ['OPENSEARCH_USERNAME'] = 'env-user'
        os.environ['OPENSEARCH_PASSWORD'] = 'env-password'
        os.environ['OPENSEARCH_HEADER_AUTH'] = 'true'

        # Mock AWS region
        mock_get_region.return_value = 'us-east-1'

        # Create mock request with malformed Authorization header
        mock_request = Mock()
        mock_request.headers = {'authorization': 'Basic invalid-base64!!!'}

        # Mock request context var to return the request directly
        mock_request_ctx.get.return_value = mock_request

        # Mock OpenSearch client
        mock_client = Mock()
        mock_opensearch.return_value = mock_client

        # Execute
        client = initialize_client(baseToolArgs(opensearch_cluster_name=''))

        # Assert - should fall back to env var credentials
        assert client == mock_client
        call_kwargs = mock_opensearch.call_args[1]
        assert call_kwargs['http_auth'] == ('env-user', 'env-password')

    @patch('opensearch.client.request_context_var')
    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_single_mode')
    def test_authorization_header_without_colon(
        self, mock_get_region, mock_opensearch, mock_request_ctx
    ):
        """Test Authorization header with credentials that don't contain a colon."""
        import base64

        # Set environment variables
        os.environ['OPENSEARCH_URL'] = 'https://test-opensearch-domain.com'
        os.environ['OPENSEARCH_USERNAME'] = 'env-user'
        os.environ['OPENSEARCH_PASSWORD'] = 'env-password'
        os.environ['OPENSEARCH_HEADER_AUTH'] = 'true'

        # Mock AWS region
        mock_get_region.return_value = 'us-east-1'

        # Create mock request with Authorization header without colon
        mock_request = Mock()
        credentials = 'usernameonly'
        encoded_credentials = base64.b64encode(credentials.encode('utf-8')).decode('utf-8')
        mock_request.headers = {'authorization': f'Basic {encoded_credentials}'}

        # Mock request context var to return the request directly
        mock_request_ctx.get.return_value = mock_request

        # Mock OpenSearch client
        mock_client = Mock()
        mock_opensearch.return_value = mock_client

        # Execute
        client = initialize_client(baseToolArgs(opensearch_cluster_name=''))

        # Assert - should fall back to env var credentials since format is invalid
        assert client == mock_client
        call_kwargs = mock_opensearch.call_args[1]
        assert call_kwargs['http_auth'] == ('env-user', 'env-password')


class TestHeaderUrlBinding:
    """A header-supplied URL may only use credentials from those same headers."""

    def setup_method(self):
        for key in [
            'OPENSEARCH_USERNAME',
            'OPENSEARCH_PASSWORD',
            'AWS_REGION',
            'OPENSEARCH_URL',
            'OPENSEARCH_NO_AUTH',
            'OPENSEARCH_HEADER_AUTH',
        ]:
            os.environ.pop(key, None)
        os.environ['OPENSEARCH_DYNAMIC_CONNECTION'] = 'true'
        from mcp_server_opensearch.global_state import set_mode

        set_mode('single')

    def teardown_method(self):
        for key in [
            'OPENSEARCH_URL',
            'OPENSEARCH_USERNAME',
            'OPENSEARCH_PASSWORD',
            'OPENSEARCH_HEADER_AUTH',
            'OPENSEARCH_DYNAMIC_CONNECTION',
        ]:
            os.environ.pop(key, None)

    def _ctx(self, mock_request_ctx, headers):
        from starlette.requests import Request

        mock_request = Mock(spec=Request)
        mock_request.headers = headers
        mock_request_ctx.get.return_value = mock_request

    @patch('opensearch.client.request_context_var')
    @patch('opensearch.client.AsyncOpenSearch')
    def test_header_url_with_own_bearer_binds(self, mock_opensearch, mock_request_ctx):
        """A header URL carrying its own Bearer token connects to that URL."""
        os.environ['OPENSEARCH_URL'] = 'https://env-cluster.example.com'
        os.environ['OPENSEARCH_HEADER_AUTH'] = 'true'
        self._ctx(
            mock_request_ctx,
            {
                'opensearch-url': 'https://header-cluster.example.com',
                'authorization': 'Bearer header-token',
            },
        )
        mock_opensearch.return_value = Mock()

        initialize_client(baseToolArgs(opensearch_cluster_name=''))

        call_kwargs = mock_opensearch.call_args[1]
        assert 'header-cluster.example.com' in call_kwargs['hosts'][0]
        assert call_kwargs['headers']['Authorization'] == 'Bearer header-token'

    @patch('opensearch.client.boto3.Session')
    @patch('opensearch.client.request_context_var')
    @patch('opensearch.client.AsyncOpenSearch')
    def test_header_url_does_not_borrow_env_basic_auth(
        self, mock_opensearch, mock_request_ctx, mock_boto_session
    ):
        """A bare header URL must not inherit env basic auth; it hard-errors."""
        os.environ['OPENSEARCH_URL'] = 'https://env-cluster.example.com'
        os.environ['OPENSEARCH_USERNAME'] = 'env-user'
        os.environ['OPENSEARCH_PASSWORD'] = 'env-pass'
        os.environ['OPENSEARCH_HEADER_AUTH'] = 'true'
        session = Mock()
        session.get_credentials.return_value = None
        mock_boto_session.return_value = session
        self._ctx(mock_request_ctx, {'opensearch-url': 'https://header-cluster.example.com'})
        mock_opensearch.return_value = Mock()

        with pytest.raises(AuthenticationError):
            initialize_client(baseToolArgs(opensearch_cluster_name=''))
        mock_opensearch.assert_not_called()

    @patch('opensearch.client.request_context_var')
    @patch('opensearch.client.AsyncOpenSearch')
    def test_arg_url_does_not_borrow_header_bearer(self, mock_opensearch, mock_request_ctx):
        """An arg-supplied URL must not bind a proxy-injected header Bearer.

        The token belongs to whoever set the header, not to the caller who passed
        the URL, so with no credentials of its own the request must fail.
        """
        os.environ['OPENSEARCH_URL'] = 'https://env-cluster.example.com'
        os.environ['OPENSEARCH_HEADER_AUTH'] = 'true'
        self._ctx(mock_request_ctx, {'authorization': 'Bearer proxy-token'})
        mock_opensearch.return_value = Mock()

        with pytest.raises(AuthenticationError):
            initialize_client(
                baseToolArgs(
                    opensearch_cluster_name='',
                    opensearch_url='https://arg-cluster.example.com',
                )
            )
        mock_opensearch.assert_not_called()

    @patch('opensearch.client._create_opensearch_client')
    @patch('opensearch.client.request_context_var')
    def test_header_url_clears_profile_and_its_requirement_together(
        self, mock_request_ctx, mock_create
    ):
        """Clearing the arg profile must also clear the flag demanding one.

        Otherwise the connection is built with "a named profile is required" set
        while no profile is named, a state nothing downstream can satisfy.
        """
        os.environ['OPENSEARCH_URL'] = 'https://env-cluster.example.com'
        os.environ['OPENSEARCH_HEADER_AUTH'] = 'true'
        self._ctx(
            mock_request_ctx,
            {
                'opensearch-url': 'https://header-cluster.example.com',
                'authorization': 'Bearer header-token',
            },
        )
        mock_create.return_value = Mock()

        initialize_client(
            baseToolArgs(
                opensearch_cluster_name='',
                opensearch_url='https://arg-cluster.example.com',
                aws_profile='arg-profile',
            )
        )

        kwargs = mock_create.call_args[1]
        assert kwargs['profile'] == ''
        assert kwargs['require_named_profile'] is False


class TestNoAuthDropsEveryCredential:
    """no_auth means no auth, whatever credentials the request carried."""

    def setup_method(self):
        for key in ['OPENSEARCH_URL', 'OPENSEARCH_NO_AUTH', 'OPENSEARCH_HEADER_AUTH']:
            os.environ.pop(key, None)
        from mcp_server_opensearch.global_state import set_mode

        set_mode('single')

    def teardown_method(self):
        for key in [
            'OPENSEARCH_URL',
            'OPENSEARCH_NO_AUTH',
            'OPENSEARCH_HEADER_AUTH',
            'OPENSEARCH_USERNAME',
            'OPENSEARCH_PASSWORD',
        ]:
            os.environ.pop(key, None)

    @patch('opensearch.client.request_context_var')
    @patch('opensearch.client.AsyncOpenSearch')
    def test_header_aws_keys_do_not_disable_no_auth(self, mock_opensearch, mock_request_ctx):
        """Credentials in the request must not switch no_auth off.

        Doing so would drop the request through to the server's own credentials.
        """
        from starlette.requests import Request

        os.environ['OPENSEARCH_URL'] = 'https://env-cluster.example.com'
        os.environ['OPENSEARCH_NO_AUTH'] = 'true'
        os.environ['OPENSEARCH_HEADER_AUTH'] = 'true'
        os.environ['OPENSEARCH_USERNAME'] = 'server-admin'
        os.environ['OPENSEARCH_PASSWORD'] = 'server-secret'

        mock_request = Mock(spec=Request)
        mock_request.headers = {'aws-access-key-id': 'key-without-secret'}
        mock_request_ctx.get.return_value = mock_request
        mock_opensearch.return_value = Mock()

        initialize_client(baseToolArgs(opensearch_cluster_name=''))

        assert 'http_auth' not in mock_opensearch.call_args[1]

    @patch('opensearch.client.request_context_var')
    @patch('opensearch.client.AsyncOpenSearch')
    def test_no_auth_wins_over_an_unusable_header_credential(
        self, mock_opensearch, mock_request_ctx
    ):
        """no_auth attaches nothing, so an unusable credential is not worth failing over."""
        import base64
        from starlette.requests import Request

        os.environ['OPENSEARCH_URL'] = 'https://env-cluster.example.com'
        os.environ['OPENSEARCH_NO_AUTH'] = 'true'
        os.environ['OPENSEARCH_HEADER_AUTH'] = 'true'

        token = base64.b64encode(b'alice:').decode()
        mock_request = Mock(spec=Request)
        mock_request.headers = {'authorization': f'Basic {token}'}
        mock_request_ctx.get.return_value = mock_request
        mock_opensearch.return_value = Mock()

        initialize_client(baseToolArgs(opensearch_cluster_name=''))

        assert 'http_auth' not in mock_opensearch.call_args[1]

    @patch('opensearch.client.request_context_var')
    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.boto3.Session')
    def test_empty_password_still_fails_without_no_auth(
        self, mock_session, mock_opensearch, mock_request_ctx
    ):
        """Without no_auth the credential is unusable, so fail rather than fall onward."""
        import base64
        from starlette.requests import Request

        os.environ['OPENSEARCH_URL'] = 'https://env-cluster.example.com'
        os.environ['OPENSEARCH_HEADER_AUTH'] = 'true'

        token = base64.b64encode(b'alice:').decode()
        mock_request = Mock(spec=Request)
        mock_request.headers = {'authorization': f'Basic {token}'}
        mock_request_ctx.get.return_value = mock_request
        mock_opensearch.return_value = Mock()
        mock_session.return_value.get_credentials.return_value = None

        with pytest.raises(AuthenticationError, match='password is empty'):
            initialize_client(baseToolArgs(opensearch_cluster_name=''))


class TestParsedWithDefaultPorts:
    """URL normalization used by ``_create_opensearch_client`` (same path as production)."""

    @staticmethod
    def _norm(url: str) -> str:
        return _parsed_with_default_ports(urlparse(url))[0]

    def test_https_adds_443(self):
        """HTTPS without a port uses TCP 443."""
        assert self._norm('https://my-cluster.example.com') == 'https://my-cluster.example.com:443'

    def test_http_adds_80(self):
        """HTTP without a port uses TCP 80."""
        assert self._norm('http://my-cluster.example.com') == 'http://my-cluster.example.com:80'

    def test_explicit_port_unchanged(self):
        """Explicit port in the URL is preserved."""
        assert (
            self._norm('https://my-cluster.example.com:9200')
            == 'https://my-cluster.example.com:9200'
        )

    def test_https_ipv6_adds_443(self):
        """HTTPS IPv6 literal without a port gets :443."""
        assert self._norm('https://[::1]/') == 'https://[::1]:443/'

    def test_basic_auth_netloc(self):
        """Userinfo in netloc is kept when inserting the default port."""
        assert (
            self._norm('https://user:secret@my-cluster.example.com/path')
            == 'https://user:secret@my-cluster.example.com:443/path'
        )


class TestScrubUrlUserinfo:
    """The log-scrub helper removes embedded credentials from URLs."""

    def _scrub(self, url):
        from opensearch.client import _scrub_url_userinfo

        return _scrub_url_userinfo(url)

    def test_strips_user_and_password(self):
        assert self._scrub('https://user:pass@host:9200/path') == 'https://host:9200/path'

    def test_strips_user_only(self):
        assert self._scrub('https://user@host:9200') == 'https://host:9200'

    def test_no_userinfo_unchanged(self):
        assert self._scrub('https://host:9200/path') == 'https://host:9200/path'

    def test_empty_unchanged(self):
        assert self._scrub('') == ''

    def test_ipv6_host_preserved(self):
        assert self._scrub('https://user:pass@[::1]:9200') == 'https://[::1]:9200'

    def test_strips_query_and_fragment(self):
        """A secret in the query string or fragment must not survive."""
        assert (
            self._scrub('https://host:9200/path?access_token=secret#frag')
            == 'https://host:9200/path'
        )

    def test_malformed_url_redacted_not_leaked(self):
        """A malformed URL that still carries a secret is redacted, not returned raw."""
        malformed = 'https://user:secret@[invalid/?access_token=q#frag'
        scrubbed = self._scrub(malformed)
        assert 'secret' not in scrubbed
        assert 'access_token' not in scrubbed

    def test_non_numeric_port_redacted_not_leaked(self):
        """A non-numeric port (parsed.port raises) must not leak the raw string."""
        scrubbed = self._scrub('https://example.com:access_token=SECRET/')
        assert 'SECRET' not in scrubbed
        assert 'access_token' not in scrubbed


class TestStripUrlCredentialsAndQuery:
    """The hosts value handed to opensearch-py keeps only host, port, and path."""

    def _strip(self, url):
        from opensearch.client import _strip_url_credentials_and_query

        return urlunparse(_strip_url_credentials_and_query(urlparse(url)))

    def test_strips_userinfo_query_fragment(self):
        assert self._strip('https://user:pass@host:9200/p?q=1#f') == 'https://host:9200/p'

    def test_strips_matrix_params(self):
        """A matrix param can carry a session secret and must not survive."""
        assert self._strip('https://host:9200/path;sessionid=SECRET') == 'https://host:9200/path'

    def test_clean_url_unchanged(self):
        assert self._strip('https://host:9200/path') == 'https://host:9200/path'


class TestMtlsIdentityWithheldFromCallerUrl:
    """A caller URL must not be given the server's mTLS client identity."""

    def setup_method(self):
        for key in ['OPENSEARCH_URL', 'OPENSEARCH_CLIENT_CERT_PATH', 'OPENSEARCH_CLIENT_KEY_PATH']:
            os.environ.pop(key, None)
        os.environ['OPENSEARCH_DYNAMIC_CONNECTION'] = 'true'
        from mcp_server_opensearch.global_state import set_mode

        set_mode('single')

    def teardown_method(self):
        for key in [
            'OPENSEARCH_URL',
            'OPENSEARCH_CLIENT_CERT_PATH',
            'OPENSEARCH_CLIENT_KEY_PATH',
            'OPENSEARCH_DYNAMIC_CONNECTION',
        ]:
            os.environ.pop(key, None)

    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_single_mode')
    def test_args_url_does_not_get_env_client_cert(self, mock_get_region, mock_opensearch):
        with tempfile.NamedTemporaryFile() as cert, tempfile.NamedTemporaryFile() as key:
            os.environ['OPENSEARCH_URL'] = 'https://env-cluster.example.com'
            os.environ['OPENSEARCH_CLIENT_CERT_PATH'] = cert.name
            os.environ['OPENSEARCH_CLIENT_KEY_PATH'] = key.name
            mock_get_region.return_value = 'us-east-1'
            mock_opensearch.return_value = Mock()

            initialize_client(
                baseToolArgs(
                    opensearch_cluster_name='',
                    opensearch_url='https://caller.example.com',
                    opensearch_no_auth=True,
                )
            )

            call_kwargs = mock_opensearch.call_args[1]
            assert 'client_cert' not in call_kwargs
            assert 'client_key' not in call_kwargs

    @patch('opensearch.client.request_context_var')
    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_single_mode')
    def test_header_url_does_not_get_env_client_cert(
        self, mock_get_region, mock_opensearch, mock_request_ctx
    ):
        from starlette.requests import Request

        with tempfile.NamedTemporaryFile() as cert, tempfile.NamedTemporaryFile() as key:
            os.environ['OPENSEARCH_URL'] = 'https://env-cluster.example.com'
            os.environ['OPENSEARCH_HEADER_AUTH'] = 'true'
            os.environ['OPENSEARCH_NO_AUTH'] = 'true'
            os.environ['OPENSEARCH_CLIENT_CERT_PATH'] = cert.name
            os.environ['OPENSEARCH_CLIENT_KEY_PATH'] = key.name
            mock_get_region.return_value = 'us-east-1'
            mock_opensearch.return_value = Mock()

            mock_request = Mock(spec=Request)
            mock_request.headers = {'opensearch-url': 'https://header-cluster.example.com'}
            mock_request_ctx.get.return_value = mock_request

            try:
                initialize_client(baseToolArgs(opensearch_cluster_name=''))
            finally:
                os.environ.pop('OPENSEARCH_HEADER_AUTH', None)
                os.environ.pop('OPENSEARCH_NO_AUTH', None)

            call_kwargs = mock_opensearch.call_args[1]
            assert 'client_cert' not in call_kwargs
            assert 'client_key' not in call_kwargs


class TestCallerUrlUserinfoStripped:
    """A caller URL must not smuggle credentials in as userinfo."""

    def setup_method(self):
        os.environ.pop('OPENSEARCH_URL', None)
        os.environ['OPENSEARCH_DYNAMIC_CONNECTION'] = 'true'
        from mcp_server_opensearch.global_state import set_mode

        set_mode('single')

    def teardown_method(self):
        for key in ['OPENSEARCH_URL', 'OPENSEARCH_DYNAMIC_CONNECTION']:
            os.environ.pop(key, None)

    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_single_mode')
    def test_caller_url_userinfo_removed(self, mock_get_region, mock_opensearch):
        os.environ['OPENSEARCH_URL'] = 'https://env-cluster.example.com'
        mock_get_region.return_value = 'us-east-1'
        mock_opensearch.return_value = Mock()

        initialize_client(
            baseToolArgs(
                opensearch_cluster_name='',
                opensearch_url='https://sneak:secret@caller.example.com',
                opensearch_no_auth=True,
            )
        )

        host = mock_opensearch.call_args[1]['hosts'][0]
        assert 'sneak' not in host
        assert 'secret' not in host

    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_single_mode')
    def test_operator_url_userinfo_preserved(self, mock_get_region, mock_opensearch):
        """opensearch-py turns these into http_auth, so removing them breaks the deployment."""
        os.environ['OPENSEARCH_URL'] = 'https://svcuser:svcpass@cluster.example.com:9200'
        mock_get_region.return_value = 'us-east-1'
        mock_opensearch.return_value = Mock()

        initialize_client(baseToolArgs(opensearch_cluster_name='', opensearch_no_auth=True))

        assert mock_opensearch.call_args[1]['hosts'][0] == (
            'https://svcuser:svcpass@cluster.example.com:9200'
        )


class TestRedirectsPairedWithSsrfGuard:
    """Redirects are refused for a caller URL only while the SSRF guard is on."""

    def setup_method(self):
        for key in ['OPENSEARCH_URL', 'OPENSEARCH_SSRF_GUARD']:
            os.environ.pop(key, None)
        os.environ['OPENSEARCH_DYNAMIC_CONNECTION'] = 'true'
        from mcp_server_opensearch.global_state import set_mode

        set_mode('single')

    def teardown_method(self):
        for key in ['OPENSEARCH_URL', 'OPENSEARCH_SSRF_GUARD', 'OPENSEARCH_DYNAMIC_CONNECTION']:
            os.environ.pop(key, None)

    def _follow_redirects(self, mock_opensearch):
        return mock_opensearch.call_args[1]['follow_redirects']

    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_single_mode')
    def test_operator_url_follows_redirects(self, mock_get_region, mock_opensearch):
        os.environ['OPENSEARCH_URL'] = 'https://env-cluster.example.com'
        os.environ['OPENSEARCH_SSRF_GUARD'] = 'true'
        mock_get_region.return_value = 'us-east-1'
        mock_opensearch.return_value = Mock()

        initialize_client(baseToolArgs(opensearch_cluster_name='', opensearch_no_auth=True))

        assert self._follow_redirects(mock_opensearch) is True

    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_single_mode')
    def test_caller_url_follows_redirects_when_guard_off(self, mock_get_region, mock_opensearch):
        """With the guard off a caller can name any address anyway, so this adds nothing."""
        os.environ['OPENSEARCH_URL'] = 'https://env-cluster.example.com'
        mock_get_region.return_value = 'us-east-1'
        mock_opensearch.return_value = Mock()

        initialize_client(
            baseToolArgs(
                opensearch_cluster_name='',
                opensearch_url='https://caller.example.com',
                opensearch_no_auth=True,
            )
        )

        assert self._follow_redirects(mock_opensearch) is True

    @patch('socket.getaddrinfo')
    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_single_mode')
    def test_caller_url_refuses_redirects_when_guard_on(
        self, mock_get_region, mock_opensearch, mock_getaddrinfo
    ):
        os.environ['OPENSEARCH_URL'] = 'https://env-cluster.example.com'
        os.environ['OPENSEARCH_SSRF_GUARD'] = 'true'
        mock_get_region.return_value = 'us-east-1'
        mock_opensearch.return_value = Mock()
        mock_getaddrinfo.return_value = [(2, 1, 6, '', ('93.184.216.34', 443))]

        initialize_client(
            baseToolArgs(
                opensearch_cluster_name='',
                opensearch_url='https://caller.example.com',
                opensearch_no_auth=True,
            )
        )

        assert self._follow_redirects(mock_opensearch) is False


class TestSsrfGuard:
    """OPENSEARCH_SSRF_GUARD blocks caller URLs to non-public addresses."""

    def setup_method(self):
        os.environ.pop('OPENSEARCH_SSRF_GUARD', None)

    def teardown_method(self):
        os.environ.pop('OPENSEARCH_SSRF_GUARD', None)

    def _assert(self, url):
        from opensearch.client import _reject_caller_url_if_not_public

        _reject_caller_url_if_not_public(url)

    def test_disabled_by_default_allows_private(self):
        """Off by default: private-VPC and localhost clusters keep working."""
        self._assert('https://10.0.0.5:9200')  # no raise

    def test_enabled_rejects_non_https(self):
        os.environ['OPENSEARCH_SSRF_GUARD'] = 'true'
        with pytest.raises(ConfigurationError):
            self._assert('http://public.example.com')

    @patch('socket.getaddrinfo')
    def test_enabled_rejects_metadata_ip(self, mock_getaddrinfo):
        """169.254.169.254 (cloud metadata) is link-local and must be blocked."""
        os.environ['OPENSEARCH_SSRF_GUARD'] = 'true'
        mock_getaddrinfo.return_value = [(2, 1, 6, '', ('169.254.169.254', 443))]
        with pytest.raises(ConfigurationError):
            self._assert('https://metadata.attacker.example')

    @patch('socket.getaddrinfo')
    def test_enabled_rejects_private_resolution(self, mock_getaddrinfo):
        """A public name that resolves to a private IP is blocked (DNS evasion)."""
        os.environ['OPENSEARCH_SSRF_GUARD'] = 'true'
        mock_getaddrinfo.return_value = [(2, 1, 6, '', ('10.0.0.9', 443))]
        with pytest.raises(ConfigurationError):
            self._assert('https://internal.attacker.example')

    @patch('socket.getaddrinfo')
    def test_enabled_allows_public(self, mock_getaddrinfo):
        os.environ['OPENSEARCH_SSRF_GUARD'] = 'true'
        mock_getaddrinfo.return_value = [(2, 1, 6, '', ('93.184.216.34', 443))]
        self._assert('https://public.example.com')  # no raise

    @pytest.mark.parametrize(
        'address',
        [
            '64:ff9b::c0a8:101',  # NAT64-wrapped 192.168.1.1
            '64:ff9b::7f00:1',  # NAT64-wrapped 127.0.0.1
            '::ffff:192.168.1.1',  # IPv4-mapped private
        ],
    )
    @patch('socket.getaddrinfo')
    def test_enabled_rejects_ipv6_wrapped_private(self, mock_getaddrinfo, address):
        """An IPv4 private address wrapped in IPv6 is global as IPv6, so unwrap first."""
        os.environ['OPENSEARCH_SSRF_GUARD'] = 'true'
        mock_getaddrinfo.return_value = [(10, 1, 6, '', (address, 443))]
        with pytest.raises(ConfigurationError):
            self._assert('https://nat64.attacker.example')

    @pytest.mark.parametrize('address', ['239.255.255.250', 'ff02::1'])
    @patch('socket.getaddrinfo')
    def test_enabled_rejects_multicast(self, mock_getaddrinfo, address):
        """Multicast reaches local-network listeners and is_global does not exclude it."""
        os.environ['OPENSEARCH_SSRF_GUARD'] = 'true'
        family = 10 if ':' in address else 2
        mock_getaddrinfo.return_value = [(family, 1, 6, '', (address, 443))]
        with pytest.raises(ConfigurationError):
            self._assert('https://multicast.attacker.example')


class TestUrlParseErrorHidesSecrets:
    """A URL parse error must not echo the text it failed on."""

    @pytest.mark.parametrize(
        'url,secret',
        [
            ('https://user:supersecret', 'supersecret'),  # no @host: password is the port
            ('https://admin:hunter2', 'hunter2'),
            ('https://user:pw@host:notaport/x', 'pw'),
            ('https://user:pw@host:99999999999999/x', 'pw'),
        ],
    )
    def test_secret_absent_from_error(self, url, secret):
        from opensearch.client import _create_opensearch_client

        with pytest.raises(ConfigurationError) as excinfo:
            _create_opensearch_client(opensearch_url=url, caller_supplied_url=True)
        assert secret not in str(excinfo.value)


class TestAmbientAwsFallbackOptIn:
    """OPENSEARCH_ALLOW_AMBIENT_AWS_FALLBACK shares AWS credentials, nothing else.

    SigV4 signs each request, so a caller who names a URL gets no reusable secret.
    Basic auth, bearer tokens, and mTLS certs travel to the named host, so they are
    withheld from a caller-chosen URL even when the opt-in is on.
    """

    ENV = [
        'OPENSEARCH_URL',
        'OPENSEARCH_USERNAME',
        'OPENSEARCH_PASSWORD',
        'OPENSEARCH_HEADER_AUTH',
        'OPENSEARCH_CLIENT_CERT_PATH',
        'OPENSEARCH_CLIENT_KEY_PATH',
        'OPENSEARCH_ALLOW_AMBIENT_AWS_FALLBACK',
        'OPENSEARCH_DYNAMIC_CONNECTION',
        'AWS_PROFILE',
        'AWS_IAM_ARN',
    ]

    def setup_method(self):
        for key in self.ENV:
            os.environ.pop(key, None)
        os.environ['OPENSEARCH_URL'] = 'https://env-cluster.example.com'
        os.environ['OPENSEARCH_DYNAMIC_CONNECTION'] = 'true'
        from mcp_server_opensearch.global_state import set_mode

        set_mode('single')

    def teardown_method(self):
        for key in self.ENV:
            os.environ.pop(key, None)

    def _session(self, mock_boto_session):
        session = Mock()
        session.get_credentials.return_value = Mock(
            access_key='SERVER_KEY', secret_key='SERVER_SECRET', token=None
        )
        mock_boto_session.return_value = session
        return session

    def _caller_args(self, **kwargs):
        return baseToolArgs(
            opensearch_cluster_name='', opensearch_url='https://caller.example.com', **kwargs
        )

    @patch('opensearch.client.boto3.Session')
    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_single_mode')
    def test_off_by_default_still_refuses(self, mock_region, mock_opensearch, mock_boto_session):
        mock_region.return_value = 'us-east-1'
        self._session(mock_boto_session)

        with pytest.raises(AuthenticationError) as excinfo:
            initialize_client(self._caller_args())
        assert 'OPENSEARCH_ALLOW_AMBIENT_AWS_FALLBACK' in str(excinfo.value)

    @patch('opensearch.client.boto3.Session')
    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_single_mode')
    def test_enabled_signs_caller_url_with_server_credentials(
        self, mock_region, mock_opensearch, mock_boto_session
    ):
        os.environ['OPENSEARCH_ALLOW_AMBIENT_AWS_FALLBACK'] = 'true'
        mock_region.return_value = 'us-east-1'
        self._session(mock_boto_session)
        mock_opensearch.return_value = Mock()

        initialize_client(self._caller_args())

        call_kwargs = mock_opensearch.call_args[1]
        assert 'caller.example.com' in call_kwargs['hosts'][0]
        assert isinstance(call_kwargs['http_auth'], AWSV4SignerAsyncAuth)

    @patch('opensearch.client.boto3.Session')
    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_single_mode')
    def test_enabled_does_not_share_env_basic_auth(
        self, mock_region, mock_opensearch, mock_boto_session
    ):
        """The opt-in covers AWS only: env basic auth must not reach a caller URL."""
        os.environ['OPENSEARCH_ALLOW_AMBIENT_AWS_FALLBACK'] = 'true'
        os.environ['OPENSEARCH_USERNAME'] = 'env-user'
        os.environ['OPENSEARCH_PASSWORD'] = 'env-pass'
        mock_region.return_value = 'us-east-1'
        self._session(mock_boto_session)
        mock_opensearch.return_value = Mock()

        initialize_client(self._caller_args())

        call_kwargs = mock_opensearch.call_args[1]
        assert isinstance(call_kwargs['http_auth'], AWSV4SignerAsyncAuth)
        assert 'env-pass' not in str(call_kwargs)

    @patch('opensearch.client.boto3.Session')
    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_single_mode')
    def test_enabled_does_not_share_env_mtls_identity(
        self, mock_region, mock_opensearch, mock_boto_session
    ):
        os.environ['OPENSEARCH_ALLOW_AMBIENT_AWS_FALLBACK'] = 'true'
        mock_region.return_value = 'us-east-1'
        self._session(mock_boto_session)
        mock_opensearch.return_value = Mock()

        with tempfile.NamedTemporaryFile() as cert, tempfile.NamedTemporaryFile() as key:
            os.environ['OPENSEARCH_CLIENT_CERT_PATH'] = cert.name
            os.environ['OPENSEARCH_CLIENT_KEY_PATH'] = key.name

            initialize_client(self._caller_args())

        call_kwargs = mock_opensearch.call_args[1]
        assert 'client_cert' not in call_kwargs
        assert 'client_key' not in call_kwargs

    @patch('opensearch.client.request_context_var')
    @patch('opensearch.client.boto3.Session')
    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_single_mode')
    def test_enabled_does_not_share_env_bearer_token(
        self, mock_region, mock_opensearch, mock_boto_session, mock_request_ctx
    ):
        """A bearer token from headers belongs to its sender, not to an args URL."""
        from starlette.requests import Request

        os.environ['OPENSEARCH_ALLOW_AMBIENT_AWS_FALLBACK'] = 'true'
        os.environ['OPENSEARCH_HEADER_AUTH'] = 'true'
        mock_region.return_value = 'us-east-1'
        self._session(mock_boto_session)
        mock_opensearch.return_value = Mock()

        mock_request = Mock(spec=Request)
        mock_request.headers = {'authorization': 'Bearer proxy-token'}
        mock_request_ctx.get.return_value = mock_request

        initialize_client(self._caller_args())

        call_kwargs = mock_opensearch.call_args[1]
        assert isinstance(call_kwargs['http_auth'], AWSV4SignerAsyncAuth)
        assert 'proxy-token' not in str(call_kwargs)

    @patch('opensearch.client.boto3.Session')
    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_single_mode')
    def test_enabled_allows_env_iam_role_for_caller_url(
        self, mock_region, mock_opensearch, mock_boto_session
    ):
        """With the opt-in on, an env IAM role may be assumed for a caller URL."""
        os.environ['OPENSEARCH_ALLOW_AMBIENT_AWS_FALLBACK'] = 'true'
        os.environ['AWS_IAM_ARN'] = 'arn:aws:iam::123456789012:role/OpenSearchRole'
        mock_region.return_value = 'us-east-1'
        session = self._session(mock_boto_session)
        session.client.return_value.assume_role.return_value = {
            'Credentials': {
                'AccessKeyId': 'ASSUMED_KEY',
                'SecretAccessKey': 'ASSUMED_SECRET',
                'SessionToken': 'ASSUMED_TOKEN',
            }
        }
        mock_opensearch.return_value = Mock()

        initialize_client(self._caller_args())

        session.client.return_value.assume_role.assert_called_once()
        assert isinstance(mock_opensearch.call_args[1]['http_auth'], AWSV4SignerAsyncAuth)

    @patch('opensearch.client.request_context_var')
    @patch('opensearch.client.boto3.Session')
    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_single_mode')
    def test_enabled_signs_header_url_with_server_credentials(
        self, mock_region, mock_opensearch, mock_boto_session, mock_request_ctx
    ):
        """The opt-in covers header-supplied URLs too, which was the same hole."""
        from starlette.requests import Request

        os.environ['OPENSEARCH_ALLOW_AMBIENT_AWS_FALLBACK'] = 'true'
        os.environ['OPENSEARCH_HEADER_AUTH'] = 'true'
        mock_region.return_value = 'us-east-1'
        self._session(mock_boto_session)
        mock_opensearch.return_value = Mock()

        mock_request = Mock(spec=Request)
        mock_request.headers = {'opensearch-url': 'https://header-cluster.example.com'}
        mock_request_ctx.get.return_value = mock_request

        initialize_client(baseToolArgs(opensearch_cluster_name=''))

        call_kwargs = mock_opensearch.call_args[1]
        assert 'header-cluster.example.com' in call_kwargs['hosts'][0]
        assert isinstance(call_kwargs['http_auth'], AWSV4SignerAsyncAuth)

    @patch('opensearch.client.boto3.Session')
    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_single_mode')
    def test_enabled_keeps_failed_profile_fatal_for_caller_url(
        self, mock_region, mock_opensearch, mock_boto_session
    ):
        """A profile that cannot build must not degrade to the default identity.

        The default identity may be broader than the profile the operator chose, so
        signing a caller's URL with it would widen what the caller can reach.
        """
        os.environ['OPENSEARCH_ALLOW_AMBIENT_AWS_FALLBACK'] = 'true'
        os.environ['AWS_PROFILE'] = 'narrow-profile'
        mock_region.return_value = 'us-east-1'

        def session(**kwargs):
            if kwargs.get('profile_name'):
                raise Exception('ProfileNotFound')
            return Mock(get_credentials=Mock(return_value=Mock(access_key='BROAD')))

        mock_boto_session.side_effect = session

        with pytest.raises(AuthenticationError, match='requested profile'):
            initialize_client(self._caller_args())

    @patch('opensearch.client.boto3.Session')
    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_single_mode')
    def test_caller_basic_auth_still_wins_when_enabled(
        self, mock_region, mock_opensearch, mock_boto_session
    ):
        """The opt-in is a fallback: credentials in the call still take precedence."""
        os.environ['OPENSEARCH_ALLOW_AMBIENT_AWS_FALLBACK'] = 'true'
        mock_region.return_value = 'us-east-1'
        self._session(mock_boto_session)
        mock_opensearch.return_value = Mock()

        initialize_client(
            self._caller_args(opensearch_username='caller', opensearch_password='caller-pass')
        )

        assert mock_opensearch.call_args[1]['http_auth'] == ('caller', 'caller-pass')


class TestHeaderMultiDatasource:
    """Multi mode + header auth: the LLM selects a datasource by name.

    The server maps it to the aligned header URL and signs with one shared credential.
    """

    def setup_method(self):
        for key in ['OPENSEARCH_URL', 'AWS_REGION', 'OPENSEARCH_HEADER_AUTH']:
            os.environ.pop(key, None)
        os.environ['OPENSEARCH_HEADER_AUTH'] = 'true'
        from mcp_server_opensearch.global_state import set_mode

        set_mode('multi')

    def teardown_method(self):
        for key in [
            'OPENSEARCH_HEADER_AUTH',
            'OPENSEARCH_DYNAMIC_CONNECTION',
            'OPENSEARCH_SSRF_GUARD',
            'OPENSEARCH_ALLOW_AMBIENT_AWS_FALLBACK',
        ]:
            os.environ.pop(key, None)
        from mcp_server_opensearch.global_state import set_mode

        set_mode('single')

    def _ctx(self, mock_request_ctx, headers):
        from starlette.requests import Request

        mock_request = Mock(spec=Request)
        mock_request.headers = headers
        mock_request_ctx.get.return_value = mock_request

    def _headers(self):
        return {
            'opensearch-url': 'https://logs.example.com,https://metrics.example.com',
            'opensearch-cluster-name': 'logs,metrics',
            'aws-service-name': 'es,aoss',
            'aws-region': 'us-east-1,us-west-2',
            'aws-access-key-id': 'AKIASHARED',
            'aws-secret-access-key': 'shared-secret',
            'aws-session-token': 'shared-token',
        }

    @patch('opensearch.client._create_opensearch_client')
    @patch('opensearch.client.request_context_var')
    def test_selects_datasource_by_name_with_shared_credential(
        self, mock_request_ctx, mock_create
    ):
        """opensearch_cluster_name maps to a header URL; shared creds sign it."""
        self._ctx(mock_request_ctx, self._headers())
        mock_create.return_value = Mock()

        initialize_client(baseToolArgs(opensearch_cluster_name='logs'))

        kwargs = mock_create.call_args[1]
        assert kwargs['opensearch_url'] == 'https://logs.example.com'
        assert kwargs['is_serverless_mode'] is False
        assert kwargs['aws_region'] == 'us-east-1'
        assert kwargs['aws_access_key_id'] == 'AKIASHARED'
        assert kwargs['aws_session_token'] == 'shared-token'

    @patch('opensearch.client._create_opensearch_client')
    @patch('opensearch.client.request_context_var')
    def test_selected_name_uses_aligned_service_and_region(self, mock_request_ctx, mock_create):
        """The aligned aws-service-name (aoss) and aws-region entries follow the chosen name."""
        self._ctx(mock_request_ctx, self._headers())
        mock_create.return_value = Mock()

        initialize_client(baseToolArgs(opensearch_cluster_name='metrics'))

        kwargs = mock_create.call_args[1]
        assert kwargs['opensearch_url'] == 'https://metrics.example.com'
        assert kwargs['is_serverless_mode'] is True
        assert kwargs['aws_region'] == 'us-west-2'
        assert kwargs['aws_access_key_id'] == 'AKIASHARED'

    @patch('opensearch.client._create_opensearch_client')
    @patch('opensearch.client.request_context_var')
    def test_works_without_dynamic_connection_flag(self, mock_request_ctx, mock_create):
        """Name selection needs no OPENSEARCH_DYNAMIC_CONNECTION: the LLM supplies no URL override."""
        os.environ.pop('OPENSEARCH_DYNAMIC_CONNECTION', None)
        self._ctx(mock_request_ctx, self._headers())
        mock_create.return_value = Mock()

        initialize_client(baseToolArgs(opensearch_cluster_name='metrics'))

        kwargs = mock_create.call_args[1]
        assert kwargs['opensearch_url'] == 'https://metrics.example.com'

    @patch('opensearch.client._create_opensearch_client')
    @patch('opensearch.client.request_context_var')
    def test_single_datasource_via_name(self, mock_request_ctx, mock_create):
        """One URL with one name is selectable by that name (single-datasource in multi mode)."""
        self._ctx(
            mock_request_ctx,
            {
                'opensearch-url': 'https://only.example.com',
                'opensearch-cluster-name': 'only',
                'aws-region': 'us-east-1',
                'aws-access-key-id': 'AKIASHARED',
                'aws-secret-access-key': 'shared-secret',
                'aws-session-token': 'shared-token',
            },
        )
        mock_create.return_value = Mock()

        initialize_client(baseToolArgs(opensearch_cluster_name='only'))

        kwargs = mock_create.call_args[1]
        assert kwargs['opensearch_url'] == 'https://only.example.com'
        assert kwargs['aws_region'] == 'us-east-1'

    @patch('opensearch.client._create_opensearch_client')
    @patch('opensearch.client.request_context_var')
    def test_missing_name_arg_errors_and_lists_available(self, mock_request_ctx, mock_create):
        self._ctx(mock_request_ctx, self._headers())

        with pytest.raises(ConfigurationError, match='required to select one'):
            initialize_client(baseToolArgs(opensearch_cluster_name=''))
        mock_create.assert_not_called()

    @patch('opensearch.client._create_opensearch_client')
    @patch('opensearch.client.request_context_var')
    def test_single_datasource_auto_selects_without_name(self, mock_request_ctx, mock_create):
        """One datasource needs no explicit name; an empty arg selects it."""
        self._ctx(
            mock_request_ctx,
            {
                'opensearch-url': 'https://only.example.com',
                'opensearch-cluster-name': 'only',
                'aws-region': 'us-east-1',
                'aws-access-key-id': 'AKIASHARED',
                'aws-secret-access-key': 'shared-secret',
                'aws-session-token': 'shared-token',
            },
        )
        mock_create.return_value = Mock()

        initialize_client(baseToolArgs(opensearch_cluster_name=''))

        kwargs = mock_create.call_args[1]
        assert kwargs['opensearch_url'] == 'https://only.example.com'

    @patch('opensearch.client._create_opensearch_client')
    @patch('opensearch.client.request_context_var')
    def test_name_not_configured_errors(self, mock_request_ctx, mock_create):
        self._ctx(mock_request_ctx, self._headers())

        with pytest.raises(ConfigurationError, match='not among the configured datasources'):
            initialize_client(baseToolArgs(opensearch_cluster_name='traces'))
        mock_create.assert_not_called()

    @patch('opensearch.client._create_opensearch_client')
    @patch('opensearch.client.request_context_var')
    def test_name_count_mismatch_errors(self, mock_request_ctx, mock_create, caplog):
        """A name list that does not align 1:1 with the URL list is rejected."""
        headers = self._headers()
        headers['opensearch-cluster-name'] = 'logs'  # 1 name for 2 urls
        self._ctx(mock_request_ctx, headers)

        with caplog.at_level(logging.ERROR):
            with pytest.raises(ConfigurationError, match='No OpenSearch datasource is available'):
                initialize_client(baseToolArgs(opensearch_cluster_name='logs'))
        assert 'opensearch-cluster-name header has 1 values' in caplog.text
        mock_create.assert_not_called()

    @patch('opensearch.client._create_opensearch_client')
    @patch('opensearch.client.request_context_var')
    def test_duplicate_names_error(self, mock_request_ctx, mock_create, caplog):
        headers = self._headers()
        headers['opensearch-cluster-name'] = 'logs,logs'
        self._ctx(mock_request_ctx, headers)

        with caplog.at_level(logging.ERROR):
            with pytest.raises(ConfigurationError, match='No OpenSearch datasource is available'):
                initialize_client(baseToolArgs(opensearch_cluster_name='logs'))
        assert 'Duplicate datasource names' in caplog.text
        mock_create.assert_not_called()

    @patch('opensearch.client._create_opensearch_client')
    @patch('opensearch.client.request_context_var')
    def test_region_length_mismatch_errors(self, mock_request_ctx, mock_create, caplog):
        """A region list that is neither length 1 nor N is rejected, not silently defaulted."""
        headers = self._headers()
        headers['aws-region'] = 'us-east-1,us-west-2,eu-west-1'  # 3 for 2 urls
        self._ctx(mock_request_ctx, headers)

        with caplog.at_level(logging.ERROR):
            with pytest.raises(ConfigurationError, match='No OpenSearch datasource is available'):
                initialize_client(baseToolArgs(opensearch_cluster_name='logs'))
        assert 'aws-region header has 3 values' in caplog.text
        mock_create.assert_not_called()

    @patch('opensearch.client._create_opensearch_client')
    @patch('opensearch.client.request_context_var')
    def test_single_service_for_multiple_errors(self, mock_request_ctx, mock_create, caplog):
        """One aws-service-name value for N datasources is rejected; each must be explicit."""
        headers = self._headers()
        headers['aws-service-name'] = 'aoss'  # 1 for 2 urls
        self._ctx(mock_request_ctx, headers)

        with caplog.at_level(logging.ERROR):
            with pytest.raises(ConfigurationError, match='No OpenSearch datasource is available'):
                initialize_client(baseToolArgs(opensearch_cluster_name='logs'))
        assert 'aws-service-name header has 1 values' in caplog.text
        mock_create.assert_not_called()

    @patch('opensearch.client._create_opensearch_client')
    @patch('opensearch.client.request_context_var')
    def test_get_header_cluster_names_returns_names(self, mock_request_ctx, mock_create):
        """Discovery: names come from the opensearch-cluster-name header for the request."""
        from opensearch.client import get_header_cluster_names

        self._ctx(mock_request_ctx, self._headers())
        assert get_header_cluster_names() == ['logs', 'metrics']

    @patch('opensearch.client._create_opensearch_client')
    @patch('opensearch.client.request_context_var')
    def test_missing_name_header_uses_placeholders(self, mock_request_ctx, mock_create):
        """When opensearch-cluster-name is omitted, names default to cluster1..clusterN."""
        from opensearch.client import get_header_cluster_names

        headers = self._headers()
        del headers['opensearch-cluster-name']
        self._ctx(mock_request_ctx, headers)
        mock_create.return_value = Mock()

        assert get_header_cluster_names() == ['cluster1', 'cluster2']
        initialize_client(baseToolArgs(opensearch_cluster_name='cluster2'))

        kwargs = mock_create.call_args[1]
        assert kwargs['opensearch_url'] == 'https://metrics.example.com'
        assert kwargs['is_serverless_mode'] is True
        assert kwargs['aws_region'] == 'us-west-2'

    @patch('opensearch.client._create_opensearch_client')
    @patch('opensearch.client.request_context_var')
    def test_missing_url_header_errors_clearly(self, mock_request_ctx, mock_create):
        """Header auth on but no opensearch-url header gives a clear error, not an opaque one."""
        from opensearch.client import get_header_cluster_names

        self._ctx(mock_request_ctx, {'aws-region': 'us-east-1'})

        with pytest.raises(ConfigurationError, match='No OpenSearch datasource is available'):
            get_header_cluster_names()
        with pytest.raises(ConfigurationError, match='No OpenSearch datasource is available'):
            initialize_client(baseToolArgs(opensearch_cluster_name='logs'))
        mock_create.assert_not_called()

    @patch('opensearch.client._create_opensearch_client')
    @patch('opensearch.client.request_context_var')
    def test_header_url_is_caller_supplied_and_forbids_ambient(
        self, mock_request_ctx, mock_create
    ):
        """A header-derived URL gets the same caller-supplied/ambient protections as single mode."""
        self._ctx(mock_request_ctx, self._headers())
        mock_create.return_value = Mock()

        initialize_client(baseToolArgs(opensearch_cluster_name='logs'))

        kwargs = mock_create.call_args[1]
        assert kwargs['caller_supplied_url'] is True
        assert kwargs['forbid_ambient_fallback'] is True

    @patch('opensearch.client._create_opensearch_client')
    @patch('opensearch.client.request_context_var')
    def test_header_url_ssrf_guard_rejects_private(self, mock_request_ctx, mock_create):
        """With the SSRF guard on, a header URL resolving to a non-public address is rejected."""
        os.environ['OPENSEARCH_SSRF_GUARD'] = 'true'
        self._ctx(
            mock_request_ctx,
            {
                'opensearch-url': 'https://127.0.0.1',
                'opensearch-cluster-name': 'local',
                'aws-region': 'us-east-1',
                'aws-access-key-id': 'AKIASHARED',
                'aws-secret-access-key': 'shared-secret',
                'aws-session-token': 'shared-token',
            },
        )

        with pytest.raises(ConfigurationError, match='non-public address'):
            initialize_client(baseToolArgs(opensearch_cluster_name='local'))
        mock_create.assert_not_called()


class TestHeaderSingleDatasource:
    """Single mode + header auth: one datasource, URL/service/region from scalar headers."""

    def setup_method(self):
        for key in ['OPENSEARCH_URL', 'AWS_REGION', 'OPENSEARCH_HEADER_AUTH']:
            os.environ.pop(key, None)
        os.environ['OPENSEARCH_HEADER_AUTH'] = 'true'
        from mcp_server_opensearch.global_state import set_mode

        set_mode('single')

    def teardown_method(self):
        os.environ.pop('OPENSEARCH_HEADER_AUTH', None)

    def _ctx(self, mock_request_ctx, headers):
        from starlette.requests import Request

        mock_request = Mock(spec=Request)
        mock_request.headers = headers
        mock_request_ctx.get.return_value = mock_request

    @patch('opensearch.client._create_opensearch_client')
    @patch('opensearch.client.request_context_var')
    def test_scalar_url_from_header(self, mock_request_ctx, mock_create):
        """A scalar opensearch-url header drives the single-mode connection; no name needed."""
        self._ctx(
            mock_request_ctx,
            {
                'opensearch-url': 'https://only.example.com',
                'aws-region': 'us-east-1',
                'aws-access-key-id': 'AKIASHARED',
                'aws-secret-access-key': 'shared-secret',
                'aws-session-token': 'shared-token',
            },
        )
        mock_create.return_value = Mock()

        initialize_client(baseToolArgs(opensearch_cluster_name=''))

        kwargs = mock_create.call_args[1]
        assert kwargs['opensearch_url'] == 'https://only.example.com'
        assert kwargs['aws_region'] == 'us-east-1'
