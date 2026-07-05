# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import json
import pytest
from unittest.mock import AsyncMock, Mock, patch


class TestTools:
    def setup_method(self):
        """Setup that runs before each test method."""
        # Create a properly configured mock client
        self.mock_client = Mock()

        # Configure mock client methods to return proper data structures
        # These will be overridden in individual tests as needed
        # Use AsyncMock for async methods
        self.mock_client.cat.indices = AsyncMock(return_value=[])
        self.mock_client.indices.get_mapping = AsyncMock(return_value={})
        self.mock_client.indices.get = AsyncMock(return_value={})
        self.mock_client.search = AsyncMock(return_value={})
        self.mock_client.cat.shards = AsyncMock(return_value=[])
        self.mock_client.cat.segments = AsyncMock(return_value=[])
        self.mock_client.cat.nodes = AsyncMock(return_value=[])
        self.mock_client.cat.allocation = AsyncMock(return_value=[])
        self.mock_client.cluster.state = AsyncMock(return_value={})
        self.mock_client.indices.stats = AsyncMock(return_value={})
        self.mock_client.transport.perform_request = AsyncMock(return_value={})
        self.mock_client.info = AsyncMock(return_value={'version': {'number': '2.19.0'}})
        self.mock_client.plugins = Mock()
        self.mock_client.plugins.search_relevance = Mock()
        self.mock_client.plugins.search_relevance.put_search_configurations = AsyncMock(
            return_value={}
        )
        self.mock_client.plugins.search_relevance.get_search_configurations = AsyncMock(
            return_value={}
        )
        self.mock_client.plugins.search_relevance.delete_search_configurations = AsyncMock(
            return_value={}
        )

        # Patch initialize_client to always return our mock client
        self.init_client_patcher = patch(
            'opensearch.client.initialize_client', return_value=self.mock_client
        )
        self.init_client_patcher.start()

        # Clear any existing imports to ensure fresh imports
        import sys

        modules_to_clear = [
            'tools.tools',
        ]
        for module in modules_to_clear:
            if module in sys.modules:
                del sys.modules[module]

        # Import after patching to ensure fresh imports
        from tools.tools import (
            TOOL_REGISTRY,
            CatNodesArgs,
            CreateSearchConfigurationArgs,
            DeleteSearchConfigurationArgs,
            GetAllocationArgs,
            GetClusterStateArgs,
            GetIndexInfoArgs,
            GetIndexMappingArgs,
            GetIndexStatsArgs,
            GetLongRunningTasksArgs,
            GetNodesArgs,
            GetNodesHotThreadsArgs,
            GetQueryInsightsArgs,
            GetSearchConfigurationArgs,
            GetSegmentsArgs,
            GetShardsArgs,
            ListIndicesArgs,
            SearchIndexArgs,
            cat_nodes_tool,
            create_search_configuration_tool,
            delete_search_configuration_tool,
            get_allocation_tool,
            get_cluster_state_tool,
            get_index_info_tool,
            get_index_mapping_tool,
            get_index_stats_tool,
            get_long_running_tasks_tool,
            get_nodes_hot_threads_tool,
            get_nodes_tool,
            get_query_insights_tool,
            get_search_configuration_tool,
            get_segments_tool,
            get_shards_tool,
            list_indices_tool,
            search_index_tool,
        )

        self.ListIndicesArgs = ListIndicesArgs
        self.GetIndexMappingArgs = GetIndexMappingArgs
        self.SearchIndexArgs = SearchIndexArgs
        self.GetShardsArgs = GetShardsArgs
        self.GetClusterStateArgs = GetClusterStateArgs
        self.GetSegmentsArgs = GetSegmentsArgs
        self.CatNodesArgs = CatNodesArgs
        self.GetIndexInfoArgs = GetIndexInfoArgs
        self.GetIndexStatsArgs = GetIndexStatsArgs
        self.GetQueryInsightsArgs = GetQueryInsightsArgs
        self.GetNodesArgs = GetNodesArgs
        self.GetNodesHotThreadsArgs = GetNodesHotThreadsArgs
        self.GetAllocationArgs = GetAllocationArgs
        self.GetLongRunningTasksArgs = GetLongRunningTasksArgs
        self.TOOL_REGISTRY = TOOL_REGISTRY
        self._list_indices_tool = list_indices_tool
        self._get_index_mapping_tool = get_index_mapping_tool
        self._search_index_tool = search_index_tool
        self._get_shards_tool = get_shards_tool
        self._get_cluster_state_tool = get_cluster_state_tool
        self._get_segments_tool = get_segments_tool
        self._cat_nodes_tool = cat_nodes_tool
        self._get_nodes_tool = get_nodes_tool
        self._get_index_info_tool = get_index_info_tool
        self._get_index_stats_tool = get_index_stats_tool
        self._get_query_insights_tool = get_query_insights_tool
        self._get_nodes_hot_threads_tool = get_nodes_hot_threads_tool
        self._get_allocation_tool = get_allocation_tool
        self._get_long_running_tasks_tool = get_long_running_tasks_tool
        self.CreateSearchConfigurationArgs = CreateSearchConfigurationArgs
        self.GetSearchConfigurationArgs = GetSearchConfigurationArgs
        self.DeleteSearchConfigurationArgs = DeleteSearchConfigurationArgs
        self._create_search_configuration_tool = create_search_configuration_tool
        self._get_search_configuration_tool = get_search_configuration_tool
        self._delete_search_configuration_tool = delete_search_configuration_tool

    def teardown_method(self):
        """Cleanup after each test method."""
        self.init_client_patcher.stop()

    @pytest.mark.asyncio
    async def test_list_indices_tool_default_full(self):
        """Default behavior: returns full JSON info for all indices (include_detail=True)."""
        # Setup: mock full index info as returned by OpenSearch cat.indices
        self.mock_client.cat.indices.return_value = [
            {
                'health': 'green',
                'status': 'open',
                'index': 'index1',
                'uuid': 'uuid1',
                'pri': '1',
                'rep': '1',
                'docs.count': '100',
                'docs.deleted': '5',
                'store.size': '1mb',
                'pri.store.size': '0.5mb',
            },
            {
                'health': 'yellow',
                'status': 'open',
                'index': 'index2',
                'uuid': 'uuid2',
                'pri': '2',
                'rep': '2',
                'docs.count': '200',
                'docs.deleted': '10',
                'store.size': '2mb',
                'pri.store.size': '1mb',
            },
        ]
        # Execute
        result = await self._list_indices_tool(self.ListIndicesArgs(opensearch_cluster_name=''))
        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        # Should include the full JSON output by default
        assert '"index":"index1"' in result[0]['text']
        assert '"docs.count":"100"' in result[0]['text']
        assert '"index":"index2"' in result[0]['text']
        assert '"docs.count":"200"' in result[0]['text']
        self.mock_client.cat.indices.assert_called_once_with(index=None, format='json')

    @pytest.mark.asyncio
    async def test_list_indices_tool_include_detail_false(self):
        """When include_detail=False, returns only pure list of index names (filtered)."""
        # Setup
        self.mock_client.cat.indices.return_value = [
            {
                'health': 'green',
                'status': 'open',
                'index': 'index1',
                'uuid': 'uuid1',
                'pri': '1',
                'rep': '1',
                'docs.count': '100',
                'docs.deleted': '5',
                'store.size': '1mb',
                'pri.store.size': '0.5mb',
            },
            {
                'health': 'yellow',
                'status': 'open',
                'index': 'index2',
                'uuid': 'uuid2',
                'pri': '2',
                'rep': '2',
                'docs.count': '200',
                'docs.deleted': '10',
                'store.size': '2mb',
                'pri.store.size': '1mb',
            },
        ]
        # Execute
        result = await self._list_indices_tool(
            self.ListIndicesArgs(include_detail=False, opensearch_cluster_name='')
        )
        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        payload = json.loads(result[0]['text'].split('\n', 1)[1])
        assert payload == ['index1', 'index2']
        assert 'docs.count' not in result[0]['text']
        self.mock_client.cat.indices.assert_called_once_with(index=None, format='json')

    @pytest.mark.asyncio
    async def test_list_indices_tool_with_index(self):
        """When index is provided with include_detail=True (default), returns detailed info."""
        # Setup: mock detailed index info as returned by OpenSearch indices.get
        mock_index_info = {
            'index1': {
                'aliases': {},
                'mappings': {'properties': {'field1': {'type': 'text'}}},
                'settings': {'index': {'number_of_shards': '1', 'number_of_replicas': '1'}},
            }
        }
        self.mock_client.indices.get.return_value = mock_index_info
        # Execute - include_detail defaults to True
        args = self.ListIndicesArgs(index='index1', opensearch_cluster_name='')
        result = await self._list_indices_tool(args)
        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Index information for index1' in result[0]['text']
        assert '"index1"' in result[0]['text']
        assert '"number_of_shards":"1"' in result[0]['text']
        assert (
            '"field1":{"type":"text"}' in result[0]['text'] or '"type":"text"' in result[0]['text']
        )
        self.mock_client.indices.get.assert_called_once_with(index='index1')

    @pytest.mark.asyncio
    async def test_list_indices_tool_with_index_pattern_no_detail(self):
        """When index pattern provided with include_detail=False, returns matching index names."""
        # Setup - mock cat.indices to return indices matching pattern
        self.mock_client.cat.indices.return_value = [
            {'index': 'cwl-2024-01', 'health': 'green'},
            {'index': 'cwl-2024-02', 'health': 'green'},
        ]

        # Execute - explicitly set include_detail=False with pattern
        args = self.ListIndicesArgs(index='cwl*', include_detail=False, opensearch_cluster_name='')
        result = await self._list_indices_tool(args)

        # Assert - should return only the matching index names
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        payload = json.loads(result[0]['text'].split('\n', 1)[1])
        assert payload == ['cwl-2024-01', 'cwl-2024-02']

        # cat.indices should be called with the pattern when include_detail=False
        self.mock_client.cat.indices.assert_called_once_with(index='cwl*', format='json')
        self.mock_client.indices.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_list_indices_tool_error(self):
        """Test list_indices_tool exception handling."""
        # Setup
        self.mock_client.cat.indices.side_effect = Exception('Test error')
        # Execute
        result = await self._list_indices_tool(self.ListIndicesArgs(opensearch_cluster_name=''))
        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Error listing indices: Test error' in result[0]['text']
        self.mock_client.cat.indices.assert_called_once_with(index=None, format='json')

    @pytest.mark.asyncio
    async def test_get_index_mapping_tool(self):
        """Test get_index_mapping_tool successful."""
        # Setup
        mock_mapping = {'mappings': {'properties': {'field1': {'type': 'text'}}}}
        self.mock_client.indices.get_mapping.return_value = mock_mapping
        # Execute
        args = self.GetIndexMappingArgs(index='test-index', opensearch_cluster_name='')
        result = await self._get_index_mapping_tool(args)
        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Mapping for test-index' in result[0]['text']
        assert json.loads(result[0]['text'].split('\n', 1)[1]) == mock_mapping
        self.mock_client.indices.get_mapping.assert_called_once_with(index='test-index')

    @pytest.mark.asyncio
    async def test_get_index_mapping_tool_error(self):
        """Test get_index_mapping_tool exception handling."""
        # Setup
        self.mock_client.indices.get_mapping.side_effect = Exception('Test error')
        # Execute
        args = self.GetIndexMappingArgs(index='test-index', opensearch_cluster_name='')
        result = await self._get_index_mapping_tool(args)
        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Error getting mapping: Test error' in result[0]['text']
        self.mock_client.indices.get_mapping.assert_called_once_with(index='test-index')

    @pytest.mark.asyncio
    async def test_search_index_tool(self):
        """Test search_index_tool successful."""
        # Setup
        mock_results = {'hits': {'total': {'value': 1}, 'hits': [{'_source': {'field': 'value'}}]}}
        self.mock_client.search.return_value = mock_results
        # Execute
        args = self.SearchIndexArgs(
            index='test-index', query_dsl={'match_all': {}}, opensearch_cluster_name=''
        )
        result = await self._search_index_tool(args)
        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Search results from test-index' in result[0]['text']
        assert json.loads(result[0]['text'].split('\n', 1)[1]) == mock_results
        # The search_index function adds size to the query body (default 10, max 100)
        self.mock_client.search.assert_called_once_with(
            index='test-index', body={'match_all': {}, 'size': 10}
        )

    @pytest.mark.asyncio
    async def test_search_index_tool_error(self):
        """Test search_index_tool exception handling."""
        # Setup
        self.mock_client.search.side_effect = Exception('Test error')
        # Execute
        args = self.SearchIndexArgs(
            index='test-index', query_dsl={'match_all': {}}, opensearch_cluster_name=''
        )
        result = await self._search_index_tool(args)
        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Error searching index: Test error' in result[0]['text']
        # The search_index function adds size to the query body (default 10, max 100)
        self.mock_client.search.assert_called_once_with(
            index='test-index', body={'match_all': {}, 'size': 10}
        )

    @pytest.mark.asyncio
    async def test_get_shards_tool(self):
        """Test get_shards_tool successful."""
        # Setup
        mock_shards = [
            {
                'index': 'test-index',
                'shard': '0',
                'prirep': 'p',
                'state': 'STARTED',
                'docs': '1000',
                'store': '1mb',
                'ip': '127.0.0.1',
                'node': 'node1',
            }
        ]
        self.mock_client.cat.shards.return_value = mock_shards
        # Execute
        args = self.GetShardsArgs(index='test-index', opensearch_cluster_name='')
        result = await self._get_shards_tool(args)
        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'index | shard | prirep | state | docs | store | ip | node' in result[0]['text']
        assert 'test-index | 0 | p | STARTED | 1000 | 1mb | 127.0.0.1 | node1' in result[0]['text']
        self.mock_client.cat.shards.assert_called_once_with(index='test-index', format='json')

    @pytest.mark.asyncio
    async def test_get_shards_tool_error(self):
        """Test get_shards_tool exception handling."""
        # Setup
        self.mock_client.cat.shards.side_effect = Exception('Test error')
        # Execute
        args = self.GetShardsArgs(index='test-index', opensearch_cluster_name='')
        result = await self._get_shards_tool(args)
        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Error getting shards information: Test error' in result[0]['text']
        self.mock_client.cat.shards.assert_called_once_with(index='test-index', format='json')

    @pytest.mark.asyncio
    async def test_get_cluster_state_tool(self):
        """Test get_cluster_state_tool successful with no parameters."""
        # Setup
        mock_state = {
            'cluster_name': 'test-cluster',
            'version': 123,
            'master_node': 'node1',
            'blocks': {},
            'nodes': {
                'node1': {
                    'name': 'node1',
                    'transport_address': '127.0.0.1:9300',
                    'roles': ['master', 'data', 'ingest'],
                }
            },
            'metadata': {
                'indices': {
                    'index1': {'state': 'open', 'settings': {'index.number_of_shards': '1'}}
                }
            },
        }
        self.mock_client.cluster.state.return_value = mock_state

        # Execute
        args = self.GetClusterStateArgs(opensearch_cluster_name='')
        result = await self._get_cluster_state_tool(args)

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Cluster state information' in result[0]['text']
        assert '"cluster_name":"test-cluster"' in result[0]['text']
        assert '"master_node":"node1"' in result[0]['text']
        self.mock_client.cluster.state.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_get_cluster_state_tool_with_metric(self):
        """Test get_cluster_state_tool with metric parameter."""
        # Setup
        mock_state = {
            'cluster_name': 'test-cluster',
            'nodes': {
                'node1': {
                    'name': 'node1',
                    'transport_address': '127.0.0.1:9300',
                    'roles': ['master', 'data', 'ingest'],
                }
            },
        }
        self.mock_client.cluster.state.return_value = mock_state

        # Execute
        args = self.GetClusterStateArgs(metric='nodes', opensearch_cluster_name='')
        result = await self._get_cluster_state_tool(args)

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Cluster state information for metric: nodes' in result[0]['text']
        assert '"cluster_name":"test-cluster"' in result[0]['text']
        assert '"nodes"' in result[0]['text']
        self.mock_client.cluster.state.assert_called_once_with(metric='nodes')

    @pytest.mark.asyncio
    async def test_get_cluster_state_tool_with_index(self):
        """Test get_cluster_state_tool with index parameter."""
        # Setup
        mock_state = {
            'cluster_name': 'test-cluster',
            'metadata': {
                'indices': {
                    'test-index': {'state': 'open', 'settings': {'index.number_of_shards': '1'}}
                }
            },
        }
        self.mock_client.cluster.state.return_value = mock_state

        # Execute
        args = self.GetClusterStateArgs(index='test-index', opensearch_cluster_name='')
        result = await self._get_cluster_state_tool(args)

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Cluster state information, filtered by index: test-index' in result[0]['text']
        assert '"test-index"' in result[0]['text']
        self.mock_client.cluster.state.assert_called_once_with(index='test-index')

    @pytest.mark.asyncio
    async def test_get_cluster_state_tool_error(self):
        """Test get_cluster_state_tool exception handling."""
        # Setup
        self.mock_client.cluster.state.side_effect = Exception('Test error')

        # Execute
        args = self.GetClusterStateArgs(opensearch_cluster_name='')
        result = await self._get_cluster_state_tool(args)

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Error getting cluster state: Test error' in result[0]['text']
        self.mock_client.cluster.state.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_get_segments_tool(self):
        """Test get_segments_tool successful."""
        # Setup
        mock_segments = [
            {
                'index': 'test-index',
                'shard': '0',
                'prirep': 'p',
                'segment': 's1',
                'generation': '1',
                'docs.count': '100',
                'docs.deleted': '5',
                'size': '1mb',
                'memory.bookkeeping': '500b',
                'memory.vectors': '0b',
                'memory.docvalues': '200b',
                'memory.terms': '300b',
                'version': '8.0.0',
            }
        ]
        self.mock_client.cat.segments.return_value = mock_segments

        # Execute
        args = self.GetSegmentsArgs(opensearch_cluster_name='')
        result = await self._get_segments_tool(args)

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Segment information for all indices' in result[0]['text']
        assert 'index | shard | prirep | segment | generation | docs.count' in result[0]['text']
        assert 'test-index | 0 | p | s1 | 1 | 100' in result[0]['text']
        self.mock_client.cat.segments.assert_called_once_with(index=None, format='json')

    @pytest.mark.asyncio
    async def test_get_segments_tool_with_index(self):
        """Test get_segments_tool with index parameter."""
        # Setup
        mock_segments = [
            {
                'index': 'test-index',
                'shard': '0',
                'prirep': 'p',
                'segment': 's1',
                'generation': '1',
                'docs.count': '100',
                'docs.deleted': '5',
                'size': '1mb',
                'memory.bookkeeping': '500b',
                'memory.vectors': '0b',
                'memory.docvalues': '200b',
                'memory.terms': '300b',
                'version': '8.0.0',
            }
        ]
        self.mock_client.cat.segments.return_value = mock_segments

        # Execute
        args = self.GetSegmentsArgs(index='test-index', opensearch_cluster_name='')
        result = await self._get_segments_tool(args)

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Segment information for index: test-index' in result[0]['text']
        assert 'test-index | 0 | p | s1' in result[0]['text']
        self.mock_client.cat.segments.assert_called_once_with(index='test-index', format='json')

    @pytest.mark.asyncio
    async def test_get_segments_tool_error(self):
        """Test get_segments_tool exception handling."""
        # Setup
        self.mock_client.cat.segments.side_effect = Exception('Test error')

        # Execute
        args = self.GetSegmentsArgs(opensearch_cluster_name='')
        result = await self._get_segments_tool(args)

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Error getting segment information: Test error' in result[0]['text']
        self.mock_client.cat.segments.assert_called_once_with(index=None, format='json')

    @pytest.mark.asyncio
    async def test_cat_nodes_tool(self):
        """Test cat_nodes_tool successful."""
        # Setup
        mock_nodes = [
            {
                'name': 'node1',
                'ip': '127.0.0.1',
                'heap.percent': '50',
                'ram.percent': '70',
                'cpu': '12',
                'load_1m': '1.2',
                'master': '*',
                'role': 'dimr',
                'disk.total': '100gb',
                'disk.used': '20gb',
                'disk.avail': '80gb',
                'disk.used_percent': '20',
            }
        ]
        self.mock_client.cat.nodes.return_value = mock_nodes

        # Execute
        args = self.CatNodesArgs(opensearch_cluster_name='')
        result = await self._cat_nodes_tool(args)

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Node information for the cluster' in result[0]['text']
        assert (
            'name | ip | heap.percent | ram.percent | cpu' in result[0]['text']
            or 'name' in result[0]['text']
        )
        assert 'node1 | 127.0.0.1' in result[0]['text']
        self.mock_client.cat.nodes.assert_called_once_with(format='json', h=None)

    @pytest.mark.asyncio
    async def test_cat_nodes_tool_with_metrics(self):
        """Test cat_nodes_tool with metrics parameter."""
        # Setup
        mock_nodes = [{'name': 'node1', 'ip': '127.0.0.1', 'heap.percent': '50'}]
        self.mock_client.cat.nodes.return_value = mock_nodes

        # Execute
        args = self.CatNodesArgs(metrics='name,ip,heap.percent', opensearch_cluster_name='')
        result = await self._cat_nodes_tool(args)

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert (
            'Node information for the cluster (metrics: name,ip,heap.percent)' in result[0]['text']
        )
        assert 'name | ip | heap.percent' in result[0]['text']
        assert 'node1 | 127.0.0.1 | 50' in result[0]['text']
        self.mock_client.cat.nodes.assert_called_once_with(format='json', h='name,ip,heap.percent')

    @pytest.mark.asyncio
    async def test_cat_nodes_tool_error(self):
        """Test cat_nodes_tool exception handling."""
        # Setup
        self.mock_client.cat.nodes.side_effect = Exception('Test error')

        # Execute
        args = self.CatNodesArgs(opensearch_cluster_name='')
        result = await self._cat_nodes_tool(args)

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Error getting node information: Test error' in result[0]['text']
        self.mock_client.cat.nodes.assert_called_once_with(format='json', h=None)

    @pytest.mark.asyncio
    async def test_get_index_info_tool(self):
        """Test get_index_info_tool successful."""
        # Setup
        mock_index_info = {
            'test-index': {
                'aliases': {},
                'mappings': {
                    'properties': {'field1': {'type': 'text'}, 'field2': {'type': 'keyword'}}
                },
                'settings': {
                    'index': {
                        'number_of_shards': '1',
                        'number_of_replicas': '1',
                        'creation_date': '1619712000000',
                    }
                },
            }
        }
        self.mock_client.indices.get.return_value = mock_index_info

        # Execute
        args = self.GetIndexInfoArgs(index='test-index', opensearch_cluster_name='')
        result = await self._get_index_info_tool(args)

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Detailed information for index: test-index' in result[0]['text']
        assert '"test-index"' in result[0]['text']
        assert (
            '"field1":{"type":"text"}' in result[0]['text'] or '"type":"text"' in result[0]['text']
        )
        assert '"number_of_shards":"1"' in result[0]['text']
        self.mock_client.indices.get.assert_called_once_with(index='test-index')

    @pytest.mark.asyncio
    async def test_get_index_info_tool_error(self):
        """Test get_index_info_tool exception handling."""
        # Setup
        self.mock_client.indices.get.side_effect = Exception('Test error')

        # Execute
        args = self.GetIndexInfoArgs(index='test-index', opensearch_cluster_name='')
        result = await self._get_index_info_tool(args)

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Error getting index information: Test error' in result[0]['text']
        self.mock_client.indices.get.assert_called_once_with(index='test-index')

    @pytest.mark.asyncio
    async def test_get_index_stats_tool(self):
        """Test get_index_stats_tool successful."""
        # Setup
        mock_stats = {
            '_all': {
                'primaries': {
                    'docs': {'count': 1000, 'deleted': 10},
                    'store': {'size_in_bytes': 1000000},
                    'indexing': {'index_total': 1000, 'index_time_in_millis': 500},
                    'search': {'query_total': 200, 'query_time_in_millis': 100},
                },
                'total': {
                    'docs': {'count': 1000, 'deleted': 10},
                    'store': {'size_in_bytes': 2000000},
                    'indexing': {'index_total': 1000, 'index_time_in_millis': 500},
                    'search': {'query_total': 200, 'query_time_in_millis': 100},
                },
            },
            'indices': {
                'test-index': {
                    'primaries': {'docs': {'count': 1000, 'deleted': 10}},
                    'total': {'docs': {'count': 1000, 'deleted': 10}},
                }
            },
        }
        self.mock_client.indices.stats.return_value = mock_stats

        # Execute
        args = self.GetIndexStatsArgs(index='test-index', opensearch_cluster_name='')
        result = await self._get_index_stats_tool(args)

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Statistics for index: test-index' in result[0]['text']
        assert (
            '"docs":{"count":1000,"deleted":10}' in result[0]['text']
            or '"count":1000' in result[0]['text']
        )
        self.mock_client.indices.stats.assert_called_once_with(index='test-index')

    @pytest.mark.asyncio
    async def test_get_index_stats_tool_with_metric(self):
        """Test get_index_stats_tool with metric parameter."""
        # Setup
        mock_stats = {
            '_all': {
                'primaries': {'search': {'query_total': 200, 'query_time_in_millis': 100}},
                'total': {'search': {'query_total': 200, 'query_time_in_millis': 100}},
            },
            'indices': {
                'test-index': {
                    'primaries': {'search': {'query_total': 200, 'query_time_in_millis': 100}},
                    'total': {'search': {'query_total': 200, 'query_time_in_millis': 100}},
                }
            },
        }
        self.mock_client.indices.stats.return_value = mock_stats

        # Execute
        args = self.GetIndexStatsArgs(
            index='test-index', metric='search', opensearch_cluster_name=''
        )
        result = await self._get_index_stats_tool(args)

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Statistics for index: test-index (metrics: search)' in result[0]['text']
        assert (
            '"search":{"query_total":200' in result[0]['text']
            or '"query_total":200' in result[0]['text']
        )
        self.mock_client.indices.stats.assert_called_once_with(index='test-index', metric='search')

    @pytest.mark.asyncio
    async def test_get_index_stats_tool_error(self):
        """Test get_index_stats_tool exception handling."""
        # Setup
        self.mock_client.indices.stats.side_effect = Exception('Test error')

        # Execute
        args = self.GetIndexStatsArgs(index='test-index', opensearch_cluster_name='')
        result = await self._get_index_stats_tool(args)

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Error getting index statistics: Test error' in result[0]['text']
        self.mock_client.indices.stats.assert_called_once_with(index='test-index')

    @pytest.mark.asyncio
    async def test_get_query_insights_tool(self):
        """Test get_query_insights_tool successful."""
        # Setup
        mock_insights = {
            'top_queries': [
                {
                    'query': {'match': {'field': 'value'}},
                    'count': 100,
                    'avg_time_ms': 5.2,
                    'total_time_ms': 520,
                },
                {
                    'query': {'term': {'field2': 'value2'}},
                    'count': 50,
                    'avg_time_ms': 3.1,
                    'total_time_ms': 155,
                },
            ]
        }
        self.mock_client.transport.perform_request.return_value = mock_insights

        # Execute
        args = self.GetQueryInsightsArgs(opensearch_cluster_name='')
        result = await self._get_query_insights_tool(args)

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Query insights from /_insights/top_queries endpoint' in result[0]['text']
        assert (
            '"query":{"match":{"field":"value"}}' in result[0]['text']
            or '"match"' in result[0]['text']
        )
        assert '"count":100' in result[0]['text']
        self.mock_client.transport.perform_request.assert_called_once_with(
            method='GET', url='/_insights/top_queries'
        )

    @pytest.mark.asyncio
    async def test_get_query_insights_tool_error(self):
        """Test get_query_insights_tool exception handling."""
        # Setup
        self.mock_client.transport.perform_request.side_effect = Exception('Test error')

        # Execute
        args = self.GetQueryInsightsArgs(opensearch_cluster_name='')
        result = await self._get_query_insights_tool(args)

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Error getting query insights: Test error' in result[0]['text']
        self.mock_client.transport.perform_request.assert_called_once_with(
            method='GET', url='/_insights/top_queries'
        )

    @pytest.mark.asyncio
    async def test_get_nodes_hot_threads_tool(self):
        """Test get_nodes_hot_threads_tool successful."""
        # Setup
        mock_hot_threads = """
::: {node1}{xyzdef-1234} {master}
   Hot threads at 2023-04-01T12:00:00Z, interval=500ms, busiestThreads=3, ignoreIdleThreads=true:

   0.23% (1.2s out of 500ms) cpu usage by thread 'elasticsearch[node1][search][T#1]'
     10/10 snapshots sharing following 5 elements
       java.lang.Thread.yield(Thread.java:1343)
       org.opensearch.common.util.concurrent.EsExecutors$DirectExecutorService.execute(EsExecutors.java:203)
       org.opensearch.action.search.SearchPhaseController.executeNextPhase(SearchPhaseController.java:156)
       org.opensearch.action.search.InitialSearchPhase.executeNextPhase(InitialSearchPhase.java:103)
       org.opensearch.action.search.AbstractSearchAsyncAction.executeNextPhase(AbstractSearchAsyncAction.java:127)
"""
        self.mock_client.transport.perform_request.return_value = mock_hot_threads

        # Execute
        args = self.GetNodesHotThreadsArgs(opensearch_cluster_name='')
        result = await self._get_nodes_hot_threads_tool(args)

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Hot threads information from /_nodes/hot_threads endpoint' in result[0]['text']
        assert 'node1' in result[0]['text']
        assert 'search' in result[0]['text']
        self.mock_client.transport.perform_request.assert_called_once_with(
            method='GET', url='/_nodes/hot_threads'
        )

    @pytest.mark.asyncio
    async def test_get_nodes_hot_threads_tool_error(self):
        """Test get_nodes_hot_threads_tool exception handling."""
        # Setup
        self.mock_client.transport.perform_request.side_effect = Exception('Test error')

        # Execute
        args = self.GetNodesHotThreadsArgs(opensearch_cluster_name='')
        result = await self._get_nodes_hot_threads_tool(args)

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Error getting hot threads information: Test error' in result[0]['text']
        self.mock_client.transport.perform_request.assert_called_once_with(
            method='GET', url='/_nodes/hot_threads'
        )

    @pytest.mark.asyncio
    async def test_get_allocation_tool(self):
        """Test get_allocation_tool successful."""
        # Setup
        mock_allocation = [
            {
                'shards': '5',
                'disk.indices': '1gb',
                'disk.used': '5gb',
                'disk.avail': '95gb',
                'disk.total': '100gb',
                'disk.percent': '5',
                'host': '127.0.0.1',
                'ip': '127.0.0.1',
                'node': 'node1',
            },
            {
                'shards': '3',
                'disk.indices': '0.5gb',
                'disk.used': '3gb',
                'disk.avail': '97gb',
                'disk.total': '100gb',
                'disk.percent': '3',
                'host': '127.0.0.2',
                'ip': '127.0.0.2',
                'node': 'node2',
            },
        ]
        self.mock_client.cat.allocation.return_value = mock_allocation

        # Execute
        args = self.GetAllocationArgs(opensearch_cluster_name='')
        result = await self._get_allocation_tool(args)

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Allocation information from /_cat/allocation endpoint' in result[0]['text']
        assert (
            'shards | disk.indices | disk.used | disk.avail | disk.total | disk.percent | host | ip | node'
            in result[0]['text']
            or 'shards' in result[0]['text']
        )
        assert 'node1' in result[0]['text']
        assert 'node2' in result[0]['text']
        self.mock_client.cat.allocation.assert_called_once_with(format='json')

    @pytest.mark.asyncio
    async def test_get_allocation_tool_error(self):
        """Test get_allocation_tool exception handling."""
        # Setup
        self.mock_client.cat.allocation.side_effect = Exception('Test error')

        # Execute
        args = self.GetAllocationArgs(opensearch_cluster_name='')
        result = await self._get_allocation_tool(args)

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Error getting allocation information: Test error' in result[0]['text']
        self.mock_client.cat.allocation.assert_called_once_with(format='json')

    @pytest.mark.asyncio
    async def test_get_long_running_tasks_tool(self):
        """Test get_long_running_tasks_tool successful."""
        # Setup
        mock_tasks = [
            {
                'action': 'indices:data/write/bulk',
                'task_id': '1234',
                'parent_task_id': '',
                'type': 'transport',
                'start_time': '1619712000000',
                'timestamp': '1619712060000',
                'running_time_ns': '60000000000',
                'running_time': '60s',
                'node_id': 'node1',
                'ip': '127.0.0.1',
                'node': 'node1',
            },
            {
                'action': 'indices:data/read/search',
                'task_id': '5678',
                'parent_task_id': '',
                'type': 'transport',
                'start_time': '1619712030000',
                'timestamp': '1619712060000',
                'running_time_ns': '30000000000',
                'running_time': '30s',
                'node_id': 'node2',
                'ip': '127.0.0.2',
                'node': 'node2',
            },
        ]
        self.mock_client.transport.perform_request.return_value = mock_tasks

        # Execute
        args = self.GetLongRunningTasksArgs(opensearch_cluster_name='')
        result = await self._get_long_running_tasks_tool(args)

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Top 2 long-running tasks sorted by running time' in result[0]['text']
        assert (
            'action | task_id | parent_task_id | type | start_time | timestamp | running_time_ns | running_time | node_id | ip | node'
            in result[0]['text']
            or 'action' in result[0]['text']
        )
        assert 'indices:data/write/bulk' in result[0]['text']
        assert 'indices:data/read/search' in result[0]['text']
        self.mock_client.transport.perform_request.assert_called_once_with(
            method='GET', url='/_cat/tasks', params={'s': 'running_time:desc', 'format': 'json'}
        )

    @pytest.mark.asyncio
    async def test_get_long_running_tasks_tool_with_limit(self):
        """Test get_long_running_tasks_tool with limit parameter."""
        # Setup
        mock_tasks = [
            {'action': 'indices:data/write/bulk', 'running_time': '60s', 'node': 'node1'},
            {'action': 'indices:data/read/search', 'running_time': '30s', 'node': 'node2'},
            {'action': 'indices:admin/create', 'running_time': '15s', 'node': 'node1'},
        ]
        self.mock_client.transport.perform_request.return_value = mock_tasks

        # Execute
        args = self.GetLongRunningTasksArgs(limit=2, opensearch_cluster_name='')
        result = await self._get_long_running_tasks_tool(args)

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Top 2 long-running tasks sorted by running time' in result[0]['text']
        assert 'indices:data/write/bulk' in result[0]['text']
        assert 'indices:data/read/search' in result[0]['text']
        assert 'indices:admin/create' not in result[0]['text']
        self.mock_client.transport.perform_request.assert_called_once_with(
            method='GET', url='/_cat/tasks', params={'s': 'running_time:desc', 'format': 'json'}
        )

    @pytest.mark.asyncio
    async def test_get_long_running_tasks_tool_error(self):
        """Test get_long_running_tasks_tool exception handling."""
        # Setup
        self.mock_client.transport.perform_request.side_effect = Exception('Test error')

        # Execute
        args = self.GetLongRunningTasksArgs(opensearch_cluster_name='')
        result = await self._get_long_running_tasks_tool(args)

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Error getting long-running tasks information: Test error' in result[0]['text']
        self.mock_client.transport.perform_request.assert_called_once_with(
            method='GET', url='/_cat/tasks', params={'s': 'running_time:desc', 'format': 'json'}
        )

    @pytest.mark.asyncio
    async def test_get_nodes_tool_success(self):
        """Test get_nodes_tool returns detailed node information."""
        # Setup: mock detailed node info as returned by OpenSearch /_nodes endpoint
        mock_response = {
            '_nodes': {'total': 2, 'successful': 2, 'failed': 0},
            'cluster_name': 'test-cluster',
            'nodes': {
                'node1': {
                    'name': 'node-1',
                    'transport_address': '127.0.0.1:9300',
                    'host': '127.0.0.1',
                    'ip': '127.0.0.1',
                    'version': '2.19.0',
                    'build_type': 'tar',
                    'roles': ['data', 'master'],
                    'os': {'name': 'Linux', 'arch': 'amd64', 'version': '5.4.0'},
                    'process': {
                        'refresh_interval_in_millis': 1000,
                        'id': 12345,
                        'mlockall': False,
                    },
                },
                'node2': {
                    'name': 'node-2',
                    'transport_address': '127.0.0.1:9301',
                    'host': '127.0.0.1',
                    'ip': '127.0.0.1',
                    'version': '2.19.0',
                    'build_type': 'tar',
                    'roles': ['data'],
                    'os': {'name': 'Linux', 'arch': 'amd64', 'version': '5.4.0'},
                },
            },
        }
        self.mock_client.transport.perform_request.return_value = mock_response

        # Execute
        args = self.GetNodesArgs(opensearch_cluster_name='')
        result = await self._get_nodes_tool(args)

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Detailed node information for all nodes' in result[0]['text']
        assert '"name":"node-1"' in result[0]['text']
        assert '"name":"node-2"' in result[0]['text']
        assert '"cluster_name":"test-cluster"' in result[0]['text']
        self.mock_client.transport.perform_request.assert_called_once_with(
            method='GET', url='/_nodes'
        )

    @pytest.mark.asyncio
    async def test_get_nodes_tool_with_filters(self):
        """Test get_nodes_tool with node_id and metric filters."""
        # Setup
        mock_response = {
            '_nodes': {'total': 1, 'successful': 1, 'failed': 0},
            'cluster_name': 'test-cluster',
            'nodes': {
                'master-node': {
                    'name': 'master-node',
                    'transport_address': '127.0.0.1:9300',
                    'process': {
                        'refresh_interval_in_millis': 1000,
                        'id': 12345,
                        'mlockall': False,
                    },
                    'transport': {
                        'bound_address': ['127.0.0.1:9300'],
                        'publish_address': '127.0.0.1:9300',
                    },
                }
            },
        }
        self.mock_client.transport.perform_request.return_value = mock_response

        # Execute
        args = self.GetNodesArgs(
            node_id='master:true', metric='process,transport', opensearch_cluster_name=''
        )
        result = await self._get_nodes_tool(args)

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Detailed node information for nodes: master:true' in result[0]['text']
        assert '(metrics: process,transport)' in result[0]['text']
        assert '"name":"master-node"' in result[0]['text']
        self.mock_client.transport.perform_request.assert_called_once_with(
            method='GET', url='/_nodes/master:true/process,transport'
        )

    @pytest.mark.asyncio
    async def test_get_nodes_tool_error(self):
        """Test get_nodes_tool exception handling."""
        # Setup
        self.mock_client.transport.perform_request.side_effect = Exception('Test error')

        # Execute
        args = self.GetNodesArgs(opensearch_cluster_name='')
        result = await self._get_nodes_tool(args)

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Error getting nodes information: Test error' in result[0]['text']
        self.mock_client.transport.perform_request.assert_called_once_with(
            method='GET', url='/_nodes'
        )

    @pytest.mark.asyncio
    async def test_create_search_configuration_tool(self):
        """Test create_search_configuration_tool successful."""
        self.mock_client.info.return_value = {'version': {'number': '3.1.0'}}
        mock_response = {'_id': 'cfg-1', 'result': 'created'}
        self.mock_client.plugins.search_relevance.put_search_configurations.return_value = (
            mock_response
        )

        args = self.CreateSearchConfigurationArgs(
            name='my-config',
            index='my-index',
            query='{"query":{"match":{"title":"%SearchText%"}}}',
            opensearch_cluster_name='',
        )
        result = await self._create_search_configuration_tool(args)

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Search configuration created' in result[0]['text']
        assert '"_id":"cfg-1"' in result[0]['text']
        self.mock_client.plugins.search_relevance.put_search_configurations.assert_called_once_with(
            body={
                'name': 'my-config',
                'index': 'my-index',
                'query': '{"query":{"match":{"title":"%SearchText%"}}}',
            }
        )

    @pytest.mark.asyncio
    async def test_create_search_configuration_tool_error(self):
        """Test create_search_configuration_tool exception handling."""
        self.mock_client.info.return_value = {'version': {'number': '3.1.0'}}
        self.mock_client.plugins.search_relevance.put_search_configurations.side_effect = (
            Exception('Test error')
        )

        args = self.CreateSearchConfigurationArgs(
            name='my-config',
            index='my-index',
            query='{"query":{"match_all":{}}}',
            opensearch_cluster_name='',
        )
        result = await self._create_search_configuration_tool(args)

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Error creating search configuration: Test error' in result[0]['text']

    @pytest.mark.asyncio
    async def test_get_search_configuration_tool(self):
        """Test get_search_configuration_tool successful."""
        self.mock_client.info.return_value = {'version': {'number': '3.1.0'}}
        mock_response = {'_id': 'cfg-1', '_source': {'name': 'my-config', 'index': 'my-index'}}
        self.mock_client.plugins.search_relevance.get_search_configurations.return_value = (
            mock_response
        )

        args = self.GetSearchConfigurationArgs(
            search_configuration_id='cfg-1', opensearch_cluster_name=''
        )
        result = await self._get_search_configuration_tool(args)

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Search configuration cfg-1' in result[0]['text']
        assert '"_id":"cfg-1"' in result[0]['text']
        self.mock_client.plugins.search_relevance.get_search_configurations.assert_called_once_with(
            search_configuration_id='cfg-1'
        )

    @pytest.mark.asyncio
    async def test_get_search_configuration_tool_error(self):
        """Test get_search_configuration_tool exception handling."""
        self.mock_client.info.return_value = {'version': {'number': '3.1.0'}}
        self.mock_client.plugins.search_relevance.get_search_configurations.side_effect = (
            Exception('Not found')
        )

        args = self.GetSearchConfigurationArgs(
            search_configuration_id='cfg-1', opensearch_cluster_name=''
        )
        result = await self._get_search_configuration_tool(args)

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Error retrieving search configuration: Not found' in result[0]['text']

    @pytest.mark.asyncio
    async def test_delete_search_configuration_tool(self):
        """Test delete_search_configuration_tool successful."""
        self.mock_client.info.return_value = {'version': {'number': '3.1.0'}}
        mock_response = {'result': 'deleted'}
        self.mock_client.plugins.search_relevance.delete_search_configurations.return_value = (
            mock_response
        )

        args = self.DeleteSearchConfigurationArgs(
            search_configuration_id='cfg-1', opensearch_cluster_name=''
        )
        result = await self._delete_search_configuration_tool(args)

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Search configuration cfg-1 deleted' in result[0]['text']
        assert '"result":"deleted"' in result[0]['text']
        self.mock_client.plugins.search_relevance.delete_search_configurations.assert_called_once_with(
            search_configuration_id='cfg-1'
        )

    @pytest.mark.asyncio
    async def test_delete_search_configuration_tool_error(self):
        """Test delete_search_configuration_tool exception handling."""
        self.mock_client.info.return_value = {'version': {'number': '3.1.0'}}
        self.mock_client.plugins.search_relevance.delete_search_configurations.side_effect = (
            Exception('Test error')
        )

        args = self.DeleteSearchConfigurationArgs(
            search_configuration_id='cfg-1', opensearch_cluster_name=''
        )
        result = await self._delete_search_configuration_tool(args)

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Error deleting search configuration: Test error' in result[0]['text']

    def test_tool_registry(self):
        """Test TOOL_REGISTRY structure."""
        expected_tools = [
            'ListIndexTool',
            'IndexMappingTool',
            'SearchIndexTool',
            'GetShardsTool',
            'GetClusterStateTool',
            'GetSegmentsTool',
            'CatNodesTool',
            'GetNodesTool',
            'GetIndexInfoTool',
            'GetIndexStatsTool',
            'GetQueryInsightsTool',
            'GetNodesHotThreadsTool',
            'GetAllocationTool',
            'GetLongRunningTasksTool',
            'CreateSearchConfigurationTool',
            'GetSearchConfigurationTool',
            'DeleteSearchConfigurationTool',
        ]

        for tool in expected_tools:
            assert tool in self.TOOL_REGISTRY
            assert 'description' in self.TOOL_REGISTRY[tool]
            assert 'input_schema' in self.TOOL_REGISTRY[tool]
            assert 'function' in self.TOOL_REGISTRY[tool]
            assert 'args_model' in self.TOOL_REGISTRY[tool]

    def test_input_models(self):
        """Test input models validation."""
        with pytest.raises(ValueError):
            self.GetIndexMappingArgs(opensearch_cluster_name='')  # Should fail without index

        with pytest.raises(ValueError):
            self.SearchIndexArgs(
                index='test', opensearch_cluster_name=''
            )  # Should fail without query

        # Test valid inputs
        assert self.GetIndexMappingArgs(index='test', opensearch_cluster_name='').index == 'test'
        assert (
            self.SearchIndexArgs(
                index='test', query_dsl={'match': {}}, opensearch_cluster_name=''
            ).index
            == 'test'
        )
        assert self.GetShardsArgs(index='test', opensearch_cluster_name='').index == 'test'
        assert isinstance(self.ListIndicesArgs(opensearch_cluster_name=''), self.ListIndicesArgs)


class TestListClustersTool:
    """Test cases for the list_clusters_tool function."""

    def setup_method(self):
        """Setup that runs before each test method."""
        self.init_client_patcher = patch(
            'opensearch.client.initialize_client', return_value=Mock()
        )
        self.init_client_patcher.start()

        from tools.tools import ListClustersArgs, list_clusters_tool

        self._list_clusters_tool = list_clusters_tool
        self.ListClustersArgs = ListClustersArgs

    def teardown_method(self):
        self.init_client_patcher.stop()

    @pytest.mark.asyncio
    async def test_list_clusters_returns_cluster_names(self):
        """Test that list_clusters_tool returns names from cluster_registry."""
        with patch(
            'tools.tools.cluster_registry',
            {'cluster-a': Mock(), 'cluster-b': Mock(), 'cluster-c': Mock()},
        ):
            args = self.ListClustersArgs()
            result = await self._list_clusters_tool(args)

            assert len(result) == 1
            assert result[0]['type'] == 'text'
            assert 'cluster-a' in result[0]['text']
            assert 'cluster-b' in result[0]['text']
            assert 'cluster-c' in result[0]['text']
            # Verify it's valid JSON in the output
            text = result[0]['text']
            json_part = text.split('\n', 1)[1]
            parsed = json.loads(json_part)
            assert parsed == ['cluster-a', 'cluster-b', 'cluster-c']

    @pytest.mark.asyncio
    async def test_list_clusters_empty_registry(self):
        """Test that list_clusters_tool returns empty list when no clusters configured."""
        with patch('tools.tools.cluster_registry', {}):
            args = self.ListClustersArgs()
            result = await self._list_clusters_tool(args)

            assert len(result) == 1
            assert result[0]['type'] == 'text'
            text = result[0]['text']
            json_part = text.split('\n', 1)[1]
            parsed = json.loads(json_part)
            assert parsed == []

    @pytest.mark.asyncio
    async def test_list_clusters_single_cluster(self):
        """Test with a single cluster in the registry."""
        with patch('tools.tools.cluster_registry', {'my-cluster': Mock()}):
            args = self.ListClustersArgs()
            result = await self._list_clusters_tool(args)

            text = result[0]['text']
            json_part = text.split('\n', 1)[1]
            parsed = json.loads(json_part)
            assert parsed == ['my-cluster']

    def test_list_clusters_args_accepts_extra_fields(self):
        """Test that ListClustersArgs doesn't reject extra fields like opensearch_cluster_name."""
        args = self.ListClustersArgs(**{'opensearch_cluster_name': 'test'})
        assert args is not None

    def test_list_clusters_in_tool_registry(self):
        """Test that ListClustersTool is present in TOOL_REGISTRY with correct metadata."""
        from tools.tools import TOOL_REGISTRY

        assert 'ListClustersTool' in TOOL_REGISTRY
        tool_info = TOOL_REGISTRY['ListClustersTool']
        assert tool_info['display_name'] == 'ListClustersTool'
        assert tool_info['multi_only'] is True
        assert tool_info['http_methods'] == 'GET'
