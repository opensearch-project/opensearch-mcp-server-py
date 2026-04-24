# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import boto3
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
from urllib.parse import urlparse


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
    @patch('opensearch.client.request_ctx')
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

        # Mock request context
        mock_context = Mock()
        mock_context.request = mock_request
        mock_request_ctx.get.return_value = mock_context

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
    @patch('opensearch.client.request_ctx')
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

        # Mock request context
        mock_context = Mock()
        mock_context.request = mock_request
        mock_request_ctx.get.return_value = mock_context

        # Mock OpenSearch client
        mock_client = Mock()
        mock_opensearch.return_value = mock_client

        # Execute
        client = initialize_client(baseToolArgs(opensearch_cluster_name=''))

        # Assert - header credentials should be used, not env var credentials
        assert client == mock_client
        call_kwargs = mock_opensearch.call_args[1]
        assert call_kwargs['http_auth'] == (header_username, header_password)

    @patch('opensearch.client.request_ctx')
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

        # Mock request context
        mock_context = Mock()
        mock_context.request = mock_request
        mock_request_ctx.get.return_value = mock_context

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

    @patch('opensearch.client.request_ctx')
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

        # Mock request context
        mock_context = Mock()
        mock_context.request = mock_request
        mock_request_ctx.get.return_value = mock_context

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

    @patch('opensearch.client.request_ctx')
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

        # Mock request context
        mock_context = Mock()
        mock_context.request = mock_request
        mock_request_ctx.get.return_value = mock_context

        # Mock OpenSearch client
        mock_client = Mock()
        mock_opensearch.return_value = mock_client

        # Execute
        client = initialize_client(baseToolArgs(opensearch_cluster_name=''))

        # Assert - should fall back to env var credentials
        assert client == mock_client
        call_kwargs = mock_opensearch.call_args[1]
        assert call_kwargs['http_auth'] == ('env-user', 'env-password')

    @patch('opensearch.client.request_ctx')
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

        # Mock request context
        mock_context = Mock()
        mock_context.request = mock_request
        mock_request_ctx.get.return_value = mock_context

        # Mock OpenSearch client
        mock_client = Mock()
        mock_opensearch.return_value = mock_client

        # Execute
        client = initialize_client(baseToolArgs(opensearch_cluster_name=''))

        # Assert - should fall back to env var credentials since format is invalid
        assert client == mock_client
        call_kwargs = mock_opensearch.call_args[1]
        assert call_kwargs['http_auth'] == ('env-user', 'env-password')


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
