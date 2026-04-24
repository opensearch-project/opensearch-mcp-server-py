# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import pytest
from integration_tests.framework.assertions import assert_tool_error, assert_tool_success
from integration_tests.framework.constants import TEST_INDEX


@pytest.mark.tools
class TestGetIndexInfoTool:
    async def test_get_index_info(self, default_client):
        result = await default_client.call_tool(
            'GetIndexInfoTool', arguments={'index': TEST_INDEX}
        )
        assert_tool_success(result, 'Detailed information for index', TEST_INDEX, 'mappings')

    async def test_nonexistent_index(self, default_client):
        result = await default_client.call_tool(
            'GetIndexInfoTool', arguments={'index': 'nonexistent_xyz_404_test'}
        )
        assert_tool_error(result, 'index_not_found_exception')
