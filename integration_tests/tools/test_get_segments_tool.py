# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import pytest
from integration_tests.framework.assertions import assert_tool_success
from integration_tests.framework.constants import TEST_INDEX


@pytest.mark.tools
class TestGetSegmentsTool:
    async def test_get_segments_for_index(self, default_client):
        result = await default_client.call_tool('GetSegmentsTool', arguments={'index': TEST_INDEX})
        assert_tool_success(result, 'Segment information', TEST_INDEX)

    async def test_get_all_segments(self, default_client):
        result = await default_client.call_tool('GetSegmentsTool', arguments={})
        assert_tool_success(result, 'Segment information')
