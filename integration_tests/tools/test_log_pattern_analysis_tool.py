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
@pytest.mark.requires_ml_tool('LogPatternAnalysisTool')
class TestLogPatternAnalysisTool:
    """Tests for LogPatternAnalysisTool (ML skills, requires OpenSearch 3.3+)."""

    async def test_log_pattern_insight_mode_structure(self, default_client):
        """Insight mode (no baseline) returns logInsights with pattern/count/sampleLogs."""
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
        data = assert_contains_json(result, 'logInsights')
        insights = data['logInsights']
        assert isinstance(insights, list)

        for entry in insights:
            assert 'pattern' in entry
            assert 'count' in entry
            assert 'sampleLogs' in entry
            assert entry['count'] > 0
            assert isinstance(entry['sampleLogs'], list)

    async def test_log_pattern_diff_mode_structure(self, default_client):
        """Diff mode (with baseline, no trace) returns patternMapDifference with lift scores."""
        result = await default_client.call_tool(
            'LogPatternAnalysisTool',
            arguments={
                'index': TEST_INDEX,
                'logFieldName': 'title',
                'timeField': 'timestamp',
                'selectionTimeRangeStart': '2025-01-02T00:00:00Z',
                'selectionTimeRangeEnd': '2025-01-04T00:00:00Z',
                'baseTimeRangeStart': '2025-01-01T00:00:00Z',
                'baseTimeRangeEnd': '2025-01-02T00:00:00Z',
            },
        )
        data = assert_contains_json(result, 'patternMapDifference')
        diffs = data['patternMapDifference']
        assert isinstance(diffs, list)

        for entry in diffs:
            assert 'pattern' in entry
            assert 'selection' in entry
            assert 'base' in entry
            assert 'lift' in entry
            assert isinstance(entry['selection'], (int, float))
            assert entry['selection'] >= 0
            assert isinstance(entry['base'], (int, float))
            assert entry['base'] >= 0
            if entry['lift'] is not None:
                assert entry['lift'] > 0

    async def test_log_pattern_nonexistent_index(self, default_client):
        """Nonexistent index returns an error."""
        result = await default_client.call_tool(
            'LogPatternAnalysisTool',
            arguments={
                'index': 'nonexistent_xyz_404_test',
                'logFieldName': 'title',
                'timeField': 'timestamp',
                'selectionTimeRangeStart': '2025-01-01T00:00:00Z',
                'selectionTimeRangeEnd': '2025-01-04T00:00:00Z',
            },
        )
        assert_tool_error(result)

    async def test_log_pattern_with_filter(self, default_client):
        """Filter expression narrows the analysis scope."""
        result = await default_client.call_tool(
            'LogPatternAnalysisTool',
            arguments={
                'index': TEST_INDEX,
                'logFieldName': 'title',
                'timeField': 'timestamp',
                'selectionTimeRangeStart': '2025-01-01T00:00:00Z',
                'selectionTimeRangeEnd': '2025-01-04T00:00:00Z',
                'filter': "category='A'",
            },
        )
        assert_tool_success(result, 'LogPatternAnalysisTool result')
