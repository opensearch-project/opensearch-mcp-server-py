# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import pytest
from integration_tests.framework.assertions import assert_tool_success
from integration_tests.framework.constants import TEST_INDEX


@pytest.mark.tools
class TestGetClusterStateTool:
    async def test_get_full_state(self, default_client):
        result = await default_client.call_tool('GetClusterStateTool', arguments={})
        assert_tool_success(result, 'Cluster state information', 'cluster_name')

    async def test_get_state_with_metric(self, default_client):
        result = await default_client.call_tool(
            'GetClusterStateTool', arguments={'metric': 'nodes'}
        )
        assert_tool_success(result, 'Cluster state information', 'nodes')

    async def test_get_state_with_index(self, default_client):
        result = await default_client.call_tool(
            'GetClusterStateTool',
            arguments={'metric': 'metadata', 'index': TEST_INDEX},
        )
        assert_tool_success(result, 'Cluster state information', 'metadata', TEST_INDEX)
