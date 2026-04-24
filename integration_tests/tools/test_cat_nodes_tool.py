# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import pytest
from integration_tests.framework.assertions import assert_tool_success


@pytest.mark.tools
class TestCatNodesTool:
    async def test_get_all_nodes(self, default_client):
        result = await default_client.call_tool('CatNodesTool', arguments={})
        assert_tool_success(result, 'Node information', 'node.role')

    async def test_get_nodes_with_metrics(self, default_client):
        result = await default_client.call_tool(
            'CatNodesTool', arguments={'metrics': 'name,ip,heap.percent'}
        )
        assert_tool_success(result, 'name', 'ip', 'heap.percent')
