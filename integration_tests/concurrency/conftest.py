# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import time
import pytest_asyncio
from integration_tests.framework.assertions import assert_tool_success
from integration_tests.framework.aws_helpers import build_header_auth_headers
from integration_tests.framework.client import mcp_client


NUM_BASELINE_CALLS = 5


@pytest_asyncio.fixture(scope='session')
async def sequential_baseline(header_auth_server):
    """Run N sequential tool calls and return the total elapsed time.

    This fixture is session-scoped so concurrent tests can reference it.
    """
    headers = build_header_auth_headers()
    times = []

    async with mcp_client(header_auth_server.url, headers=headers) as session:
        # Warmup: prime DNS, connection pool, and server-side caches
        for _ in range(2):
            await session.call_tool('ListIndexTool', arguments={})

        for _ in range(NUM_BASELINE_CALLS):
            t0 = time.perf_counter()
            result = await session.call_tool('ListIndexTool', arguments={})
            times.append(time.perf_counter() - t0)
            assert_tool_success(result)

    total = sum(times)
    avg = total / len(times)
    print(f'Sequential baseline: total={total:.2f}s, avg={avg:.3f}s')
    return total
