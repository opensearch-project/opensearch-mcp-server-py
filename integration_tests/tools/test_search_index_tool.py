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

    async def test_compressed_format(self, default_client):
        result = await default_client.call_tool(
            'SearchIndexTool',
            arguments={
                'index': TEST_INDEX,
                'query_dsl': '{"query": {"match_all": {}}}',
                'format': 'compressed',
            },
        )
        text = assert_tool_success(result, f'Search results from {TEST_INDEX}')
        lines = text.split('\n')
        header_line = None
        for line in lines:
            if 'title' in line and 'category' in line:
                header_line = line
                break
        assert header_line is not None, f'No TSV header found in compressed output: {text[:500]}'
        assert '\t' in header_line

    async def test_compressed_contains_all_documents(self, default_client):
        result = await default_client.call_tool(
            'SearchIndexTool',
            arguments={
                'index': TEST_INDEX,
                'query_dsl': '{"query": {"match_all": {}}}',
                'format': 'compressed',
                'size': 3,
            },
        )
        text = assert_tool_success(result, f'Search results from {TEST_INDEX}')
        assert 'Test document 1' in text
        assert 'Test document 2' in text
        assert 'Test document 3' in text

    async def test_compressed_aggregation_only(self, default_client):
        result = await default_client.call_tool(
            'SearchIndexTool',
            arguments={
                'index': TEST_INDEX,
                'query_dsl': '{"query": {"match_all": {}}, "size": 0, "aggs": {"categories": {"terms": {"field": "category"}}}}',
                'format': 'compressed',
            },
        )
        text = assert_tool_success(result, f'Search results from {TEST_INDEX}')
        assert 'categories' in text

    async def test_compressed_empty_results(self, default_client):
        result = await default_client.call_tool(
            'SearchIndexTool',
            arguments={
                'index': TEST_INDEX,
                'query_dsl': '{"query": {"match": {"title": "xyznonexistent"}}}',
                'format': 'compressed',
            },
        )
        assert_tool_success(result, 'No documents found')

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
