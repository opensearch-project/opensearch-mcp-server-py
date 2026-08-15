# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import pytest
from integration_tests.framework.constants import BUILTIN_CATEGORIES


@pytest.mark.tools
class TestListToolsMeta:
    """Verify that tools/list returns _meta.category for each enabled tool."""

    async def test_core_tools_have_category_in_meta(self, default_client):
        """Core tools must advertise category='core_tools' in _meta."""
        result = await default_client.list_tools()
        tools_by_name = {t.name: t for t in result.tools}

        core_tools = ('ListIndexTool', 'SearchIndexTool', 'ClusterHealthTool', 'GetShardsTool')
        for tool_name in core_tools:
            assert tool_name in tools_by_name, f'{tool_name} missing from tools/list'
            tool = tools_by_name[tool_name]
            assert tool.meta is not None, f'{tool_name} is missing _meta'
            assert tool.meta.get('category') == 'core_tools', (
                f'{tool_name}: expected category=core_tools, got {tool.meta}'
            )

    async def test_all_listed_tools_have_known_category_or_no_meta(self, default_client):
        """Every tool either has a known category in _meta or has no _meta at all."""
        result = await default_client.list_tools()

        for tool in result.tools:
            if tool.meta is None:
                continue
            assert 'category' in tool.meta, (
                f'{tool.name} has _meta but is missing the category key: {tool.meta}'
            )
            assert tool.meta['category'] in BUILTIN_CATEGORIES, (
                f'{tool.name} has unknown category "{tool.meta["category"]}"'
            )

    async def test_list_tools_returns_tools(self, default_client):
        """Sanity check: tools/list returns at least the default core tools."""
        result = await default_client.list_tools()
        assert len(result.tools) >= 9, f'Expected at least 9 core tools, got {len(result.tools)}'
