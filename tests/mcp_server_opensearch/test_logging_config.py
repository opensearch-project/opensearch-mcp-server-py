# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import asyncio
import io
import json
import logging
import pytest
from mcp_server_opensearch.logging_config import (
    JsonFormatter,
    _get_rss_mb,
    _handle_monitor_error,
    configure_logging,
    memory_monitor,
    start_memory_monitor,
)
from unittest.mock import patch


class TestJsonFormatter:
    def setup_method(self):
        self.formatter = JsonFormatter()

    def test_basic_format_produces_valid_json(self):
        record = logging.LogRecord(
            name='test.logger',
            level=logging.INFO,
            pathname='test.py',
            lineno=1,
            msg='Hello %s',
            args=('world',),
            exc_info=None,
        )
        output = self.formatter.format(record)
        parsed = json.loads(output)

        assert parsed['level'] == 'INFO'
        assert parsed['logger'] == 'test.logger'
        assert parsed['message'] == 'Hello world'
        assert 'timestamp' in parsed

    def test_extra_fields_merged_into_top_level(self):
        record = logging.LogRecord(
            name='test.logger',
            level=logging.ERROR,
            pathname='test.py',
            lineno=1,
            msg='tool failed',
            args=(),
            exc_info=None,
        )
        record.event_type = 'tool_execution'
        record.tool_name = 'SearchIndexTool'
        record.duration_ms = 42.5

        output = self.formatter.format(record)
        parsed = json.loads(output)

        assert parsed['event_type'] == 'tool_execution'
        assert parsed['tool_name'] == 'SearchIndexTool'
        assert parsed['duration_ms'] == 42.5

    def test_exception_info_included(self):
        try:
            raise ValueError('test error')
        except ValueError:
            import sys

            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name='test.logger',
            level=logging.ERROR,
            pathname='test.py',
            lineno=1,
            msg='error occurred',
            args=(),
            exc_info=exc_info,
        )
        output = self.formatter.format(record)
        parsed = json.loads(output)

        assert 'exception' in parsed
        assert 'ValueError' in parsed['exception']

    def test_timestamp_format_is_iso8601(self):
        record = logging.LogRecord(
            name='test',
            level=logging.INFO,
            pathname='',
            lineno=0,
            msg='test',
            args=(),
            exc_info=None,
        )
        output = self.formatter.format(record)
        parsed = json.loads(output)
        # Should end with Z and have T separator
        assert parsed['timestamp'].endswith('Z')
        assert 'T' in parsed['timestamp']


class TestConfigureLogging:
    def teardown_method(self):
        # Reset root logger after each test
        root = logging.getLogger()
        for handler in root.handlers[:]:
            root.removeHandler(handler)

    def test_json_format_uses_json_formatter(self):
        configure_logging(level=logging.INFO, log_format='json')
        root = logging.getLogger()
        assert any(isinstance(h.formatter, JsonFormatter) for h in root.handlers)

    def test_text_format_uses_standard_formatter(self):
        configure_logging(level=logging.INFO, log_format='text')
        root = logging.getLogger()
        assert not any(isinstance(h.formatter, JsonFormatter) for h in root.handlers)
        assert len(root.handlers) > 0

    def test_removes_existing_handlers(self):
        root = logging.getLogger()
        initial_count = len(root.handlers)
        # Add extra handlers
        root.addHandler(logging.StreamHandler())
        root.addHandler(logging.StreamHandler())
        assert len(root.handlers) == initial_count + 2

        configure_logging(level=logging.INFO, log_format='text')
        # Should have exactly 1 handler (ours), regardless of what was there before
        assert len(root.handlers) == 1

    def test_sets_log_level(self):
        configure_logging(level=logging.DEBUG, log_format='text')
        root = logging.getLogger()
        assert root.level == logging.DEBUG


class TestGetRssMb:
    def test_returns_float(self):
        """_get_rss_mb returns a float on any platform."""
        result = _get_rss_mb()
        assert isinstance(result, float)

    def test_returns_positive_value(self):
        """_get_rss_mb returns a positive value (or -1 on unsupported platforms)."""
        result = _get_rss_mb()
        assert result > 0 or result == -1.0

    def test_linux_procfs_path(self):
        """_get_rss_mb computes correct MB from /proc/self/statm on Linux."""
        # statm format: size resident shared text lib data dt (in pages)
        fake_statm = io.StringIO('50000 12345 3000 100 0 8000 0')
        page_size = 4096  # common Linux page size
        expected_mb = round(12345 * page_size / (1024 * 1024), 2)

        with patch('builtins.open', return_value=fake_statm):
            with patch('os.sysconf', create=True, return_value=page_size):
                assert _get_rss_mb() == expected_mb

    def test_fallback_when_procfs_and_resource_unavailable(self):
        """_get_rss_mb returns -1.0 when neither procfs nor resource is available."""
        with patch('builtins.open', side_effect=OSError('no procfs')):
            with patch.dict('sys.modules', {'resource': None}):
                assert _get_rss_mb() == -1.0


_PATCH_SLEEP = 'mcp_server_opensearch.logging_config._async_sleep'
_PATCH_GET_RSS = 'mcp_server_opensearch.logging_config._get_rss_mb'


class TestMemoryMonitor:
    async def _run_one_iteration(self, caplog, **monitor_kwargs):
        """Helper: run memory_monitor for one iteration then cancel."""
        call_count = 0

        async def _fast_sleep(seconds):
            nonlocal call_count
            call_count += 1
            if call_count > 1:
                await asyncio.sleep(10)
            return

        with patch(_PATCH_SLEEP, _fast_sleep):
            with caplog.at_level(
                logging.INFO, logger='mcp_server_opensearch.logging_config.memory'
            ):
                task = asyncio.create_task(memory_monitor(**monitor_kwargs))
                await asyncio.sleep(0.05)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task

    @pytest.mark.asyncio
    async def test_emits_memory_snapshot_event(self, caplog):
        """memory_monitor logs an event_type=memory_snapshot entry."""
        await self._run_one_iteration(caplog, interval_seconds=1)

        assert any('Memory snapshot' in r.message for r in caplog.records)
        snapshot_record = next(r for r in caplog.records if 'Memory snapshot' in r.message)
        assert snapshot_record.event_type == 'memory_snapshot'
        assert isinstance(snapshot_record.memory_rss_mb, float)
        assert isinstance(snapshot_record.pid, int)

    @pytest.mark.asyncio
    async def test_start_memory_monitor_returns_task(self):
        """start_memory_monitor returns a running asyncio.Task."""
        task = start_memory_monitor(interval_seconds=60)
        try:
            assert isinstance(task, asyncio.Task)
            assert not task.done()
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    @pytest.mark.asyncio
    async def test_start_memory_monitor_reads_env_var(self):
        """start_memory_monitor reads interval from OPENSEARCH_MEMORY_MONITOR_INTERVAL env var."""
        sleep_values = []

        async def capture_sleep(seconds):
            sleep_values.append(seconds)
            raise asyncio.CancelledError

        with patch(_PATCH_SLEEP, side_effect=capture_sleep):
            with patch.dict('os.environ', {'OPENSEARCH_MEMORY_MONITOR_INTERVAL': '30'}):
                task = start_memory_monitor()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        assert sleep_values == [30]

    @pytest.mark.asyncio
    async def test_fallback_when_no_rss_source(self, caplog):
        """memory_monitor logs rss_mb=-1.0 when no RSS source is available."""
        with patch(_PATCH_GET_RSS, return_value=-1.0):
            await self._run_one_iteration(caplog, interval_seconds=1)

        snapshot_record = next(r for r in caplog.records if 'Memory snapshot' in r.message)
        assert snapshot_record.memory_rss_mb == -1.0

    @pytest.mark.asyncio
    async def test_interval_clamped_to_minimum_of_1(self):
        """interval_seconds=0 is clamped to 1 to prevent CPU spin."""
        sleep_values = []

        async def _capture_sleep(seconds):
            sleep_values.append(seconds)
            await asyncio.sleep(10)

        with patch(_PATCH_SLEEP, _capture_sleep):
            task = asyncio.create_task(memory_monitor(interval_seconds=0))
            await asyncio.sleep(0.05)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        assert sleep_values[0] >= 1

    @pytest.mark.asyncio
    async def test_loop_survives_iteration_error(self, caplog):
        """An exception in one iteration is logged and the loop continues."""
        call_count = 0

        async def _fast_sleep(seconds):
            nonlocal call_count
            call_count += 1
            if call_count > 2:
                await asyncio.sleep(10)
            return

        with patch(_PATCH_GET_RSS, side_effect=RuntimeError('boom')):
            with patch(_PATCH_SLEEP, _fast_sleep):
                with caplog.at_level(
                    logging.WARNING,
                    logger='mcp_server_opensearch.logging_config.memory',
                ):
                    task = asyncio.create_task(memory_monitor(interval_seconds=1))
                    await asyncio.sleep(0.05)
                    task.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await task

        assert any('Memory monitor iteration failed' in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_handle_monitor_error_logs_crash(self, caplog):
        """_handle_monitor_error logs when the task raises an unexpected exception."""

        async def _failing_coro():
            raise RuntimeError('unexpected crash')

        with caplog.at_level(logging.ERROR, logger='mcp_server_opensearch.logging_config.memory'):
            task = asyncio.create_task(_failing_coro())
            with pytest.raises(RuntimeError):
                await task
            _handle_monitor_error(task)

        assert any('Memory monitor crashed' in r.message for r in caplog.records)
