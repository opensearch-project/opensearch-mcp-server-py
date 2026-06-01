# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import pytest
from integration_tests.framework.assertions import (
    assert_contains_json,
    assert_tool_error,
    assert_tool_success,
)
from integration_tests.framework.constants import TEST_INDEX


@pytest.mark.tools
@pytest.mark.requires_ml_tool('DataDistributionTool')
class TestMetricChangeAnalysisTool:
    """Tests for MetricChangeAnalysisTool (ML skills, requires OpenSearch 3.3+)."""

    async def test_metric_change_analysis_structure(self, default_client):
        """Result contains percentileAnalysis with correct field structure."""
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
        data = assert_contains_json(result, 'percentileAnalysis')
        analysis = data['percentileAnalysis']
        assert isinstance(analysis, list)
        assert len(analysis) > 0

        for entry in analysis:
            assert 'field' in entry
            assert 'changeScore' in entry
            assert 'selectionPercentiles' in entry
            assert 'baselinePercentiles' in entry
            assert 'logRatios' in entry

            assert entry['changeScore'] >= 0
            assert 'p50' in entry['selectionPercentiles']
            assert 'p90' in entry['selectionPercentiles']
            assert 'p50' in entry['baselinePercentiles']
            assert 'p90' in entry['baselinePercentiles']
            assert 'p50' in entry['logRatios']
            assert 'p90' in entry['logRatios']

    async def test_metric_change_with_top_n(self, default_client):
        """topN parameter limits the number of returned fields."""
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
        data = assert_contains_json(result, 'percentileAnalysis')
        assert len(data['percentileAnalysis']) <= 1

    async def test_metric_change_results_sorted_by_change_score(self, default_client):
        """Results are sorted by changeScore in descending order."""
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
        data = assert_contains_json(result, 'percentileAnalysis')
        scores = [entry['changeScore'] for entry in data['percentileAnalysis']]
        assert scores == sorted(scores, reverse=True)

    async def test_metric_change_nonexistent_index(self, default_client):
        """Nonexistent index returns an error."""
        result = await default_client.call_tool(
            'MetricChangeAnalysisTool',
            arguments={
                'index': 'nonexistent_xyz_404_test',
                'timeField': 'timestamp',
                'selectionTimeRangeStart': '2025-01-02 00:00:00',
                'selectionTimeRangeEnd': '2025-01-04 00:00:00',
                'baselineTimeRangeStart': '2025-01-01 00:00:00',
                'baselineTimeRangeEnd': '2025-01-02 00:00:00',
            },
        )
        assert_tool_error(result)

    async def test_metric_change_no_data_in_range(self, default_client):
        """Time range with no data returns an error."""
        result = await default_client.call_tool(
            'MetricChangeAnalysisTool',
            arguments={
                'index': TEST_INDEX,
                'timeField': 'timestamp',
                'selectionTimeRangeStart': '2020-01-02 00:00:00',
                'selectionTimeRangeEnd': '2020-01-04 00:00:00',
                'baselineTimeRangeStart': '2020-01-01 00:00:00',
                'baselineTimeRangeEnd': '2020-01-02 00:00:00',
            },
        )
        assert_tool_error(result, 'No data found')

    async def test_metric_change_percentile_values_are_numeric(self, default_client):
        """Percentile values (p50, p90) are valid numbers."""
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
        data = assert_contains_json(result, 'percentileAnalysis')
        for entry in data['percentileAnalysis']:
            for percentile_key in ('selectionPercentiles', 'baselinePercentiles'):
                p50 = entry[percentile_key]['p50']
                p90 = entry[percentile_key]['p90']
                assert isinstance(p50, (int, float))
                assert isinstance(p90, (int, float))
                assert p90 >= p50

            for ratio_key in ('p50', 'p90'):
                ratio = entry['logRatios'][ratio_key]
                assert isinstance(ratio, (int, float))
                assert ratio >= 0
