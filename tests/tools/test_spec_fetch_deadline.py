# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Bound startup downloads and keep failures off the MCP stdout stream."""

import aiohttp
import asyncio
import contextlib
import logging
import pytest
from aiohttp import web
from tools import tool_generator
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_spec_fetch_has_explicit_deadlines(monkeypatch):
    """Check all timeout phases without relying on wall-clock timing."""
    response = AsyncMock()
    response.raise_for_status = lambda: None
    response.text.return_value = 'paths: {}'
    request_context = AsyncMock()
    request_context.__aenter__.return_value = response
    session = AsyncMock()
    session.get = lambda *args, **kwargs: request_context
    session_context = AsyncMock()
    session_context.__aenter__.return_value = session
    captured = {}

    def create_session(**kwargs):
        captured.update(kwargs)
        return session_context

    monkeypatch.setattr(tool_generator.aiohttp, 'ClientSession', create_session)
    # Avoid creating an unused real connector in this constructor-only test.
    monkeypatch.setattr(tool_generator.aiohttp, 'TCPConnector', lambda **kwargs: object())
    assert await tool_generator.fetch_github_spec('_core.yaml') == {'paths': {}}
    timeout = captured.get('timeout')
    assert isinstance(timeout, aiohttp.ClientTimeout)
    assert timeout.total == 10
    assert timeout.connect == 5
    assert timeout.sock_read == 5


@pytest.mark.asyncio
@pytest.mark.parametrize('stall', [False, True])
async def test_real_local_spec_download(monkeypatch, stall):
    """Exercise real aiohttp success and a server that never returns headers."""
    release = asyncio.Event()
    entered = asyncio.Event()

    async def serve_spec(request):
        entered.set()
        if stall:
            await release.wait()
        return web.Response(text='paths: {}', content_type='application/yaml')

    app = web.Application()
    app.router.add_get('/_core.yaml', serve_spec)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    monkeypatch.setattr(tool_generator, 'BASE_URL', f'http://127.0.0.1:{port}')
    monkeypatch.setattr(
        tool_generator, 'SPEC_FETCH_TIMEOUT', aiohttp.ClientTimeout(total=0.1), raising=False
    )
    task = asyncio.create_task(tool_generator.fetch_github_spec('_core.yaml'))
    try:
        await asyncio.wait_for(entered.wait(), 5)
        if stall:
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(asyncio.shield(task), 2)
            # A timeout from the outer safety guard leaves the shielded request
            # pending. Only the actual client deadline completes the task.
            assert task.done(), 'The client did not apply its download deadline'
        else:
            assert await asyncio.wait_for(task, 5) == {'paths': {}}
    finally:
        release.set()
        if not task.done():
            task.cancel()
        with contextlib.suppress(asyncio.CancelledError, asyncio.TimeoutError):
            await task
        await runner.cleanup()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'error', [asyncio.TimeoutError('download timed out'), aiohttp.ClientError('offline')]
)
async def test_failed_generation_preserves_builtins_without_stdout(
    monkeypatch, capsys, caplog, error
):
    """A failed optional download must not corrupt stdio or remove builtins."""
    registry = {'ListIndexTool': {'display_name': 'ListIndexTool'}}
    monkeypatch.setattr(tool_generator, 'TOOL_REGISTRY', registry)
    fetch = AsyncMock(side_effect=error)
    monkeypatch.setattr(tool_generator, 'fetch_github_spec', fetch)
    with caplog.at_level(logging.WARNING, logger=tool_generator.__name__):
        result = await tool_generator.generate_tools_from_openapi()
    assert result is registry
    assert registry == {'ListIndexTool': {'display_name': 'ListIndexTool'}}
    fetch.assert_awaited_once_with(tool_generator.SPEC_FILES[0])
    assert capsys.readouterr().out == ''
    assert type(error).__name__ in caplog.text


@pytest.mark.asyncio
async def test_generation_cancellation_propagates(monkeypatch, capsys):
    """Cancellation is not swallowed as an optional-download failure."""
    monkeypatch.setattr(
        tool_generator, 'fetch_github_spec', AsyncMock(side_effect=asyncio.CancelledError)
    )
    with pytest.raises(asyncio.CancelledError):
        await tool_generator.generate_tools_from_openapi()
    assert capsys.readouterr().out == ''
