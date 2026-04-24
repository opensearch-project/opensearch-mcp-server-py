# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import pytest
from integration_tests.framework.assertions import assert_contains_json, assert_tool_success
from integration_tests.framework.constants import TEST_INDEX


@pytest.mark.auth
@pytest.mark.iam_role
class TestIAMRole:
    """Verify that IAM role assumption auth works."""

    async def test_cluster_health(self, iam_role_client):
        result = await iam_role_client.call_tool('ClusterHealthTool', arguments={})
        data = assert_contains_json(result, 'cluster_name', 'status')
        assert data['status'] in ('green', 'yellow', 'red')

    async def test_list_index(self, iam_role_client):
        result = await iam_role_client.call_tool('ListIndexTool', arguments={})
        assert_tool_success(result, 'All indices information:', TEST_INDEX)
