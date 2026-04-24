# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import json
import pytest
from integration_tests.framework.assertions import assert_tool_success
from integration_tests.framework.constants import TEST_INDEX


@pytest.mark.tools
class TestMsearchTool:
    async def test_multi_search(self, default_client):
        searches = json.dumps(
            [
                {'index': TEST_INDEX},
                {'query': {'match_all': {}}},
            ]
        )
        result = await default_client.call_tool('MsearchTool', arguments={'body': searches})
        assert_tool_success(result, '"responses"')

    async def test_msearch_nonexistent_index(self, default_client):
        searches = json.dumps(
            [
                {'index': 'nonexistent_xyz_404_test'},
                {'query': {'match_all': {}}},
            ]
        )
        result = await default_client.call_tool('MsearchTool', arguments={'body': searches})
        # Msearch returns 200 with per-search errors in the responses array
        assert_tool_success(result, '"responses"')
