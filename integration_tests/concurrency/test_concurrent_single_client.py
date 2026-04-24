# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import asyncio
import pytest
import time
from integration_tests.framework.assertions import assert_tool_success
from integration_tests.framework.aws_helpers import build_header_auth_headers
from integration_tests.framework.client import mcp_client


NUM_CALLS = 5


@pytest.mark.concurrency
class TestConcurrentSingleClient:
    """Fire N requests concurrently through a single MCP session."""

    async def test_concurrent_faster_than_sequential(
        self, header_auth_server, sequential_baseline
    ):
        """FAIL if wall-clock > 90% of sequential total."""
        headers = build_header_auth_headers()
        start_event = asyncio.Event()

        async with mcp_client(header_auth_server.url, headers=headers) as session:

            async def worker(i):
                await start_event.wait()
                t0 = time.perf_counter()
                result = await session.call_tool('ListIndexTool', arguments={})
                return time.perf_counter() - t0, result

            tasks = [asyncio.create_task(worker(i)) for i in range(NUM_CALLS)]
            await asyncio.sleep(0.05)  # Let all tasks reach the barrier
            start_event.set()

            results = await asyncio.gather(*tasks)

        wall_clock = max(t for t, _ in results)
        threshold = sequential_baseline * 0.90

        for _, result in results:
            assert_tool_success(result)

        assert wall_clock < threshold, (
            f'Concurrent single-client ({wall_clock:.2f}s) was NOT faster than '
            f'90% of sequential ({sequential_baseline:.2f}s, threshold={threshold:.2f}s). '
            f'Server appears to be serializing requests.'
        )
        speedup = sequential_baseline / wall_clock if wall_clock > 0 else float('inf')
        print(
            f'PASS: concurrent={wall_clock:.2f}s < threshold={threshold:.2f}s '
            f'(speedup: {speedup:.1f}x)'
        )
