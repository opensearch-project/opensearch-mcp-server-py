# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import logging
from tools.tool_logging import log_tool_error


class TestLogToolError:
    def test_returns_mcp_error_format(self):
        exc = Exception('something broke')
        result = log_tool_error('TestTool', exc, 'doing stuff')

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert result[0]['text'] == 'Error doing stuff: something broke'
        assert result[0]['is_error'] is True

    def test_returns_error_without_operation(self):
        exc = Exception('fail')
        result = log_tool_error('TestTool', exc)

        assert result[0]['text'] == 'Error: fail'

    def test_emits_structured_log(self, caplog):
        exc = Exception('test error')
        with caplog.at_level(logging.ERROR):
            log_tool_error('SearchIndexTool', exc, 'searching index')

        records = [
            r for r in caplog.records if hasattr(r, 'event_type') and r.event_type == 'tool_error'
        ]
        assert len(records) == 1

        record = records[0]
        assert record.tool_name == 'SearchIndexTool'
        assert record.exception_type == 'Exception'
        assert record.status == 'error'

    def test_extracts_status_code_from_transport_error(self, caplog):
        # Simulate opensearchpy TransportError which has status_code attribute
        exc = Exception('index_not_found_exception')
        exc.status_code = 404

        with caplog.at_level(logging.ERROR):
            log_tool_error('SearchIndexTool', exc, 'searching index')

        records = [r for r in caplog.records if hasattr(r, 'status_code')]
        assert len(records) == 1
        assert records[0].status_code == 404

    def test_extracts_root_cause_from_info(self, caplog):
        exc = Exception('search error')
        exc.status_code = 400
        exc.info = {
            'error': {
                'root_cause': [{'type': 'query_shard_exception', 'reason': 'bad query'}],
                'type': 'search_phase_execution_exception',
            }
        }

        with caplog.at_level(logging.ERROR):
            log_tool_error('SearchIndexTool', exc, 'searching index')

        records = [r for r in caplog.records if hasattr(r, 'root_cause')]
        assert len(records) == 1
        assert records[0].root_cause == 'query_shard_exception'

    def test_extracts_root_cause_from_string_info(self, caplog):
        """When exception.info is a JSON string (fallback path), root_cause should still be extracted."""
        exc = Exception('search error')
        exc.status_code = 400
        exc.info = '{"error":{"root_cause":[{"type":"parsing_exception","reason":"unknown query"}],"type":"search_phase_execution_exception"},"status":400}'

        with caplog.at_level(logging.ERROR):
            log_tool_error('SearchIndexTool', exc, 'searching index')

        records = [r for r in caplog.records if hasattr(r, 'root_cause')]
        assert len(records) == 1
        assert records[0].root_cause == 'parsing_exception'

    def test_extracts_root_cause_from_error_attr(self, caplog):
        """Async opensearchpy stores response body in exception.error, not exception.info."""
        exc = Exception('not found')
        exc.status_code = 404
        exc.info = None
        exc.error = '{"error":{"root_cause":[{"type":"index_not_found_exception","reason":"no such index"}],"type":"index_not_found_exception"},"status":404}'

        with caplog.at_level(logging.ERROR):
            log_tool_error('CountTool', exc, 'executing CountTool')

        records = [r for r in caplog.records if hasattr(r, 'root_cause')]
        assert len(records) == 1
        assert records[0].root_cause == 'index_not_found_exception'

    def test_string_info_not_json_is_ignored(self, caplog):
        """When exception.info is a non-JSON string, root_cause should be absent."""
        exc = Exception('error')
        exc.status_code = 400
        exc.info = 'plain text error body'

        with caplog.at_level(logging.ERROR):
            log_tool_error('SearchIndexTool', exc, 'searching index')

        records = [
            r for r in caplog.records if hasattr(r, 'event_type') and r.event_type == 'tool_error'
        ]
        assert len(records) == 1
        assert not hasattr(records[0], 'root_cause')

    def test_context_kwargs_included_in_log(self, caplog):
        exc = Exception('error')
        with caplog.at_level(logging.ERROR):
            log_tool_error('SearchIndexTool', exc, 'searching', index='my-index', method='GET')

        records = [
            r for r in caplog.records if hasattr(r, 'event_type') and r.event_type == 'tool_error'
        ]
        assert len(records) == 1
        assert records[0].index == 'my-index'
        assert records[0].method == 'GET'

    def test_none_context_values_excluded(self, caplog):
        exc = Exception('error')
        with caplog.at_level(logging.ERROR):
            log_tool_error('TestTool', exc, 'doing stuff', index=None, other='value')

        records = [
            r for r in caplog.records if hasattr(r, 'event_type') and r.event_type == 'tool_error'
        ]
        assert len(records) == 1
        assert not hasattr(records[0], 'index')
        assert records[0].other == 'value'

    def test_no_status_code_attribute(self, caplog):
        """When exception has no status_code, the field should not appear in the log."""
        exc = ValueError('plain error')
        with caplog.at_level(logging.ERROR):
            log_tool_error('TestTool', exc, 'doing stuff')

        records = [
            r for r in caplog.records if hasattr(r, 'event_type') and r.event_type == 'tool_error'
        ]
        assert len(records) == 1
        assert not hasattr(records[0], 'status_code')
        assert records[0].exception_type == 'ValueError'
