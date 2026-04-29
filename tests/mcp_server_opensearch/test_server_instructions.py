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
        """Save and clear env vars, set single mode, clear cluster registry."""
        from mcp_server_opensearch.global_state import set_mode

        set_mode('single')
        self._original = os.environ.get('OPENSEARCH_URL')
        self._original_dynamic = os.environ.get('OPENSEARCH_DYNAMIC_CONNECTION')
        os.environ.pop('OPENSEARCH_URL', None)
        os.environ.pop('OPENSEARCH_DYNAMIC_CONNECTION', None)
        from mcp_server_opensearch.clusters_information import cluster_registry

        cluster_registry.clear()

    def teardown_method(self):
        """Restore env and clear cluster registry."""
        if self._original is not None:
            os.environ['OPENSEARCH_URL'] = self._original
        else:
            os.environ.pop('OPENSEARCH_URL', None)
        if self._original_dynamic is not None:
            os.environ['OPENSEARCH_DYNAMIC_CONNECTION'] = self._original_dynamic
        else:
            os.environ.pop('OPENSEARCH_DYNAMIC_CONNECTION', None)
        from mcp_server_opensearch.clusters_information import cluster_registry

        cluster_registry.clear()

    def test_returns_instructions_when_nothing_configured(self):
        """When no URL and no clusters, instructions are returned in single mode."""
        from mcp_server_opensearch.server_instructions import get_server_instructions

        result = get_server_instructions()
        assert result is not None
        assert 'opensearch_url' in result

    def test_returns_none_in_multi_mode(self):
        """In multi mode, instructions are always None regardless of config."""
        from mcp_server_opensearch.global_state import set_mode
        from mcp_server_opensearch.server_instructions import get_server_instructions

        set_mode('multi')
        assert get_server_instructions() is None

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

    def test_dynamic_connection_true_forces_instructions_even_with_url(self):
        """OPENSEARCH_DYNAMIC_CONNECTION=true forces instructions even when URL is set."""
        os.environ['OPENSEARCH_URL'] = 'https://my-cluster.example.com'
        os.environ['OPENSEARCH_DYNAMIC_CONNECTION'] = 'true'
        from mcp_server_opensearch.server_instructions import get_server_instructions

        result = get_server_instructions()
        assert result is not None
        assert 'opensearch_url' in result

    def test_dynamic_connection_false_suppresses_instructions_in_zero_config(self):
        """OPENSEARCH_DYNAMIC_CONNECTION=false suppresses instructions even with no URL."""
        os.environ.pop('OPENSEARCH_URL', None)
        os.environ['OPENSEARCH_DYNAMIC_CONNECTION'] = 'false'
        from mcp_server_opensearch.server_instructions import get_server_instructions

        assert get_server_instructions() is None


class TestIsDynamicModeEnabled:
    """Tests for the is_dynamic_mode_enabled() function."""

    def setup_method(self):
        self._original_url = os.environ.get('OPENSEARCH_URL')
        self._original_dynamic = os.environ.get('OPENSEARCH_DYNAMIC_CONNECTION')
        os.environ.pop('OPENSEARCH_URL', None)
        os.environ.pop('OPENSEARCH_DYNAMIC_CONNECTION', None)
        from mcp_server_opensearch.clusters_information import cluster_registry

        cluster_registry.clear()

    def teardown_method(self):
        if self._original_url is not None:
            os.environ['OPENSEARCH_URL'] = self._original_url
        else:
            os.environ.pop('OPENSEARCH_URL', None)
        if self._original_dynamic is not None:
            os.environ['OPENSEARCH_DYNAMIC_CONNECTION'] = self._original_dynamic
        else:
            os.environ.pop('OPENSEARCH_DYNAMIC_CONNECTION', None)
        from mcp_server_opensearch.clusters_information import cluster_registry

        cluster_registry.clear()

    def test_auto_on_when_nothing_configured(self):
        """Auto-detects dynamic mode on when no URL and no clusters."""
        from mcp_server_opensearch.server_instructions import is_dynamic_mode_enabled

        assert is_dynamic_mode_enabled() is True

    def test_auto_off_when_url_configured(self):
        """Auto-detects dynamic mode off when OPENSEARCH_URL is set."""
        os.environ['OPENSEARCH_URL'] = 'https://cluster.example.com'
        from mcp_server_opensearch.server_instructions import is_dynamic_mode_enabled

        assert is_dynamic_mode_enabled() is False

    def test_auto_off_when_clusters_loaded(self):
        """Auto-detects dynamic mode off when clusters are in the registry."""
        from mcp_server_opensearch.clusters_information import ClusterInfo, add_cluster
        from mcp_server_opensearch.server_instructions import is_dynamic_mode_enabled

        add_cluster('prod', ClusterInfo(opensearch_url='https://prod.example.com'))
        assert is_dynamic_mode_enabled() is False

    def test_explicit_true_overrides_url(self):
        """OPENSEARCH_DYNAMIC_CONNECTION=true forces on even when URL is set."""
        os.environ['OPENSEARCH_URL'] = 'https://cluster.example.com'
        os.environ['OPENSEARCH_DYNAMIC_CONNECTION'] = 'true'
        from mcp_server_opensearch.server_instructions import is_dynamic_mode_enabled

        assert is_dynamic_mode_enabled() is True

    def test_explicit_1_overrides_url(self):
        """OPENSEARCH_DYNAMIC_CONNECTION=1 is treated as true."""
        os.environ['OPENSEARCH_URL'] = 'https://cluster.example.com'
        os.environ['OPENSEARCH_DYNAMIC_CONNECTION'] = '1'
        from mcp_server_opensearch.server_instructions import is_dynamic_mode_enabled

        assert is_dynamic_mode_enabled() is True

    def test_explicit_false_overrides_zero_config(self):
        """OPENSEARCH_DYNAMIC_CONNECTION=false forces off even with no URL."""
        os.environ['OPENSEARCH_DYNAMIC_CONNECTION'] = 'false'
        from mcp_server_opensearch.server_instructions import is_dynamic_mode_enabled

        assert is_dynamic_mode_enabled() is False

    def test_explicit_0_overrides_zero_config(self):
        """OPENSEARCH_DYNAMIC_CONNECTION=0 is treated as false."""
        os.environ['OPENSEARCH_DYNAMIC_CONNECTION'] = '0'
        from mcp_server_opensearch.server_instructions import is_dynamic_mode_enabled

        assert is_dynamic_mode_enabled() is False

    def test_case_insensitive(self):
        """OPENSEARCH_DYNAMIC_CONNECTION is case-insensitive."""
        os.environ['OPENSEARCH_DYNAMIC_CONNECTION'] = 'TRUE'
        from mcp_server_opensearch.server_instructions import is_dynamic_mode_enabled

        assert is_dynamic_mode_enabled() is True


class TestConditionalSchemaStripping:
    """Tests that tool schemas are conditionally stripped based on configuration."""

    def setup_method(self):
        """Set single mode, save env, clear cluster registry."""
        from mcp_server_opensearch.global_state import set_mode

        set_mode('single')
        self._original = os.environ.get('OPENSEARCH_URL')
        self._original_dynamic = os.environ.get('OPENSEARCH_DYNAMIC_CONNECTION')
        self._original_header_auth = os.environ.get('OPENSEARCH_HEADER_AUTH')
        os.environ.pop('OPENSEARCH_DYNAMIC_CONNECTION', None)
        os.environ.pop('OPENSEARCH_HEADER_AUTH', None)
        from mcp_server_opensearch.clusters_information import cluster_registry

        cluster_registry.clear()

    def teardown_method(self):
        """Restore env and clear cluster registry."""
        if self._original is not None:
            os.environ['OPENSEARCH_URL'] = self._original
        else:
            os.environ.pop('OPENSEARCH_URL', None)
        if self._original_dynamic is not None:
            os.environ['OPENSEARCH_DYNAMIC_CONNECTION'] = self._original_dynamic
        else:
            os.environ.pop('OPENSEARCH_DYNAMIC_CONNECTION', None)
        if self._original_header_auth is not None:
            os.environ['OPENSEARCH_HEADER_AUTH'] = self._original_header_auth
        else:
            os.environ.pop('OPENSEARCH_HEADER_AUTH', None)
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
    async def test_multi_mode_no_clusters_strips_overrides(self):
        """Multi mode always strips override fields — dynamic params are single-mode only."""
        from mcp_server_opensearch.clusters_information import cluster_registry
        from mcp_server_opensearch.global_state import set_mode
        from tools.tool_filter import get_tools

        set_mode('multi')
        os.environ.pop('OPENSEARCH_URL', None)
        cluster_registry.clear()

        result = await get_tools(self._make_registry())

        props = result['ListIndexTool']['input_schema']['properties']
        assert 'index' in props
        # Override fields are always stripped in multi mode
        assert 'opensearch_url' not in props
        assert 'aws_region' not in props
        # opensearch_cluster_name should be kept in multi mode
        assert 'opensearch_cluster_name' in props

    @pytest.mark.asyncio
    async def test_dynamic_mode_marks_opensearch_url_required(self):
        """In dynamic mode without header auth or URL fallback, opensearch_url is required."""
        os.environ.pop('OPENSEARCH_URL', None)
        os.environ.pop('OPENSEARCH_HEADER_AUTH', None)
        from tools.tool_filter import get_tools

        with patch('tools.tool_filter.get_opensearch_version', return_value=None):
            with patch('tools.tool_filter.is_tool_compatible', return_value=True):
                result = await get_tools(self._make_registry())

        schema = result['ListIndexTool']['input_schema']
        assert 'opensearch_url' in schema['properties']
        assert 'opensearch_url' in schema.get('required', [])

    @pytest.mark.asyncio
    async def test_dynamic_mode_with_url_env_var_does_not_mark_required(self):
        """When OPENSEARCH_DYNAMIC_CONNECTION=true but OPENSEARCH_URL is set,
        opensearch_url is exposed in schema but NOT required (server has a fallback)."""
        os.environ['OPENSEARCH_URL'] = 'https://cluster.example.com'
        os.environ['OPENSEARCH_DYNAMIC_CONNECTION'] = 'true'
        from tools.tool_filter import get_tools

        with patch('tools.tool_filter.get_opensearch_version', return_value=None):
            with patch('tools.tool_filter.is_tool_compatible', return_value=True):
                result = await get_tools(self._make_registry())

        schema = result['ListIndexTool']['input_schema']
        assert 'opensearch_url' in schema['properties']
        assert 'opensearch_url' not in schema.get('required', [])

    @pytest.mark.asyncio
    async def test_header_auth_mode_does_not_mark_opensearch_url_required(self):
        """In header auth mode, opensearch_url must NOT be required (URL comes from headers)."""
        os.environ.pop('OPENSEARCH_URL', None)
        os.environ['OPENSEARCH_HEADER_AUTH'] = 'true'
        from tools.tool_filter import get_tools

        with patch('tools.tool_filter.get_opensearch_version', return_value=None):
            with patch('tools.tool_filter.is_tool_compatible', return_value=True):
                result = await get_tools(self._make_registry())

        schema = result['ListIndexTool']['input_schema']
        assert 'opensearch_url' in schema['properties']
        assert 'opensearch_url' not in schema.get('required', [])
