# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import pytest
import sys
from unittest.mock import AsyncMock, Mock, patch


class TestSkillsTools:
    def setup_method(self):
        """Setup that runs before each test method."""
        self.mock_client = Mock()
        self.mock_client.close = AsyncMock()
        # MetricChangeAnalysisTool counts each window before analyzing; default
        # to a small count so the doc-count guard passes. Tests that exercise
        # the guard override this.
        self.mock_client.count = AsyncMock(return_value={'count': 10})

        self.init_client_patcher = patch(
            'opensearch.client.initialize_client', return_value=self.mock_client
        )
        self.init_client_patcher.start()

        modules_to_clear = [
            'tools.skills_tools',
        ]
        for module in modules_to_clear:
            if module in sys.modules:
                del sys.modules[module]

        from tools.skills_tools import (
            SKILLS_TOOLS_REGISTRY,
            DataDistributionToolArgs,
            LogPatternAnalysisToolArgs,
            MetricChangeAnalysisToolArgs,
            data_distribution_tool,
            log_pattern_analysis_tool,
            metric_change_analysis_tool,
        )

        self.SKILLS_TOOLS_REGISTRY = SKILLS_TOOLS_REGISTRY
        self.DataDistributionToolArgs = DataDistributionToolArgs
        self.LogPatternAnalysisToolArgs = LogPatternAnalysisToolArgs
        self.MetricChangeAnalysisToolArgs = MetricChangeAnalysisToolArgs
        self._data_distribution_tool = data_distribution_tool
        self._log_pattern_analysis_tool = log_pattern_analysis_tool
        self._metric_change_analysis_tool = metric_change_analysis_tool

    def teardown_method(self):
        """Cleanup after each test method."""
        self.init_client_patcher.stop()

    @pytest.mark.asyncio
    async def test_data_distribution_tool_single_analysis(self):
        """Test data_distribution_tool single dataset analysis (no baseline)."""
        # Mock search response
        self.mock_client.search = AsyncMock(
            return_value={
                'hits': {
                    'hits': [
                        {'_source': {'status': 'error', 'level': 'high'}},
                        {'_source': {'status': 'ok', 'level': 'low'}},
                        {'_source': {'status': 'error', 'level': 'high'}},
                        {'_source': {'status': 'ok', 'level': 'medium'}},
                    ]
                }
            }
        )
        # Mock mappings response
        self.mock_client.indices = Mock()
        self.mock_client.indices.get_mapping = AsyncMock(
            return_value={
                'test-index': {
                    'mappings': {
                        'properties': {
                            'status': {'type': 'keyword'},
                            'level': {'type': 'keyword'},
                            '@timestamp': {'type': 'date'},
                        }
                    }
                }
            }
        )

        args = self.DataDistributionToolArgs(
            index='test-index',
            selectionTimeRangeStart='2023-01-01 00:00:00',
            selectionTimeRangeEnd='2023-01-02 00:00:00',
            timeField='@timestamp',
            opensearch_cluster_name='',
        )

        result = await self._data_distribution_tool(args)

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'DataDistributionTool result:' in result[0]['text']
        assert 'singleAnalysis' in result[0]['text']

    @pytest.mark.asyncio
    async def test_data_distribution_tool_comparison_analysis(self):
        """Test data_distribution_tool comparison analysis with baseline."""
        call_count = [0]

        async def mock_search(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return {
                    'hits': {
                        'hits': [
                            {'_source': {'status': 'error'}},
                            {'_source': {'status': 'error'}},
                            {'_source': {'status': 'ok'}},
                        ]
                    }
                }
            else:
                return {
                    'hits': {
                        'hits': [
                            {'_source': {'status': 'ok'}},
                            {'_source': {'status': 'ok'}},
                            {'_source': {'status': 'error'}},
                        ]
                    }
                }

        self.mock_client.search = AsyncMock(side_effect=mock_search)
        self.mock_client.indices = Mock()
        self.mock_client.indices.get_mapping = AsyncMock(
            return_value={
                'test-index': {
                    'mappings': {
                        'properties': {
                            'status': {'type': 'keyword'},
                            '@timestamp': {'type': 'date'},
                        }
                    }
                }
            }
        )

        args = self.DataDistributionToolArgs(
            index='test-index',
            selectionTimeRangeStart='2023-01-01 00:00:00',
            selectionTimeRangeEnd='2023-01-02 00:00:00',
            timeField='@timestamp',
            baselineTimeRangeStart='2022-12-01 00:00:00',
            baselineTimeRangeEnd='2022-12-02 00:00:00',
            opensearch_cluster_name='',
        )

        result = await self._data_distribution_tool(args)

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'comparisonAnalysis' in result[0]['text']

    @pytest.mark.asyncio
    async def test_data_distribution_tool_error_handling(self):
        """Test data_distribution_tool exception handling."""
        self.mock_client.search = AsyncMock(side_effect=Exception('Connection error'))
        self.mock_client.indices = Mock()
        self.mock_client.indices.get_mapping = AsyncMock(return_value={})

        args = self.DataDistributionToolArgs(
            index='test-index',
            selectionTimeRangeStart='2023-01-01 00:00:00',
            selectionTimeRangeEnd='2023-01-02 00:00:00',
            timeField='@timestamp',
            opensearch_cluster_name='',
        )

        result = await self._data_distribution_tool(args)

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Error' in result[0]['text']

    @pytest.mark.asyncio
    async def test_log_pattern_analysis_tool_insight_mode(self):
        """Test log_pattern_analysis_tool in insight mode (no baseline)."""
        self.mock_client.transport = Mock()
        self.mock_client.transport.perform_request = AsyncMock(
            return_value={
                'schema': [
                    {'name': 'patterns_field'},
                    {'name': 'pattern_count'},
                    {'name': 'sample_logs'},
                ],
                'datarows': [
                    ['ERROR <*> failed', 5, ['ERROR connection failed', 'ERROR auth failed']],
                    ['WARN <*> timeout', 3, ['WARN request timeout']],
                ],
            }
        )

        args = self.LogPatternAnalysisToolArgs(
            index='logs-index',
            logFieldName='message',
            selectionTimeRangeStart='2023-01-01 00:00:00',
            selectionTimeRangeEnd='2023-01-02 00:00:00',
            timeField='@timestamp',
            opensearch_cluster_name='',
        )

        result = await self._log_pattern_analysis_tool(args)

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'LogPatternAnalysisTool result:' in result[0]['text']
        assert 'logInsights' in result[0]['text']

    @pytest.mark.asyncio
    async def test_log_pattern_analysis_tool_diff_mode(self):
        """Test log_pattern_analysis_tool in pattern diff mode (with baseline, no trace)."""
        call_count = [0]

        async def mock_ppl_request(*args, **kwargs):
            call_count[0] += 1
            return {
                'schema': [{'name': 'pattern_count'}, {'name': 'patterns_field'}],
                'datarows': [
                    [10, 'ERROR <*> connection refused'],
                    [5, 'WARN <*> retry attempt'],
                ],
            }

        self.mock_client.transport = Mock()
        self.mock_client.transport.perform_request = AsyncMock(side_effect=mock_ppl_request)

        args = self.LogPatternAnalysisToolArgs(
            index='logs-index',
            logFieldName='message',
            selectionTimeRangeStart='2023-01-01 00:00:00',
            selectionTimeRangeEnd='2023-01-02 00:00:00',
            timeField='@timestamp',
            baseTimeRangeStart='2022-12-01 00:00:00',
            baseTimeRangeEnd='2022-12-02 00:00:00',
            opensearch_cluster_name='',
        )

        result = await self._log_pattern_analysis_tool(args)

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'LogPatternAnalysisTool result:' in result[0]['text']
        assert 'patternMapDifference' in result[0]['text']

    @pytest.mark.asyncio
    async def test_log_pattern_analysis_tool_sequence_mode(self):
        """Test log_pattern_analysis_tool in sequence analysis mode (with trace + baseline)."""
        call_count = [0]

        async def mock_ppl_request(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # Selection result
                return {
                    'schema': [
                        {'name': 'traceId'},
                        {'name': 'patterns_field'},
                        {'name': '@timestamp'},
                    ],
                    'datarows': [
                        ['trace-1', 'GET <*> /api', '2023-01-01 01:00:00'],
                        ['trace-1', 'ERROR <*> timeout', '2023-01-01 01:01:00'],
                        ['trace-2', 'GET <*> /api', '2023-01-01 02:00:00'],
                    ],
                }
            else:
                # Base result
                return {
                    'schema': [
                        {'name': 'traceId'},
                        {'name': 'patterns_field'},
                        {'name': '@timestamp'},
                    ],
                    'datarows': [
                        ['trace-3', 'GET <*> /api', '2022-12-01 01:00:00'],
                        ['trace-3', 'OK <*> response', '2022-12-01 01:01:00'],
                        ['trace-4', 'GET <*> /api', '2022-12-01 02:00:00'],
                    ],
                }

        self.mock_client.transport = Mock()
        self.mock_client.transport.perform_request = AsyncMock(side_effect=mock_ppl_request)

        args = self.LogPatternAnalysisToolArgs(
            index='logs-index',
            logFieldName='message',
            selectionTimeRangeStart='2023-01-01 00:00:00',
            selectionTimeRangeEnd='2023-01-02 00:00:00',
            timeField='@timestamp',
            traceFieldName='traceId',
            baseTimeRangeStart='2022-12-01 00:00:00',
            baseTimeRangeEnd='2022-12-02 00:00:00',
            opensearch_cluster_name='',
        )

        result = await self._log_pattern_analysis_tool(args)

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'LogPatternAnalysisTool result:' in result[0]['text']
        assert 'EXCEPTIONAL' in result[0]['text']
        assert 'BASE' in result[0]['text']

    @pytest.mark.asyncio
    async def test_log_pattern_analysis_tool_error_handling(self):
        """Test log_pattern_analysis_tool exception handling."""
        self.mock_client.transport = Mock()
        self.mock_client.transport.perform_request = AsyncMock(
            side_effect=Exception('PPL query failed')
        )

        args = self.LogPatternAnalysisToolArgs(
            index='logs-index',
            logFieldName='message',
            selectionTimeRangeStart='2023-01-01 00:00:00',
            selectionTimeRangeEnd='2023-01-02 00:00:00',
            timeField='@timestamp',
            opensearch_cluster_name='',
        )

        result = await self._log_pattern_analysis_tool(args)

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Error' in result[0]['text']

    @pytest.mark.asyncio
    async def test_metric_change_analysis_tool_basic(self):
        """Default behavior: per-column percentile aggs, no groupBy."""
        call_count = [0]

        async def mock_search(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                # Selection aggregation - high response times
                return {
                    'hits': {'total': {'value': 5, 'relation': 'eq'}},
                    'aggregations': {
                        'responseTime': {'values': {'50.0': 5500.0, '90.0': 6800.0}},
                        'cpuUsage': {'values': {'50.0': 88.0, '90.0': 91.6}},
                    },
                }
            else:
                # Baseline aggregation - normal response times
                return {
                    'hits': {'total': {'value': 5, 'relation': 'eq'}},
                    'aggregations': {
                        'responseTime': {'values': {'50.0': 120.0, '90.0': 146.0}},
                        'cpuUsage': {'values': {'50.0': 31.0, '90.0': 34.6}},
                    },
                }

        self.mock_client.search = AsyncMock(side_effect=mock_search)
        self.mock_client.indices = Mock()
        self.mock_client.indices.get_mapping = AsyncMock(
            return_value={
                'test-index': {
                    'mappings': {
                        'properties': {
                            'responseTime': {'type': 'long'},
                            'cpuUsage': {'type': 'float'},
                            '@timestamp': {'type': 'date'},
                        }
                    }
                }
            }
        )

        args = self.MetricChangeAnalysisToolArgs(
            index='test-index',
            selectionTimeRangeStart='2023-01-01 10:00:00',
            selectionTimeRangeEnd='2023-01-01 10:30:00',
            timeField='@timestamp',
            baselineTimeRangeStart='2023-01-01 08:00:00',
            baselineTimeRangeEnd='2023-01-01 08:30:00',
            opensearch_cluster_name='',
        )

        result = await self._metric_change_analysis_tool(args)

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'MetricChangeAnalysisTool result:' in result[0]['text']
        assert 'percentileAnalysis' in result[0]['text']
        assert 'changeScore' in result[0]['text']
        assert 'selectionPercentiles' in result[0]['text']
        assert 'baselinePercentiles' in result[0]['text']
        assert 'logRatios' in result[0]['text']
        print('\n=== MetricChangeAnalysisTool basic result ===')
        print(result[0]['text'])

    @pytest.mark.asyncio
    async def test_metric_change_analysis_tool_no_numeric_fields(self):
        """Test metric_change_analysis_tool when no numeric fields exist."""
        self.mock_client.indices = Mock()
        self.mock_client.indices.get_mapping = AsyncMock(
            return_value={
                'test-index': {
                    'mappings': {
                        'properties': {
                            'status': {'type': 'keyword'},
                            '@timestamp': {'type': 'date'},
                        }
                    }
                }
            }
        )

        args = self.MetricChangeAnalysisToolArgs(
            index='test-index',
            selectionTimeRangeStart='2023-01-01 10:00:00',
            selectionTimeRangeEnd='2023-01-01 10:30:00',
            timeField='@timestamp',
            baselineTimeRangeStart='2023-01-01 08:00:00',
            baselineTimeRangeEnd='2023-01-01 08:30:00',
            opensearch_cluster_name='',
        )

        result = await self._metric_change_analysis_tool(args)

        assert len(result) == 1
        assert 'Error' in result[0]['text']
        assert 'numeric fields' in result[0]['text']
        print('\n=== MetricChangeAnalysisTool no numeric fields ===')
        print(result[0]['text'])

    @pytest.mark.asyncio
    async def test_metric_change_analysis_tool_no_data(self):
        """Test metric_change_analysis_tool when no data found."""
        self.mock_client.search = AsyncMock(
            return_value={
                'hits': {'total': {'value': 0, 'relation': 'eq'}},
                'aggregations': {
                    'responseTime': {'values': {'50.0': None, '90.0': None}},
                },
            }
        )
        self.mock_client.indices = Mock()
        self.mock_client.indices.get_mapping = AsyncMock(
            return_value={
                'test-index': {
                    'mappings': {
                        'properties': {
                            'responseTime': {'type': 'long'},
                            '@timestamp': {'type': 'date'},
                        }
                    }
                }
            }
        )

        args = self.MetricChangeAnalysisToolArgs(
            index='test-index',
            selectionTimeRangeStart='2023-01-01 10:00:00',
            selectionTimeRangeEnd='2023-01-01 10:30:00',
            timeField='@timestamp',
            baselineTimeRangeStart='2023-01-01 08:00:00',
            baselineTimeRangeEnd='2023-01-01 08:30:00',
            opensearch_cluster_name='',
        )

        result = await self._metric_change_analysis_tool(args)

        assert len(result) == 1
        assert 'Error' in result[0]['text']
        assert 'No data found' in result[0]['text']
        print('\n=== MetricChangeAnalysisTool no data ===')
        print(result[0]['text'])

    @pytest.mark.asyncio
    async def test_metric_change_analysis_tool_with_top_n(self):
        """Test metric_change_analysis_tool with custom topN parameter."""
        call_count = [0]

        async def mock_search(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return {
                    'hits': {'total': {'value': 3, 'relation': 'eq'}},
                    'aggregations': {
                        'fieldA': {'values': {'50.0': 550.0, '90.0': 590.0}},
                        'fieldB': {'values': {'50.0': 21.0, '90.0': 21.8}},
                        'fieldC': {'values': {'50.0': 3200.0, '90.0': 3440.0}},
                    },
                }
            else:
                return {
                    'hits': {'total': {'value': 3, 'relation': 'eq'}},
                    'aggregations': {
                        'fieldA': {'values': {'50.0': 105.0, '90.0': 109.0}},
                        'fieldB': {'values': {'50.0': 20.0, '90.0': 20.8}},
                        'fieldC': {'values': {'50.0': 110.0, '90.0': 118.0}},
                    },
                }

        self.mock_client.search = AsyncMock(side_effect=mock_search)
        self.mock_client.indices = Mock()
        self.mock_client.indices.get_mapping = AsyncMock(
            return_value={
                'test-index': {
                    'mappings': {
                        'properties': {
                            'fieldA': {'type': 'long'},
                            'fieldB': {'type': 'float'},
                            'fieldC': {'type': 'integer'},
                            '@timestamp': {'type': 'date'},
                        }
                    }
                }
            }
        )

        args = self.MetricChangeAnalysisToolArgs(
            index='test-index',
            selectionTimeRangeStart='2023-01-01 10:00:00',
            selectionTimeRangeEnd='2023-01-01 10:30:00',
            timeField='@timestamp',
            baselineTimeRangeStart='2023-01-01 08:00:00',
            baselineTimeRangeEnd='2023-01-01 08:30:00',
            topN=2,
            opensearch_cluster_name='',
        )

        result = await self._metric_change_analysis_tool(args)

        assert len(result) == 1
        assert 'percentileAnalysis' in result[0]['text']
        print('\n=== MetricChangeAnalysisTool with topN=2 ===')
        print(result[0]['text'])

    @pytest.mark.asyncio
    async def test_metric_change_analysis_tool_group_by_single(self):
        """Single-field groupBy yields percentiles per (group, numeric column).

        Output keys take the shape `<group>_<column>`.
        """
        call_count = [0]

        async def mock_search(**kwargs):
            call_count[0] += 1
            # selection window: svc-a latency surges, svc-b stable
            if call_count[0] == 1:
                return {
                    'hits': {'total': {'value': 200, 'relation': 'eq'}},
                    'aggregations': {
                        'groups': {
                            'buckets': [
                                {
                                    'key': 'svc-a',
                                    'latency': {'values': {'50.0': 800.0, '90.0': 950.0}},
                                    'cpu': {'values': {'50.0': 0.5, '90.0': 0.6}},
                                },
                                {
                                    'key': 'svc-b',
                                    'latency': {'values': {'50.0': 100.0, '90.0': 120.0}},
                                    'cpu': {'values': {'50.0': 0.3, '90.0': 0.32}},
                                },
                            ]
                        }
                    },
                }
            # baseline window: both services low
            return {
                'hits': {'total': {'value': 200, 'relation': 'eq'}},
                'aggregations': {
                    'groups': {
                        'buckets': [
                            {
                                'key': 'svc-a',
                                'latency': {'values': {'50.0': 80.0, '90.0': 100.0}},
                                'cpu': {'values': {'50.0': 0.49, '90.0': 0.59}},
                            },
                            {
                                'key': 'svc-b',
                                'latency': {'values': {'50.0': 95.0, '90.0': 115.0}},
                                'cpu': {'values': {'50.0': 0.30, '90.0': 0.32}},
                            },
                        ]
                    }
                },
            }

        self.mock_client.search = AsyncMock(side_effect=mock_search)
        self.mock_client.indices = Mock()
        self.mock_client.indices.get_mapping = AsyncMock(
            return_value={
                'svc-index': {
                    'mappings': {
                        'properties': {
                            'service_name': {'type': 'keyword'},
                            'latency': {'type': 'long'},
                            'cpu': {'type': 'float'},
                            'timestamp': {'type': 'date'},
                        }
                    }
                }
            }
        )

        args = self.MetricChangeAnalysisToolArgs(
            index='svc-index',
            selectionTimeRangeStart='2023-01-01 10:00:00',
            selectionTimeRangeEnd='2023-01-01 10:30:00',
            timeField='timestamp',
            baselineTimeRangeStart='2023-01-01 08:00:00',
            baselineTimeRangeEnd='2023-01-01 08:30:00',
            groupBy=['service_name'],
            opensearch_cluster_name='',
        )

        result = await self._metric_change_analysis_tool(args)

        text = result[0]['text']
        # Composite keys must use single-field separator `_`.
        assert 'svc-a_latency' in text
        assert 'svc-a_cpu' in text
        assert 'svc-b_latency' in text
        # svc-a_latency moved 80→800 — should outrank stable svc-b_latency.
        a_lat = text.find('svc-a_latency')
        b_lat = text.find('svc-b_latency')
        assert a_lat != -1 and b_lat != -1 and a_lat < b_lat
        print('\n=== MetricChangeAnalysisTool groupBy=[service_name] ===')
        print(text)

    @pytest.mark.asyncio
    async def test_metric_change_analysis_tool_group_by_multi(self):
        """groupBy=['kpi_name','cmdb_id']: multi_terms key parts joined by `|`."""

        async def mock_search(**kwargs):
            return {
                'hits': {'total': {'value': 50, 'relation': 'eq'}},
                'aggregations': {
                    'groups': {
                        'buckets': [
                            {
                                # multi_terms returns list `key` plus pre-joined string
                                'key': ['cpu_pct', 'host01'],
                                'key_as_string': 'cpu_pct|host01',
                                'value': {'values': {'50.0': 70.0, '90.0': 90.0}},
                            },
                        ]
                    }
                },
            }

        self.mock_client.search = AsyncMock(side_effect=mock_search)
        self.mock_client.indices = Mock()
        self.mock_client.indices.get_mapping = AsyncMock(
            return_value={
                'long-index': {
                    'mappings': {
                        'properties': {
                            'kpi_name': {'type': 'keyword'},
                            'cmdb_id': {'type': 'keyword'},
                            'value': {'type': 'float'},
                            'timestamp': {'type': 'date'},
                        }
                    }
                }
            }
        )

        args = self.MetricChangeAnalysisToolArgs(
            index='long-index',
            selectionTimeRangeStart='2023-01-01 10:00:00',
            selectionTimeRangeEnd='2023-01-01 10:30:00',
            timeField='timestamp',
            baselineTimeRangeStart='2023-01-01 08:00:00',
            baselineTimeRangeEnd='2023-01-01 08:30:00',
            groupBy=['kpi_name', 'cmdb_id'],
            opensearch_cluster_name='',
        )

        result = await self._metric_change_analysis_tool(args)
        text = result[0]['text']
        # Group parts joined by `|`; numeric column appended with `_`.
        assert 'cpu_pct|host01_value' in text
        print('\n=== MetricChangeAnalysisTool groupBy=[kpi_name, cmdb_id] ===')
        print(text)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        'selection_over, baseline_over',
        [
            (True, False),  # only selection too large
            (False, True),  # only baseline too large
            (True, True),  # both windows too large
        ],
    )
    async def test_metric_change_analysis_tool_window_too_large(
        self, selection_over, baseline_over
    ):
        """When a window exceeds the doc-count cap, the tool asks to narrow it.

        Only the offending range(s) should be named; when both exceed the cap
        both are reported.
        """
        from tools.analysis.constants import MAX_ANALYSIS_DOC_COUNT

        count_calls = [0]

        async def mock_count(**kwargs):
            # First count = selection window, second = baseline window.
            count_calls[0] += 1
            over = selection_over if count_calls[0] == 1 else baseline_over
            return {'count': MAX_ANALYSIS_DOC_COUNT + 1 if over else 10}

        self.mock_client.count = AsyncMock(side_effect=mock_count)
        # search should never be reached once the guard trips.
        self.mock_client.search = AsyncMock(
            side_effect=AssertionError('search must not run when window is too large')
        )
        self.mock_client.indices = Mock()
        self.mock_client.indices.get_mapping = AsyncMock(
            return_value={
                'test-index': {
                    'mappings': {
                        'properties': {
                            'responseTime': {'type': 'long'},
                            '@timestamp': {'type': 'date'},
                        }
                    }
                }
            }
        )

        args = self.MetricChangeAnalysisToolArgs(
            index='test-index',
            selectionTimeRangeStart='2023-01-01 10:00:00',
            selectionTimeRangeEnd='2023-01-01 11:00:00',
            timeField='@timestamp',
            baselineTimeRangeStart='2023-01-01 08:00:00',
            baselineTimeRangeEnd='2023-01-01 08:30:00',
            opensearch_cluster_name='',
        )

        result = await self._metric_change_analysis_tool(args)
        text = result[0]['text']
        assert 'Error' in text
        assert 'Too many documents' in text
        # Only the offending range(s) are named.
        assert ('the selection range' in text) == selection_over
        assert ('the baseline range' in text) == baseline_over
        print(f'\n=== window too large (sel={selection_over}, base={baseline_over}) ===')
        print(text)

    @pytest.mark.asyncio
    async def test_metric_change_analysis_tool_window_at_cap_allowed(self):
        """A window exactly at the cap is allowed (guard uses strict `>`)."""
        from tools.analysis.constants import MAX_ANALYSIS_DOC_COUNT

        # Both windows sit exactly at the cap — must pass the guard and analyze.
        self.mock_client.count = AsyncMock(return_value={'count': MAX_ANALYSIS_DOC_COUNT})

        call_count = [0]

        async def mock_search(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return {
                    'hits': {'total': {'value': 5, 'relation': 'eq'}},
                    'aggregations': {
                        'responseTime': {'values': {'50.0': 5500.0, '90.0': 6800.0}},
                    },
                }
            return {
                'hits': {'total': {'value': 5, 'relation': 'eq'}},
                'aggregations': {
                    'responseTime': {'values': {'50.0': 120.0, '90.0': 146.0}},
                },
            }

        self.mock_client.search = AsyncMock(side_effect=mock_search)
        self.mock_client.indices = Mock()
        self.mock_client.indices.get_mapping = AsyncMock(
            return_value={
                'test-index': {
                    'mappings': {
                        'properties': {
                            'responseTime': {'type': 'long'},
                            '@timestamp': {'type': 'date'},
                        }
                    }
                }
            }
        )

        args = self.MetricChangeAnalysisToolArgs(
            index='test-index',
            selectionTimeRangeStart='2023-01-01 10:00:00',
            selectionTimeRangeEnd='2023-01-01 10:30:00',
            timeField='@timestamp',
            baselineTimeRangeStart='2023-01-01 08:00:00',
            baselineTimeRangeEnd='2023-01-01 08:30:00',
            opensearch_cluster_name='',
        )

        result = await self._metric_change_analysis_tool(args)
        text = result[0]['text']
        assert 'Too many documents' not in text
        assert 'percentileAnalysis' in text
        print('\n=== window exactly at cap (allowed) ===')
        print(text)

    def test_skills_tools_registry(self):
        """Test SKILLS_TOOLS_REGISTRY structure."""
        expected_tools = [
            'DataDistributionTool',
            'LogPatternAnalysisTool',
            'MetricChangeAnalysisTool',
        ]

        for tool in expected_tools:
            assert tool in self.SKILLS_TOOLS_REGISTRY
            assert 'display_name' in self.SKILLS_TOOLS_REGISTRY[tool]
            assert 'description' in self.SKILLS_TOOLS_REGISTRY[tool]
            assert 'input_schema' in self.SKILLS_TOOLS_REGISTRY[tool]
            assert 'function' in self.SKILLS_TOOLS_REGISTRY[tool]
            assert 'args_model' in self.SKILLS_TOOLS_REGISTRY[tool]
            assert 'min_version' in self.SKILLS_TOOLS_REGISTRY[tool]
            assert 'http_methods' in self.SKILLS_TOOLS_REGISTRY[tool]

    def test_data_distribution_tool_args_validation(self):
        """Test DataDistributionToolArgs validation."""
        args = self.DataDistributionToolArgs(
            index='test-index',
            selectionTimeRangeStart='2023-01-01T00:00:00Z',
            selectionTimeRangeEnd='2023-01-02T00:00:00Z',
            timeField='@timestamp',
            opensearch_cluster_name='',
        )
        assert args.index == 'test-index'
        assert args.timeField == '@timestamp'
        assert args.size == 1000
        assert args.queryType == 'dsl'

        args_custom = self.DataDistributionToolArgs(
            index='test-index',
            selectionTimeRangeStart='2023-01-01T00:00:00Z',
            selectionTimeRangeEnd='2023-01-02T00:00:00Z',
            timeField='@timestamp',
            size=500,
            opensearch_cluster_name='',
        )
        assert args_custom.size == 500

    def test_log_pattern_analysis_tool_args_validation(self):
        """Test LogPatternAnalysisToolArgs validation."""
        args = self.LogPatternAnalysisToolArgs(
            index='logs-index',
            logFieldName='message',
            selectionTimeRangeStart='2023-01-01T00:00:00Z',
            selectionTimeRangeEnd='2023-01-02T00:00:00Z',
            timeField='@timestamp',
            opensearch_cluster_name='',
        )
        assert args.index == 'logs-index'
        assert args.logFieldName == 'message'
        assert args.timeField == '@timestamp'
        assert args.traceFieldName == ''
        assert args.filter == ''

        args_full = self.LogPatternAnalysisToolArgs(
            index='logs-index',
            logFieldName='message',
            selectionTimeRangeStart='2023-01-01T00:00:00Z',
            selectionTimeRangeEnd='2023-01-02T00:00:00Z',
            timeField='@timestamp',
            traceFieldName='trace_id',
            baseTimeRangeStart='2022-12-01T00:00:00Z',
            baseTimeRangeEnd='2022-12-02T00:00:00Z',
            opensearch_cluster_name='',
        )
        assert args_full.traceFieldName == 'trace_id'
        assert args_full.baseTimeRangeStart == '2022-12-01T00:00:00Z'

    def test_input_models_validation(self):
        """Test input models validation for required fields."""
        with pytest.raises(ValueError):
            self.DataDistributionToolArgs(opensearch_cluster_name='')

        with pytest.raises(ValueError):
            self.LogPatternAnalysisToolArgs(opensearch_cluster_name='')


class TestMetricChangeAnalysisLogic:
    """Tests for metric_change_analysis internal computation correctness."""

    def setup_method(self):
        from tools.analysis.metric_change_analysis import (
            _calculate_percentile_variance,
            _format_results,
            _safe_log_ratio,
        )

        self._calculate_percentile_variance = _calculate_percentile_variance
        self._format_results = _format_results
        self._safe_log_ratio = _safe_log_ratio

    def test_safe_log_ratio_equal_values(self):
        assert self._safe_log_ratio(100.0, 100.0) == 0.0

    def test_safe_log_ratio_doubled(self):
        import math

        assert self._safe_log_ratio(200.0, 100.0) == pytest.approx(math.log(2.0))

    def test_safe_log_ratio_halved(self):
        import math

        assert self._safe_log_ratio(50.0, 100.0) == pytest.approx(math.log(2.0))

    def test_safe_log_ratio_baseline_zero(self):
        assert self._safe_log_ratio(100.0, 0.0) == 10.0

    def test_safe_log_ratio_both_zero(self):
        assert self._safe_log_ratio(0.0, 0.0) == 0.0

    def test_variance_no_change(self):
        stats = {'p50': 100.0, 'p90': 200.0}
        assert self._calculate_percentile_variance(stats, stats) == 0.0

    def test_variance_large_change(self):
        import math

        selection = {'p50': 5000.0, 'p90': 7000.0}
        baseline = {'p50': 100.0, 'p90': 150.0}
        variance = self._calculate_percentile_variance(selection, baseline)
        expected = 0.5 * math.log(5000 / 100) + 0.5 * math.log(7000 / 150)
        assert variance == pytest.approx(expected)

    def test_format_results_respects_top_n(self):
        analyses = [
            {
                'field': 'a',
                'variance': 3.0,
                'selection_stats': {'p50': 1.0, 'p90': 2.0},
                'baseline_stats': {'p50': 1.0, 'p90': 2.0},
            },
            {
                'field': 'b',
                'variance': 2.0,
                'selection_stats': {'p50': 1.0, 'p90': 2.0},
                'baseline_stats': {'p50': 1.0, 'p90': 2.0},
            },
            {
                'field': 'c',
                'variance': 1.0,
                'selection_stats': {'p50': 1.0, 'p90': 2.0},
                'baseline_stats': {'p50': 1.0, 'p90': 2.0},
            },
        ]
        result = self._format_results(analyses, top_n=2)
        assert len(result) == 2
        assert result[0]['field'] == 'a'
        assert result[1]['field'] == 'b'


class TestLogPatternAnalysisLogic:
    """Tests for log_pattern_analysis internal computation correctness."""

    def setup_method(self):
        from tools.analysis.log_pattern_analysis import (
            _calculate_pattern_differences,
            _merge_similar_patterns,
            _post_process_pattern,
        )

        self._calculate_pattern_differences = _calculate_pattern_differences
        self._merge_similar_patterns = _merge_similar_patterns
        self._post_process_pattern = _post_process_pattern

    def test_post_process_collapses_consecutive_wildcards(self):
        assert self._post_process_pattern('ERROR <*> <*> <*> failed') == 'ERROR <*> failed'
        assert self._post_process_pattern('GET <*> 200') == 'GET <*> 200'

    def test_merge_similar_patterns(self):
        patterns = {
            'ERROR connection failed <*>': 10.0,
            'ERROR connection failed <*> <*>': 5.0,
            'GET /api/health 200': 100.0,
        }
        self._merge_similar_patterns(patterns)
        assert 'GET /api/health 200' in patterns
        total_error = sum(v for k, v in patterns.items() if 'ERROR' in k)
        assert total_error == 15.0

    def test_pattern_differences_new_pattern(self):
        base = {'pattern_a': 10.0}
        selection = {'pattern_a': 5.0, 'pattern_b': 15.0}
        diffs = self._calculate_pattern_differences(base, selection)
        new_patterns = [d for d in diffs if d['lift'] is None]
        assert len(new_patterns) == 1
        assert new_patterns[0]['pattern'] == 'pattern_b'
        assert new_patterns[0]['selection'] == pytest.approx(15.0 / 20.0)

    def test_pattern_differences_high_lift(self):
        base = {'pattern_a': 100.0, 'pattern_b': 1.0}
        selection = {'pattern_a': 1.0, 'pattern_b': 100.0}
        diffs = self._calculate_pattern_differences(base, selection)
        lifted = [d for d in diffs if d['lift'] is not None]
        assert len(lifted) > 0
        for d in lifted:
            assert d['lift'] > 3.0

    def test_pattern_differences_no_lift_when_proportional(self):
        base = {'pattern_a': 50.0, 'pattern_b': 50.0}
        selection = {'pattern_a': 50.0, 'pattern_b': 50.0}
        diffs = self._calculate_pattern_differences(base, selection)
        assert len(diffs) == 0


class TestDataDistributionLogic:
    """Tests for data_distribution internal computation correctness."""

    def setup_method(self):
        from tools.analysis.data_distribution import (
            _calculate_field_distribution,
            _calculate_max_difference,
            _group_numeric_keys,
        )

        self._calculate_field_distribution = _calculate_field_distribution
        self._calculate_max_difference = _calculate_max_difference
        self._group_numeric_keys = _group_numeric_keys

    def test_field_distribution_calculation(self):
        data = [
            {'status': 'ok'},
            {'status': 'ok'},
            {'status': 'error'},
            {'status': 'ok'},
        ]
        dist = self._calculate_field_distribution(data, 'status')
        assert dist['ok'] == pytest.approx(0.75)
        assert dist['error'] == pytest.approx(0.25)

    def test_max_difference_identical(self):
        dist = {'a': 0.5, 'b': 0.5}
        assert self._calculate_max_difference(dist, dist) == 0.0

    def test_max_difference_complete_shift(self):
        selection = {'a': 1.0}
        baseline = {'b': 1.0}
        assert self._calculate_max_difference(selection, baseline) == 1.0

    def test_max_difference_partial_shift(self):
        selection = {'a': 0.8, 'b': 0.2}
        baseline = {'a': 0.3, 'b': 0.7}
        assert self._calculate_max_difference(selection, baseline) == pytest.approx(0.5)

    def test_group_numeric_keys_below_threshold(self):
        dist = {'1': 0.25, '2': 0.25, '3': 0.25, '4': 0.25}
        grouped_sel, grouped_base = self._group_numeric_keys(dist, {})
        assert grouped_sel == dist

    def test_group_numeric_keys_above_threshold(self):
        dist = {str(float(i)): 1.0 / 20 for i in range(20)}
        grouped_sel, grouped_base = self._group_numeric_keys(dist, {})
        assert len(grouped_sel) == 5
        assert sum(grouped_sel.values()) == pytest.approx(1.0)
