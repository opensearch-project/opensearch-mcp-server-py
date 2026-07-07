# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import json
import pytest
from integration_tests.framework.assertions import (
    assert_contains_json,
    assert_tool_error,
    assert_tool_success,
)
from integration_tests.framework.constants import TEST_INDEX


@pytest.mark.tools
@pytest.mark.requires_ml_tool('DataDistributionTool')
class TestDataDistributionTool:
    """Tests for DataDistributionTool (ML skills, requires OpenSearch 3.3+)."""

    async def test_data_distribution_single_analysis(self, default_client):
        """Single analysis mode returns singleAnalysis with field distributions."""
        result = await default_client.call_tool(
            'DataDistributionTool',
            arguments={
                'index': TEST_INDEX,
                'timeField': 'timestamp',
                'selectionTimeRangeStart': '2025-01-01T00:00:00Z',
                'selectionTimeRangeEnd': '2025-01-04T00:00:00Z',
            },
        )
        data = assert_contains_json(result, 'singleAnalysis')
        analysis = data['singleAnalysis']
        assert isinstance(analysis, list)
        assert len(analysis) > 0

        for entry in analysis:
            assert 'field' in entry
            assert 'divergence' in entry
            assert 'topChanges' in entry
            assert isinstance(entry['topChanges'], list)
            assert entry['divergence'] >= 0

            for change in entry['topChanges']:
                assert 'value' in change
                assert 'selectionPercentage' in change
                assert 0 <= change['selectionPercentage'] <= 1.0

    async def test_data_distribution_comparison_analysis(self, default_client):
        """Comparison analysis with baseline returns comparisonAnalysis with divergence scores."""
        result = await default_client.call_tool(
            'DataDistributionTool',
            arguments={
                'index': TEST_INDEX,
                'timeField': 'timestamp',
                'selectionTimeRangeStart': '2025-01-02T00:00:00Z',
                'selectionTimeRangeEnd': '2025-01-04T00:00:00Z',
                'baselineTimeRangeStart': '2025-01-01T00:00:00Z',
                'baselineTimeRangeEnd': '2025-01-02T00:00:00Z',
            },
        )
        data = assert_contains_json(result, 'comparisonAnalysis')
        analysis = data['comparisonAnalysis']
        assert isinstance(analysis, list)
        assert len(analysis) > 0

        for entry in analysis:
            assert 'field' in entry
            assert 'divergence' in entry
            assert 'topChanges' in entry
            assert entry['divergence'] > 0

            for change in entry['topChanges']:
                assert 'value' in change
                assert 'selectionPercentage' in change
                assert 'baselinePercentage' in change

    async def test_data_distribution_nonexistent_index(self, default_client):
        """Nonexistent index returns an error."""
        result = await default_client.call_tool(
            'DataDistributionTool',
            arguments={
                'index': 'nonexistent_xyz_404_test',
                'timeField': 'timestamp',
                'selectionTimeRangeStart': '2025-01-01T00:00:00Z',
                'selectionTimeRangeEnd': '2025-01-04T00:00:00Z',
            },
        )
        assert_tool_error(result)

    async def test_data_distribution_no_data_in_range(self, default_client):
        """Time range with no data returns an error."""
        result = await default_client.call_tool(
            'DataDistributionTool',
            arguments={
                'index': TEST_INDEX,
                'timeField': 'timestamp',
                'selectionTimeRangeStart': '2020-01-01T00:00:00Z',
                'selectionTimeRangeEnd': '2020-01-02T00:00:00Z',
            },
        )
        assert_tool_error(result, 'No data found')

    async def test_data_distribution_with_custom_size(self, default_client):
        """Custom size parameter limits document sampling."""
        result = await default_client.call_tool(
            'DataDistributionTool',
            arguments={
                'index': TEST_INDEX,
                'timeField': 'timestamp',
                'selectionTimeRangeStart': '2025-01-01T00:00:00Z',
                'selectionTimeRangeEnd': '2025-01-04T00:00:00Z',
                'size': 2,
            },
        )
        assert_tool_success(result, 'DataDistributionTool result')

    async def test_data_distribution_with_dsl_filter(self, default_client):
        """DSL filter narrows the analysis scope."""
        result = await default_client.call_tool(
            'DataDistributionTool',
            arguments={
                'index': TEST_INDEX,
                'timeField': 'timestamp',
                'selectionTimeRangeStart': '2025-01-01T00:00:00Z',
                'selectionTimeRangeEnd': '2025-01-04T00:00:00Z',
                'dsl': json.dumps({'match': {'category': 'A'}}),
            },
        )
        assert_tool_success(result, 'DataDistributionTool result')
