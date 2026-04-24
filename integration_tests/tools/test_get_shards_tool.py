# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import pytest
from integration_tests.framework.assertions import assert_tool_error, assert_tool_success
from integration_tests.framework.constants import TEST_INDEX


@pytest.mark.tools
class TestGetShardsTool:
    async def test_get_shards(self, default_client):
        result = await default_client.call_tool('GetShardsTool', arguments={'index': TEST_INDEX})
        assert_tool_success(result, TEST_INDEX, 'shard', 'prirep', 'state')

    async def test_nonexistent_index(self, default_client):
        result = await default_client.call_tool(
            'GetShardsTool', arguments={'index': 'nonexistent_xyz_404_test'}
        )
        assert_tool_error(result, 'index_not_found_exception')
