# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import pytest
from integration_tests.framework.assertions import assert_tool_success
from integration_tests.framework.constants import TEST_INDEX


@pytest.mark.tools
@pytest.mark.requires_ml_tool('DataDistributionTool')
class TestMetricChangeAnalysisTool:
    """Tests for MetricChangeAnalysisTool (ML skills, requires OpenSearch 3.3+)."""

    async def test_metric_change_analysis(self, default_client):
        result = await default_client.call_tool(
            'MetricChangeAnalysisTool',
            arguments={
                'index': TEST_INDEX,
                'timeField': 'timestamp',
                'selectionTimeRangeStart': '2025-01-02 00:00:00',
                'selectionTimeRangeEnd': '2025-01-04 00:00:00',
                'baselineTimeRangeStart': '2025-01-01 00:00:00',
                'baselineTimeRangeEnd': '2025-01-02 00:00:00',
            },
        )
        assert_tool_success(result, 'MetricChangeAnalysisTool result')

    async def test_metric_change_with_top_n(self, default_client):
        result = await default_client.call_tool(
            'MetricChangeAnalysisTool',
            arguments={
                'index': TEST_INDEX,
                'timeField': 'timestamp',
                'selectionTimeRangeStart': '2025-01-02 00:00:00',
                'selectionTimeRangeEnd': '2025-01-04 00:00:00',
                'baselineTimeRangeStart': '2025-01-01 00:00:00',
                'baselineTimeRangeEnd': '2025-01-02 00:00:00',
                'topN': 1,
            },
        )
        assert_tool_success(result, 'MetricChangeAnalysisTool result')
