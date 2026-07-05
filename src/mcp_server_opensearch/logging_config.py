# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Structured logging configuration for metric extraction.

Provides a JSON formatter that outputs one JSON object per log line, making
log events directly targetable by metric filters. Extra fields passed via
logger.info("msg", extra={...}) are merged into the top-level JSON object.
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone


# Attributes that exist on every LogRecord by default.
# We compute this once at import time to avoid per-record overhead.
_STANDARD_LOG_RECORD_ATTRS = frozenset(
    logging.LogRecord('', 0, '', 0, '', (), None).__dict__.keys()
) | {'message', 'asctime'}


class JsonFormatter(logging.Formatter):
    """Minimal JSON formatter for structured logging.

    Produces one JSON object per line on stderr. Extra fields attached
    to the LogRecord (via logger.info("msg", extra={...})) are merged
    into the top-level object, making them directly targetable by
    metric filters (e.g., { $.event_type = "tool_execution" }).
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as a JSON string."""
        log_entry = {
            'timestamp': datetime.fromtimestamp(record.created, tz=timezone.utc).strftime(
                '%Y-%m-%dT%H:%M:%S.%f'
            )[:-3]
            + 'Z',
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }

        # Merge extra fields into the top-level object.
        for key, value in record.__dict__.items():
            if key not in _STANDARD_LOG_RECORD_ATTRS and not key.startswith('_'):
                log_entry[key] = value

        if record.exc_info and record.exc_info[0] is not None:
            log_entry['exception'] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)


def configure_logging(level: int = logging.INFO, log_format: str = 'text') -> None:
    """Configure the root logger for the MCP server.

    Args:
        level: Logging level (DEBUG, INFO, etc.)
        log_format: "text" for human-readable (default, backward-compatible)
                    or "json" for structured logging.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove any existing handlers to avoid duplicate output.
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler()  # defaults to stderr
    handler.setLevel(level)

    if log_format == 'json':
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        )

    root_logger.addHandler(handler)


_memory_logger = logging.getLogger(__name__ + '.memory')
_async_sleep = asyncio.sleep


def _get_rss_mb() -> float:
    """Return process memory in MB (current RSS on Linux, peak RSS on macOS, -1 elsewhere)."""
    # Linux / containers: read current RSS from procfs
    try:
        with open('/proc/self/statm') as f:
            pages = int(f.read().split()[1])  # 2nd field = RSS in pages
        return round(pages * os.sysconf('SC_PAGE_SIZE') / (1024 * 1024), 2)
    except (OSError, IndexError, ValueError):
        pass

    # macOS: peak RSS via resource (no procfs available)
    try:
        import resource

        return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024), 2)
    except ImportError:
        pass

    return -1.0


async def memory_monitor(interval_seconds: int = 60) -> None:
    """Periodically log process RSS memory usage.

    Emits a structured log event (event_type="memory_snapshot") with
    memory_rss_mb and pid fields, enabling CloudWatch metric filters
    for memory tracking.

    Args:
        interval_seconds: Seconds between snapshots (default: 60).
    """
    interval_seconds = max(interval_seconds, 1)
    pid = os.getpid()
    while True:
        await _async_sleep(interval_seconds)
        try:
            rss_mb = _get_rss_mb()
            _memory_logger.info(
                f'Memory snapshot: {rss_mb} MB (pid={pid})',
                extra={
                    'event_type': 'memory_snapshot',
                    'memory_rss_mb': rss_mb,
                    'pid': pid,
                },
            )
        except Exception as e:
            _memory_logger.warning(f'Memory monitor iteration failed: {e}')


def start_memory_monitor(interval_seconds: int | None = None) -> asyncio.Task:
    """Start the memory monitor as a background asyncio task.

    Args:
        interval_seconds: Seconds between snapshots. If not provided,
            reads from OPENSEARCH_MEMORY_MONITOR_INTERVAL env var (default: 60).

    Returns:
        The asyncio.Task running the monitor.
    """
    if interval_seconds is None:
        interval_seconds = int(os.environ.get('OPENSEARCH_MEMORY_MONITOR_INTERVAL', '60'))
    task = asyncio.create_task(memory_monitor(interval_seconds))
    task.add_done_callback(_handle_monitor_error)
    return task


def _handle_monitor_error(task: asyncio.Task) -> None:
    """Log any unexpected errors from the memory monitor task."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        _memory_logger.error(f'MCP Memory monitor crashed: {exc}')
