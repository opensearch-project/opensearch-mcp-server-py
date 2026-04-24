# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import asyncio
import pytest
import time
from integration_tests.framework.assertions import assert_tool_success
from integration_tests.framework.aws_helpers import build_header_auth_headers
from integration_tests.framework.client import mcp_client


RAMP_N = 5  # Total requests per concurrency level


@pytest.mark.concurrency
class TestRampLoad:
    """Progressive concurrency increase — reports stats, fails on >10% error rate."""

    @pytest.mark.parametrize('concurrency', [1, 2, 4])
    async def test_ramp(self, header_auth_server, concurrency):
        """Run RAMP_N requests at given concurrency level. Fail on >10% errors."""
        headers = build_header_auth_headers()
        sem = asyncio.Semaphore(concurrency)
        lock = asyncio.Lock()
        successes = 0
        failures = 0
        times = []

        async def worker(i):
            nonlocal successes, failures
            async with sem:
                async with mcp_client(header_auth_server.url, headers=headers) as session:
                    t0 = time.perf_counter()
                    try:
                        result = await asyncio.wait_for(
                            session.call_tool('ListIndexTool', arguments={}),
                            timeout=30.0,
                        )
                        assert_tool_success(result)
                        async with lock:
                            successes += 1
                            times.append(time.perf_counter() - t0)
                    except Exception:
                        async with lock:
                            failures += 1

        await asyncio.gather(*[worker(i) for i in range(RAMP_N)])

        total = successes + failures
        error_rate = failures / total if total > 0 else 0

        # Print stats
        if times:
            sorted_times = sorted(times)
            p95_idx = int(len(sorted_times) * 0.95)
            p95 = sorted_times[min(p95_idx, len(sorted_times) - 1)]
            print(
                f'Concurrency={concurrency}: success={successes}, fail={failures}, '
                f'error_rate={error_rate:.1%}, p95={p95:.3f}s'
            )
        else:
            print(
                f'Concurrency={concurrency}: success={successes}, fail={failures}, '
                f'error_rate={error_rate:.1%}'
            )

        assert error_rate <= 0.10, (
            f'Error rate {error_rate:.1%} exceeds 10% at concurrency={concurrency}'
        )
