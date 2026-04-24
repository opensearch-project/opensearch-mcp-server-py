# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import pytest
from integration_tests.framework.assertions import assert_contains_json
from integration_tests.framework.constants import TEST_INDEX


@pytest.mark.auth
@pytest.mark.aws
class TestAWSCredentials:
    """Verify that direct AWS credentials (access key + secret + session token) work."""

    async def test_list_tools(self, aws_creds_client):
        tools = await aws_creds_client.list_tools()
        tool_names = {t.name for t in tools.tools}
        assert 'ListIndexTool' in tool_names

    async def test_cluster_health(self, aws_creds_client):
        result = await aws_creds_client.call_tool('ClusterHealthTool', arguments={})
        data = assert_contains_json(result, 'cluster_name', 'status')
        assert data['status'] in ('green', 'yellow', 'red')

    async def test_count(self, aws_creds_client):
        result = await aws_creds_client.call_tool(
            'CountTool',
            arguments={'index': TEST_INDEX},
        )
        assert_contains_json(result, 'count')
