# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import pytest
from integration_tests.framework.assertions import assert_tool_success
from integration_tests.framework.constants import TEST_INDEX


@pytest.mark.server_modes
class TestSingleMode:
    """Verify single mode (default) behavior."""

    async def test_tools_available(self, default_client):
        tools = await default_client.list_tools()
        tool_names = {t.name for t in tools.tools}
        # Core tools should be present
        assert 'ListIndexTool' in tool_names
        assert 'SearchIndexTool' in tool_names

    async def test_no_cluster_name_param_required(self, default_client):
        """In single mode, tools should NOT require opensearch_cluster_name."""
        tools = await default_client.list_tools()
        for tool in tools.tools:
            props = tool.inputSchema.get('properties', {})
            assert 'opensearch_cluster_name' not in props, (
                f'Tool {tool.name} should not expose opensearch_cluster_name in single mode'
            )

    async def test_tool_call_without_cluster_name(self, default_client):
        result = await default_client.call_tool('ListIndexTool', arguments={})
        response = assert_tool_success(result)
        assert TEST_INDEX in response
