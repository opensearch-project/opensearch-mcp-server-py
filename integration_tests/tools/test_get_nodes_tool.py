# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import pytest
from integration_tests.framework.assertions import assert_tool_success


@pytest.mark.tools
class TestGetNodesTool:
    async def test_get_all_nodes(self, default_client):
        result = await default_client.call_tool('GetNodesTool', arguments={})
        assert_tool_success(result, 'Detailed node information')

    async def test_get_nodes_with_metric(self, default_client):
        result = await default_client.call_tool('GetNodesTool', arguments={'metric': 'jvm,os'})
        assert_tool_success(result, 'Detailed node information')
