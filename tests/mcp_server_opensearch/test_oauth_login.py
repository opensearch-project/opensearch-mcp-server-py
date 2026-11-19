# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import base64
import hashlib
import json
import pytest
import socket
import stat
import subprocess
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from mcp_server_opensearch import oauth_login
from mcp_server_opensearch.oauth_login import (
    BrowserLogin,
    LoginConfig,
    LoginRequired,
    load_login_config,
)
from urllib.parse import parse_qs, urlencode, urlsplit


@pytest.fixture
def token_server():
    """Provider token endpoint: records each form and answers from state['responses']."""
    state = {'requests': [], 'responses': []}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            form = parse_qs(self.rfile.read(int(self.headers['Content-Length'])).decode())
            state['requests'].append((dict(self.headers), {k: v[0] for k, v in form.items()}))
            if state.get('on_post'):
                state['on_post']()  # e.g. another process writing the token file meanwhile
            status, body = (
                state['responses'].pop(0) if state['responses'] else (400, {'error': 'x'})
            )
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/token', state
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def free_port() -> int:
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def make_login(token_server, tmp_path):
    token_url, _ = token_server
    created = []

    def make(secret='', clock=None):
        config = LoginConfig(
            authorization_url='https://idp.example/auth',
            token_url=token_url,
            client_id='mcp-client',
            client_secret=secret,
            redirect_uri=f'http://127.0.0.1:{free_port()}/oauth/callback',
            scopes='openid',
            token_file=tmp_path / 'login.json',
        )
        opened = []
        login = BrowserLogin(config, open_browser=opened.append, now=clock or Clock())
        created.append(login)
        return login, opened

    yield make
    for login in created:
        login.close()


def tokens(access='at-1', refresh='rt-1', expires_in=300):
    return 200, {'access_token': access, 'refresh_token': refresh, 'expires_in': expires_in}


def callback(login, url, **query):
    """Simulate the provider redirecting the browser to the redirect URI."""
    state = parse_qs(urlsplit(url).query)['state'][0]
    params = {'state': state, 'code': 'the-code', **query}
    try:
        with urllib.request.urlopen(f'{login.config.redirect_uri}?{urlencode(params)}') as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def login_now(login, state):
    """Run a full login and return the authorization URL."""
    state['responses'].append(tokens())
    with pytest.raises(LoginRequired) as exc:
        login.subject_token()
    assert callback(login, exc.value.url) == 200
    return exc.value.url


ENV = {
    'MCP_OAUTH_ENABLED': 'true',
    'MCP_OAUTH_AUTHORIZATION_URL': 'https://idp.example/auth',
    'MCP_OAUTH_TOKEN_URL': 'https://idp.example/token',
    'MCP_OAUTH_CLIENT_ID': 'mcp-client',
}


def set_env(monkeypatch, **overrides):
    for name in [
        *ENV,
        'MCP_OAUTH_CLIENT_SECRET',
        'MCP_OAUTH_OPENSEARCH_AUDIENCE',
        'MCP_OAUTH_REDIRECT_URI',
        'MCP_OAUTH_TOKEN_FILE',
    ]:
        monkeypatch.delenv(name, raising=False)
    for name, value in {**ENV, **overrides}.items():
        monkeypatch.setenv(name, value)


def test_load_login_config_disabled_returns_none(monkeypatch):
    set_env(monkeypatch, MCP_OAUTH_ENABLED='false')
    assert load_login_config() is None


def test_load_login_config_defaults(monkeypatch):
    set_env(monkeypatch)
    config = load_login_config()
    assert config.redirect_uri == 'http://127.0.0.1:9900/oauth/callback'
    assert config.scopes == 'openid'
    assert config.token_file.name == 'oauth-login.json'
    assert config.client_id == 'mcp-client'
    assert config.client_secret == ''
    assert config.exchange is None


def test_load_login_config_with_exchange(monkeypatch):
    set_env(
        monkeypatch,
        MCP_OAUTH_CLIENT_SECRET='secret',
        MCP_OAUTH_OPENSEARCH_AUDIENCE='opensearch',
    )
    config = load_login_config()
    assert config.exchange.audience == 'opensearch'
    assert config.exchange.client_secret == 'secret'


def test_exchange_audience_requires_secret(monkeypatch):
    set_env(monkeypatch, MCP_OAUTH_OPENSEARCH_AUDIENCE='opensearch')
    with pytest.raises(ValueError, match='MCP_OAUTH_CLIENT_SECRET'):
        load_login_config()


@pytest.mark.parametrize('name', list(ENV)[1:])
def test_load_login_config_requires_fields(monkeypatch, name):
    set_env(monkeypatch, **{name: ''})
    with pytest.raises(ValueError, match=name):
        load_login_config()


@pytest.mark.parametrize(
    'uri',
    [
        'https://127.0.0.1:9900/oauth/callback',
        'http://example.com:9900/oauth/callback',
        'http://127.0.0.1/oauth/callback',
    ],
)
def test_redirect_uri_must_be_loopback_http(monkeypatch, uri):
    set_env(monkeypatch, MCP_OAUTH_REDIRECT_URI=uri)
    with pytest.raises(ValueError, match='MCP_OAUTH_REDIRECT_URI'):
        load_login_config()


def test_first_call_opens_browser_and_raises_login_required(make_login):
    login, opened = make_login()
    with pytest.raises(LoginRequired) as exc:
        login.subject_token()
    assert opened == [exc.value.url]
    assert exc.value.url in str(exc.value)
    query = parse_qs(urlsplit(exc.value.url).query)
    assert exc.value.url.startswith('https://idp.example/auth?')
    assert query['response_type'] == ['code']
    assert query['client_id'] == ['mcp-client']
    assert query['redirect_uri'] == [login.config.redirect_uri]
    assert query['code_challenge_method'] == ['S256']
    assert query['scope'] == ['openid']


def test_callback_redeems_code_and_stores_tokens(make_login, token_server):
    _, state = token_server
    login, _ = make_login()
    url = login_now(login, state)
    headers, form = state['requests'][0]
    assert 'Authorization' not in headers  # public client: PKCE, no secret
    assert form['client_id'] == 'mcp-client'
    assert form['grant_type'] == 'authorization_code'
    assert form['code'] == 'the-code'
    assert form['redirect_uri'] == login.config.redirect_uri
    challenge = parse_qs(urlsplit(url).query)['code_challenge'][0]
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(form['code_verifier'].encode()).digest())
        .rstrip(b'=')
        .decode()
    )
    assert challenge == expected
    assert login.subject_token() == 'at-1'
    path = login.config.token_file
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_confidential_client_uses_basic_auth(make_login, token_server):
    _, state = token_server
    login, _ = make_login(secret='secret')
    login_now(login, state)
    headers, form = state['requests'][0]
    assert headers['Authorization'] == 'Basic ' + base64.b64encode(b'mcp-client:secret').decode()
    assert 'client_id' not in form


def test_unsafe_access_token_is_rejected(make_login, token_server):
    _, state = token_server
    login, _ = make_login()
    state['responses'].append((200, {'access_token': 'bad\r\nheader', 'expires_in': 300}))
    with pytest.raises(LoginRequired) as exc:
        login.subject_token()
    assert callback(login, exc.value.url) == 502
    assert not login.config.token_file.exists()


def test_callback_rejects_wrong_state(make_login, token_server):
    _, state = token_server
    login, _ = make_login()
    state['responses'].append(tokens())
    with pytest.raises(LoginRequired) as exc:
        login.subject_token()
    wrong = exc.value.url.replace('state=', 'state=x')
    assert callback(login, wrong) == 400
    assert not state['requests']
    assert callback(login, exc.value.url) == 200
    assert login.subject_token() == 'at-1'


def test_callback_with_provider_error_does_not_redeem(make_login, token_server):
    _, state = token_server
    login, _ = make_login()
    with pytest.raises(LoginRequired) as exc:
        login.subject_token()
    assert callback(login, exc.value.url, error='access_denied', code='') == 400
    assert not state['requests']


def test_second_call_reuses_pending_login(make_login):
    login, opened = make_login()
    urls = []
    for _ in range(2):
        with pytest.raises(LoginRequired) as exc:
            login.subject_token()
        urls.append(exc.value.url)
    assert urls[0] == urls[1]
    assert len(opened) == 1


def test_pending_login_expires_after_5_minutes(make_login):
    clock = Clock()
    login, opened = make_login(clock=clock)
    with pytest.raises(LoginRequired) as first:
        login.subject_token()
    clock.t += 301
    with pytest.raises(LoginRequired) as second:
        login.subject_token()
    assert first.value.url != second.value.url
    assert len(opened) == 2


def test_valid_token_is_reused(make_login, token_server):
    _, state = token_server
    login, _ = make_login()
    login_now(login, state)
    assert login.subject_token() == 'at-1'
    assert login.subject_token() == 'at-1'
    assert len(state['requests']) == 1


def test_expired_token_is_refreshed(make_login, token_server):
    _, state = token_server
    clock = Clock()
    login, _ = make_login(clock=clock)
    login_now(login, state)
    clock.t += 280  # within 30 seconds of expiry
    state['responses'].append(tokens('at-2', 'rt-2'))
    assert login.subject_token() == 'at-2'
    _, form = state['requests'][1]
    assert form == {
        'grant_type': 'refresh_token',
        'refresh_token': 'rt-1',
        'client_id': 'mcp-client',
    }
    clock.t += 280
    state['responses'].append(tokens('at-3', None))
    assert login.subject_token() == 'at-3'
    assert state['requests'][2][1]['refresh_token'] == 'rt-2'


def test_failed_refresh_starts_login(make_login, token_server):
    _, state = token_server
    clock = Clock()
    login, opened = make_login(clock=clock)
    login_now(login, state)
    clock.t += 400
    state['responses'].append((400, {'error': 'invalid_grant'}))
    with pytest.raises(LoginRequired):
        login.subject_token()
    assert not login.config.token_file.exists()
    assert len(opened) == 2


def test_token_survives_new_instance(make_login, token_server):
    _, state = token_server
    login, _ = make_login()
    login_now(login, state)
    again = BrowserLogin(login.config, open_browser=pytest.fail, now=Clock())
    assert again.subject_token() == 'at-1'


def test_corrupt_file_means_no_login(make_login):
    login, _ = make_login()
    login.config.token_file.write_text('not json')
    fresh = BrowserLogin(login.config, open_browser=lambda url: None, now=Clock())
    try:
        with pytest.raises(LoginRequired):
            fresh.subject_token()
    finally:
        fresh.close()


def test_port_in_use_reports_error(make_login):
    login, opened = make_login()
    port = urlsplit(login.config.redirect_uri).port
    with socket.socket() as busy:
        busy.bind(('127.0.0.1', port))
        busy.listen()
        with pytest.raises(ValueError, match='in use') as exc:
            login.subject_token()
    assert not isinstance(exc.value, LoginRequired)
    assert not opened


def test_idle_connection_does_not_block_callback(make_login, token_server, monkeypatch):
    import mcp_server_opensearch.oauth_login as oauth_login

    monkeypatch.setattr(oauth_login, 'CALLBACK_READ_TIMEOUT', 0.5)
    _, state = token_server
    login, _ = make_login()
    state['responses'].append(tokens())
    with pytest.raises(LoginRequired) as exc:
        login.subject_token()
    port = urlsplit(login.config.redirect_uri).port
    with socket.create_connection(('127.0.0.1', port)):  # e.g. a browser preconnect
        query = urlencode(
            {'state': parse_qs(urlsplit(exc.value.url).query)['state'][0], 'code': 'c'}
        )
        with urllib.request.urlopen(f'{login.config.redirect_uri}?{query}', timeout=3) as r:
            assert r.status == 200


def test_second_process_sees_login_from_first(make_login, token_server):
    _, state = token_server
    first, _ = make_login()
    second = BrowserLogin(first.config, open_browser=pytest.fail, now=Clock())
    login_now(first, state)
    assert second.subject_token() == 'at-1'


def test_second_process_uses_refresh_done_by_first(make_login, token_server):
    _, state = token_server
    clock = Clock()
    first, _ = make_login(clock=clock)
    login_now(first, state)
    second = BrowserLogin(first.config, open_browser=pytest.fail, now=clock)
    clock.t += 280
    state['responses'].append(tokens('at-2', 'rt-2'))
    assert first.subject_token() == 'at-2'
    assert second.subject_token() == 'at-2'
    assert len(state['requests']) == 2  # one code redemption, one refresh


def test_default_browser_opener_is_detached_from_stdio(monkeypatch):
    """The server's stdin/stdout carry MCP: the browser launcher must not inherit them."""
    calls = []
    monkeypatch.setattr(oauth_login.subprocess, 'Popen', lambda *a, **k: calls.append((a, k)))
    oauth_login.open_browser_detached('https://idp.example/auth?x=1')
    ((args, kwargs),) = calls
    assert args[0][-1] == 'https://idp.example/auth?x=1'
    assert kwargs['stdin'] is subprocess.DEVNULL
    assert kwargs['stdout'] is subprocess.DEVNULL
    assert kwargs['stderr'] is subprocess.DEVNULL
    assert kwargs['start_new_session'] is True


def test_browser_login_uses_detached_opener_by_default(make_login):
    login, _ = make_login()
    assert BrowserLogin(login.config)._open_browser is oauth_login.open_browser_detached


def test_transient_refresh_failure_keeps_login(make_login, token_server):
    _, state = token_server
    clock = Clock()
    login, opened = make_login(clock=clock)
    login_now(login, state)
    clock.t += 400
    state['responses'].append((503, {'error': 'unavailable'}))
    with pytest.raises(ValueError, match='retry') as exc:
        login.subject_token()
    assert not isinstance(exc.value, LoginRequired)
    assert login.config.token_file.exists()
    assert len(opened) == 1  # no new browser login
    state['responses'].append(tokens('at-2', 'rt-2'))
    assert login.subject_token() == 'at-2'


def test_rejected_refresh_uses_tokens_another_process_just_stored(make_login, token_server):
    """Refresh-token rotation: the loser of a concurrent refresh must not delete the winner's file."""
    _, state = token_server
    clock = Clock()
    first, opened = make_login(clock=clock)
    login_now(first, state)
    clock.t += 400
    second = BrowserLogin(first.config, open_browser=pytest.fail, now=clock)
    state['on_post'] = lambda: first._store(
        {'access_token': 'at-2', 'refresh_token': 'rt-2', 'expires_in': 300}, None
    )
    state['responses'].append((400, {'error': 'invalid_grant'}))
    assert second.subject_token() == 'at-2'
    assert first.config.token_file.exists()


def test_deleted_token_file_logs_out(make_login, token_server):
    _, state = token_server
    login, opened = make_login()
    login_now(login, state)
    login.config.token_file.unlink()
    with pytest.raises(LoginRequired):
        login.subject_token()
    assert len(opened) == 2
