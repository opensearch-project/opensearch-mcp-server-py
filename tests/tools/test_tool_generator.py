# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import pytest
import yaml
from mcp.types import TextContent
from pydantic import BaseModel
from unittest.mock import AsyncMock, Mock, patch


class TestToolGenerator:
    def setup_method(self):
        """Setup that runs before each test method."""
        # Mock OpenSearch client
        self.mock_client = Mock()
        self.mock_client.transport.perform_request = AsyncMock()

        # Mock spec
        self.mock_spec = {
            'paths': {
                '/_cluster/health/{index}': {
                    'get': {
                        'description': 'Returns cluster health',
                        'x-operation-group': 'cluster.health',
                    }
                },
                '/_count': {
                    'get': {
                        'description': 'Returns count of documents',
                        'x-operation-group': 'count',
                        'requestBody': {'content': {'application/json': {'schema': {}}}},
                    }
                },
            }
        }

        # Import after mocking
        from tools.tool_generator import (
            SPEC_FILES,
            extract_parameters,
            fetch_github_spec,
            generate_tool_from_group,
            generate_tools_from_openapi,
            group_endpoints_by_operation,
            process_body,
            select_endpoint,
        )

        self.fetch_github_spec = fetch_github_spec
        self.group_endpoints_by_operation = group_endpoints_by_operation
        self.extract_parameters = extract_parameters
        self.process_body = process_body
        self.select_endpoint = select_endpoint
        self.generate_tool_from_group = generate_tool_from_group
        self.generate_tools_from_openapi = generate_tools_from_openapi
        self.SPEC_FILES = SPEC_FILES

    @pytest.mark.asyncio
    async def test_fetch_github_spec(self):
        """Test fetching OpenSearch API specification from GitHub."""
        # Create a mock response
        mock_response = AsyncMock()
        mock_response.text = AsyncMock(return_value=yaml.dump(self.mock_spec))
        mock_response.raise_for_status = Mock()

        # Create a mock for the get response context manager
        mock_get_context = AsyncMock()
        mock_get_context.__aenter__ = AsyncMock(return_value=mock_response)
        mock_get_context.__aexit__ = AsyncMock(return_value=None)

        # Create a mock session
        mock_session = AsyncMock()
        mock_session.get = Mock(return_value=mock_get_context)

        # Create a mock for the ClientSession context manager
        mock_client_context = AsyncMock()
        mock_client_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_client_context.__aexit__ = AsyncMock(return_value=None)

        # Patch aiohttp.ClientSession
        with patch('aiohttp.ClientSession', return_value=mock_client_context):
            # Call the function
            result = await self.fetch_github_spec('test.yaml')

            # Verify result
            assert result == self.mock_spec
            mock_session.get.assert_called_once()
            mock_response.raise_for_status.assert_called_once()
            mock_response.text.assert_called_once()

    def test_group_endpoints_by_operation(self):
        """Test grouping endpoints by operation."""
        # Call the function
        result = self.group_endpoints_by_operation(self.mock_spec['paths'])

        # Verify result
        assert 'cluster.health' in result
        assert 'count' in result
        assert len(result['cluster.health']) == 1
        assert result['cluster.health'][0]['path'] == '/_cluster/health/{index}'
        assert result['cluster.health'][0]['method'] == 'get'

    def test_extract_parameters(self):
        """Test extracting parameters from endpoints."""
        # Create endpoints from mock_spec
        endpoints = []
        for path, methods in self.mock_spec['paths'].items():
            for method, details in methods.items():
                endpoints.append({'path': path, 'method': method, 'details': details})

        # Call the function
        all_parameters, path_parameters, required_parameters = self.extract_parameters(endpoints)

        # Verify results
        assert 'opensearch_cluster_name' in all_parameters
        assert 'index' in all_parameters
        assert 'body' in all_parameters

        # Check path parameters
        assert 'index' in path_parameters
        assert len(path_parameters) == 1

        # Check parameter details
        assert all_parameters['index']['title'] == 'Index'
        assert all_parameters['index']['type'] == 'string'
        assert all_parameters['body']['title'] == 'Body'

    def test_process_body(self):
        """Test processing request body."""
        # Test with dictionary containing float values
        body = {'settings': {'number_of_shards': 1.0, 'number_of_replicas': 2.0}}
        result = self.process_body(body, 'IndicesCreate')
        assert result['settings']['number_of_shards'] == 1
        assert result['settings']['number_of_replicas'] == 2

        # Test with msearch NDJSON
        body = '{"index":"test"}\n{"query":{"match_all":{}}}'
        result = self.process_body(body, 'MsearchTool')
        assert result.endswith('\n')

        # Test with JSON string
        body = '{"query":{"match_all":{}}}'
        result = self.process_body(body, 'Count')
        assert isinstance(result, dict)
        assert 'query' in result

        # Test with JSON array for msearch
        body = '[{"index":"test"},{"query":{"match_all":{}}}]'
        result = self.process_body(body, 'MsearchTool')
        assert result.endswith('\n')
        assert '{"index": "test"}\n{"query": {"match_all": {}}}' in result

    def test_select_endpoint(self):
        """Test selecting the most appropriate endpoint based on parameters."""
        # Setup test endpoints
        endpoints = [
            {
                'path': '/_cluster/health',
                'method': 'get',
                'details': {'description': 'Returns cluster health for index'},
            },
            {
                'path': '/_cluster/health/{index}',
                'method': 'get',
                'details': {'description': 'Returns cluster health'},
            },
            {
                'path': '/_cluster/health/{index}/{shard}',
                'method': 'get',
                'details': {'description': 'Returns cluster health for specific shard'},
            },
        ]

        # Test case 1: With index parameter - should select the endpoint with {index}
        params = {'index': 'test-index'}
        selected = self.select_endpoint(endpoints, params)
        assert selected['path'] == '/_cluster/health/{index}'

        # Test case 2: Without index parameter - should select the simpler endpoint
        params = {}
        selected = self.select_endpoint(endpoints, params)
        assert selected['path'] == '/_cluster/health'

        # Test case 3: With both index and shard parameters - should select the most specific endpoint
        params = {'index': 'test-index', 'shard': '0'}
        selected = self.select_endpoint(endpoints, params)
        assert selected['path'] == '/_cluster/health/{index}/{shard}'

        # Test case 4: With index and extra parameters - should still select the index endpoint
        params = {'index': 'test-index', 'other_param': 'value'}
        selected = self.select_endpoint(endpoints, params)
        assert selected['path'] == '/_cluster/health/{index}'

        # Test case 5: With shard but no index - should select the base endpoint
        # since the shard endpoint requires index parameter
        params = {'shard': '0'}
        selected = self.select_endpoint(endpoints, params)
        assert selected['path'] == '/_cluster/health'

    @pytest.mark.asyncio
    async def test_generate_tool_from_group(self):
        """Test generating a tool from a group of endpoints."""
        # Setup
        endpoints = [
            {
                'path': '/_count',
                'method': 'get',
                'details': {
                    'description': 'Returns count of documents',
                    'x-operation-group': 'count',
                    'requestBody': {'content': {'application/json': {'schema': {}}}},
                },
            },
            {
                'path': '/_count',
                'method': 'post',
                'details': {
                    'description': 'Returns count of documents',
                    'x-operation-group': 'count',
                    'requestBody': {'content': {'application/json': {'schema': {}}}},
                },
            },
        ]

        # Mock initialize_client to return our mock client
        with patch('opensearch.client.initialize_client', return_value=self.mock_client):
            # Generate the tool
            tool = self.generate_tool_from_group('Count', endpoints)

            # Verify tool structure
            assert 'description' in tool
            assert 'input_schema' in tool
            assert 'function' in tool
            assert 'args_model' in tool
            assert tool['http_methods'] == 'GET, POST'
            assert tool['read_only_hint'] is True

            # Test the tool function with proper Pydantic model
            class MockParams(BaseModel):
                body: dict = {'query': {'match_all': {}}}
                opensearch_cluster_name: str = 'test-cluster'

            # Mock the tool function to avoid actual execution
            mock_tool_function = AsyncMock(
                return_value=[TextContent(type='text', text='test result')]
            )
            tool['function'] = mock_tool_function

            result = await tool['function'](MockParams())

            # Verify result
            assert len(result) == 1
            assert result[0].type == 'text'
            mock_tool_function.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_tools_from_openapi(self):
        """Test generating tools from OpenAPI specifications."""
        # Setup
        mock_spec = {
            'paths': {
                '/_cluster/health': {
                    'get': {
                        'description': 'Returns cluster health',
                        'x-operation-group': 'cluster.health',
                    }
                },
                '/_count': {
                    'get': {
                        'description': 'Returns count of documents',
                        'x-operation-group': 'count',
                        'requestBody': {'content': {'application/json': {'schema': {}}}},
                    }
                },
            }
        }

        # Mock fetch_github_spec to return our mock spec
        with patch('tools.tool_generator.fetch_github_spec', AsyncMock(return_value=mock_spec)):
            # Mock TOOL_REGISTRY
            mock_registry = {}
            with patch('tools.tool_generator.TOOL_REGISTRY', mock_registry):
                # Mock generate_tool_from_group
                mock_tool = {
                    'description': 'Test description',
                    'input_schema': {},
                    'function': AsyncMock(),
                    'args_model': Mock(),
                    'read_only_hint': True,
                }
                with patch(
                    'tools.tool_generator.generate_tool_from_group', return_value=mock_tool
                ):
                    # Call the function
                    result = await self.generate_tools_from_openapi()

                    # Verify results
                    assert 'ClusterHealthTool' in result
                    assert 'CountTool' in result
                    assert 'ClusterHealthTool' in result
                    assert 'CountTool' in result
                    assert 'description' in result['ClusterHealthTool']
                    assert 'input_schema' in result['ClusterHealthTool']
                    assert 'function' in result['ClusterHealthTool']
                    assert 'args_model' in result['ClusterHealthTool']
                    assert 'read_only_hint' in result['ClusterHealthTool']
                    assert result['ClusterHealthTool']['read_only_hint'] is True
