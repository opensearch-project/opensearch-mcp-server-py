# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import asyncio
import base64
import json
import jwt
import pytest
import socket
import threading
import time
import uvicorn
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from cryptography.hazmat.primitives.asymmetric import rsa
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp_server_opensearch.client_context import request_context_var
from mcp_server_opensearch.oauth import (
    JwtTokenVerifier,
    OAuthConfig,
    TokenExchangeConfig,
    validate_oauth_url,
)
from opensearch.client import AuthenticationError, ConfigurationError, get_opensearch_client
from starlette.applications import Starlette
from starlette.requests import Request
from tools.tool_params import baseToolArgs
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, unquote_plus


@pytest.fixture(autouse=True)
def single_mode():
    with patch('opensearch.client.get_mode', return_value='single'):
        yield


@pytest.fixture
def exchange_server():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    state = {'requests': [], 'backend_users': [], 'status': 200, 'response': None}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            form = parse_qs(self.rfile.read(int(self.headers['Content-Length'])).decode())
            state['requests'].append((dict(self.headers), form))
            subject = jwt.decode(
                form['subject_token'][0],
                key.public_key(),
                algorithms=['RS256'],
                audience='mcp',
                issuer='https://issuer.example/',
            )
            token = jwt.encode(
                {
                    'iss': 'https://issuer.example/',
                    'aud': 'opensearch',
                    'sub': subject['sub'],
                    'exp': int(time.time()) + 60,
                },
                key,
                algorithm='RS256',
            )
            body = (
                state['response']
                if state['response'] is not None
                else {
                    'access_token': token,
                    'token_type': 'Bearer',
                    'expires_in': 60,
                    'issued_token_type': 'urn:ietf:params:oauth:token-type:access_token',
                }
            )
            self.send_response(state['status'])
            self.send_header('Content-Type', 'application/json')
            self.send_header('Location', '/must-not-follow')
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())

        def do_GET(self):
            subject = jwt.decode(
                self.headers['Authorization'][7:],
                key.public_key(),
                algorithms=['RS256'],
                audience='opensearch',
            )
            state['backend_users'].append(subject['sub'])
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'user': subject['sub']}).encode())

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f'http://127.0.0.1:{server.server_port}'
    config = OAuthConfig(
        enabled=True,
        issuer_url='https://issuer.example/',
        resource_url='https://mcp.example/mcp',
        jwks_url='https://issuer.example/jwks',
        required_scopes=[],
        audience='mcp',
        exchange=TokenExchangeConfig(url + '/token', 'mcp-client', 'secret', 'opensearch', 'read'),
    )
    try:
        yield url, config, key, state
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


async def authenticated_request(config, key, name):
    token = jwt.encode(
        {'iss': config.issuer_url, 'aud': 'mcp', 'sub': name, 'exp': int(time.time()) + 60},
        key,
        algorithm='RS256',
    )
    verifier = JwtTokenVerifier(config)
    with patch.object(
        verifier._jwks_client, 'get_signing_key_from_jwt', return_value=Mock(key=key.public_key())
    ):
        access_token = await verifier.verify_token(token)
    assert access_token is not None
    app = Starlette()
    app.state.oauth_config = config
    return Request(
        {
            'type': 'http',
            'app': app,
            'user': AuthenticatedUser(access_token),
            'headers': [
                (b'authorization', f'Bearer {token}'.encode()),
                (b'opensearch-url', b'https://attacker.example'),
                (b'aws-access-key-id', b'ignored'),
            ],
        }
    )


@pytest.mark.parametrize('mode', ['single', 'multi'])
async def test_exchange_preserves_user_and_uses_only_configured_destination(
    exchange_server, monkeypatch, mode
):
    from mcp_server_opensearch.clusters_information import ClusterInfo

    url, config, key, state = exchange_server
    monkeypatch.setenv('OPENSEARCH_URL', url)
    monkeypatch.setenv('OPENSEARCH_USERNAME', 'admin')
    monkeypatch.setenv('OPENSEARCH_PASSWORD', 'must-not-be-used')
    monkeypatch.setenv('OPENSEARCH_NO_AUTH', 'true')
    monkeypatch.setenv(
        'OPENSEARCH_HEADER_AUTH', 'true'
    )  # Even a changed env cannot redirect credentials.
    with (
        patch('opensearch.client.get_mode', return_value=mode),
        patch('opensearch.client.get_cluster', return_value=ClusterInfo(opensearch_url=url)),
    ):
        for name in ['alice', 'bob']:
            request = await authenticated_request(config, key, name)
            reset = request_context_var.set(request)
            try:
                async with get_opensearch_client(
                    baseToolArgs(opensearch_cluster_name='test')
                ) as client:
                    assert await client.info() == {'user': name}
            finally:
                request_context_var.reset(reset)
    assert state['backend_users'] == ['alice', 'bob']
    for headers, form in state['requests']:
        assert (
            headers['Authorization'] == 'Basic ' + base64.b64encode(b'mcp-client:secret').decode()
        )
        assert form['grant_type'] == ['urn:ietf:params:oauth:grant-type:token-exchange']
        assert form['audience'] == ['opensearch']
        assert form['scope'] == ['read']
        assert form['subject_token_type'] == ['urn:ietf:params:oauth:token-type:access_token']


@pytest.mark.parametrize(
    'status,response',
    [(401, {'error': 'secret'}), (302, {}), (200, {}), (200, {'access_token': 'bad\r\nheader'})],
)
async def test_exchange_failure_never_uses_fallback(
    exchange_server, monkeypatch, status, response
):
    url, config, key, state = exchange_server
    monkeypatch.setenv('OPENSEARCH_URL', url)
    monkeypatch.setenv('OPENSEARCH_USERNAME', 'admin')
    monkeypatch.setenv('OPENSEARCH_PASSWORD', 'secret')
    state.update(status=status, response=response)
    reset = request_context_var.set(await authenticated_request(config, key, 'alice'))
    try:
        with pytest.raises(AuthenticationError, match='no fallback credentials'):
            async with get_opensearch_client(baseToolArgs(opensearch_cluster_name='')):
                pytest.fail('Must not create a backend client')
    finally:
        request_context_var.reset(reset)
    assert not state['backend_users']
    assert len(state['requests']) == 1


async def test_reject_destination_override_before_exchange(exchange_server):
    _, config, key, state = exchange_server
    reset = request_context_var.set(await authenticated_request(config, key, 'alice'))
    try:
        with pytest.raises(ConfigurationError, match='connection overrides'):
            async with get_opensearch_client(
                baseToolArgs(opensearch_cluster_name='', opensearch_url='https://attacker.example')
            ):
                pytest.fail('Must not create a backend client')
    finally:
        request_context_var.reset(reset)
    assert not state['requests']


@pytest.mark.parametrize(
    'url',
    [
        'http://example.com',
        'http://localhost.example.com',
        'file:///keys',
        'https://user:secret@example.com',
        'https://example.com/#fragment',
        'https://example.com/?token=secret',
        'https://example.com:bad',
    ],
)
def test_reject_unsafe_urls(url):
    with pytest.raises(ValueError, match='HTTPS URL'):
        validate_oauth_url(url, 'test endpoint')


@pytest.mark.parametrize(
    'url',
    [
        'https://example.com/',
        'http://localhost:8080',
        'http://127.0.0.1:8080',
        'http://[::1]:8080',
        'http://[::1]:9900/mcp/',
    ],
)
def test_accept_https_and_loopback_urls(url):
    assert validate_oauth_url(url, 'test endpoint') == url


@pytest.mark.parametrize(
    'overrides',
    [
        {'access_token': 'incoming-token'},
        {'access_token': ''},
        {'access_token': 123},
        {'access_token': 'bad\r\nheader'},
        {'token_type': 'MAC'},
        {'issued_token_type': 'jwt'},
        {'expires_in': -1},
        {'expires_in': 'nan'},
        {'expires_in': None},
    ],
)
def test_reject_invalid_exchange_response(overrides):
    payload = {
        'access_token': 'new-token',
        'token_type': 'Bearer',
        'expires_in': 60,
        'issued_token_type': 'urn:ietf:params:oauth:token-type:access_token',
        **overrides,
    }
    response = Mock(status_code=200)
    response.json.return_value = payload
    with patch('mcp_server_opensearch.oauth.requests.post') as post:
        post.return_value.__enter__.return_value = response
        with pytest.raises(ValueError, match='no fallback credentials'):
            TokenExchangeConfig(
                'https://issuer.example/token', 'client', 'secret', 'backend'
            ).exchange('incoming-token')


def test_exchange_timeout_does_not_expose_secrets():
    import requests

    with patch(
        'mcp_server_opensearch.oauth.requests.post', side_effect=requests.Timeout('secret-token')
    ):
        with pytest.raises(ValueError) as error:
            TokenExchangeConfig(
                'https://issuer.example/token', 'client', 'secret', 'backend'
            ).exchange('incoming-token')
    assert 'secret' not in str(error.value)


@asynccontextmanager
async def running_server(app):
    ready = asyncio.Event()

    class Server(uvicorn.Server):
        async def startup(self, sockets=None):
            await super().startup(sockets=sockets)
            ready.set()

    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        server = Server(uvicorn.Config(app, log_level='warning'))
        task = asyncio.create_task(server.serve(sockets=[listener]))
        try:
            await asyncio.wait_for(ready.wait(), 10)
            yield f'http://127.0.0.1:{listener.getsockname()[1]}'
        finally:
            server.should_exit = True
            await asyncio.wait_for(task, 10)


@pytest.mark.parametrize('transport', ['streamable', 'sse'])
async def test_mcp_tool_call_exchanges_token_end_to_end(exchange_server, monkeypatch, transport):
    from mcp import ClientSession
    from mcp.client.sse import sse_client
    from mcp.types import CallToolResult, TextContent
    from mcp_server_opensearch.streaming_server import MCPStarletteApp, create_mcp_server
    from starlette.testclient import TestClient
    from unittest.mock import AsyncMock

    url, config, key, state = exchange_server
    monkeypatch.setenv('OPENSEARCH_URL', url)

    async def execute(*args):
        async with get_opensearch_client(baseToolArgs(opensearch_cluster_name='')) as client:
            result = await client.info()
        return CallToolResult(content=[TextContent(type='text', text=json.dumps(result))])

    with (
        patch(
            'mcp_server_opensearch.streaming_server.generate_tools_from_openapi',
            new_callable=AsyncMock,
        ),
        patch(
            'mcp_server_opensearch.streaming_server.get_tools',
            new_callable=AsyncMock,
            return_value={},
        ),
        patch('mcp_server_opensearch.tool_executor.execute_tool', side_effect=execute),
        patch('mcp_server_opensearch.oauth.jwt.PyJWKClient') as jwks,
    ):
        jwks.return_value.get_signing_key_from_jwt.return_value = Mock(key=key.public_key())
        server = await create_mcp_server(oauth_config=config)
        app = MCPStarletteApp(server, oauth_config=config).create_app()
        tokens = {
            name: jwt.encode(
                {
                    'iss': config.issuer_url,
                    'aud': 'mcp',
                    'sub': name,
                    'exp': int(time.time()) + 60,
                },
                key,
                algorithm='RS256',
            )
            for name in ['alice', 'bob']
        }
        if transport == 'sse':
            async with running_server(app) as address:
                for name, token in tokens.items():
                    async with sse_client(
                        address + '/sse', headers={'Authorization': f'Bearer {token}'}
                    ) as streams:
                        async with ClientSession(*streams) as session:
                            await session.initialize()
                            result = await session.call_tool('WhoAmI', {})
                            assert not result.is_error
                            assert json.loads(result.content[0].text) == {'user': name}
        else:
            with TestClient(app) as client:
                for name, token in tokens.items():
                    response = client.post(
                        '/mcp',
                        headers={
                            'Authorization': f'Bearer {token}',
                            'Accept': 'application/json, text/event-stream',
                            'MCP-Protocol-Version': '2025-11-25',
                            'opensearch-url': 'https://attacker.example',
                        },
                        json={
                            'jsonrpc': '2.0',
                            'id': 1,
                            'method': 'tools/call',
                            'params': {'name': 'WhoAmI', 'arguments': {}},
                        },
                    )
                    assert response.status_code == 200, response.text
                    assert name in response.text, response.text
    assert state['backend_users'] == ['alice', 'bob']


async def test_client_secret_basic_form_encoding(exchange_server):
    _, config, key, state = exchange_server
    request = await authenticated_request(config, key, 'alice')
    exchange = replace(config.exchange, client_id='client+/:=', client_secret='secret+/= :')
    exchange.exchange(request.scope['user'].access_token.token)
    headers, _ = state['requests'][0]
    encoded = base64.b64decode(headers['Authorization'].removeprefix('Basic ')).decode()
    assert encoded == 'client%2B%2F%3A%3D:secret%2B%2F%3D+%3A'
    assert tuple(map(unquote_plus, encoded.split(':'))) == (
        exchange.client_id,
        exchange.client_secret,
    )


@pytest.mark.parametrize(
    'status,category',
    [(401, 'http_error'), (403, 'http_error'), (503, 'http_error'), (200, 'invalid_response')],
)
def test_exchange_failure_logging_is_bounded_and_redacted(caplog, status, category):
    config = TokenExchangeConfig(
        'https://issuer.example/token', 'client', 'client-secret', 'backend'
    )
    response = Mock(status_code=status)
    response.json.return_value = {'error': 'private-provider-message'}
    with (
        patch('mcp_server_opensearch.oauth.requests.post') as post,
        patch('mcp_server_opensearch.oauth.time.monotonic', return_value=100) as clock,
    ):
        post.return_value.__enter__.return_value = response

        def exchange(_):
            with pytest.raises(ValueError, match='no fallback credentials'):
                config.exchange('private-subject-token')

        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(exchange, range(16)))
        assert len(caplog.records) == 1
        clock.return_value = 159
        exchange(None)
        assert len(caplog.records) == 1
        clock.return_value = 160
        exchange(None)
        assert len(caplog.records) == 2
    assert all(record.levelname == 'WARNING' for record in caplog.records)
    assert f'http_status={status} category={category}' in caplog.text
    for secret in ['client-secret', 'private-subject-token', 'private-provider-message']:
        assert secret not in caplog.text


def test_exchange_network_error_logging(caplog):
    import requests

    with patch(
        'mcp_server_opensearch.oauth.requests.post', side_effect=requests.Timeout('secret-token')
    ):
        with pytest.raises(ValueError, match='no fallback credentials'):
            TokenExchangeConfig(
                'https://issuer.example/token', 'client', 'secret', 'backend'
            ).exchange('token')
    assert 'http_status=unavailable category=request_error' in caplog.text
    assert 'secret-token' not in caplog.text
