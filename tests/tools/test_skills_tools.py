# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import pytest
import sys
from unittest.mock import AsyncMock, Mock, patch


class TestSkillsTools:
    def setup_method(self):
        """Setup that runs before each test method."""
        # Create a properly configured mock client
        self.mock_client = Mock()

        # Configure mock client methods to return proper data structures
        # Use AsyncMock for async methods
        self.mock_client.transport.perform_request = AsyncMock(return_value={})
        self.mock_client.info.return_value = {'version': {'number': '3.3.0'}}

        # Patch initialize_client to always return our mock client
        self.init_client_patcher = patch(
            'opensearch.client.initialize_client', return_value=self.mock_client
        )
        self.init_client_patcher.start()

        # Clear any existing imports to ensure fresh imports
        modules_to_clear = [
            'tools.skills_tools',
        ]
        for module in modules_to_clear:
            if module in sys.modules:
                del sys.modules[module]

        # Import after patching to ensure fresh imports
        from tools.skills_tools import (
            SKILLS_TOOLS_REGISTRY,
            DataDistributionToolArgs,
            LogPatternAnalysisToolArgs,
            call_opensearch_tool,
            data_distribution_tool,
            log_pattern_analysis_tool,
        )

        self.SKILLS_TOOLS_REGISTRY = SKILLS_TOOLS_REGISTRY
        self.DataDistributionToolArgs = DataDistributionToolArgs
        self.LogPatternAnalysisToolArgs = LogPatternAnalysisToolArgs
        self._data_distribution_tool = data_distribution_tool
        self._log_pattern_analysis_tool = log_pattern_analysis_tool
        self._call_opensearch_tool = call_opensearch_tool

    def teardown_method(self):
        """Cleanup after each test method."""
        self.init_client_patcher.stop()

    @pytest.mark.asyncio
    async def test_call_opensearch_tool_success(self):
        """Test call_opensearch_tool successful execution."""
        # Setup
        mock_response = {'status': 'success', 'result': {'analysis': 'data distribution complete'}}
        self.mock_client.transport.perform_request.return_value = mock_response

        args = self.DataDistributionToolArgs(
            index='test-index',
            selectionTimeRangeStart='2023-01-01T00:00:00Z',
            selectionTimeRangeEnd='2023-01-02T00:00:00Z',
            timeField='@timestamp',
            opensearch_cluster_name='',
        )

        # Execute
        result = await self._call_opensearch_tool(
            'DataDistributionTool', {'index': 'test-index'}, args
        )

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'DataDistributionTool result:' in result[0]['text']
        assert '"status":"success"' in result[0]['text']
        self.mock_client.transport.perform_request.assert_called_once_with(
            'POST',
            '/_plugins/_ml/tools/_execute/DataDistributionTool',
            body={'parameters': {'index': 'test-index'}},
        )

    @pytest.mark.asyncio
    async def test_call_opensearch_tool_error(self):
        """Test call_opensearch_tool exception handling."""
        # Setup
        self.mock_client.transport.perform_request.side_effect = Exception('Test error')

        args = self.DataDistributionToolArgs(
            index='test-index',
            selectionTimeRangeStart='2023-01-01T00:00:00Z',
            selectionTimeRangeEnd='2023-01-02T00:00:00Z',
            timeField='@timestamp',
            opensearch_cluster_name='',
        )

        # Execute
        result = await self._call_opensearch_tool(
            'DataDistributionTool', {'index': 'test-index'}, args
        )

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Error executing DataDistributionTool: Test error' in result[0]['text']

    @pytest.mark.asyncio
    async def test_data_distribution_tool_minimal_params(self):
        """Test data_distribution_tool with minimal required parameters."""
        # Setup
        mock_response = {
            'status': 'success',
            'result': {'field_distributions': {'field1': {'count': 100}}},
        }
        self.mock_client.transport.perform_request.return_value = mock_response

        args = self.DataDistributionToolArgs(
            index='test-index',
            selectionTimeRangeStart='2023-01-01T00:00:00Z',
            selectionTimeRangeEnd='2023-01-02T00:00:00Z',
            timeField='@timestamp',
            opensearch_cluster_name='',
        )

        # Execute
        result = await self._data_distribution_tool(args)

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'DataDistributionTool result:' in result[0]['text']

        # Verify the correct parameters were passed
        expected_params = {
            'index': 'test-index',
            'timeField': '@timestamp',
            'selectionTimeRangeStart': '2023-01-01T00:00:00Z',
            'selectionTimeRangeEnd': '2023-01-02T00:00:00Z',
            'size': 1000,
        }
        self.mock_client.transport.perform_request.assert_called_once_with(
            'POST',
            '/_plugins/_ml/tools/_execute/DataDistributionTool',
            body={'parameters': expected_params},
        )

    @pytest.mark.asyncio
    async def test_data_distribution_tool_all_params(self):
        """Test data_distribution_tool with all parameters."""
        # Setup
        mock_response = {'status': 'success', 'result': {}}
        self.mock_client.transport.perform_request.return_value = mock_response

        args = self.DataDistributionToolArgs(
            index='test-index',
            selectionTimeRangeStart='2023-01-01T00:00:00Z',
            selectionTimeRangeEnd='2023-01-02T00:00:00Z',
            timeField='@timestamp',
            baselineTimeRangeStart='2022-12-01T00:00:00Z',
            baselineTimeRangeEnd='2022-12-02T00:00:00Z',
            size=500,
            opensearch_cluster_name='',
        )

        # Execute
        await self._data_distribution_tool(args)

        # Assert
        expected_params = {
            'index': 'test-index',
            'timeField': '@timestamp',
            'selectionTimeRangeStart': '2023-01-01T00:00:00Z',
            'selectionTimeRangeEnd': '2023-01-02T00:00:00Z',
            'size': 500,
            'baselineTimeRangeStart': '2022-12-01T00:00:00Z',
            'baselineTimeRangeEnd': '2022-12-02T00:00:00Z',
        }
        self.mock_client.transport.perform_request.assert_called_once_with(
            'POST',
            '/_plugins/_ml/tools/_execute/DataDistributionTool',
            body={'parameters': expected_params},
        )

    @pytest.mark.asyncio
    async def test_log_pattern_analysis_tool_minimal_params(self):
        """Test log_pattern_analysis_tool with minimal required parameters."""
        # Setup
        mock_response = {
            'status': 'success',
            'result': {'patterns': [{'pattern': 'ERROR', 'count': 10}]},
        }
        self.mock_client.transport.perform_request.return_value = mock_response

        args = self.LogPatternAnalysisToolArgs(
            index='logs-index',
            logFieldName='message',
            selectionTimeRangeStart='2023-01-01T00:00:00Z',
            selectionTimeRangeEnd='2023-01-02T00:00:00Z',
            timeField='@timestamp',
            opensearch_cluster_name='',
        )

        # Execute
        result = await self._log_pattern_analysis_tool(args)

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'LogPatternAnalysisTool result:' in result[0]['text']

        expected_params = {
            'index': 'logs-index',
            'timeField': '@timestamp',
            'logFieldName': 'message',
            'selectionTimeRangeStart': '2023-01-01T00:00:00Z',
            'selectionTimeRangeEnd': '2023-01-02T00:00:00Z',
        }
        self.mock_client.transport.perform_request.assert_called_once_with(
            'POST',
            '/_plugins/_ml/tools/_execute/LogPatternAnalysisTool',
            body={'parameters': expected_params},
        )

    @pytest.mark.asyncio
    async def test_log_pattern_analysis_tool_all_params(self):
        """Test log_pattern_analysis_tool with all parameters."""
        # Setup
        mock_response = {'status': 'success', 'result': {}}
        self.mock_client.transport.perform_request.return_value = mock_response

        args = self.LogPatternAnalysisToolArgs(
            index='logs-index',
            logFieldName='message',
            selectionTimeRangeStart='2023-01-01T00:00:00Z',
            selectionTimeRangeEnd='2023-01-02T00:00:00Z',
            timeField='@timestamp',
            traceFieldName='trace_id',
            baseTimeRangeStart='2022-12-01T00:00:00Z',
            baseTimeRangeEnd='2022-12-02T00:00:00Z',
            opensearch_cluster_name='',
        )

        # Execute
        await self._log_pattern_analysis_tool(args)

        # Assert
        expected_params = {
            'index': 'logs-index',
            'timeField': '@timestamp',
            'logFieldName': 'message',
            'selectionTimeRangeStart': '2023-01-01T00:00:00Z',
            'selectionTimeRangeEnd': '2023-01-02T00:00:00Z',
            'traceFieldName': 'trace_id',
            'baseTimeRangeStart': '2022-12-01T00:00:00Z',
            'baseTimeRangeEnd': '2022-12-02T00:00:00Z',
        }
        self.mock_client.transport.perform_request.assert_called_once_with(
            'POST',
            '/_plugins/_ml/tools/_execute/LogPatternAnalysisTool',
            body={'parameters': expected_params},
        )

    def test_skills_tools_registry(self):
        """Test SKILLS_TOOLS_REGISTRY structure."""
        expected_tools = [
            'DataDistributionTool',
            'LogPatternAnalysisTool',
        ]

        for tool in expected_tools:
            assert tool in self.SKILLS_TOOLS_REGISTRY
            assert 'display_name' in self.SKILLS_TOOLS_REGISTRY[tool]
            assert 'description' in self.SKILLS_TOOLS_REGISTRY[tool]
            assert 'input_schema' in self.SKILLS_TOOLS_REGISTRY[tool]
            assert 'function' in self.SKILLS_TOOLS_REGISTRY[tool]
            assert 'args_model' in self.SKILLS_TOOLS_REGISTRY[tool]
            assert 'min_version' in self.SKILLS_TOOLS_REGISTRY[tool]
            assert 'http_methods' in self.SKILLS_TOOLS_REGISTRY[tool]

    def test_data_distribution_tool_args_validation(self):
        """Test DataDistributionToolArgs validation."""
        # Test valid inputs
        args = self.DataDistributionToolArgs(
            index='test-index',
            selectionTimeRangeStart='2023-01-01T00:00:00Z',
            selectionTimeRangeEnd='2023-01-02T00:00:00Z',
            timeField='@timestamp',
            opensearch_cluster_name='',
        )
        assert args.index == 'test-index'
        assert args.timeField == '@timestamp'
        assert args.size == 1000  # default value

        # Test with custom size
        args_custom = self.DataDistributionToolArgs(
            index='test-index',
            selectionTimeRangeStart='2023-01-01T00:00:00Z',
            selectionTimeRangeEnd='2023-01-02T00:00:00Z',
            timeField='@timestamp',
            size=500,
            opensearch_cluster_name='',
        )
        assert args_custom.size == 500

    def test_log_pattern_analysis_tool_args_validation(self):
        """Test LogPatternAnalysisToolArgs validation."""
        # Test valid inputs
        args = self.LogPatternAnalysisToolArgs(
            index='logs-index',
            logFieldName='message',
            selectionTimeRangeStart='2023-01-01T00:00:00Z',
            selectionTimeRangeEnd='2023-01-02T00:00:00Z',
            timeField='@timestamp',
            opensearch_cluster_name='',
        )
        assert args.index == 'logs-index'
        assert args.logFieldName == 'message'
        assert args.timeField == '@timestamp'
        assert args.traceFieldName == ''  # default empty value

        # Test with optional fields
        args_full = self.LogPatternAnalysisToolArgs(
            index='logs-index',
            logFieldName='message',
            selectionTimeRangeStart='2023-01-01T00:00:00Z',
            selectionTimeRangeEnd='2023-01-02T00:00:00Z',
            timeField='@timestamp',
            traceFieldName='trace_id',
            baseTimeRangeStart='2022-12-01T00:00:00Z',
            baseTimeRangeEnd='2022-12-02T00:00:00Z',
            opensearch_cluster_name='',
        )
        assert args_full.traceFieldName == 'trace_id'
        assert args_full.baseTimeRangeStart == '2022-12-01T00:00:00Z'

    def test_input_models_validation(self):
        """Test input models validation for required fields."""
        # Test DataDistributionToolArgs - should fail without required fields
        with pytest.raises(ValueError):
            self.DataDistributionToolArgs(opensearch_cluster_name='')  # Missing required fields

        # Test LogPatternAnalysisToolArgs - should fail without required fields
        with pytest.raises(ValueError):
            self.LogPatternAnalysisToolArgs(opensearch_cluster_name='')  # Missing required fields
