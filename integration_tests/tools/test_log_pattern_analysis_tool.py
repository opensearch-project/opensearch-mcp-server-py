# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import pytest
from integration_tests.framework.assertions import assert_tool_success
from integration_tests.framework.constants import TEST_INDEX


@pytest.mark.tools
class TestLogPatternAnalysisTool:
    """Tests for LogPatternAnalysisTool (ML skills, requires OpenSearch 3.3+)."""

    async def test_log_pattern_analysis(self, default_client):
        result = await default_client.call_tool(
            'LogPatternAnalysisTool',
            arguments={
                'index': TEST_INDEX,
                'logFieldName': 'title',
                'timeField': 'timestamp',
                'selectionTimeRangeStart': '2025-01-01T00:00:00Z',
                'selectionTimeRangeEnd': '2025-01-04T00:00:00Z',
            },
        )
        assert_tool_success(result, 'LogPatternAnalysisTool result')
