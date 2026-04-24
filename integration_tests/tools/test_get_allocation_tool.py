# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import pytest
from integration_tests.framework.assertions import assert_tool_success


@pytest.mark.tools
class TestGetAllocationTool:
    async def test_get_allocation(self, default_client):
        result = await default_client.call_tool('GetAllocationTool', arguments={})
        assert_tool_success(result, 'Allocation information')
