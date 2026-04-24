# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import pytest
from integration_tests.framework.assertions import assert_contains_json, assert_tool_error
from integration_tests.framework.constants import TEST_INDEX


@pytest.mark.tools
class TestCountTool:
    async def test_count_test_index(self, default_client):
        result = await default_client.call_tool('CountTool', arguments={'index': TEST_INDEX})
        data = assert_contains_json(result, 'count')
        assert data['count'] == 3

    async def test_count_nonexistent_index(self, default_client):
        result = await default_client.call_tool(
            'CountTool', arguments={'index': 'nonexistent_xyz_404_test'}
        )
        assert_tool_error(result, 'index_not_found_exception')
