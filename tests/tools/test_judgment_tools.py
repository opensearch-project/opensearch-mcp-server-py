# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import pytest
from unittest.mock import AsyncMock, Mock, patch


class TestJudgmentTools:
    def setup_method(self):
        """Setup that runs before each test method."""
        self.mock_client = Mock()
        self.mock_client.info = AsyncMock(return_value={'version': {'number': '3.1.0'}})

        self.mock_client.plugins = Mock()
        self.mock_client.plugins.search_relevance = Mock()
        self.mock_client.plugins.search_relevance.get_judgments = AsyncMock(return_value={})
        self.mock_client.plugins.search_relevance.put_judgments = AsyncMock(return_value={})
        self.mock_client.plugins.search_relevance.delete_judgments = AsyncMock(return_value={})

        self.init_client_patcher = patch(
            'opensearch.client.initialize_client', return_value=self.mock_client
        )
        self.init_client_patcher.start()

        import sys

        for module in ['tools.tools']:
            if module in sys.modules:
                del sys.modules[module]

        from tools.tools import (
            CreateJudgmentListArgs,
            CreateLLMJudgmentListArgs,
            CreateUBIJudgmentListArgs,
            DeleteJudgmentListArgs,
            GetJudgmentListArgs,
            create_judgment_list_tool,
            create_llm_judgment_list_tool,
            create_ubi_judgment_list_tool,
            delete_judgment_list_tool,
            get_judgment_list_tool,
        )

        self.GetJudgmentListArgs = GetJudgmentListArgs
        self.CreateJudgmentListArgs = CreateJudgmentListArgs
        self.CreateLLMJudgmentListArgs = CreateLLMJudgmentListArgs
        self.CreateUBIJudgmentListArgs = CreateUBIJudgmentListArgs
        self.DeleteJudgmentListArgs = DeleteJudgmentListArgs
        self._get_judgment_list_tool = get_judgment_list_tool
        self._create_judgment_list_tool = create_judgment_list_tool
        self._create_llm_judgment_list_tool = create_llm_judgment_list_tool
        self._create_ubi_judgment_list_tool = create_ubi_judgment_list_tool
        self._delete_judgment_list_tool = delete_judgment_list_tool

    def teardown_method(self):
        """Cleanup after each test method."""
        self.init_client_patcher.stop()

    @pytest.mark.asyncio
    async def test_get_judgment_list_tool_success(self):
        """Test successful retrieval of a judgment by ID."""
        judgment_id = 'abc123'
        mock_response = {
            '_id': judgment_id,
            '_source': {
                'name': 'my-judgments',
                'type': 'IMPORT_JUDGMENT',
                'judgmentRatings': [
                    {'query': 'laptop', 'ratings': [{'docId': 'doc1', 'rating': 3}]}
                ],
            },
        }
        self.mock_client.plugins.search_relevance.get_judgments.return_value = mock_response

        result = await self._get_judgment_list_tool(
            self.GetJudgmentListArgs(opensearch_cluster_name='', judgment_id=judgment_id)
        )

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert judgment_id in result[0]['text']
        assert 'my-judgments' in result[0]['text']
        self.mock_client.plugins.search_relevance.get_judgments.assert_called_once_with(
            judgment_id=judgment_id
        )

    @pytest.mark.asyncio
    async def test_get_judgment_list_tool_error(self):
        """Test error handling when retrieving a judgment fails."""
        self.mock_client.plugins.search_relevance.get_judgments.side_effect = Exception(
            'Not found'
        )

        result = await self._get_judgment_list_tool(
            self.GetJudgmentListArgs(opensearch_cluster_name='', judgment_id='missing-id')
        )

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Error retrieving judgment' in result[0]['text']
        assert 'Not found' in result[0]['text']

    @pytest.mark.asyncio
    async def test_create_judgment_list_tool_success(self):
        """Test creating a judgment list with manual relevance ratings."""
        mock_response = {'_id': 'new-id', 'result': 'created'}
        self.mock_client.plugins.search_relevance.put_judgments.return_value = mock_response

        result = await self._create_judgment_list_tool(
            self.CreateJudgmentListArgs(
                opensearch_cluster_name='',
                name='my-judgments',
                judgment_ratings='[{"query": "laptop", "ratings": [{"docId": "doc1", "rating": 3}]}]',
                description='Test judgments',
            )
        )

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Judgment created' in result[0]['text']
        assert 'new-id' in result[0]['text']

        call_kwargs = self.mock_client.plugins.search_relevance.put_judgments.call_args
        body = call_kwargs.kwargs['body']
        assert body['name'] == 'my-judgments'
        assert body['type'] == 'IMPORT_JUDGMENT'
        assert body['description'] == 'Test judgments'
        assert body['judgmentRatings'] == [
            {'query': 'laptop', 'ratings': [{'docId': 'doc1', 'rating': 3}]}
        ]

    @pytest.mark.asyncio
    async def test_create_judgment_list_tool_no_description(self):
        """Test that description is omitted from body when not provided."""
        self.mock_client.plugins.search_relevance.put_judgments.return_value = {'_id': 'id1'}

        await self._create_judgment_list_tool(
            self.CreateJudgmentListArgs(
                opensearch_cluster_name='',
                name='my-judgments',
                judgment_ratings='[{"query": "laptop", "ratings": [{"docId": "doc1", "rating": 3}]}]',
            )
        )

        call_kwargs = self.mock_client.plugins.search_relevance.put_judgments.call_args
        body = call_kwargs.kwargs['body']
        assert 'description' not in body

    @pytest.mark.asyncio
    async def test_create_judgment_list_tool_invalid_json(self):
        """Test that invalid judgment_ratings JSON returns an error."""
        result = await self._create_judgment_list_tool(
            self.CreateJudgmentListArgs(
                opensearch_cluster_name='',
                name='my-judgments',
                judgment_ratings='not-valid-json',
            )
        )

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Error creating judgment' in result[0]['text']

    @pytest.mark.asyncio
    async def test_create_judgment_list_tool_error(self):
        """Test error handling when creating a judgment fails."""
        self.mock_client.plugins.search_relevance.put_judgments.side_effect = Exception(
            'Index not found'
        )

        result = await self._create_judgment_list_tool(
            self.CreateJudgmentListArgs(
                opensearch_cluster_name='',
                name='my-judgments',
                judgment_ratings='[{"query": "laptop", "ratings": [{"docId": "doc1", "rating": 3}]}]',
            )
        )

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Error creating judgment' in result[0]['text']
        assert 'Index not found' in result[0]['text']

    @pytest.mark.asyncio
    async def test_create_ubi_judgment_list_tool_success(self):
        """Test successful creation of a UBI judgment."""
        mock_response = {'_id': 'ubi-id', 'result': 'created', 'status': 'PROCESSING'}
        self.mock_client.plugins.search_relevance.put_judgments.return_value = mock_response

        result = await self._create_ubi_judgment_list_tool(
            self.CreateUBIJudgmentListArgs(
                opensearch_cluster_name='',
                name='ubi-judgments',
                click_model='coec',
                max_rank=20,
            )
        )

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'UBI judgment created' in result[0]['text']
        assert 'ubi-id' in result[0]['text']

        call_kwargs = self.mock_client.plugins.search_relevance.put_judgments.call_args
        body = call_kwargs.kwargs['body']
        assert body['name'] == 'ubi-judgments'
        assert body['type'] == 'UBI_JUDGMENT'
        assert body['clickModel'] == 'coec'
        assert body['maxRank'] == 20
        assert 'startDate' not in body
        assert 'endDate' not in body

    @pytest.mark.asyncio
    async def test_create_ubi_judgment_list_tool_with_date_range(self):
        """Test UBI judgment creation with optional start and end dates."""
        self.mock_client.plugins.search_relevance.put_judgments.return_value = {'_id': 'id1'}

        await self._create_ubi_judgment_list_tool(
            self.CreateUBIJudgmentListArgs(
                opensearch_cluster_name='',
                name='ubi-judgments-q1',
                click_model='coec',
                max_rank=10,
                start_date='2024-01-01',
                end_date='2024-03-31',
            )
        )

        call_kwargs = self.mock_client.plugins.search_relevance.put_judgments.call_args
        body = call_kwargs.kwargs['body']
        assert body['startDate'] == '2024-01-01'
        assert body['endDate'] == '2024-03-31'

    @pytest.mark.asyncio
    async def test_create_ubi_judgment_list_tool_error(self):
        """Test error handling when creating a UBI judgment fails."""
        self.mock_client.plugins.search_relevance.put_judgments.side_effect = Exception(
            'UBI index not found'
        )

        result = await self._create_ubi_judgment_list_tool(
            self.CreateUBIJudgmentListArgs(
                opensearch_cluster_name='',
                name='ubi-judgments',
                click_model='coec',
            )
        )

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Error creating UBI judgment' in result[0]['text']
        assert 'UBI index not found' in result[0]['text']

    @pytest.mark.asyncio
    async def test_delete_judgment_list_tool_success(self):
        """Test successful deletion of a judgment by ID."""
        judgment_id = 'abc123'
        mock_response = {'_id': judgment_id, 'result': 'deleted'}
        self.mock_client.plugins.search_relevance.delete_judgments.return_value = mock_response

        result = await self._delete_judgment_list_tool(
            self.DeleteJudgmentListArgs(opensearch_cluster_name='', judgment_id=judgment_id)
        )

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert judgment_id in result[0]['text']
        assert 'deleted' in result[0]['text']
        self.mock_client.plugins.search_relevance.delete_judgments.assert_called_once_with(
            judgment_id=judgment_id
        )

    @pytest.mark.asyncio
    async def test_delete_judgment_list_tool_error(self):
        """Test error handling when deleting a judgment fails."""
        self.mock_client.plugins.search_relevance.delete_judgments.side_effect = Exception(
            'Judgment not found'
        )

        result = await self._delete_judgment_list_tool(
            self.DeleteJudgmentListArgs(opensearch_cluster_name='', judgment_id='missing-id')
        )

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Error deleting judgment' in result[0]['text']
        assert 'Judgment not found' in result[0]['text']

    @pytest.mark.asyncio
    async def test_create_llm_judgment_list_tool_success(self):
        """Test successful creation of an LLM judgment list."""
        mock_response = {'_id': 'llm-id', 'result': 'created', 'status': 'PROCESSING'}
        self.mock_client.plugins.search_relevance.put_judgments.return_value = mock_response

        result = await self._create_llm_judgment_list_tool(
            self.CreateLLMJudgmentListArgs(
                opensearch_cluster_name='',
                name='llm-judgments',
                query_set_id='qs-123',
                search_configuration_id='sc-456',
                model_id='model-789',
                size=5,
            )
        )

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'LLM judgment list created' in result[0]['text']
        assert 'llm-id' in result[0]['text']

        call_kwargs = self.mock_client.plugins.search_relevance.put_judgments.call_args
        body = call_kwargs.kwargs['body']
        assert body['name'] == 'llm-judgments'
        assert body['type'] == 'LLM_JUDGMENT'
        assert body['querySetId'] == 'qs-123'
        assert body['searchConfigurationList'] == ['sc-456']
        assert body['modelId'] == 'model-789'
        assert body['size'] == 5
        assert body['contextFields'] == []

    @pytest.mark.asyncio
    async def test_create_llm_judgment_list_tool_with_context_fields(self):
        """Test LLM judgment creation with explicit context fields."""
        self.mock_client.plugins.search_relevance.put_judgments.return_value = {'_id': 'id1'}

        await self._create_llm_judgment_list_tool(
            self.CreateLLMJudgmentListArgs(
                opensearch_cluster_name='',
                name='llm-judgments',
                query_set_id='qs-123',
                search_configuration_id='sc-456',
                model_id='model-789',
                context_fields='["title", "description"]',
            )
        )

        call_kwargs = self.mock_client.plugins.search_relevance.put_judgments.call_args
        body = call_kwargs.kwargs['body']
        assert body['contextFields'] == ['title', 'description']

    @pytest.mark.asyncio
    async def test_create_llm_judgment_list_tool_invalid_context_fields(self):
        """Test that invalid context_fields JSON returns an error."""
        result = await self._create_llm_judgment_list_tool(
            self.CreateLLMJudgmentListArgs(
                opensearch_cluster_name='',
                name='llm-judgments',
                query_set_id='qs-123',
                search_configuration_id='sc-456',
                model_id='model-789',
                context_fields='not-valid-json',
            )
        )

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Error creating LLM judgment list' in result[0]['text']

    @pytest.mark.asyncio
    async def test_create_llm_judgment_list_tool_error(self):
        """Test error handling when creating an LLM judgment list fails."""
        self.mock_client.plugins.search_relevance.put_judgments.side_effect = Exception(
            'Model not found'
        )

        result = await self._create_llm_judgment_list_tool(
            self.CreateLLMJudgmentListArgs(
                opensearch_cluster_name='',
                name='llm-judgments',
                query_set_id='qs-123',
                search_configuration_id='sc-456',
                model_id='invalid-model',
            )
        )

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Error creating LLM judgment list' in result[0]['text']
        assert 'Model not found' in result[0]['text']

    @pytest.mark.asyncio
    async def test_judgment_tools_registered_in_registry(self):
        """Test that all judgment tools are registered in the TOOL_REGISTRY."""
        import sys

        for module in ['tools.tools']:
            if module in sys.modules:
                del sys.modules[module]

        from tools.tools import TOOL_REGISTRY

        assert 'GetJudgmentListTool' in TOOL_REGISTRY
        assert 'CreateJudgmentListTool' in TOOL_REGISTRY
        assert 'CreateUBIJudgmentListTool' in TOOL_REGISTRY
        assert 'CreateLLMJudgmentListTool' in TOOL_REGISTRY
        assert 'DeleteJudgmentListTool' in TOOL_REGISTRY

        for tool_name in [
            'GetJudgmentListTool',
            'CreateJudgmentListTool',
            'CreateUBIJudgmentListTool',
            'CreateLLMJudgmentListTool',
            'DeleteJudgmentListTool',
        ]:
            tool = TOOL_REGISTRY[tool_name]
            assert 'description' in tool
            assert 'input_schema' in tool
            assert 'function' in tool
            assert 'args_model' in tool
            assert tool.get('min_version') == '3.1.0'
