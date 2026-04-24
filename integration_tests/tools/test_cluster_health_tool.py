# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import pytest
from integration_tests.framework.assertions import assert_contains_json


@pytest.mark.tools
class TestClusterHealthTool:
    async def test_happy_path(self, default_client):
        result = await default_client.call_tool('ClusterHealthTool', arguments={})
        data = assert_contains_json(result, 'cluster_name', 'status')
        assert data['status'] in ('green', 'yellow', 'red')
