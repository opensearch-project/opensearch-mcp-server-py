# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import pytest
from integration_tests.framework.assertions import assert_tool_error, assert_tool_success
from integration_tests.framework.constants import TEST_INDEX


@pytest.mark.tools
class TestListIndexTool:
    async def test_list_all_indices(self, default_client):
        result = await default_client.call_tool('ListIndexTool', arguments={})
        assert_tool_success(result, 'All indices information:', TEST_INDEX)

    async def test_list_specific_index(self, default_client):
        result = await default_client.call_tool('ListIndexTool', arguments={'index': TEST_INDEX})
        assert_tool_success(result, TEST_INDEX)

    async def test_list_names_only(self, default_client):
        result = await default_client.call_tool(
            'ListIndexTool', arguments={'include_detail': False}
        )
        assert_tool_success(result, 'Indices:', TEST_INDEX)

    async def test_nonexistent_index_returns_error(self, default_client):
        result = await default_client.call_tool(
            'ListIndexTool', arguments={'index': 'nonexistent_xyz_404_test'}
        )
        assert_tool_error(result, 'index_not_found_exception')
