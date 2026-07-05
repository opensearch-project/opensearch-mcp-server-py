# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import pytest
from unittest.mock import AsyncMock, Mock, patch


class TestQuerySetTools:
    def setup_method(self):
        """Setup that runs before each test method."""
        self.mock_client = Mock()
        self.mock_client.info = AsyncMock(return_value={'version': {'number': '3.1.0'}})

        self.mock_client.plugins = Mock()
        self.mock_client.plugins.search_relevance = Mock()
        self.mock_client.plugins.search_relevance.get_query_sets = AsyncMock(return_value={})
        self.mock_client.plugins.search_relevance.put_query_sets = AsyncMock(return_value={})
        self.mock_client.plugins.search_relevance.post_query_sets = AsyncMock(return_value={})
        self.mock_client.plugins.search_relevance.delete_query_sets = AsyncMock(return_value={})

        self.init_client_patcher = patch(
            'opensearch.client.initialize_client', return_value=self.mock_client
        )
        self.init_client_patcher.start()

        import sys

        for module in ['tools.tools']:
            if module in sys.modules:
                del sys.modules[module]

        from tools.tools import (
            CreateQuerySetArgs,
            DeleteQuerySetArgs,
            GetQuerySetArgs,
            SampleQuerySetArgs,
            create_query_set_tool,
            delete_query_set_tool,
            get_query_set_tool,
            sample_query_set_tool,
        )

        self.GetQuerySetArgs = GetQuerySetArgs
        self.CreateQuerySetArgs = CreateQuerySetArgs
        self.SampleQuerySetArgs = SampleQuerySetArgs
        self.DeleteQuerySetArgs = DeleteQuerySetArgs
        self._get_query_set_tool = get_query_set_tool
        self._create_query_set_tool = create_query_set_tool
        self._sample_query_set_tool = sample_query_set_tool
        self._delete_query_set_tool = delete_query_set_tool

    def teardown_method(self):
        """Cleanup after each test method."""
        self.init_client_patcher.stop()

    @pytest.mark.asyncio
    async def test_get_query_set_tool_success(self):
        """Test successful retrieval of a query set by ID."""
        query_set_id = 'abc123'
        mock_response = {
            '_id': query_set_id,
            '_source': {
                'name': 'my-query-set',
                'description': 'Test queries',
                'querySetQueries': [{'queryText': 'laptop'}],
            },
        }
        self.mock_client.plugins.search_relevance.get_query_sets.return_value = mock_response

        result = await self._get_query_set_tool(
            self.GetQuerySetArgs(opensearch_cluster_name='', query_set_id=query_set_id)
        )

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert query_set_id in result[0]['text']
        assert 'my-query-set' in result[0]['text']
        self.mock_client.plugins.search_relevance.get_query_sets.assert_called_once_with(
            query_set_id=query_set_id
        )

    @pytest.mark.asyncio
    async def test_get_query_set_tool_error(self):
        """Test error handling when retrieving a query set fails."""
        self.mock_client.plugins.search_relevance.get_query_sets.side_effect = Exception(
            'Not found'
        )

        result = await self._get_query_set_tool(
            self.GetQuerySetArgs(opensearch_cluster_name='', query_set_id='missing-id')
        )

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Error retrieving query set' in result[0]['text']
        assert 'Not found' in result[0]['text']

    @pytest.mark.asyncio
    async def test_create_query_set_tool_string_queries(self):
        """Test creating a query set with a list of plain string queries."""
        mock_response = {'_id': 'new-id', 'result': 'created'}
        self.mock_client.plugins.search_relevance.put_query_sets.return_value = mock_response

        result = await self._create_query_set_tool(
            self.CreateQuerySetArgs(
                opensearch_cluster_name='',
                name='my-set',
                queries='["laptop", "headphones"]',
                description='Test set',
            )
        )

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Query set created' in result[0]['text']
        assert 'new-id' in result[0]['text']

        call_kwargs = self.mock_client.plugins.search_relevance.put_query_sets.call_args
        body = call_kwargs.kwargs['body']
        assert body['name'] == 'my-set'
        assert body['sampling'] == 'manual'
        assert body['querySetQueries'] == [
            {'queryText': 'laptop'},
            {'queryText': 'headphones'},
        ]

    @pytest.mark.asyncio
    async def test_create_query_set_tool_dict_queries(self):
        """Test creating a query set with queries already in queryText dict format."""
        mock_response = {'_id': 'new-id', 'result': 'created'}
        self.mock_client.plugins.search_relevance.put_query_sets.return_value = mock_response

        result = await self._create_query_set_tool(
            self.CreateQuerySetArgs(
                opensearch_cluster_name='',
                name='my-set',
                queries='[{"queryText": "laptop"}, {"queryText": "monitor"}]',
            )
        )

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Query set created' in result[0]['text']

        call_kwargs = self.mock_client.plugins.search_relevance.put_query_sets.call_args
        body = call_kwargs.kwargs['body']
        assert body['querySetQueries'] == [
            {'queryText': 'laptop'},
            {'queryText': 'monitor'},
        ]

    @pytest.mark.asyncio
    async def test_create_query_set_tool_default_description(self):
        """Test that description defaults to 'Query set: <name>' when not provided."""
        self.mock_client.plugins.search_relevance.put_query_sets.return_value = {'_id': 'id1'}

        await self._create_query_set_tool(
            self.CreateQuerySetArgs(
                opensearch_cluster_name='',
                name='my-set',
                queries='["query1"]',
            )
        )

        call_kwargs = self.mock_client.plugins.search_relevance.put_query_sets.call_args
        body = call_kwargs.kwargs['body']
        assert body['description'] == 'Query set: my-set'

    @pytest.mark.asyncio
    async def test_create_query_set_tool_invalid_queries(self):
        """Test that invalid queries JSON returns an error."""
        result = await self._create_query_set_tool(
            self.CreateQuerySetArgs(
                opensearch_cluster_name='',
                name='my-set',
                queries='not-valid-json',
            )
        )

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Error creating query set' in result[0]['text']

    @pytest.mark.asyncio
    async def test_sample_query_set_tool_success(self):
        """Test successful sampling of a query set from UBI data."""
        mock_response = {'_id': 'sampled-id', 'result': 'created'}
        self.mock_client.plugins.search_relevance.post_query_sets.return_value = mock_response

        result = await self._sample_query_set_tool(
            self.SampleQuerySetArgs(
                opensearch_cluster_name='',
                name='top-queries',
                query_set_size=20,
            )
        )

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Query set sampled' in result[0]['text']
        assert 'sampled-id' in result[0]['text']

        call_kwargs = self.mock_client.plugins.search_relevance.post_query_sets.call_args
        body = call_kwargs.kwargs['body']
        assert body['name'] == 'top-queries'
        assert body['sampling'] == 'topn'
        assert body['querySetSize'] == 20

    @pytest.mark.asyncio
    async def test_sample_query_set_tool_custom_sampling(self):
        """Test sampling a query set with a non-default sampling method."""
        self.mock_client.plugins.search_relevance.post_query_sets.return_value = {
            '_id': 'random-id',
            'result': 'created',
        }

        result = await self._sample_query_set_tool(
            self.SampleQuerySetArgs(
                opensearch_cluster_name='',
                name='random-queries',
                query_set_size=30,
                sampling='random',
            )
        )

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Query set sampled' in result[0]['text']

        call_kwargs = self.mock_client.plugins.search_relevance.post_query_sets.call_args
        body = call_kwargs.kwargs['body']
        assert body['sampling'] == 'random'
        assert body['querySetSize'] == 30

    @pytest.mark.asyncio
    async def test_sample_query_set_tool_default_description(self):
        """Test that description defaults to a generated string when not provided."""
        self.mock_client.plugins.search_relevance.post_query_sets.return_value = {'_id': 'id1'}

        await self._sample_query_set_tool(
            self.SampleQuerySetArgs(
                opensearch_cluster_name='',
                name='top-queries',
                query_set_size=50,
            )
        )

        call_kwargs = self.mock_client.plugins.search_relevance.post_query_sets.call_args
        body = call_kwargs.kwargs['body']
        assert body['description'] == 'Query set: top-queries (topn, size=50)'

    @pytest.mark.asyncio
    async def test_sample_query_set_tool_error(self):
        """Test error handling when sampling a query set fails."""
        self.mock_client.plugins.search_relevance.post_query_sets.side_effect = Exception(
            'UBI index not found'
        )

        result = await self._sample_query_set_tool(
            self.SampleQuerySetArgs(
                opensearch_cluster_name='',
                name='top-queries',
                query_set_size=20,
            )
        )

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Error sampling query set' in result[0]['text']
        assert 'UBI index not found' in result[0]['text']

    @pytest.mark.asyncio
    async def test_delete_query_set_tool_success(self):
        """Test successful deletion of a query set by ID."""
        query_set_id = 'abc123'
        mock_response = {'_id': query_set_id, 'result': 'deleted'}
        self.mock_client.plugins.search_relevance.delete_query_sets.return_value = mock_response

        result = await self._delete_query_set_tool(
            self.DeleteQuerySetArgs(opensearch_cluster_name='', query_set_id=query_set_id)
        )

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert query_set_id in result[0]['text']
        assert 'deleted' in result[0]['text']
        self.mock_client.plugins.search_relevance.delete_query_sets.assert_called_once_with(
            query_set_id=query_set_id
        )

    @pytest.mark.asyncio
    async def test_delete_query_set_tool_error(self):
        """Test error handling when deleting a query set fails."""
        self.mock_client.plugins.search_relevance.delete_query_sets.side_effect = Exception(
            'Query set not found'
        )

        result = await self._delete_query_set_tool(
            self.DeleteQuerySetArgs(opensearch_cluster_name='', query_set_id='missing-id')
        )

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Error deleting query set' in result[0]['text']
        assert 'Query set not found' in result[0]['text']

    @pytest.mark.asyncio
    async def test_query_set_tools_registered_in_registry(self):
        """Test that all query set tools are registered in the TOOL_REGISTRY."""
        import sys

        for module in ['tools.tools']:
            if module in sys.modules:
                del sys.modules[module]

        from tools.tools import TOOL_REGISTRY

        assert 'GetQuerySetTool' in TOOL_REGISTRY
        assert 'CreateQuerySetTool' in TOOL_REGISTRY
        assert 'SampleQuerySetTool' in TOOL_REGISTRY
        assert 'DeleteQuerySetTool' in TOOL_REGISTRY

        for tool_name in [
            'GetQuerySetTool',
            'CreateQuerySetTool',
            'SampleQuerySetTool',
            'DeleteQuerySetTool',
        ]:
            tool = TOOL_REGISTRY[tool_name]
            assert 'description' in tool
            assert 'input_schema' in tool
            assert 'function' in tool
            assert 'args_model' in tool
            assert tool.get('min_version') == '3.1.0'
