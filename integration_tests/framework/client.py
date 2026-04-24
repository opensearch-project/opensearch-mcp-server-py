# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import logging
from contextlib import AsyncExitStack, asynccontextmanager
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


logger = logging.getLogger(__name__)


@asynccontextmanager
async def mcp_client(server_url: str, headers: dict | None = None, timeout: float = 30.0):
    """Create an MCP client session connected to the given server URL.

    Args:
        server_url: The MCP server URL (e.g. http://127.0.0.1:9901/mcp).
        headers: Optional HTTP headers for auth.
        timeout: Connection timeout in seconds.

    Yields:
        An initialized MCP ClientSession.
    """
    stack = AsyncExitStack()
    try:
        transport_ctx = streamablehttp_client(
            url=server_url,
            headers=headers or {},
            timeout=timeout,
        )
        streams = await stack.enter_async_context(transport_ctx)
        read_stream, write_stream = streams[0], streams[1]

        session_ctx = ClientSession(read_stream, write_stream)
        session = await stack.enter_async_context(session_ctx)
        await session.initialize()

        yield session
    finally:
        # Suppress cancel scope errors during teardown — pytest-asyncio may
        # run fixture finalizers in a different task than the one that entered
        # the anyio cancel scopes, causing a harmless RuntimeError.
        try:
            await stack.aclose()
        except RuntimeError as e:
            logger.debug(f'Suppressed exception during client teardown: {e}')
