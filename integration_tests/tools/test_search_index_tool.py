# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import pytest
from integration_tests.framework.assertions import (
    assert_contains_json,
    assert_tool_error,
    assert_tool_success,
)
from integration_tests.framework.constants import TEST_INDEX


@pytest.mark.tools
class TestSearchIndexTool:
    # -- Happy paths --

    async def test_match_all(self, default_client):
        result = await default_client.call_tool(
            'SearchIndexTool',
            arguments={'index': TEST_INDEX, 'query_dsl': '{"query": {"match_all": {}}}'},
        )
        assert_tool_success(result, 'Search results from', 'Test document')

    async def test_specific_field_query(self, default_client):
        result = await default_client.call_tool(
            'SearchIndexTool',
            arguments={
                'index': TEST_INDEX,
                'query_dsl': '{"query": {"match": {"category": "A"}}}',
            },
        )
        assert_tool_success(result, 'Search results from', 'Test document 1')

    async def test_csv_output_format(self, default_client):
        result = await default_client.call_tool(
            'SearchIndexTool',
            arguments={
                'index': TEST_INDEX,
                'query_dsl': '{"query": {"match_all": {}}}',
                'format': 'csv',
            },
        )
        assert_tool_success(result, 'CSV format', 'Test document')

    async def test_size_parameter(self, default_client):
        result = await default_client.call_tool(
            'SearchIndexTool',
            arguments={
                'index': TEST_INDEX,
                'query_dsl': '{"query": {"match_all": {}}}',
                'size': 1,
            },
        )
        data = assert_contains_json(result)
        assert len(data['hits']['hits']) == 1

    async def test_empty_results_is_not_error(self, default_client):
        result = await default_client.call_tool(
            'SearchIndexTool',
            arguments={
                'index': TEST_INDEX,
                'query_dsl': '{"query": {"match": {"title": "xyznonexistent"}}}',
            },
        )
        data = assert_contains_json(result)
        assert data['hits']['total']['value'] == 0

    # -- Bad paths --

    async def test_nonexistent_index_returns_error(self, default_client):
        result = await default_client.call_tool(
            'SearchIndexTool',
            arguments={
                'index': 'nonexistent_xyz_404_test',
                'query_dsl': '{"query": {"match_all": {}}}',
            },
        )
        assert_tool_error(result, 'index_not_found_exception')

    async def test_malformed_query_dsl_returns_error(self, default_client):
        result = await default_client.call_tool(
            'SearchIndexTool',
            arguments={
                'index': TEST_INDEX,
                'query_dsl': '{"bad_field": {"unknown_query": true}}',
            },
        )
        assert_tool_error(result, 'parsing_exception')
