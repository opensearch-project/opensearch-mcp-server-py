# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import json
import pytest
from unittest.mock import AsyncMock, Mock, patch


class TestSRWSearchTools:
    def setup_method(self):
        """Setup that runs before each test method."""
        self.mock_client = Mock()
        self.mock_client.info = AsyncMock(return_value={'version': {'number': '3.5.0'}})
        self.mock_client.transport = Mock()
        self.mock_client.transport.perform_request = AsyncMock(return_value={})

        self.init_client_patcher = patch(
            'opensearch.client.initialize_client', return_value=self.mock_client
        )
        self.init_client_patcher.start()

        import sys

        for module in ['tools.tools']:
            if module in sys.modules:
                del sys.modules[module]

        from tools.tools import (
            SearchExperimentsArgs,
            SearchJudgmentsArgs,
            SearchQuerySetsArgs,
            SearchSearchConfigurationsArgs,
            search_experiments_tool,
            search_judgments_tool,
            search_query_sets_tool,
            search_search_configurations_tool,
        )

        self.SearchQuerySetsArgs = SearchQuerySetsArgs
        self.SearchSearchConfigurationsArgs = SearchSearchConfigurationsArgs
        self.SearchJudgmentsArgs = SearchJudgmentsArgs
        self.SearchExperimentsArgs = SearchExperimentsArgs
        self._search_query_sets_tool = search_query_sets_tool
        self._search_search_configurations_tool = search_search_configurations_tool
        self._search_judgments_tool = search_judgments_tool
        self._search_experiments_tool = search_experiments_tool

    def teardown_method(self):
        """Cleanup after each test method."""
        self.init_client_patcher.stop()

    # --- SearchQuerySetsTool ---

    @pytest.mark.asyncio
    async def test_search_query_sets_default_query(self):
        """Test that SearchQuerySetsTool uses match_all when no query body is provided."""
        mock_response = {'hits': {'total': {'value': 2}, 'hits': []}}
        self.mock_client.transport.perform_request.return_value = mock_response

        result = await self._search_query_sets_tool(
            self.SearchQuerySetsArgs(opensearch_cluster_name='')
        )

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Query set search results' in result[0]['text']

        call_kwargs = self.mock_client.transport.perform_request.call_args
        assert call_kwargs.kwargs['method'] == 'POST'
        assert call_kwargs.kwargs['url'] == '/_plugins/_search_relevance/query_sets/_search'
        body = json.loads(call_kwargs.kwargs['body'])
        assert body == {'query': {'match_all': {}}}

    @pytest.mark.asyncio
    async def test_search_query_sets_custom_query(self):
        """Test SearchQuerySetsTool with a custom query DSL body."""
        mock_response = {'hits': {'total': {'value': 1}, 'hits': []}}
        self.mock_client.transport.perform_request.return_value = mock_response

        query_body = {'query': {'match': {'name': 'my-set'}}, 'size': 5}
        result = await self._search_query_sets_tool(
            self.SearchQuerySetsArgs(opensearch_cluster_name='', query_body=query_body)
        )

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Query set search results' in result[0]['text']

        call_kwargs = self.mock_client.transport.perform_request.call_args
        body = json.loads(call_kwargs.kwargs['body'])
        assert body == query_body

    @pytest.mark.asyncio
    async def test_search_query_sets_error(self):
        """Test error handling for SearchQuerySetsTool."""
        self.mock_client.transport.perform_request.side_effect = Exception('Connection refused')

        result = await self._search_query_sets_tool(
            self.SearchQuerySetsArgs(opensearch_cluster_name='')
        )

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Error searching query sets' in result[0]['text']
        assert 'Connection refused' in result[0]['text']

    # --- SearchSearchConfigurationsTool ---

    @pytest.mark.asyncio
    async def test_search_search_configurations_default_query(self):
        """Test that SearchSearchConfigurationsTool uses match_all when no query body provided."""
        mock_response = {'hits': {'total': {'value': 3}, 'hits': []}}
        self.mock_client.transport.perform_request.return_value = mock_response

        result = await self._search_search_configurations_tool(
            self.SearchSearchConfigurationsArgs(opensearch_cluster_name='')
        )

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Search configuration search results' in result[0]['text']

        call_kwargs = self.mock_client.transport.perform_request.call_args
        assert (
            call_kwargs.kwargs['url']
            == '/_plugins/_search_relevance/search_configurations/_search'
        )
        body = json.loads(call_kwargs.kwargs['body'])
        assert body == {'query': {'match_all': {}}}

    @pytest.mark.asyncio
    async def test_search_search_configurations_custom_query(self):
        """Test SearchSearchConfigurationsTool with a custom query DSL body."""
        mock_response = {'hits': {'total': {'value': 1}, 'hits': []}}
        self.mock_client.transport.perform_request.return_value = mock_response

        query_body = {'query': {'match': {'name': 'bm25'}}, 'size': 10}
        await self._search_search_configurations_tool(
            self.SearchSearchConfigurationsArgs(opensearch_cluster_name='', query_body=query_body)
        )

        call_kwargs = self.mock_client.transport.perform_request.call_args
        body = json.loads(call_kwargs.kwargs['body'])
        assert body == query_body

    @pytest.mark.asyncio
    async def test_search_search_configurations_error(self):
        """Test error handling for SearchSearchConfigurationsTool."""
        self.mock_client.transport.perform_request.side_effect = Exception('Not found')

        result = await self._search_search_configurations_tool(
            self.SearchSearchConfigurationsArgs(opensearch_cluster_name='')
        )

        assert 'Error searching search configurations' in result[0]['text']
        assert 'Not found' in result[0]['text']

    # --- SearchJudgmentsTool ---

    @pytest.mark.asyncio
    async def test_search_judgments_default_query(self):
        """Test that SearchJudgmentsTool uses match_all when no query body is provided."""
        mock_response = {'hits': {'total': {'value': 5}, 'hits': []}}
        self.mock_client.transport.perform_request.return_value = mock_response

        result = await self._search_judgments_tool(
            self.SearchJudgmentsArgs(opensearch_cluster_name='')
        )

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Judgment search results' in result[0]['text']

        call_kwargs = self.mock_client.transport.perform_request.call_args
        assert call_kwargs.kwargs['url'] == '/_plugins/_search_relevance/judgments/_search'
        body = json.loads(call_kwargs.kwargs['body'])
        assert body == {'query': {'match_all': {}}}

    @pytest.mark.asyncio
    async def test_search_judgments_custom_query(self):
        """Test SearchJudgmentsTool with a custom query DSL body."""
        mock_response = {'hits': {'total': {'value': 1}, 'hits': []}}
        self.mock_client.transport.perform_request.return_value = mock_response

        query_body = {'query': {'match': {'name': 'my-judgments'}}}
        await self._search_judgments_tool(
            self.SearchJudgmentsArgs(opensearch_cluster_name='', query_body=query_body)
        )

        call_kwargs = self.mock_client.transport.perform_request.call_args
        body = json.loads(call_kwargs.kwargs['body'])
        assert body == query_body

    @pytest.mark.asyncio
    async def test_search_judgments_error(self):
        """Test error handling for SearchJudgmentsTool."""
        self.mock_client.transport.perform_request.side_effect = Exception('Timeout')

        result = await self._search_judgments_tool(
            self.SearchJudgmentsArgs(opensearch_cluster_name='')
        )

        assert 'Error searching judgments' in result[0]['text']
        assert 'Timeout' in result[0]['text']

    # --- SearchExperimentsTool ---

    @pytest.mark.asyncio
    async def test_search_experiments_default_query(self):
        """Test that SearchExperimentsTool uses match_all when no query body is provided."""
        mock_response = {'hits': {'total': {'value': 2}, 'hits': []}}
        self.mock_client.transport.perform_request.return_value = mock_response

        result = await self._search_experiments_tool(
            self.SearchExperimentsArgs(opensearch_cluster_name='')
        )

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Experiment search results' in result[0]['text']

        call_kwargs = self.mock_client.transport.perform_request.call_args
        assert call_kwargs.kwargs['url'] == '/_plugins/_search_relevance/experiments/_search'
        body = json.loads(call_kwargs.kwargs['body'])
        assert body == {'query': {'match_all': {}}}

    @pytest.mark.asyncio
    async def test_search_experiments_custom_query(self):
        """Test SearchExperimentsTool with a custom query DSL body."""
        mock_response = {'hits': {'total': {'value': 1}, 'hits': []}}
        self.mock_client.transport.perform_request.return_value = mock_response

        query_body = {'query': {'term': {'type.keyword': 'PAIRWISE_COMPARISON'}}, 'size': 10}
        await self._search_experiments_tool(
            self.SearchExperimentsArgs(opensearch_cluster_name='', query_body=query_body)
        )

        call_kwargs = self.mock_client.transport.perform_request.call_args
        body = json.loads(call_kwargs.kwargs['body'])
        assert body == query_body

    @pytest.mark.asyncio
    async def test_search_experiments_error(self):
        """Test error handling for SearchExperimentsTool."""
        self.mock_client.transport.perform_request.side_effect = Exception('Server error')

        result = await self._search_experiments_tool(
            self.SearchExperimentsArgs(opensearch_cluster_name='')
        )

        assert 'Error searching experiments' in result[0]['text']
        assert 'Server error' in result[0]['text']

    # --- Registry ---

    @pytest.mark.asyncio
    async def test_srw_search_tools_registered_in_registry(self):
        """Test that all SRW search tools are registered in the TOOL_REGISTRY."""
        import sys

        for module in ['tools.tools']:
            if module in sys.modules:
                del sys.modules[module]

        from tools.tools import TOOL_REGISTRY

        for tool_name in [
            'SearchQuerySetsTool',
            'SearchSearchConfigurationsTool',
            'SearchJudgmentsTool',
            'SearchExperimentsTool',
        ]:
            assert tool_name in TOOL_REGISTRY
            tool = TOOL_REGISTRY[tool_name]
            assert 'description' in tool
            assert 'input_schema' in tool
            assert 'function' in tool
            assert 'args_model' in tool
            assert tool.get('min_version') == '3.5.0'
            assert 'GET' in tool.get('http_methods', '')
