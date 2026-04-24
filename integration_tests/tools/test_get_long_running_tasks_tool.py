# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import pytest
from integration_tests.framework.assertions import assert_tool_success


@pytest.mark.tools
class TestGetLongRunningTasksTool:
    async def test_get_tasks(self, default_client):
        result = await default_client.call_tool('GetLongRunningTasksTool', arguments={})
        # Returns either "Top N long-running tasks..." or "No tasks found in the cluster."
        assert_tool_success(result, 'tasks')

    async def test_get_tasks_with_limit(self, default_client):
        result = await default_client.call_tool('GetLongRunningTasksTool', arguments={'limit': 5})
        assert_tool_success(result, 'tasks')
