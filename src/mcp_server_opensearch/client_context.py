# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Per-request client identification for multi-client MCP deployments.

Provides a Starlette middleware that extracts the ``X-MCP-Client-Name`` HTTP
header from incoming requests and stores the value in a :mod:`contextvars`
variable. Downstream code (e.g., :mod:`tool_executor`) reads the variable to
include client attribution in structured log events, enabling per-client metric
filtering without changes to the MCP protocol itself.

The header is optional — if absent, the client name defaults to ``"unknown"``.
"""

import contextvars
import re
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send
from typing import Optional


#: Context variable holding the client name for the current request.
#: Defaults to ``"unknown"`` when the ``X-MCP-Client-Name`` header is not provided.
client_name_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    'mcp_client_name', default='unknown'
)

#: Context variable holding the current Starlette Request for header-auth extraction.
#: Set from the call_tool handler when the transport provides a request object.
request_context_var: contextvars.ContextVar[Optional[Request]] = contextvars.ContextVar(
    'mcp_request_context', default=None
)

# Header name (lowercase for case-insensitive lookup in ASGI scope).
_HEADER_NAME = b'x-mcp-client-name'

# Maximum allowed length for the client name.
_MAX_CLIENT_NAME_LENGTH = 64

# Pattern: only alphanumeric, hyphens, underscores, and dots are allowed.
_VALID_CLIENT_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9._-]+$')


def _sanitize_client_name(raw: str) -> str:
    """Sanitize and validate the client name header value.

    Enforces a length limit and character allowlist to prevent log injection
    or metric dimension pollution from malformed/malicious header values.

    Args:
        raw: The raw decoded header value.

    Returns:
        The sanitized client name, or ``"unknown"`` if the value is
        empty or contains invalid characters.
    """
    if not raw:
        return 'unknown'
    truncated = raw[:_MAX_CLIENT_NAME_LENGTH]
    if not _VALID_CLIENT_NAME_PATTERN.match(truncated):
        return 'unknown'
    return truncated


class ClientNameMiddleware:
    """Pure-ASGI middleware that extracts ``X-MCP-Client-Name`` into a contextvar.

    Using a raw ASGI middleware (instead of Starlette's BaseHTTPMiddleware)
    avoids the per-request overhead of wrapping the response in a background
    task and is compatible with streaming/SSE endpoints.
    """

    def __init__(self, app: ASGIApp) -> None:
        """Initialize with the wrapped ASGI application."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Extract client name header and forward to the wrapped app."""
        if scope['type'] not in ('http', 'websocket'):
            await self.app(scope, receive, send)
            return

        # Extract X-MCP-Client-Name from raw ASGI headers (list of [name, value] byte pairs).
        client_name = 'unknown'
        for header_name, header_value in scope.get('headers', []):
            if header_name == _HEADER_NAME:
                client_name = _sanitize_client_name(header_value.decode('latin-1'))
                break

        token = client_name_var.set(client_name)
        try:
            await self.app(scope, receive, send)
        finally:
            client_name_var.reset(token)
