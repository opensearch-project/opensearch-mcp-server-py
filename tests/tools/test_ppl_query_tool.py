# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import pytest
from unittest.mock import AsyncMock, Mock, patch


class TestPPLQueryTool:
    def setup_method(self):
        self.mock_client = Mock()
        self.mock_client.transport.perform_request = AsyncMock(return_value={})
        self.mock_client.info = AsyncMock(return_value={'version': {'number': '2.19.0'}})

        self.init_client_patcher = patch(
            'opensearch.client.initialize_client', return_value=self.mock_client
        )
        self.init_client_patcher.start()

        import sys

        for module in ['tools.tools', 'opensearch.helper']:
            if module in sys.modules:
                del sys.modules[module]

        from tools.tools import PplQueryArgs, ppl_query_tool

        self._ppl_query_tool = ppl_query_tool
        self.PplQueryArgs = PplQueryArgs

    def teardown_method(self):
        self.init_client_patcher.stop()

    @pytest.mark.asyncio
    async def test_basic_ppl_query(self):
        """Test basic PPL query execution."""
        self.mock_client.transport.perform_request.return_value = {
            'schema': [{'name': 'host', 'type': 'string'}],
            'datarows': [['host1'], ['host2']],
            'total': 2,
            'size': 2,
            'status': 200,
        }

        args = self.PplQueryArgs(
            opensearch_cluster_name='test',
            query='source=my_index | stats count() by host',
        )
        result = await self._ppl_query_tool(args)

        assert len(result) == 1
        assert 'PPL query results' in result[0]['text']
        assert 'host1' in result[0]['text']

        self.mock_client.transport.perform_request.assert_called_once_with(
            method='POST',
            url='/_plugins/_ppl',
            body='{"query": "source=my_index | stats count() by host"}',
            params={},
        )

    @pytest.mark.asyncio
    async def test_ppl_query_with_csv_format(self):
        """Test PPL query with non-default format passes format param."""
        self.mock_client.transport.perform_request.return_value = 'host\nhost1\nhost2'

        args = self.PplQueryArgs(
            opensearch_cluster_name='test',
            query='source=my_index | fields host',
            format='csv',
        )
        await self._ppl_query_tool(args)

        self.mock_client.transport.perform_request.assert_called_once_with(
            method='POST',
            url='/_plugins/_ppl',
            body='{"query": "source=my_index | fields host"}',
            params={'format': 'csv'},
        )

    @pytest.mark.asyncio
    async def test_ppl_query_error_handling(self):
        """Test PPL query error is properly reported."""
        self.mock_client.transport.perform_request.side_effect = Exception(
            'SyntaxError: Invalid query'
        )

        args = self.PplQueryArgs(
            opensearch_cluster_name='test',
            query='invalid query',
        )
        result = await self._ppl_query_tool(args)

        assert 'Error' in result[0]['text']
        assert 'PPL query' in result[0]['text']

    @pytest.mark.asyncio
    async def test_ppl_query_jdbc_format_no_param(self):
        """Test that jdbc (default) format does not pass format param."""
        self.mock_client.transport.perform_request.return_value = {'status': 200}

        args = self.PplQueryArgs(
            opensearch_cluster_name='test',
            query='source=my_index',
            format='jdbc',
        )
        await self._ppl_query_tool(args)

        call_kwargs = self.mock_client.transport.perform_request.call_args[1]
        assert call_kwargs['params'] == {}
