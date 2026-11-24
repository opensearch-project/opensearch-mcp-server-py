# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Browser login for the stdio server.

The stdio transport has no MCP-level authorization, so the server logs its one
user in itself: it opens the browser at the provider (authorization code +
PKCE), takes the code on a loopback redirect URI, and keeps the provider tokens
in a file only that user can read. Each tool call sends the provider access token
to OpenSearch, or first exchanges it (RFC 8693) when an OpenSearch audience is
configured.

The client is normally public (no secret): the server runs on each user's own
machine, where a secret could not stay secret. A client secret is optional, for
providers that require a confidential client, and is required for the exchange.
"""

import base64
import hashlib
import html
import ipaddress
import json
import logging
import os
import requests
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from mcp_server_opensearch.oauth import (
    TokenExchangeConfig,
    _is_truthy,
    _required_env,
    load_exchange_config,
    reject_incompatible_auth,
    validate_oauth_url,
)
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, urlencode, urlsplit


logger = logging.getLogger(__name__)

DEFAULT_REDIRECT_URI = 'http://127.0.0.1:9900/oauth/callback'
DEFAULT_TOKEN_FILE = '~/.opensearch-mcp/oauth-login.json'
LOGIN_TIMEOUT = 300  # seconds a pending login waits for the browser
EXPIRY_MARGIN = 30  # refresh this many seconds before the access token expires
CALLBACK_READ_TIMEOUT = 5  # seconds the callback listener waits on one idle connection


@dataclass(frozen=True)
class LoginConfig:
    """Settings for the stdio browser login."""

    authorization_url: str
    token_url: str
    client_id: str
    redirect_uri: str
    scopes: str
    token_file: Path
    client_secret: str = field(default='', repr=False)
    exchange: TokenExchangeConfig | None = None


def _validate_redirect_uri(uri: str) -> str:
    name = 'MCP_OAUTH_REDIRECT_URI'
    validate_oauth_url(uri, name)
    parsed = urlsplit(uri)
    try:
        loopback = (
            parsed.hostname == 'localhost' or ipaddress.ip_address(parsed.hostname).is_loopback
        )
    except ValueError:
        loopback = False
    if parsed.scheme != 'http' or not loopback or parsed.port is None or not parsed.path:
        raise ValueError(f'{name} must be an http URL on a loopback host with an explicit port')
    return uri


def load_login_config() -> LoginConfig | None:
    """Load the stdio browser-login settings, or None when OAuth is off."""
    if not _is_truthy(os.getenv('MCP_OAUTH_ENABLED')):
        return None
    reject_incompatible_auth()
    exchange = (
        load_exchange_config() if os.getenv('MCP_OAUTH_OPENSEARCH_AUDIENCE', '').strip() else None
    )
    return LoginConfig(
        authorization_url=validate_oauth_url(
            _required_env('MCP_OAUTH_AUTHORIZATION_URL'), 'MCP_OAUTH_AUTHORIZATION_URL'
        ),
        token_url=validate_oauth_url(_required_env('MCP_OAUTH_TOKEN_URL'), 'MCP_OAUTH_TOKEN_URL'),
        client_id=_required_env('MCP_OAUTH_CLIENT_ID'),
        client_secret=os.getenv('MCP_OAUTH_CLIENT_SECRET', '').strip(),
        redirect_uri=_validate_redirect_uri(
            os.getenv('MCP_OAUTH_REDIRECT_URI', '').strip() or DEFAULT_REDIRECT_URI
        ),
        scopes=os.getenv('MCP_OAUTH_LOGIN_SCOPES', '').strip() or 'openid',
        token_file=Path(
            os.getenv('MCP_OAUTH_TOKEN_FILE', '').strip() or DEFAULT_TOKEN_FILE
        ).expanduser(),
        exchange=exchange,
    )


def open_browser_detached(url: str) -> None:
    """Open url in the default browser without sharing this process's stdin/stdout.

    The stdio transport speaks MCP over stdin/stdout. webbrowser.open in this process lets the
    launcher inherit them: on Linux it can print into the protocol stream, or a text-mode browser
    can take over stdin and block. A separate interpreter with no stdio avoids both; the login URL
    is in the tool error as well, in case no browser opens.
    """
    subprocess.Popen(
        [sys.executable, '-m', 'webbrowser', '-t', url],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


class LoginRequired(ValueError):
    """No usable login: the user has to finish the browser login, then retry."""

    def __init__(self, url: str):
        """Keep the authorization URL so the caller can show it."""
        self.url = url
        super().__init__(
            'Log in to OpenSearch in the browser window that just opened, then retry. '
            f'If no window opened, open: {url}'
        )


@dataclass
class _Pending:
    server: HTTPServer
    url: str
    state: str
    verifier: str
    started: float
    stopped: threading.Event = field(default_factory=threading.Event)

    def stop(self) -> None:
        """Close the listening socket now, so the port is free when this returns."""
        self.stopped.set()
        try:
            self.server.socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.server.socket.close()

    def serve(self) -> None:
        while not self.stopped.is_set():
            try:
                self.server.handle_request()
            except (OSError, ValueError):
                break
        self.server.server_close()


class BrowserLogin:
    """Provider tokens for the stdio server's single user, with a browser login."""

    def __init__(
        self,
        config: LoginConfig,
        open_browser: Callable[[str], object] = open_browser_detached,
        now: Callable[[], float] = time.time,
    ):
        """Load any stored login; nothing is opened until a token is needed."""
        self.config = config
        self._open_browser = open_browser
        self._now = now
        self._lock = threading.Lock()
        self._pending: _Pending | None = None
        self._tokens = self._load()

    def subject_token(self) -> str:
        """Return a valid provider access token, refreshing it or starting a login."""
        with self._lock:
            # The file is the source of truth: another server process may have logged in or
            # refreshed, and deleting the file logs out.
            tokens = self._tokens = self._load()
            if self._usable(tokens):
                return tokens['access_token']
            if tokens and tokens.get('refresh_token'):
                payload, rejected = self._token_request(
                    {'grant_type': 'refresh_token', 'refresh_token': tokens['refresh_token']}
                )
                if payload:
                    self._store(payload, tokens['refresh_token'])
                    return self._tokens['access_token']
                # With refresh-token rotation, another process may have refreshed first; its
                # new tokens are in the file, and deleting it would log both processes out.
                latest = self._load()
                if (
                    latest
                    and latest.get('refresh_token') != tokens['refresh_token']
                    and self._usable(latest)
                ):
                    self._tokens = latest
                    return latest['access_token']
                if not rejected:
                    raise ValueError(
                        'The OpenSearch login could not be refreshed because the identity '
                        'provider did not answer; retry shortly'
                    )
            if tokens:
                self._clear()
            raise LoginRequired(self._start_login())

    def _usable(self, tokens: dict | None) -> bool:
        return bool(tokens) and tokens['expires_at'] - EXPIRY_MARGIN > self._now()

    def close(self) -> None:
        """Stop a pending login's callback listener."""
        with self._lock:
            self._stop_pending()

    def _start_login(self) -> str:
        pending = self._pending
        if pending and self._now() - pending.started < LOGIN_TIMEOUT:
            return pending.url
        self._stop_pending()
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b'=')
            .decode()
        )
        url = (
            self.config.authorization_url
            + '?'
            + urlencode(
                {
                    'response_type': 'code',
                    'client_id': self.config.client_id,
                    'redirect_uri': self.config.redirect_uri,
                    'scope': self.config.scopes,
                    'state': state,
                    'code_challenge': challenge,
                    'code_challenge_method': 'S256',
                }
            )
        )
        redirect = urlsplit(self.config.redirect_uri)
        deadline = time.monotonic() + 1  # a listener we just stopped may still hold the port
        while True:
            try:
                server = HTTPServer((redirect.hostname, redirect.port), self._handler())
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise ValueError(
                        f'Port {redirect.port} on {redirect.hostname} is in use, so the OAuth '
                        'login callback cannot listen there; stop whatever uses it and retry'
                    ) from None
                time.sleep(0.05)
        server.timeout = 0.5
        pending = _Pending(server, url, state, verifier, self._now())
        self._pending = pending
        threading.Thread(target=pending.serve, daemon=True).start()
        timer = threading.Timer(LOGIN_TIMEOUT, self._expire, args=(pending,))
        timer.daemon = True
        timer.start()
        self._open_browser(url)
        return url

    def _expire(self, pending: _Pending) -> None:
        with self._lock:
            if self._pending is pending:
                self._stop_pending()

    def _stop_pending(self) -> None:
        if self._pending:
            self._pending.stop()
            self._pending = None

    def _handle_callback(self, query: dict[str, list[str]]) -> tuple[int, str]:
        with self._lock:
            pending = self._pending
        if not pending or query.get('state') != [pending.state]:
            return 400, 'This login link is stale or invalid. Retry the tool call.'
        code = query.get('code', [''])[0]
        if not code:
            return 400, 'The login was not completed. Retry the tool call.'
        payload, _ = self._token_request(
            {
                'grant_type': 'authorization_code',
                'code': code,
                'redirect_uri': self.config.redirect_uri,
                'code_verifier': pending.verifier,
            }
        )
        if not payload:
            return 502, 'The login could not be completed. Retry the tool call.'
        with self._lock:
            self._store(payload, None)
            if self._pending is pending:
                self._stop_pending()
        return 200, 'Logged in to OpenSearch. You can close this window and retry the tool call.'

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        login = self
        path = urlsplit(self.config.redirect_uri).path

        class Handler(BaseHTTPRequestHandler):
            # The listener is single-threaded: drop a connection that sends nothing (for
            # example a browser preconnect) instead of letting it block the real callback.
            timeout = CALLBACK_READ_TIMEOUT

            def log_message(self, *args):
                pass

            def do_GET(self):
                parsed = urlsplit(self.path)
                if parsed.path != path:
                    status, message = 404, 'Not found.'
                else:
                    status, message = login._handle_callback(parse_qs(parsed.query))
                body = f'<!doctype html><title>OpenSearch MCP</title><p>{html.escape(message)}</p>'
                self.send_response(status)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(body.encode())

        return Handler

    def _token_request(self, data: dict) -> tuple[dict | None, bool]:
        """POST to the provider token endpoint.

        Returns (body, False) on success, (None, True) when the provider rejected the grant
        (HTTP 400/401, e.g. invalid_grant), and (None, False) on any other failure (timeout,
        connection error, 5xx, an unusable response), which a retry may fix.
        """
        config = self.config
        auth = None
        if config.client_secret:
            auth = (quote_plus(config.client_id), quote_plus(config.client_secret))
        else:
            data = {**data, 'client_id': config.client_id}  # public client
        status = None
        try:
            with requests.post(
                config.token_url, data=data, auth=auth, timeout=10, allow_redirects=False
            ) as response:
                status = response.status_code
                payload = response.json() if status == 200 else None
            token = payload.get('access_token') if isinstance(payload, dict) else None
            # The token goes into an Authorization header as is: printable ASCII, no spaces.
            if isinstance(token, str) and token and all(32 < ord(c) < 127 for c in token):
                return payload, False
        except (requests.RequestException, ValueError):
            pass
        logger.warning(
            'OAuth login token request failed: grant=%s http_status=%s',
            data['grant_type'],
            status if status is not None else 'unavailable',
        )
        return None, status in (400, 401)

    def _store(self, payload: dict, old_refresh: str | None) -> None:
        try:
            expires_in = float(payload.get('expires_in', 60))
        except (TypeError, ValueError):
            expires_in = 60.0
        self._tokens = {
            'access_token': payload['access_token'],
            'refresh_token': payload.get('refresh_token') or old_refresh,
            'expires_at': self._now() + expires_in,
        }
        path = self.config.token_file
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        # mkstemp creates the file with mode 0600: only this user can read the tokens.
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.oauth-login-')
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(self._tokens, f)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def _clear(self) -> None:
        self._tokens = None
        self.config.token_file.unlink(missing_ok=True)

    def _load(self) -> dict | None:
        try:
            tokens = json.loads(self.config.token_file.read_text())
            if isinstance(tokens.get('access_token'), str) and isinstance(
                tokens.get('expires_at'), (int, float)
            ):
                return tokens
        except FileNotFoundError:
            return None
        except Exception:
            pass
        logger.warning('OAuth login file is unreadable or invalid; a new login is needed')
        return None


_browser_login: BrowserLogin | None = None


def set_browser_login(login: BrowserLogin | None) -> None:
    """Install the stdio server's browser login (None turns it off)."""
    global _browser_login
    _browser_login = login


def get_browser_login() -> BrowserLogin | None:
    """Return the stdio server's browser login, if one is configured."""
    return _browser_login
