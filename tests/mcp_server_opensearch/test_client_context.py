# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

from mcp_server_opensearch.client_context import (
    _MAX_CLIENT_NAME_LENGTH,
    ClientNameMiddleware,
    _sanitize_client_name,
    client_name_var,
)
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient


def _make_app():
    """Create a minimal Starlette app that echoes the client_name_var value."""

    async def echo_client_name(request: Request) -> JSONResponse:
        return JSONResponse({'client_name': client_name_var.get('unknown')})

    app = Starlette(routes=[Route('/test', endpoint=echo_client_name)])
    app.add_middleware(ClientNameMiddleware)
    return app


class TestSanitizeClientName:
    """Tests for the _sanitize_client_name validation function."""

    def test_valid_simple_name(self):
        """Alphanumeric names pass through unchanged."""
        assert _sanitize_client_name('default') == 'default'
        assert _sanitize_client_name('art') == 'art'

    def test_valid_with_hyphens_underscores_dots(self):
        """Hyphens, underscores, and dots are allowed."""
        assert _sanitize_client_name('my-agent') == 'my-agent'
        assert _sanitize_client_name('my_agent') == 'my_agent'
        assert _sanitize_client_name('agent.v2') == 'agent.v2'

    def test_empty_string_returns_unknown(self):
        """Empty header value defaults to unknown."""
        assert _sanitize_client_name('') == 'unknown'

    def test_too_long_is_truncated(self):
        """Values exceeding the max length are truncated."""
        long_value = 'a' * 200
        result = _sanitize_client_name(long_value)
        assert len(result) == _MAX_CLIENT_NAME_LENGTH
        assert result == 'a' * _MAX_CLIENT_NAME_LENGTH

    def test_invalid_characters_returns_unknown(self):
        """Values with special characters are rejected."""
        assert _sanitize_client_name('agent;DROP TABLE') == 'unknown'
        assert _sanitize_client_name('agent\ninjection') == 'unknown'
        assert _sanitize_client_name('agent/sub') == 'unknown'
        assert _sanitize_client_name('<script>alert(1)</script>') == 'unknown'
        assert _sanitize_client_name('agent name with spaces') == 'unknown'

    def test_truncation_before_validation(self):
        """Truncation happens before character validation."""
        # Valid chars but too long — should truncate and pass
        valid_long = 'a-b_c.' * 20  # 120 chars
        result = _sanitize_client_name(valid_long)
        assert len(result) == _MAX_CLIENT_NAME_LENGTH


class TestClientNameMiddleware:
    """Tests for the X-MCP-Client-Name header extraction middleware."""

    def test_header_present_sets_client_name(self):
        """Middleware extracts X-MCP-Client-Name header value into contextvar."""
        client = TestClient(_make_app())
        response = client.get('/test', headers={'X-MCP-Client-Name': 'my-agent'})
        assert response.status_code == 200
        assert response.json() == {'client_name': 'my-agent'}

    def test_header_absent_defaults_to_unknown(self):
        """Without the header, client name defaults to 'unknown'."""
        client = TestClient(_make_app())
        response = client.get('/test')
        assert response.status_code == 200
        assert response.json() == {'client_name': 'unknown'}

    def test_header_case_insensitive(self):
        """HTTP headers are case-insensitive; lowercase should work."""
        client = TestClient(_make_app())
        response = client.get('/test', headers={'x-mcp-client-name': 'lower-case'})
        assert response.status_code == 200
        assert response.json() == {'client_name': 'lower-case'}

    def test_client_name_does_not_leak_across_requests(self):
        """Each request gets its own contextvar scope."""
        client = TestClient(_make_app())
        resp1 = client.get('/test', headers={'X-MCP-Client-Name': 'agent-a'})
        resp2 = client.get('/test')
        resp3 = client.get('/test', headers={'X-MCP-Client-Name': 'agent-b'})

        assert resp1.json() == {'client_name': 'agent-a'}
        assert resp2.json() == {'client_name': 'unknown'}
        assert resp3.json() == {'client_name': 'agent-b'}

    def test_malicious_header_sanitized(self):
        """Headers with invalid characters are sanitized to 'unknown'."""
        client = TestClient(_make_app())
        response = client.get('/test', headers={'X-MCP-Client-Name': 'evil\ninjection'})
        assert response.json() == {'client_name': 'unknown'}

    def test_oversized_header_truncated(self):
        """Headers exceeding max length are truncated."""
        client = TestClient(_make_app())
        long_name = 'a' * 200
        response = client.get('/test', headers={'X-MCP-Client-Name': long_name})
        assert len(response.json()['client_name']) == _MAX_CLIENT_NAME_LENGTH
