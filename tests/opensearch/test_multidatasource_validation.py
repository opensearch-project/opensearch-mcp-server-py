# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for multi-datasource validation functions."""

import pytest
from unittest.mock import Mock, patch

from opensearch.client import (
    _get_allowed_datasources_from_headers,
    _normalize_opensearch_url,
    _validate_opensearch_url,
    AuthenticationError,
)


class TestGetAllowedDatasourcesFromHeaders:
    """Tests for _get_allowed_datasources_from_headers()."""

    @patch('opensearch.client.request_context_var')
    def test_legacy_single_header(self, mock_request_ctx):
        """Test extraction of single non-indexed opensearch-url header."""
        from starlette.requests import Request

        mock_request = Mock(spec=Request)
        mock_request.headers = {
            'opensearch-url': 'https://domain1.us-west-2.es.amazonaws.com'
        }

        mock_request_ctx.get.return_value = mock_request

        result = _get_allowed_datasources_from_headers()

        assert result == ['https://domain1.us-west-2.es.amazonaws.com']

    @patch('opensearch.client.request_context_var')
    def test_indexed_multiple_headers(self, mock_request_ctx):
        """Test extraction of multiple indexed opensearch-url headers."""
        from starlette.requests import Request

        mock_request = Mock(spec=Request)
        mock_request.headers = {
            'opensearch-url-0': 'https://domain1.us-west-2.es.amazonaws.com',
            'opensearch-url-1': 'https://collection1.us-east-1.aoss.amazonaws.com',
            'opensearch-url-2': 'https://domain2.eu-west-1.es.amazonaws.com',
        }

        mock_request_ctx.get.return_value = mock_request

        result = _get_allowed_datasources_from_headers()

        assert result == [
            'https://domain1.us-west-2.es.amazonaws.com',
            'https://collection1.us-east-1.aoss.amazonaws.com',
            'https://domain2.eu-west-1.es.amazonaws.com',
        ]

    @patch('opensearch.client.request_context_var')
    def test_indexed_headers_with_gaps_stops_at_first_gap(self, mock_request_ctx):
        """Test that extraction stops at the first missing index."""
        from starlette.requests import Request

        mock_request = Mock(spec=Request)
        mock_request.headers = {
            'opensearch-url-0': 'https://domain1.us-west-2.es.amazonaws.com',
            'opensearch-url-1': 'https://collection1.us-east-1.aoss.amazonaws.com',
            # Missing index 2
            'opensearch-url-3': 'https://domain3.eu-west-1.es.amazonaws.com',  # Should not be extracted
        }

        mock_request_ctx.get.return_value = mock_request

        result = _get_allowed_datasources_from_headers()

        # Should only get 0 and 1, not 3
        assert result == [
            'https://domain1.us-west-2.es.amazonaws.com',
            'https://collection1.us-east-1.aoss.amazonaws.com',
        ]

    @patch('opensearch.client.request_context_var')
    def test_no_headers_returns_empty_list(self, mock_request_ctx):
        """Test that no headers returns empty list."""
        from starlette.requests import Request

        mock_request = Mock(spec=Request)
        mock_request.headers = {}

        mock_request_ctx.get.return_value = mock_request

        result = _get_allowed_datasources_from_headers()

        assert result == []

    @patch('opensearch.client.request_context_var')
    def test_empty_header_value_returns_empty_list(self, mock_request_ctx):
        """Test that empty header value returns empty list."""
        from starlette.requests import Request

        mock_request = Mock(spec=Request)
        mock_request.headers = {'opensearch-url': '   '}  # Just whitespace

        mock_request_ctx.get.return_value = mock_request

        result = _get_allowed_datasources_from_headers()

        assert result == []

    @patch('opensearch.client.request_context_var')
    def test_no_request_context_returns_empty_list(self, mock_request_ctx):
        """Test that no request context returns empty list."""
        mock_request_ctx.get.return_value = None

        result = _get_allowed_datasources_from_headers()

        assert result == []


class TestNormalizeOpensearchUrl:
    """Tests for _normalize_opensearch_url()."""

    def test_lowercase_conversion(self):
        """Test that URLs are converted to lowercase."""
        url = 'HTTPS://DOMAIN.COM/PATH'
        result = _normalize_opensearch_url(url)
        assert result == 'https://domain.com/path'

    def test_trailing_slash_removal(self):
        """Test that trailing slashes are removed."""
        url = 'https://domain.com/'
        result = _normalize_opensearch_url(url)
        assert result == 'https://domain.com'

    def test_multiple_trailing_slashes_removed(self):
        """Test that multiple trailing slashes are removed."""
        url = 'https://domain.com///'
        result = _normalize_opensearch_url(url)
        assert result == 'https://domain.com'

    def test_adds_https_prefix_when_missing(self):
        """Test that https:// is added when no protocol is specified."""
        url = 'domain.com'
        result = _normalize_opensearch_url(url)
        assert result == 'https://domain.com'

    def test_preserves_http_protocol(self):
        """Test that http:// protocol is preserved."""
        url = 'http://domain.com'
        result = _normalize_opensearch_url(url)
        assert result == 'http://domain.com'

    def test_preserves_https_protocol(self):
        """Test that https:// protocol is preserved."""
        url = 'https://domain.com'
        result = _normalize_opensearch_url(url)
        assert result == 'https://domain.com'

    def test_empty_string_returns_empty(self):
        """Test that empty string returns empty string."""
        result = _normalize_opensearch_url('')
        assert result == ''

    def test_none_returns_empty(self):
        """Test that None returns empty string."""
        result = _normalize_opensearch_url(None)
        assert result == ''

    def test_whitespace_trimmed(self):
        """Test that leading/trailing whitespace is trimmed."""
        url = '  https://domain.com  '
        result = _normalize_opensearch_url(url)
        assert result == 'https://domain.com'

    def test_path_preserved(self):
        """Test that URL paths are preserved."""
        url = 'https://domain.com/path/to/resource'
        result = _normalize_opensearch_url(url)
        assert result == 'https://domain.com/path/to/resource'

    def test_port_preserved(self):
        """Test that port numbers are preserved."""
        url = 'https://domain.com:9200'
        result = _normalize_opensearch_url(url)
        assert result == 'https://domain.com:9200'


class TestValidateOpensearchUrl:
    """Tests for _validate_opensearch_url()."""

    def test_validation_success_exact_match(self):
        """Test that validation succeeds with exact URL match."""
        requested = 'https://domain.us-west-2.es.amazonaws.com'
        allowed = ['https://domain.us-west-2.es.amazonaws.com']

        # Should not raise
        _validate_opensearch_url(requested, allowed)

    def test_validation_success_case_insensitive(self):
        """Test that validation succeeds with different case."""
        requested = 'HTTPS://DOMAIN.US-WEST-2.ES.AMAZONAWS.COM'
        allowed = ['https://domain.us-west-2.es.amazonaws.com']

        # Should not raise (normalized comparison)
        _validate_opensearch_url(requested, allowed)

    def test_validation_success_trailing_slash_ignored(self):
        """Test that validation succeeds ignoring trailing slashes."""
        requested = 'https://domain.com/'
        allowed = ['https://domain.com']

        # Should not raise (normalized comparison)
        _validate_opensearch_url(requested, allowed)

    def test_validation_success_multiple_allowed_urls(self):
        """Test that validation succeeds when URL is in allowlist."""
        requested = 'https://domain2.com'
        allowed = [
            'https://domain1.com',
            'https://domain2.com',
            'https://domain3.com',
        ]

        # Should not raise
        _validate_opensearch_url(requested, allowed)

    def test_validation_failure_not_in_allowlist(self):
        """Test that validation fails when URL is not in allowlist."""
        requested = 'https://unauthorized.com'
        allowed = ['https://domain1.com', 'https://domain2.com']

        with pytest.raises(AuthenticationError) as exc_info:
            _validate_opensearch_url(requested, allowed)

        assert 'not authorized' in str(exc_info.value)
        assert 'unauthorized.com' in str(exc_info.value)

    def test_validation_failure_empty_allowlist(self):
        """Test that validation fails when allowlist is empty."""
        requested = 'https://domain.com'
        allowed = []

        with pytest.raises(AuthenticationError) as exc_info:
            _validate_opensearch_url(requested, allowed)

        assert 'No datasources are authorized' in str(exc_info.value)

    def test_validation_failure_empty_requested_url(self):
        """Test that validation fails when requested URL is empty."""
        requested = ''
        allowed = ['https://domain.com']

        with pytest.raises(AuthenticationError) as exc_info:
            _validate_opensearch_url(requested, allowed)

        assert 'OpenSearch URL is required' in str(exc_info.value)

    def test_validation_failure_none_requested_url(self):
        """Test that validation fails when requested URL is None."""
        requested = None
        allowed = ['https://domain.com']

        with pytest.raises(AuthenticationError) as exc_info:
            _validate_opensearch_url(requested, allowed)

        assert 'OpenSearch URL is required' in str(exc_info.value)

    def test_validation_with_protocol_mismatch_normalized(self):
        """Test validation with protocol differences (normalized)."""
        # Both should be normalized to https://
        requested = 'domain.com'  # Will be normalized to https://domain.com
        allowed = ['https://domain.com']

        # Should not raise
        _validate_opensearch_url(requested, allowed)


class TestMultiDatasourceIntegration:
    """Integration tests for multi-datasource header auth flow."""

    def setup_method(self):
        """Setup before each test."""
        import os
        # Clear environment variables
        for key in ['OPENSEARCH_URL', 'OPENSEARCH_HEADER_AUTH', 'AWS_REGION']:
            if key in os.environ:
                del os.environ[key]

        from mcp_server_opensearch.global_state import set_mode
        set_mode('single')

    @patch('opensearch.client.request_context_var')
    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_single_mode')
    def test_single_mode_with_validation_success(
        self, mock_get_region, mock_opensearch, mock_request_ctx
    ):
        """Test single mode with header auth and successful validation."""
        import os
        from starlette.requests import Request
        from opensearch.client import initialize_client
        from tools.tool_params import baseToolArgs

        # Enable header auth
        os.environ['OPENSEARCH_HEADER_AUTH'] = 'true'

        # Mock request with datasource headers
        mock_request = Mock(spec=Request)
        mock_request.headers = {
            'opensearch-url': 'https://allowed-domain.com',
            'aws-access-key-id': 'test-key',
            'aws-secret-access-key': 'test-secret',
            'aws-session-token': 'test-token',
            'aws-region': 'us-west-2',
            'aws-service-name': 'es',
        }

        mock_request_ctx.get.return_value = mock_request

        mock_get_region.return_value = 'us-west-2'
        mock_client = Mock()
        mock_opensearch.return_value = mock_client

        # Should succeed - URL matches allowlist
        client = initialize_client(baseToolArgs(opensearch_cluster_name=''))
        assert client == mock_client

    @patch('opensearch.client.request_context_var')
    def test_single_mode_with_validation_failure(self, mock_request_ctx):
        """Test single mode with header auth and failed validation."""
        import os
        from starlette.requests import Request
        from opensearch.client import initialize_client
        from tools.tool_params import baseToolArgs

        # Enable header auth
        os.environ['OPENSEARCH_HEADER_AUTH'] = 'true'

        # Mock request - requesting URL not in allowlist
        mock_request = Mock(spec=Request)
        mock_request.headers = {
            'opensearch-url-0': 'https://allowed-domain.com',  # Allowlist
            'opensearch-url-1': 'https://another-allowed.com',  # Allowlist
            'opensearch-url': 'https://unauthorized-domain.com',  # Requested (legacy format)
            'aws-access-key-id': 'test-key',
            'aws-secret-access-key': 'test-secret',
            'aws-session-token': 'test-token',
        }

        mock_request_ctx.get.return_value = mock_request

        # Should fail - requested URL not in allowlist
        with pytest.raises(AuthenticationError) as exc_info:
            initialize_client(baseToolArgs(opensearch_cluster_name=''))

        assert 'not authorized' in str(exc_info.value)

    @patch('opensearch.client.request_context_var')
    @patch('opensearch.client.AsyncOpenSearch')
    @patch('opensearch.client.get_aws_region_single_mode')
    def test_multi_datasource_headers_indexed_format(
        self, mock_get_region, mock_opensearch, mock_request_ctx
    ):
        """Test with multiple indexed datasource headers."""
        import os
        from starlette.requests import Request
        from opensearch.client import initialize_client
        from tools.tool_params import baseToolArgs

        # Enable header auth
        os.environ['OPENSEARCH_HEADER_AUTH'] = 'true'

        # Mock request with indexed headers for allowlist + requested URL
        mock_request = Mock(spec=Request)
        mock_request.headers = {
            # Allowlist (indexed headers)
            'opensearch-url-0': 'https://domain1.com',
            'opensearch-url-1': 'https://domain2.com',
            # Requested URL (non-indexed header)
            'opensearch-url': 'https://domain1.com',  # Request domain1 from allowlist
            'aws-region': 'us-west-2',
            'aws-service-name': 'es',
            'aws-access-key-id': 'test-key',
            'aws-secret-access-key': 'test-secret',
        }

        mock_request_ctx.get.return_value = mock_request

        mock_get_region.return_value = 'us-west-2'
        mock_client = Mock()
        mock_opensearch.return_value = mock_client

        # Should succeed - domain1.com is in allowlist
        client = initialize_client(baseToolArgs(opensearch_cluster_name=''))
        assert client == mock_client
