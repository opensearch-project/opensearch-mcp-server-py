import pytest
from semver import Version
from unittest.mock import patch, MagicMock
from tools.utils import is_tool_compatible
from tools.tool_filter import get_tools, process_tool_filter
from tools.tool_params import baseToolArgs
import copy

# A dictionary for mocking TOOL_REGISTRY
MOCK_TOOL_REGISTRY = {
    'ListIndexTool': {
        'display_name': 'ListIndexTool',
        'description': 'List indices',
        'input_schema': {'type': 'object', 'properties': {'param1': {'type': 'string'}}},
        'function': MagicMock(),
        'args_model': MagicMock(),
        'min_version': '1.0.0',
        'max_version': '3.0.0',
    },
    'SearchIndexTool': {
        'display_name': 'SearchIndexTool',
        'description': 'Search an index',
        'input_schema': {
            'type': 'object',
            'properties': {
                'opensearch_cluster_name': {'type': 'string'},
                'query': {'type': 'object'},
            },
        },
        'function': MagicMock(),
        'args_model': MagicMock(),
        'min_version': '2.0.0',
        'max_version': '3.0.0',
    },
    'DataDistributionTool': {
        'display_name': 'DataDistributionTool',
        'description': 'Analyze data distribution patterns',
        'input_schema': {
            'type': 'object',
            'properties': {
                'opensearch_cluster_name': {'type': 'string'},
                'index': {'type': 'string'},
            },
        },
        'function': MagicMock(),
        'args_model': MagicMock(),
        'min_version': '3.3.0',
        'http_methods': 'POST',
    },
    'LogPatternAnalysisTool': {
        'display_name': 'LogPatternAnalysisTool',
        'description': 'Analyze log patterns',
        'input_schema': {
            'type': 'object',
            'properties': {
                'opensearch_cluster_name': {'type': 'string'},
                'index': {'type': 'string'},
            },
        },
        'function': MagicMock(),
        'args_model': MagicMock(),
        'min_version': '3.3.0',
        'http_methods': 'POST',
    },
}


class TestIsToolCompatible:
    def test_version_within_range(self):
        tool_info = {'min_version': '1.0.0', 'max_version': '3.0.0'}
        assert is_tool_compatible(Version.parse('2.0.0'), tool_info) is True

    def test_version_below_min(self):
        tool_info = {'min_version': '2.0.0', 'max_version': '3.0.0'}
        assert is_tool_compatible(Version.parse('1.5.0'), tool_info) is False

    def test_version_above_max(self):
        tool_info = {'min_version': '1.0.0', 'max_version': '2.0.0'}
        assert is_tool_compatible(Version.parse('2.1.0'), tool_info) is False

    def test_version_equal_to_min(self):
        tool_info = {'min_version': '1.0.0', 'max_version': '3.0.0'}
        assert is_tool_compatible(Version.parse('1.0.0'), tool_info) is True

    def test_version_equal_to_max(self):
        tool_info = {'min_version': '1.0.0', 'max_version': '3.0.0'}
        assert is_tool_compatible(Version.parse('3.0.0'), tool_info) is True

    def test_version_only_patch_not_provided(self):
        tool_info = {'min_version': '2.5', 'max_version': '3'}
        assert is_tool_compatible(Version.parse('2.5.1'), tool_info) is True
        assert is_tool_compatible(Version.parse('2.15.0'), tool_info) is True
        assert is_tool_compatible(Version.parse('3.0.0'), tool_info) is True

    def test_default_tool_info(self):
        # Should be True for almost any reasonable version
        assert is_tool_compatible(Version.parse('1.2.3')) is True
        assert is_tool_compatible(Version.parse('99.0.0')) is True
        assert is_tool_compatible(Version.parse('0.0.1')) is True

    def test_invalid_version_strings(self):
        # If min_version or max_version is not a valid semver, should raise ValueError
        with pytest.raises(ValueError):
            is_tool_compatible(Version.parse('1.0.0'), {'min_version': 'not_a_version'})
        with pytest.raises(ValueError):
            is_tool_compatible(Version.parse('1.0.0'), {'max_version': 'not_a_version'})


class TestGetTools:
    """Test cases for the get_tools function."""

    def setup_method(self):
        """Setup before each test method."""
        # Set global mode for tests
        from mcp_server_opensearch.global_state import set_mode

        set_mode('single')

    @pytest.fixture
    def mock_tool_registry(self):
        """Return a deep copy of the mock tool registry for isolation."""
        return copy.deepcopy(MOCK_TOOL_REGISTRY)

    @pytest.fixture
    def mock_patches(self):
        """Set up common patches for get_tools tests."""
        with (
            patch('tools.tool_filter.get_opensearch_version') as mock_get_version,
            patch('tools.tool_filter.is_tool_compatible') as mock_is_compatible,
        ):
            yield mock_get_version, mock_is_compatible

    @pytest.mark.asyncio
    async def test_get_tools_multi_mode_returns_all_tools(self, mock_tool_registry):
        """Test that multi mode returns all tools with base fields intact."""
        from mcp_server_opensearch.global_state import set_mode

        set_mode('multi')  # Set mode to multi for this test

        result = await get_tools(mock_tool_registry)
        assert result == mock_tool_registry
        assert 'param1' in result['ListIndexTool']['input_schema']['properties']
        assert 'opensearch_cluster_name' in result['SearchIndexTool']['input_schema']['properties']

    @pytest.mark.asyncio
    async def test_get_tools_single_mode_filters_and_removes_base_fields(
        self, mock_tool_registry, mock_patches
    ):
        """Test that single mode filters by version AND removes base fields."""
        mock_get_version, mock_is_compatible = mock_patches

        # Setup mocks
        mock_get_version.return_value = Version.parse('2.5.0')

        # Mock compatibility: only ListIndexTool should be compatible
        mock_is_compatible.side_effect = (
            lambda version, tool_info: tool_info['min_version'] == '1.0.0'
        )

        # Patch TOOL_REGISTRY to use our mock registry
        with patch('tools.tool_filter.TOOL_REGISTRY', mock_tool_registry):
            # Call get_tools in single mode
            result = await get_tools(mock_tool_registry)

            # Assertions
            assert 'ListIndexTool' in result
            assert 'SearchIndexTool' not in result
            assert 'param1' in result['ListIndexTool']['input_schema']['properties']
            assert (
                'opensearch_cluster_name'
                not in result['ListIndexTool']['input_schema']['properties']
            )

    @pytest.mark.asyncio
    @patch.dict('os.environ', {'AWS_OPENSEARCH_SERVERLESS': 'true'})
    async def test_get_tools_single_mode_serverless_passes_compatibility_check(
        self, mock_tool_registry, mock_patches
    ):
        """Test that serverless mode passes version compatibility checks."""
        mock_get_version, mock_is_compatible = mock_patches

        # Setup mocks
        mock_get_version.return_value = None
        mock_is_compatible.return_value = True  # Should return True for serverless mode

        # Patch TOOL_REGISTRY to use our mock registry
        with patch('tools.tool_filter.TOOL_REGISTRY', mock_tool_registry):
            # Call get_tools in single mode with serverless environment
            result = await get_tools(mock_tool_registry)

            # is_tool_compatible should be called with None version, and should return True for serverless
            mock_is_compatible.assert_called()
            # Verify all calls were made with None as the version
            for call in mock_is_compatible.call_args_list:
                if len(call.args) > 0:  # Check if there are positional arguments
                    assert call.args[0] is None, f'Expected None version, got {call.args[0]}'

            # Both tools should be enabled in serverless mode
            assert 'ListIndexTool' in result
            assert 'SearchIndexTool' in result

    @pytest.mark.asyncio
    async def test_get_tools_single_mode_handles_missing_properties(self, mock_patches):
        """Test that single mode handles schemas without properties field."""
        mock_get_version, mock_is_compatible = mock_patches

        # Create tool with missing properties
        tool_without_properties = {
            'ListIndexTool': {
                'display_name': 'ListIndexTool',
                'description': 'List indices',
                'input_schema': {'type': 'object', 'title': 'ListIndexArgs'},
                'function': MagicMock(),
                'args_model': MagicMock(),
                'min_version': '1.0.0',
                'max_version': '3.0.0',
            }
        }
        mock_get_version.return_value = Version.parse('2.5.0')
        mock_is_compatible.return_value = True

        # Patch TOOL_REGISTRY to use our test tool registry
        with patch('tools.tool_filter.TOOL_REGISTRY', tool_without_properties):
            # Call get_tools in single mode - should not raise error
            result = await get_tools(tool_without_properties)
            assert 'ListIndexTool' in result
            assert 'properties' not in result['ListIndexTool']['input_schema']

    @pytest.mark.asyncio
    async def test_get_tools_default_mode_is_single(self, mock_tool_registry, mock_patches):
        """Test that get_tools defaults to single mode."""
        mock_get_version, mock_is_compatible = mock_patches

        mock_get_version.return_value = Version.parse('2.5.0')
        mock_is_compatible.return_value = True

        # Patch TOOL_REGISTRY to use our mock registry
        with patch('tools.tool_filter.TOOL_REGISTRY', mock_tool_registry):
            # Call get_tools without specifying mode
            result = await get_tools(mock_tool_registry)
            assert (
                'opensearch_cluster_name'
                not in result['SearchIndexTool']['input_schema']['properties']
            )

    @pytest.mark.asyncio
    async def test_get_tools_skills_tools_version_filtering(self, mock_tool_registry, mock_patches):
        """Test that skills tools are filtered based on version compatibility."""
        mock_get_version, mock_is_compatible = mock_patches

        # Setup mocks - simulate OpenSearch 2.5.0 (below skills tools min version 3.3.0)
        mock_get_version.return_value = Version.parse('2.5.0')

        # Mock compatibility: skills tools should be incompatible with 2.5.0
        def mock_compatibility(version, tool_info):
            min_version = tool_info.get('min_version', '1.0.0')
            return version >= Version.parse(min_version)

        mock_is_compatible.side_effect = mock_compatibility

        # Patch TOOL_REGISTRY to use our mock registry
        with patch('tools.tool_filter.TOOL_REGISTRY', mock_tool_registry):
            result = await get_tools(mock_tool_registry)

            # Skills tools should be filtered out due to version incompatibility
            assert 'DataDistributionTool' not in result
            assert 'LogPatternAnalysisTool' not in result
            # Other tools should still be present
            assert 'ListIndexTool' in result
            assert 'SearchIndexTool' in result

    @pytest.mark.asyncio
    async def test_get_tools_skills_tools_compatible_version(self, mock_tool_registry, mock_patches):
        """Test that skills tools are excluded by default even when version is compatible,
        since they belong to the 'skills' category which is not enabled by default."""
        mock_get_version, mock_is_compatible = mock_patches

        # Setup mocks - simulate OpenSearch 3.5.0 (above skills tools min version 3.3.0)
        mock_get_version.return_value = Version.parse('3.5.0')
        mock_is_compatible.return_value = True  # All tools compatible

        # Patch TOOL_REGISTRY to use our mock registry
        with patch('tools.tool_filter.TOOL_REGISTRY', mock_tool_registry):
            result = await get_tools(mock_tool_registry)

            # Skills tools should be excluded since the skills category is not enabled by default
            assert 'DataDistributionTool' not in result
            assert 'LogPatternAnalysisTool' not in result
            # Core tools should still be present
            assert 'ListIndexTool' in result
            assert 'SearchIndexTool' in result

    @pytest.mark.asyncio
    async def test_get_tools_logs_version_info(self, mock_tool_registry, mock_patches, caplog):
        """Test that get_tools logs version information in single mode."""
        mock_get_version, mock_is_compatible = mock_patches
        mock_get_version.return_value = Version.parse('2.5.0')
        mock_is_compatible.return_value = True

        # Patch TOOL_REGISTRY to use our mock registry
        with patch('tools.tool_filter.TOOL_REGISTRY', mock_tool_registry):
            # Call get_tools in single mode with logging capture
            with caplog.at_level('INFO'):
                await get_tools(mock_tool_registry)
                assert 'Connected OpenSearch version: 2.5.0' in caplog.text


class TestProcessToolFilter:
    """Test cases for the process_tool_filter function."""

    def setup_method(self):
        """Set up a fresh copy of the tool registry for each test."""
        self.tool_registry = {
            'ListIndexTool': {'display_name': 'ListIndexTool', 'http_methods': 'GET'},
            'SearchIndexTool': {'display_name': 'SearchIndexTool', 'http_methods': 'GET, POST'},
            'MsearchTool': {'display_name': 'MsearchTool', 'http_methods': 'GET, POST'},
            'ExplainTool': {'display_name': 'ExplainTool', 'http_methods': 'GET, POST'},
            'ClusterHealthTool': {'display_name': 'ClusterHealthTool', 'http_methods': 'GET'},
            'IndicesCreateTool': {'display_name': 'IndicesCreateTool', 'http_methods': 'PUT'},
            'IndicesStatsTool': {'display_name': 'IndicesStatsTool', 'http_methods': 'GET'},
            'CountTool': {'display_name': 'CustomCountTool', 'http_methods': 'GET'},
            'ListModelTool': {'display_name': 'ModelListTool', 'http_methods': 'GET'},
        }
        self.category_to_tools = {
            'critical': ['SearchIndexTool', 'ExplainTool'],
            'admin': ['ClusterHealthTool', 'IndicesStatsTool'],
        }

    def test_process_tool_filter_config(self):
        """Test processing tool filter from a YAML config file."""
        process_tool_filter(
            tool_registry=self.tool_registry,
            filter_path='tests/tools/test_config.yml',
            tool_categories=self.category_to_tools,
        )

        # Core tools, enabled by default
        assert 'ClusterHealthTool' in self.tool_registry
        assert 'ListIndexTool' in self.tool_registry

        # Non-core tools, but enabled in test_config.yml
        assert 'IndicesStatsTool' in self.tool_registry

        # Core tools, but disabled in test_config.yml
        assert 'MsearchTool' not in self.tool_registry

        # Tools are in the 'critical' category which is disabled in test_config.yml
        assert 'SearchIndexTool' not in self.tool_registry
        assert 'ExplainTool' not in self.tool_registry

    def test_process_tool_filter_env(self):
        """Test processing tool filter from environment variables."""
        # Call the function with environment variables
        process_tool_filter(
            tool_registry=self.tool_registry,
            disabled_tools='ExplainTool',
            disabled_tools_regex='search.*',
            allow_write=True,
        )

        # Core tools, enabled by default
        assert 'ListIndexTool' in self.tool_registry
        assert 'ClusterHealthTool' in self.tool_registry
        assert 'MsearchTool' in self.tool_registry

        # Non-core tools, disabled by default
        assert 'IndicesCreateTool' not in self.tool_registry
        assert 'IndicesStatsTool' not in self.tool_registry

        # In disabled_tools_regex and disabled_tools
        assert 'SearchIndexTool' not in self.tool_registry
        assert 'ExplainTool' not in self.tool_registry

    def test_process_tool_filter_rename_tool(self):
        """Test processing tool filtering with tool renaming feature"""
        process_tool_filter(
            tool_registry=self.tool_registry,
            enabled_tools='ModelListTool',
            disabled_tools='CountTool',
            disabled_tools_regex='list.*',
            allow_write=True,
        )
        assert 'CountTool' in self.tool_registry  # Renamed to CustomCountTool
        assert 'ListModelTool' in self.tool_registry  # Renamed to ModelListTool

        process_tool_filter(
            tool_registry=self.tool_registry,
            disabled_tools='CustomCountTool',
            disabled_tools_regex='model.*',
            allow_write=True,
        )
        assert 'CustomCountTool' not in self.tool_registry
        assert 'ModelListTool' not in self.tool_registry

    def test_core_tools_default(self):
        """Test core tools enabled by default"""
        process_tool_filter(
            tool_registry=self.tool_registry,
            allow_write=True,
        )

        # Core tools
        assert 'ListIndexTool' in self.tool_registry
        assert 'ClusterHealthTool' in self.tool_registry

        # Non-core tools
        assert 'IndicesStatsTool' not in self.tool_registry
        assert 'ListModelTool' not in self.tool_registry

    def test_disable_core_tools(self):
        """Test disable core tools categories, which is enabled by default"""
        process_tool_filter(
            tool_registry=self.tool_registry,
            disabled_categories='core_tools',
            allow_write=True,
        )

        # Core tools, should be disabled
        assert 'ListIndexTool' not in self.tool_registry
        assert 'ClusterHealthTool' not in self.tool_registry
        assert 'ExplainTool' not in self.tool_registry

    def test_skills_category_is_not_enabled_by_default(self):
        """skills tools are not enabled unless the category is explicitly enabled."""
        registry = {
            'ListIndexTool': {'display_name': 'ListIndexTool', 'http_methods': 'GET'},
            'DataDistributionTool': {
                'display_name': 'DataDistributionTool',
                'http_methods': 'POST',
            },
            'LogPatternAnalysisTool': {
                'display_name': 'LogPatternAnalysisTool',
                'http_methods': 'POST',
            },
        }
        process_tool_filter(tool_registry=registry, allow_write=True)

        assert 'ListIndexTool' in registry
        assert 'DataDistributionTool' not in registry
        assert 'LogPatternAnalysisTool' not in registry

    def test_skills_category_can_be_enabled(self):
        """skills tools are exposed when the category is explicitly enabled."""
        registry = {
            'ListIndexTool': {'display_name': 'ListIndexTool', 'http_methods': 'GET'},
            'DataDistributionTool': {
                'display_name': 'DataDistributionTool',
                'http_methods': 'POST',
            },
            'LogPatternAnalysisTool': {
                'display_name': 'LogPatternAnalysisTool',
                'http_methods': 'POST',
            },
        }
        process_tool_filter(
            tool_registry=registry,
            enabled_categories='core_tools,skills',
            allow_write=True,
        )

        assert 'ListIndexTool' in registry
        assert 'DataDistributionTool' in registry
        assert 'LogPatternAnalysisTool' in registry

    def test_data_distribution_and_log_pattern_not_in_core_tools(self):
        """DataDistributionTool and LogPatternAnalysisTool are not part of core_tools category."""
        registry = {
            'ListIndexTool': {'display_name': 'ListIndexTool', 'http_methods': 'GET'},
            'ClusterHealthTool': {'display_name': 'ClusterHealthTool', 'http_methods': 'GET'},
            'DataDistributionTool': {
                'display_name': 'DataDistributionTool',
                'http_methods': 'POST',
            },
            'LogPatternAnalysisTool': {
                'display_name': 'LogPatternAnalysisTool',
                'http_methods': 'POST',
            },
        }
        process_tool_filter(tool_registry=registry, allow_write=True)

        assert 'ListIndexTool' in registry
        assert 'ClusterHealthTool' in registry
        assert 'DataDistributionTool' not in registry
        assert 'LogPatternAnalysisTool' not in registry

    def test_search_relevance_category_is_not_enabled_by_default(self):
        """search_relevance tools are not enabled unless the category is explicitly enabled."""
        registry = {
            'ListIndexTool': {'display_name': 'ListIndexTool', 'http_methods': 'GET'},
            'CreateSearchConfigurationTool': {
                'display_name': 'CreateSearchConfigurationTool',
                'http_methods': 'PUT',
            },
            'GetSearchConfigurationTool': {
                'display_name': 'GetSearchConfigurationTool',
                'http_methods': 'GET',
            },
            'DeleteSearchConfigurationTool': {
                'display_name': 'DeleteSearchConfigurationTool',
                'http_methods': 'DELETE',
            },
            'GetQuerySetTool': {'display_name': 'GetQuerySetTool', 'http_methods': 'GET'},
            'CreateQuerySetTool': {'display_name': 'CreateQuerySetTool', 'http_methods': 'PUT'},
            'SampleQuerySetTool': {'display_name': 'SampleQuerySetTool', 'http_methods': 'POST'},
            'DeleteQuerySetTool': {'display_name': 'DeleteQuerySetTool', 'http_methods': 'DELETE'},
            'GetJudgmentListTool': {'display_name': 'GetJudgmentListTool', 'http_methods': 'GET'},
            'CreateJudgmentListTool': {'display_name': 'CreateJudgmentListTool', 'http_methods': 'PUT'},
            'CreateUBIJudgmentListTool': {
                'display_name': 'CreateUBIJudgmentListTool',
                'http_methods': 'PUT',
            },
            'CreateLLMJudgmentListTool': {
                'display_name': 'CreateLLMJudgmentListTool',
                'http_methods': 'PUT',
            },
            'DeleteJudgmentListTool': {'display_name': 'DeleteJudgmentListTool', 'http_methods': 'DELETE'},
            'GetExperimentTool': {'display_name': 'GetExperimentTool', 'http_methods': 'GET'},
            'CreateExperimentTool': {'display_name': 'CreateExperimentTool', 'http_methods': 'PUT'},
            'DeleteExperimentTool': {'display_name': 'DeleteExperimentTool', 'http_methods': 'DELETE'},
            'SearchQuerySetsTool': {'display_name': 'SearchQuerySetsTool', 'http_methods': 'GET, POST'},
            'SearchSearchConfigurationsTool': {'display_name': 'SearchSearchConfigurationsTool', 'http_methods': 'GET, POST'},
            'SearchJudgmentsTool': {'display_name': 'SearchJudgmentsTool', 'http_methods': 'GET, POST'},
            'SearchExperimentsTool': {'display_name': 'SearchExperimentsTool', 'http_methods': 'GET, POST'},
        }
        process_tool_filter(tool_registry=registry, allow_write=True)

        # core_tools are enabled by default, search_relevance tools are not
        assert 'ListIndexTool' in registry
        assert 'CreateSearchConfigurationTool' not in registry
        assert 'GetSearchConfigurationTool' not in registry
        assert 'DeleteSearchConfigurationTool' not in registry
        assert 'GetQuerySetTool' not in registry
        assert 'CreateQuerySetTool' not in registry
        assert 'SampleQuerySetTool' not in registry
        assert 'DeleteQuerySetTool' not in registry
        assert 'GetJudgmentListTool' not in registry
        assert 'CreateJudgmentListTool' not in registry
        assert 'CreateUBIJudgmentListTool' not in registry
        assert 'CreateLLMJudgmentListTool' not in registry
        assert 'DeleteJudgmentListTool' not in registry
        assert 'GetExperimentTool' not in registry
        assert 'CreateExperimentTool' not in registry
        assert 'DeleteExperimentTool' not in registry
        assert 'SearchQuerySetsTool' not in registry
        assert 'SearchSearchConfigurationsTool' not in registry
        assert 'SearchJudgmentsTool' not in registry
        assert 'SearchExperimentsTool' not in registry

    def test_search_relevance_category_can_be_enabled(self):
        """search_relevance tools are exposed when the category is explicitly enabled."""
        registry = {
            'ListIndexTool': {'display_name': 'ListIndexTool', 'http_methods': 'GET'},
            'CreateSearchConfigurationTool': {
                'display_name': 'CreateSearchConfigurationTool',
                'http_methods': 'PUT',
            },
            'GetSearchConfigurationTool': {
                'display_name': 'GetSearchConfigurationTool',
                'http_methods': 'GET',
            },
            'DeleteSearchConfigurationTool': {
                'display_name': 'DeleteSearchConfigurationTool',
                'http_methods': 'DELETE',
            },
            'GetQuerySetTool': {'display_name': 'GetQuerySetTool', 'http_methods': 'GET'},
            'CreateQuerySetTool': {'display_name': 'CreateQuerySetTool', 'http_methods': 'PUT'},
            'SampleQuerySetTool': {'display_name': 'SampleQuerySetTool', 'http_methods': 'POST'},
            'DeleteQuerySetTool': {'display_name': 'DeleteQuerySetTool', 'http_methods': 'DELETE'},
            'GetJudgmentListTool': {'display_name': 'GetJudgmentListTool', 'http_methods': 'GET'},
            'CreateJudgmentListTool': {'display_name': 'CreateJudgmentListTool', 'http_methods': 'PUT'},
            'CreateUBIJudgmentListTool': {
                'display_name': 'CreateUBIJudgmentListTool',
                'http_methods': 'PUT',
            },
            'CreateLLMJudgmentListTool': {
                'display_name': 'CreateLLMJudgmentListTool',
                'http_methods': 'PUT',
            },
            'DeleteJudgmentListTool': {'display_name': 'DeleteJudgmentListTool', 'http_methods': 'DELETE'},
            'GetExperimentTool': {'display_name': 'GetExperimentTool', 'http_methods': 'GET'},
            'CreateExperimentTool': {'display_name': 'CreateExperimentTool', 'http_methods': 'PUT'},
            'DeleteExperimentTool': {'display_name': 'DeleteExperimentTool', 'http_methods': 'DELETE'},
            'SearchQuerySetsTool': {'display_name': 'SearchQuerySetsTool', 'http_methods': 'GET, POST'},
            'SearchSearchConfigurationsTool': {'display_name': 'SearchSearchConfigurationsTool', 'http_methods': 'GET, POST'},
            'SearchJudgmentsTool': {'display_name': 'SearchJudgmentsTool', 'http_methods': 'GET, POST'},
            'SearchExperimentsTool': {'display_name': 'SearchExperimentsTool', 'http_methods': 'GET, POST'},
        }
        process_tool_filter(
            tool_registry=registry,
            enabled_categories='core_tools,search_relevance',
            allow_write=True,
        )

        assert 'ListIndexTool' in registry
        assert 'CreateSearchConfigurationTool' in registry
        assert 'GetSearchConfigurationTool' in registry
        assert 'DeleteSearchConfigurationTool' in registry
        assert 'GetQuerySetTool' in registry
        assert 'CreateQuerySetTool' in registry
        assert 'SampleQuerySetTool' in registry
        assert 'DeleteQuerySetTool' in registry
        assert 'GetJudgmentListTool' in registry
        assert 'CreateJudgmentListTool' in registry
        assert 'CreateUBIJudgmentListTool' in registry
        assert 'CreateLLMJudgmentListTool' in registry
        assert 'DeleteJudgmentListTool' in registry
        assert 'GetExperimentTool' in registry
        assert 'CreateExperimentTool' in registry
        assert 'DeleteExperimentTool' in registry
        assert 'SearchQuerySetsTool' in registry
        assert 'SearchSearchConfigurationsTool' in registry
        assert 'SearchJudgmentsTool' in registry
        assert 'SearchExperimentsTool' in registry


class TestAllowWriteSettings:
    """Test cases for the allow_write setting functionality."""

    def setup_method(self):
        """Set up test environment before each test."""
        # Reset the global setting before each test
        from tools.tool_filter import set_allow_write_setting

        set_allow_write_setting(None)

        # Save original environment variable
        import os

        self.original_env = os.environ.get('OPENSEARCH_SETTINGS_ALLOW_WRITE')

    def teardown_method(self):
        """Clean up test environment after each test."""
        # Reset the global setting after each test
        from tools.tool_filter import set_allow_write_setting

        set_allow_write_setting(None)

        # Restore original environment variable
        import os

        if self.original_env is not None:
            os.environ['OPENSEARCH_SETTINGS_ALLOW_WRITE'] = self.original_env
        elif 'OPENSEARCH_SETTINGS_ALLOW_WRITE' in os.environ:
            del os.environ['OPENSEARCH_SETTINGS_ALLOW_WRITE']

    def test_set_and_get_allow_write_setting(self):
        """Test basic set and get functionality for allow_write setting."""
        from tools.tool_filter import set_allow_write_setting, get_allow_write_setting

        # Test setting to False
        set_allow_write_setting(False)
        assert get_allow_write_setting() is False

        # Test setting to True
        set_allow_write_setting(True)
        assert get_allow_write_setting() is True

    def test_get_allow_write_setting_fallback_to_env(self):
        """Test that get_allow_write_setting falls back to environment variable when global setting is not set."""
        import os
        from tools.tool_filter import get_allow_write_setting

        # Test fallback to env var when set to 'true'
        os.environ['OPENSEARCH_SETTINGS_ALLOW_WRITE'] = 'true'
        assert get_allow_write_setting() is True

        # Test fallback to env var when set to 'false'
        os.environ['OPENSEARCH_SETTINGS_ALLOW_WRITE'] = 'false'
        assert get_allow_write_setting() is False

        # Test fallback to default (true) when env var not set
        if 'OPENSEARCH_SETTINGS_ALLOW_WRITE' in os.environ:
            del os.environ['OPENSEARCH_SETTINGS_ALLOW_WRITE']
        assert get_allow_write_setting() is True

    @patch('tools.tool_filter.load_yaml_config')
    def test_resolve_allow_write_setting_from_env_only(self, mock_load_yaml):
        """Test _resolve_allow_write_setting with environment variable only."""
        import os
        from tools.tool_filter import _resolve_allow_write_setting

        # Test with env var set to true
        os.environ['OPENSEARCH_SETTINGS_ALLOW_WRITE'] = 'true'
        result = _resolve_allow_write_setting()
        assert result is True
        mock_load_yaml.assert_not_called()

        # Test with env var set to false
        os.environ['OPENSEARCH_SETTINGS_ALLOW_WRITE'] = 'false'
        result = _resolve_allow_write_setting()
        assert result is False
        mock_load_yaml.assert_not_called()

    @patch('tools.tool_filter.load_yaml_config')
    @patch('os.path.exists')
    def test_resolve_allow_write_setting_from_config_file(self, mock_exists, mock_load_yaml):
        """Test _resolve_allow_write_setting with config file."""
        import os
        from tools.tool_filter import _resolve_allow_write_setting

        # Set up mocks
        mock_exists.return_value = True
        mock_config = {'tool_filters': {'settings': {'allow_write': False}}}
        mock_load_yaml.return_value = mock_config

        # Set env var to true, but config should override
        os.environ['OPENSEARCH_SETTINGS_ALLOW_WRITE'] = 'true'
        result = _resolve_allow_write_setting('/path/to/config.yml')

        assert result is False  # Config file should override env var
        mock_exists.assert_called_once_with('/path/to/config.yml')
        mock_load_yaml.assert_called_once_with('/path/to/config.yml')

    @patch('tools.tool_filter.load_yaml_config')
    @patch('os.path.exists')
    def test_resolve_allow_write_setting_config_file_not_found(self, mock_exists, mock_load_yaml):
        """Test _resolve_allow_write_setting when config file doesn't exist."""
        import os
        from tools.tool_filter import _resolve_allow_write_setting

        # Set up mocks
        mock_exists.return_value = False

        # Set env var to false
        os.environ['OPENSEARCH_SETTINGS_ALLOW_WRITE'] = 'false'
        result = _resolve_allow_write_setting('/path/to/nonexistent.yml')

        assert result is False  # Should use env var
        mock_exists.assert_called_once_with('/path/to/nonexistent.yml')
        mock_load_yaml.assert_not_called()

    @patch('tools.tool_filter.load_yaml_config')
    @patch('os.path.exists')
    def test_resolve_allow_write_setting_config_file_no_settings(
        self, mock_exists, mock_load_yaml
    ):
        """Test _resolve_allow_write_setting when config file has no allow_write setting."""
        import os
        from tools.tool_filter import _resolve_allow_write_setting

        # Set up mocks
        mock_exists.return_value = True
        mock_config = {
            'tool_filters': {
                'enabled_tools': ['SomeTool']
                # No 'settings' section
            }
        }
        mock_load_yaml.return_value = mock_config

        # Set env var to false
        os.environ['OPENSEARCH_SETTINGS_ALLOW_WRITE'] = 'false'
        result = _resolve_allow_write_setting('/path/to/config.yml')

        assert result is False  # Should use env var since config has no allow_write
        mock_exists.assert_called_once_with('/path/to/config.yml')
        mock_load_yaml.assert_called_once_with('/path/to/config.yml')

    @patch('tools.tool_filter.load_yaml_config')
    @patch('os.path.exists')
    def test_resolve_allow_write_setting_config_file_error(self, mock_exists, mock_load_yaml):
        """Test _resolve_allow_write_setting when config file loading fails."""
        import os
        from tools.tool_filter import _resolve_allow_write_setting

        # Set up mocks
        mock_exists.return_value = True
        mock_load_yaml.side_effect = Exception('YAML parsing error')

        # Set env var to true
        os.environ['OPENSEARCH_SETTINGS_ALLOW_WRITE'] = 'true'
        result = _resolve_allow_write_setting('/path/to/config.yml')

        assert result is True  # Should fall back to env var on error
        mock_exists.assert_called_once_with('/path/to/config.yml')
        mock_load_yaml.assert_called_once_with('/path/to/config.yml')

    @patch('tools.tool_filter._resolve_allow_write_setting')
    @patch('tools.tool_filter.set_allow_write_setting')
    @pytest.mark.asyncio
    async def test_get_tools_calls_resolve_and_set_allow_write(self, mock_set, mock_resolve):
        """Test that get_tools calls _resolve_allow_write_setting and set_allow_write_setting."""
        from tools.tool_filter import get_tools

        # Set up mocks
        mock_resolve.return_value = False
        mock_tool_registry = {
            'TestTool': {
                'display_name': 'TestTool',
                'description': 'Test tool',
                'input_schema': {'type': 'object'},
                'function': MagicMock(),
                'args_model': MagicMock(),
            }
        }

        # Test single mode
        with (
            patch('tools.tool_filter.get_opensearch_version'),
            patch('tools.tool_filter.process_tool_filter'),
            patch('tools.tool_filter.is_tool_compatible', return_value=True),
        ):
            await get_tools(mock_tool_registry, config_file_path='/path/to/config.yml')

            mock_resolve.assert_called_once_with('/path/to/config.yml')
            mock_set.assert_called_once_with(False)


class TestMultiOnlyFilter:
    """Test cases for multi_only tool filtering in get_tools."""

    def setup_method(self):
        from mcp_server_opensearch.global_state import set_mode

        set_mode('single')

    @pytest.fixture
    def registry_with_multi_only(self):
        """Return a registry containing a multi_only tool and a normal tool."""
        return {
            'ListIndexTool': {
                'display_name': 'ListIndexTool',
                'description': 'List indices',
                'input_schema': {'type': 'object', 'properties': {'param1': {'type': 'string'}}},
                'function': MagicMock(),
                'args_model': MagicMock(),
                'min_version': '1.0.0',
            },
            'ListClustersTool': {
                'display_name': 'ListClustersTool',
                'description': 'Lists clusters',
                'input_schema': {'type': 'object', 'properties': {}},
                'function': MagicMock(),
                'args_model': MagicMock(),
                'http_methods': 'GET',
                'multi_only': True,
            },
        }

    @pytest.fixture
    def mock_patches(self):
        with (
            patch('tools.tool_filter.get_opensearch_version') as mock_get_version,
            patch('tools.tool_filter.is_tool_compatible', return_value=True) as mock_is_compatible,
        ):
            yield mock_get_version, mock_is_compatible

    @pytest.mark.asyncio
    async def test_multi_only_tool_excluded_in_single_mode(
        self, registry_with_multi_only, mock_patches
    ):
        """Test that multi_only tools are excluded when running in single mode."""
        mock_get_version, _ = mock_patches
        mock_get_version.return_value = Version.parse('2.5.0')

        with patch('tools.tool_filter.TOOL_REGISTRY', registry_with_multi_only):
            result = await get_tools(registry_with_multi_only)

        assert 'ListIndexTool' in result
        assert 'ListClustersTool' not in result

    @pytest.mark.asyncio
    async def test_multi_only_tool_included_in_multi_mode(self, registry_with_multi_only):
        """Test that multi_only tools are included when running in multi mode."""
        from mcp_server_opensearch.global_state import set_mode

        set_mode('multi')

        result = await get_tools(registry_with_multi_only)

        assert 'ListIndexTool' in result
        assert 'ListClustersTool' in result

    @pytest.mark.asyncio
    async def test_tools_without_multi_only_unaffected(self, mock_patches):
        """Test that tools without multi_only flag are not affected by the filter."""
        mock_get_version, _ = mock_patches
        mock_get_version.return_value = Version.parse('2.5.0')

        registry = {
            'ListIndexTool': {
                'display_name': 'ListIndexTool',
                'description': 'List indices',
                'input_schema': {'type': 'object', 'properties': {}},
                'function': MagicMock(),
                'args_model': MagicMock(),
                'min_version': '1.0.0',
            },
        }

        with patch('tools.tool_filter.TOOL_REGISTRY', registry):
            result = await get_tools(registry)

        assert 'ListIndexTool' in result
