# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import pytest
from integration_tests.framework.assertions import assert_tool_error, assert_tool_success
from integration_tests.framework.constants import TEST_INDEX


@pytest.mark.tools
class TestIndexMappingTool:
    async def test_get_mapping(self, default_client):
        result = await default_client.call_tool(
            'IndexMappingTool', arguments={'index': TEST_INDEX}
        )
        assert_tool_success(result, 'Mapping for', 'title', 'category', 'timestamp', 'value')

    async def test_nonexistent_index(self, default_client):
        result = await default_client.call_tool(
            'IndexMappingTool', arguments={'index': 'nonexistent_xyz_404_test'}
        )
        assert_tool_error(result, 'index_not_found_exception')
