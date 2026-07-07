# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import pytest
from integration_tests.framework.assertions import (
    assert_tool_error,
    assert_tool_success,
)
from integration_tests.framework.constants import TEST_INDEX


@pytest.mark.tools
class TestPPLQueryTool:
    # -- Happy paths --

    async def test_basic_source_query(self, default_client):
        result = await default_client.call_tool(
            'PPLQueryTool',
            arguments={'query': f'source={TEST_INDEX}'},
        )
        assert_tool_success(result, 'PPL query results')

    async def test_query_with_fields(self, default_client):
        result = await default_client.call_tool(
            'PPLQueryTool',
            arguments={'query': f'source={TEST_INDEX} | fields title, category'},
        )
        assert_tool_success(result, 'PPL query results')

    async def test_query_with_stats(self, default_client):
        result = await default_client.call_tool(
            'PPLQueryTool',
            arguments={'query': f'source={TEST_INDEX} | stats count() by category'},
        )
        assert_tool_success(result, 'PPL query results')

    async def test_query_with_where(self, default_client):
        result = await default_client.call_tool(
            'PPLQueryTool',
            arguments={'query': f'source={TEST_INDEX} | where category="A"'},
        )
        assert_tool_success(result, 'PPL query results')

    async def test_csv_format(self, default_client):
        result = await default_client.call_tool(
            'PPLQueryTool',
            arguments={
                'query': f'source={TEST_INDEX} | fields title',
                'format': 'csv',
            },
        )
        assert_tool_success(result, 'PPL query results')

    # -- Bad paths --

    async def test_nonexistent_index_returns_error(self, default_client):
        result = await default_client.call_tool(
            'PPLQueryTool',
            arguments={'query': 'source=nonexistent_xyz_404_test'},
        )
        assert_tool_error(result)

    async def test_invalid_syntax_returns_error(self, default_client):
        result = await default_client.call_tool(
            'PPLQueryTool',
            arguments={'query': 'INVALID PPL SYNTAX |||'},
        )
        assert_tool_error(result)
