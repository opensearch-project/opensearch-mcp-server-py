# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import pytest
from unittest.mock import AsyncMock, Mock, patch


class TestExperimentTools:
    def setup_method(self):
        """Setup that runs before each test method."""
        self.mock_client = Mock()
        self.mock_client.info = AsyncMock(return_value={'version': {'number': '3.1.0'}})

        self.mock_client.plugins = Mock()
        self.mock_client.plugins.search_relevance = Mock()
        self.mock_client.plugins.search_relevance.get_experiments = AsyncMock(return_value={})
        self.mock_client.plugins.search_relevance.put_experiments = AsyncMock(return_value={})
        self.mock_client.plugins.search_relevance.delete_experiments = AsyncMock(return_value={})

        self.init_client_patcher = patch(
            'opensearch.client.initialize_client', return_value=self.mock_client
        )
        self.init_client_patcher.start()

        import sys

        for module in ['tools.tools']:
            if module in sys.modules:
                del sys.modules[module]

        from tools.tools import (
            CreateExperimentArgs,
            DeleteExperimentArgs,
            GetExperimentArgs,
            create_experiment_tool,
            delete_experiment_tool,
            get_experiment_tool,
        )

        self.GetExperimentArgs = GetExperimentArgs
        self.CreateExperimentArgs = CreateExperimentArgs
        self.DeleteExperimentArgs = DeleteExperimentArgs
        self._get_experiment_tool = get_experiment_tool
        self._create_experiment_tool = create_experiment_tool
        self._delete_experiment_tool = delete_experiment_tool

    def teardown_method(self):
        """Cleanup after each test method."""
        self.init_client_patcher.stop()

    @pytest.mark.asyncio
    async def test_get_experiment_tool_success(self):
        """Test successful retrieval of an experiment by ID."""
        experiment_id = 'exp-abc123'
        mock_response = {
            '_id': experiment_id,
            '_source': {
                'type': 'PAIRWISE_COMPARISON',
                'status': 'COMPLETED',
                'querySetId': 'qs-1',
            },
        }
        self.mock_client.plugins.search_relevance.get_experiments.return_value = mock_response

        result = await self._get_experiment_tool(
            self.GetExperimentArgs(opensearch_cluster_name='', experiment_id=experiment_id)
        )

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert experiment_id in result[0]['text']
        assert 'PAIRWISE_COMPARISON' in result[0]['text']
        self.mock_client.plugins.search_relevance.get_experiments.assert_called_once_with(
            experiment_id=experiment_id
        )

    @pytest.mark.asyncio
    async def test_get_experiment_tool_error(self):
        """Test error handling when retrieving an experiment fails."""
        self.mock_client.plugins.search_relevance.get_experiments.side_effect = Exception(
            'Experiment not found'
        )

        result = await self._get_experiment_tool(
            self.GetExperimentArgs(opensearch_cluster_name='', experiment_id='missing-id')
        )

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Error retrieving experiment' in result[0]['text']
        assert 'Experiment not found' in result[0]['text']

    @pytest.mark.asyncio
    async def test_create_experiment_tool_pairwise(self):
        """Test creating a PAIRWISE_COMPARISON experiment with 2 configs."""
        mock_response = {'_id': 'exp-new', 'result': 'created'}
        self.mock_client.plugins.search_relevance.put_experiments.return_value = mock_response

        result = await self._create_experiment_tool(
            self.CreateExperimentArgs(
                opensearch_cluster_name='',
                query_set_id='qs-1',
                search_configuration_ids='["config-1", "config-2"]',
                experiment_type='PAIRWISE_COMPARISON',
                size=10,
            )
        )

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Experiment created' in result[0]['text']
        assert 'exp-new' in result[0]['text']

        call_kwargs = self.mock_client.plugins.search_relevance.put_experiments.call_args
        body = call_kwargs.kwargs['body']
        assert body['querySetId'] == 'qs-1'
        assert body['searchConfigurationList'] == ['config-1', 'config-2']
        assert body['type'] == 'PAIRWISE_COMPARISON'
        assert body['size'] == 10
        assert 'judgmentList' not in body

    @pytest.mark.asyncio
    async def test_create_experiment_tool_pointwise(self):
        """Test creating a POINTWISE_EVALUATION experiment with 1 config and judgment lists."""
        mock_response = {'_id': 'exp-new', 'result': 'created'}
        self.mock_client.plugins.search_relevance.put_experiments.return_value = mock_response

        result = await self._create_experiment_tool(
            self.CreateExperimentArgs(
                opensearch_cluster_name='',
                query_set_id='qs-1',
                search_configuration_ids='["config-1"]',
                experiment_type='POINTWISE_EVALUATION',
                judgment_list_ids='["judgment-1", "judgment-2"]',
            )
        )

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Experiment created' in result[0]['text']

        call_kwargs = self.mock_client.plugins.search_relevance.put_experiments.call_args
        body = call_kwargs.kwargs['body']
        assert body['type'] == 'POINTWISE_EVALUATION'
        assert body['searchConfigurationList'] == ['config-1']
        assert body['judgmentList'] == ['judgment-1', 'judgment-2']

    @pytest.mark.asyncio
    async def test_create_experiment_tool_hybrid_optimizer(self):
        """Test creating a HYBRID_OPTIMIZER experiment."""
        mock_response = {'_id': 'exp-hybrid', 'result': 'created'}
        self.mock_client.plugins.search_relevance.put_experiments.return_value = mock_response

        result = await self._create_experiment_tool(
            self.CreateExperimentArgs(
                opensearch_cluster_name='',
                query_set_id='qs-1',
                search_configuration_ids='["config-1"]',
                experiment_type='HYBRID_OPTIMIZER',
                judgment_list_ids='["judgment-1"]',
            )
        )

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Experiment created' in result[0]['text']

        call_kwargs = self.mock_client.plugins.search_relevance.put_experiments.call_args
        body = call_kwargs.kwargs['body']
        assert body['type'] == 'HYBRID_OPTIMIZER'
        assert body['judgmentList'] == ['judgment-1']

    @pytest.mark.asyncio
    async def test_create_experiment_pairwise_wrong_config_count(self):
        """Test that PAIRWISE_COMPARISON with != 2 configs returns an error."""
        result = await self._create_experiment_tool(
            self.CreateExperimentArgs(
                opensearch_cluster_name='',
                query_set_id='qs-1',
                search_configuration_ids='["config-1"]',
                experiment_type='PAIRWISE_COMPARISON',
            )
        )

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Error creating experiment' in result[0]['text']
        assert 'PAIRWISE_COMPARISON requires exactly 2' in result[0]['text']
        self.mock_client.plugins.search_relevance.put_experiments.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_experiment_pointwise_wrong_config_count(self):
        """Test that POINTWISE_EVALUATION with != 1 config returns an error."""
        result = await self._create_experiment_tool(
            self.CreateExperimentArgs(
                opensearch_cluster_name='',
                query_set_id='qs-1',
                search_configuration_ids='["config-1", "config-2"]',
                experiment_type='POINTWISE_EVALUATION',
                judgment_list_ids='["judgment-1"]',
            )
        )

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Error creating experiment' in result[0]['text']
        assert 'POINTWISE_EVALUATION requires exactly 1' in result[0]['text']
        self.mock_client.plugins.search_relevance.put_experiments.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_experiment_pointwise_missing_judgment_lists(self):
        """Test that POINTWISE_EVALUATION without judgment_list_ids returns an error."""
        result = await self._create_experiment_tool(
            self.CreateExperimentArgs(
                opensearch_cluster_name='',
                query_set_id='qs-1',
                search_configuration_ids='["config-1"]',
                experiment_type='POINTWISE_EVALUATION',
            )
        )

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Error creating experiment' in result[0]['text']
        assert 'judgment_list_ids' in result[0]['text']
        self.mock_client.plugins.search_relevance.put_experiments.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_experiment_invalid_search_config_json(self):
        """Test that invalid JSON for search_configuration_ids returns an error."""
        result = await self._create_experiment_tool(
            self.CreateExperimentArgs(
                opensearch_cluster_name='',
                query_set_id='qs-1',
                search_configuration_ids='not-valid-json',
                experiment_type='PAIRWISE_COMPARISON',
            )
        )

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Error creating experiment' in result[0]['text']
        self.mock_client.plugins.search_relevance.put_experiments.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_experiment_tool_error(self):
        """Test error handling when creating an experiment fails."""
        self.mock_client.plugins.search_relevance.put_experiments.side_effect = Exception(
            'Server error'
        )

        result = await self._create_experiment_tool(
            self.CreateExperimentArgs(
                opensearch_cluster_name='',
                query_set_id='qs-1',
                search_configuration_ids='["config-1", "config-2"]',
                experiment_type='PAIRWISE_COMPARISON',
            )
        )

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Error creating experiment' in result[0]['text']
        assert 'Server error' in result[0]['text']

    @pytest.mark.asyncio
    async def test_delete_experiment_tool_success(self):
        """Test successful deletion of an experiment by ID."""
        experiment_id = 'exp-abc123'
        mock_response = {'_id': experiment_id, 'result': 'deleted'}
        self.mock_client.plugins.search_relevance.delete_experiments.return_value = mock_response

        result = await self._delete_experiment_tool(
            self.DeleteExperimentArgs(opensearch_cluster_name='', experiment_id=experiment_id)
        )

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert experiment_id in result[0]['text']
        assert 'deleted' in result[0]['text']
        self.mock_client.plugins.search_relevance.delete_experiments.assert_called_once_with(
            experiment_id=experiment_id
        )

    @pytest.mark.asyncio
    async def test_delete_experiment_tool_error(self):
        """Test error handling when deleting an experiment fails."""
        self.mock_client.plugins.search_relevance.delete_experiments.side_effect = Exception(
            'Experiment not found'
        )

        result = await self._delete_experiment_tool(
            self.DeleteExperimentArgs(opensearch_cluster_name='', experiment_id='missing-id')
        )

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Error deleting experiment' in result[0]['text']
        assert 'Experiment not found' in result[0]['text']

    @pytest.mark.asyncio
    async def test_experiment_tools_registered_in_registry(self):
        """Test that all experiment tools are registered in the TOOL_REGISTRY."""
        import sys

        for module in ['tools.tools']:
            if module in sys.modules:
                del sys.modules[module]

        from tools.tools import TOOL_REGISTRY

        assert 'GetExperimentTool' in TOOL_REGISTRY
        assert 'CreateExperimentTool' in TOOL_REGISTRY
        assert 'DeleteExperimentTool' in TOOL_REGISTRY

        for tool_name in ['GetExperimentTool', 'CreateExperimentTool', 'DeleteExperimentTool']:
            tool = TOOL_REGISTRY[tool_name]
            assert 'description' in tool
            assert 'input_schema' in tool
            assert 'function' in tool
            assert 'args_model' in tool
            assert tool.get('min_version') == '3.1.0'
