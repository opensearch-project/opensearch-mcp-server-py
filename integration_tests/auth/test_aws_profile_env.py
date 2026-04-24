# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import pytest
from integration_tests.framework.assertions import assert_tool_success
from integration_tests.framework.constants import TEST_INDEX


@pytest.mark.auth
@pytest.mark.aws
class TestAWSProfileEnv:
    """Verify that AWS_PROFILE env var auth works."""

    async def test_list_index(self, profile_env_client):
        result = await profile_env_client.call_tool('ListIndexTool', arguments={})
        assert_tool_success(result, 'All indices information:', TEST_INDEX)

    async def test_get_shards(self, profile_env_client):
        result = await profile_env_client.call_tool(
            'GetShardsTool',
            arguments={'index': TEST_INDEX},
        )
        assert_tool_success(result, TEST_INDEX, 'shard', 'prirep', 'state')
