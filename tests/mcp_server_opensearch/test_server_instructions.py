# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for server instructions and conditional schema stripping."""

import os
import pytest
from unittest.mock import MagicMock, patch


class TestHasPreconfiguredConnection:
    """Tests for has_preconfigured_connection across single and multi mode."""

    def setup_method(self):
        """Save and clear relevant env vars and cluster registry."""
        self._original_url = os.environ.get('OPENSEARCH_URL')
        os.environ.pop('OPENSEARCH_URL', None)

    def teardown_method(self):
        """Restore env and clear cluster registry."""
        if self._original_url is not None:
            os.environ['OPENSEARCH_URL'] = self._original_url
        else:
            os.environ.pop('OPENSEARCH_URL', None)
        # Clear cluster registry
        from mcp_server_opensearch.clusters_information import cluster_registry

        cluster_registry.clear()

    def test_true_when_opensearch_url_set(self):
        """Returns True when OPENSEARCH_URL env var is set."""
        os.environ['OPENSEARCH_URL'] = 'https://cluster.example.com'
        from mcp_server_opensearch.server_instructions import has_preconfigured_connection

        assert has_preconfigured_connection() is True

    def test_false_when_nothing_configured(self):
        """Returns False when no URL and no clusters loaded."""
        from mcp_server_opensearch.server_instructions import has_preconfigured_connection

        assert has_preconfigured_connection() is False

    def test_false_when_url_is_whitespace(self):
        """Whitespace-only OPENSEARCH_URL is treated as not configured."""
        os.environ['OPENSEARCH_URL'] = '   '
        from mcp_server_opensearch.server_instructions import has_preconfigured_connection

        assert has_preconfigured_connection() is False

    def test_true_when_clusters_loaded(self):
        """Returns True when clusters are in the registry (multi mode with YAML)."""
        from mcp_server_opensearch.clusters_information import ClusterInfo, add_cluster
        from mcp_server_opensearch.server_instructions import has_preconfigured_connection

        add_cluster('test', ClusterInfo(opensearch_url='https://cluster.example.com'))
        assert has_preconfigured_connection() is True

    def test_true_when_both_url_and_clusters(self):
        """Returns True when both URL and clusters are configured."""
        os.environ['OPENSEARCH_URL'] = 'https://cluster.example.com'
        from mcp_server_opensearch.clusters_information import ClusterInfo, add_cluster
        from mcp_server_opensearch.server_instructions import has_preconfigured_connection

        add_cluster('test', ClusterInfo(opensearch_url='https://other.example.com'))
        assert has_preconfigured_connection() is True


class TestGetServerInstructions:
    """Tests for get_server_instructions based on configuration state."""

    def setup_method(self):
        """Save and clear OPENSEARCH_URL and cluster registry."""
        self._original = os.environ.get('OPENSEARCH_URL')
        os.environ.pop('OPENSEARCH_URL', None)
        from mcp_server_opensearch.clusters_information import cluster_registry

        cluster_registry.clear()

    def teardown_method(self):
        """Restore env and clear cluster registry."""
        if self._original is not None:
            os.environ['OPENSEARCH_URL'] = self._original
        else:
            os.environ.pop('OPENSEARCH_URL', None)
        from mcp_server_opensearch.clusters_information import cluster_registry

        cluster_registry.clear()

    def test_returns_instructions_when_nothing_configured(self):
        """When no URL and no clusters, instructions are returned."""
        from mcp_server_opensearch.server_instructions import get_server_instructions

        result = get_server_instructions()
        assert result is not None
        assert 'opensearch_url' in result

    def test_returns_none_when_url_configured(self):
        """When OPENSEARCH_URL is set, no instructions needed."""
        os.environ['OPENSEARCH_URL'] = 'https://my-cluster.example.com'
        from mcp_server_opensearch.server_instructions import get_server_instructions

        assert get_server_instructions() is None

    def test_returns_none_when_clusters_loaded(self):
        """When clusters are loaded from YAML, no instructions needed."""
        from mcp_server_opensearch.clusters_information import ClusterInfo, add_cluster
        from mcp_server_opensearch.server_instructions import get_server_instructions

        add_cluster('prod', ClusterInfo(opensearch_url='https://prod.example.com'))
        assert get_server_instructions() is None

    def test_instructions_mention_key_parameters(self):
        """Instructions should mention the key connection parameters."""
        from mcp_server_opensearch.server_instructions import get_server_instructions

        result = get_server_instructions()
        for param in ['opensearch_url', 'aws_region', 'aws_profile', 'opensearch_username']:
            assert param in result


class TestConditionalSchemaStripping:
    """Tests that tool schemas are conditionally stripped based on configuration."""

    def setup_method(self):
        """Set single mode, save env, clear cluster registry."""
        from mcp_server_opensearch.global_state import set_mode

        set_mode('single')
        self._original = os.environ.get('OPENSEARCH_URL')
        from mcp_server_opensearch.clusters_information import cluster_registry

        cluster_registry.clear()

    def teardown_method(self):
        """Restore env and clear cluster registry."""
        if self._original is not None:
            os.environ['OPENSEARCH_URL'] = self._original
        else:
            os.environ.pop('OPENSEARCH_URL', None)
        from mcp_server_opensearch.clusters_information import cluster_registry

        cluster_registry.clear()

    def _make_registry(self):
        """Create a mock tool registry with override fields in schema."""
        return {
            'ListIndexTool': {
                'display_name': 'ListIndexTool',
                'description': 'List indices',
                'input_schema': {
                    'type': 'object',
                    'properties': {
                        'opensearch_cluster_name': {'type': 'string'},
                        'opensearch_url': {'type': 'string'},
                        'aws_region': {'type': 'string'},
                        'aws_profile': {'type': 'string'},
                        'index': {'type': 'string'},
                    },
                },
                'function': MagicMock(),
                'args_model': MagicMock(),
                'min_version': '1.0.0',
            }
        }

    @pytest.mark.asyncio
    async def test_single_mode_url_configured_strips_overrides(self):
        """Single mode with OPENSEARCH_URL strips override fields."""
        os.environ['OPENSEARCH_URL'] = 'https://cluster.example.com'
        from tools.tool_filter import get_tools

        with patch('tools.tool_filter.get_opensearch_version', return_value=None):
            with patch('tools.tool_filter.is_tool_compatible', return_value=True):
                result = await get_tools(self._make_registry())

        props = result['ListIndexTool']['input_schema']['properties']
        assert 'index' in props
        assert 'opensearch_url' not in props
        assert 'aws_region' not in props
        assert 'opensearch_cluster_name' not in props

    @pytest.mark.asyncio
    async def test_single_mode_no_config_keeps_overrides(self):
        """Single mode with no URL keeps override fields for dynamic use."""
        os.environ.pop('OPENSEARCH_URL', None)
        from tools.tool_filter import get_tools

        with patch('tools.tool_filter.get_opensearch_version', return_value=None):
            with patch('tools.tool_filter.is_tool_compatible', return_value=True):
                result = await get_tools(self._make_registry())

        props = result['ListIndexTool']['input_schema']['properties']
        assert 'index' in props
        assert 'opensearch_url' in props
        assert 'aws_region' in props
        assert 'opensearch_cluster_name' not in props

    @pytest.mark.asyncio
    async def test_multi_mode_with_clusters_strips_overrides(self):
        """Multi mode with loaded clusters strips override fields."""
        from mcp_server_opensearch.clusters_information import ClusterInfo, add_cluster
        from mcp_server_opensearch.global_state import set_mode
        from tools.tool_filter import get_tools

        set_mode('multi')
        add_cluster('prod', ClusterInfo(opensearch_url='https://prod.example.com'))

        result = await get_tools(self._make_registry())

        props = result['ListIndexTool']['input_schema']['properties']
        assert 'index' in props
        assert 'opensearch_url' not in props
        assert 'aws_region' not in props
        # opensearch_cluster_name should be kept in multi mode
        assert 'opensearch_cluster_name' in props

    @pytest.mark.asyncio
    async def test_multi_mode_no_clusters_keeps_overrides(self):
        """Multi mode with no clusters loaded keeps override fields."""
        from mcp_server_opensearch.clusters_information import cluster_registry
        from mcp_server_opensearch.global_state import set_mode
        from mcp_server_opensearch.server_instructions import has_preconfigured_connection
        from tools.tool_filter import get_tools

        set_mode('multi')
        # Ensure clean state: no clusters, no OPENSEARCH_URL
        os.environ.pop('OPENSEARCH_URL', None)
        cluster_registry.clear()
        assert not has_preconfigured_connection(), 'Expected no preconfigured connection'

        result = await get_tools(self._make_registry())

        props = result['ListIndexTool']['input_schema']['properties']
        assert 'index' in props
        assert 'opensearch_url' in props
        assert 'aws_region' in props
        assert 'opensearch_cluster_name' in props
