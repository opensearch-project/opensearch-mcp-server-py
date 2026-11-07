# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import asyncio
import ipaddress
import jwt
import logging
import math
import os
import requests
import threading
import time
from dataclasses import dataclass, field
from mcp.server.auth.provider import AccessToken, TokenVerifier
from typing import Any
from urllib.parse import quote_plus, urlsplit


logger = logging.getLogger(__name__)


class _ExchangeFailureLog:
    """Bound diagnostics across concurrent tool calls without retaining credentials."""

    def __init__(self):
        self._lock = threading.Lock()
        self._next_log = 0.0

    def warning(self, status: int | None, category: str) -> None:
        with self._lock:
            now = time.monotonic()
            if now < self._next_log:
                return
            self._next_log = now + 60
        logger.warning(
            'OpenSearch token exchange failed: http_status=%s category=%s '
            '(logged at most once per minute)',
            status if status is not None else 'unavailable',
            category,
        )


def validate_oauth_url(value: str, name: str) -> str:
    """Require HTTPS, permitting HTTP only for literal loopback development endpoints."""
    try:
        parsed = urlsplit(value)
        loopback = parsed.hostname == 'localhost'
        if parsed.hostname and not loopback:
            try:
                loopback = ipaddress.ip_address(parsed.hostname).is_loopback
            except ValueError:
                pass
        valid = parsed.scheme == 'https' or (parsed.scheme == 'http' and loopback)
        if (
            not valid
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError
        parsed.port  # Validate the port without including the URL in errors.
    except ValueError:
        raise ValueError(
            f'{name} must be an HTTPS URL (HTTP is allowed only on loopback), without credentials, query, or fragment'
        ) from None
    return value


@dataclass(frozen=True)
class TokenExchangeConfig:
    """Operator-configured RFC 8693 exchange using client_secret_basic authentication."""

    token_url: str
    client_id: str
    client_secret: str = field(repr=False)
    audience: str
    scope: str = ''
    _failure_log: _ExchangeFailureLog = field(
        default_factory=_ExchangeFailureLog, init=False, repr=False, compare=False
    )

    def exchange(self, subject_token: str) -> str:
        """Exchange a verified MCP token; never fall back or expose provider errors/secrets."""
        data = {
            'grant_type': 'urn:ietf:params:oauth:grant-type:token-exchange',
            'subject_token': subject_token,
            'subject_token_type': 'urn:ietf:params:oauth:token-type:access_token',
            'requested_token_type': 'urn:ietf:params:oauth:token-type:access_token',
            'audience': self.audience,
        }
        if self.scope:
            data['scope'] = self.scope
        status = None
        category = 'request_error'
        try:
            with requests.post(
                self.token_url,
                data=data,
                auth=(quote_plus(self.client_id), quote_plus(self.client_secret)),
                timeout=10,
                allow_redirects=False,
            ) as response:
                status = response.status_code
                if response.status_code != 200:
                    category = 'http_error'
                    raise ValueError
                category = 'invalid_response'
                payload = response.json()
            token = payload.get('access_token')
            if (
                not isinstance(token, str)
                or not token
                or token == subject_token
                or any(c.isspace() or ord(c) < 32 or ord(c) > 126 for c in token)
                or payload.get('token_type', '').lower() != 'bearer'
                or payload.get('issued_token_type')
                != 'urn:ietf:params:oauth:token-type:access_token'
            ):
                raise ValueError
            if 'expires_in' in payload:
                expires_in = float(payload['expires_in'])
                if not math.isfinite(expires_in) or expires_in <= 0:
                    raise ValueError
            return token
        except (requests.RequestException, ValueError, TypeError, AttributeError):
            self._failure_log.warning(status, category)
            raise ValueError(
                'OpenSearch token exchange failed; no fallback credentials were used'
            ) from None


def _is_truthy(value: str | None) -> bool:
    normalized = (value or '').strip().lower()
    if normalized in {'1', 'true', 'yes', 'on'}:
        return True
    if normalized in {'', '0', 'false', 'no', 'off'}:
        return False
    raise ValueError('MCP_OAUTH_ENABLED must be true or false (also accepts 1/0, yes/no, on/off)')


def _split_scopes(value: str | None) -> list[str]:
    if not value:
        return []
    return [scope for scope in value.replace(',', ' ').split() if scope]


@dataclass(frozen=True)
class OAuthConfig:
    """OAuth resource-server settings for the streaming MCP transport."""

    enabled: bool
    issuer_url: str
    resource_url: str
    jwks_url: str
    required_scopes: list[str]
    audience: str | None = None
    algorithms: tuple[str, ...] = ('RS256',)
    exchange: TokenExchangeConfig | None = None

    def __post_init__(self):
        """Require an MCP audience and an explicit asymmetric algorithm allowlist."""
        if not self.audience:
            object.__setattr__(self, 'audience', self.resource_url)
        allowed = {
            'RS256',
            'RS384',
            'RS512',
            'PS256',
            'PS384',
            'PS512',
            'ES256',
            'ES384',
            'ES512',
            'EdDSA',
        }
        if not self.algorithms or not set(self.algorithms) <= allowed:
            raise ValueError(
                'MCP_OAUTH_ALGORITHMS must contain supported asymmetric JWT algorithms'
            )


def load_oauth_config(host: str, port: int) -> OAuthConfig | None:
    """Load OAuth resource-server settings from environment variables."""
    if not _is_truthy(os.getenv('MCP_OAUTH_ENABLED')):
        return None

    if os.getenv('OPENSEARCH_HEADER_AUTH', '').strip().lower() == 'true':
        raise ValueError('OAuth token exchange cannot be combined with OPENSEARCH_HEADER_AUTH')
    if os.getenv('OPENSEARCH_DYNAMIC_CONNECTION', '').strip().lower() in {'true', '1'}:
        raise ValueError(
            'OAuth token exchange cannot be combined with OPENSEARCH_DYNAMIC_CONNECTION'
        )

    def required(name: str) -> str:
        value = os.getenv(name, '').strip()
        if not value:
            raise ValueError(f'{name} must be set when MCP_OAUTH_ENABLED=true')
        return value

    issuer_url = validate_oauth_url(required('MCP_OAUTH_ISSUER_URL'), 'MCP_OAUTH_ISSUER_URL')
    resource_url = validate_oauth_url(required('MCP_OAUTH_RESOURCE_URL'), 'MCP_OAUTH_RESOURCE_URL')
    jwks_url = validate_oauth_url(required('MCP_OAUTH_JWKS_URL'), 'MCP_OAUTH_JWKS_URL')
    exchange = TokenExchangeConfig(
        token_url=validate_oauth_url(required('MCP_OAUTH_TOKEN_URL'), 'MCP_OAUTH_TOKEN_URL'),
        client_id=required('MCP_OAUTH_CLIENT_ID'),
        client_secret=required('MCP_OAUTH_CLIENT_SECRET'),
        audience=required('MCP_OAUTH_OPENSEARCH_AUDIENCE'),
        scope=os.getenv('MCP_OAUTH_OPENSEARCH_SCOPES', '').strip(),
    )
    audience = os.getenv('MCP_OAUTH_AUDIENCE', '').strip() or resource_url
    if exchange.audience.rstrip('/') == audience.rstrip('/'):
        raise ValueError('MCP and OpenSearch must have distinct token audiences')

    return OAuthConfig(
        enabled=True,
        issuer_url=issuer_url,
        resource_url=resource_url,
        jwks_url=jwks_url,
        required_scopes=_split_scopes(os.getenv('MCP_OAUTH_REQUIRED_SCOPES')),
        audience=audience,
        algorithms=tuple(_split_scopes(os.getenv('MCP_OAUTH_ALGORITHMS', 'RS256'))),
        exchange=exchange,
    )


class JwtTokenVerifier(TokenVerifier):
    """Verify JWT bearer tokens issued by the configured OAuth/OIDC provider."""

    def __init__(self, config: OAuthConfig):
        """Create a verifier for the configured OAuth issuer and JWKS endpoint."""
        self.config = config
        self._jwks_client = jwt.PyJWKClient(config.jwks_url)
        self._next_rejection_log = 0.0

    async def verify_token(self, token: str) -> AccessToken | None:
        """Verify a bearer token and return MCP access-token metadata."""
        try:
            signing_key = await asyncio.to_thread(
                self._jwks_client.get_signing_key_from_jwt, token
            )
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=list(self.config.algorithms),
                audience=(
                    [
                        self.config.resource_url.rstrip('/'),
                        self.config.resource_url.rstrip('/') + '/',
                    ]
                    if self.config.audience == self.config.resource_url
                    else self.config.audience
                ),
                issuer=self.config.issuer_url,
                options={'require': ['exp', 'iss', 'aud']},
            )
        except jwt.PyJWTError as e:
            # Log only a bounded error category, not attacker-controlled claims or key IDs.
            now = time.monotonic()
            if now >= self._next_rejection_log:
                logger.info(
                    'Bearer token rejected: %s (logged at most once per minute)', type(e).__name__
                )
                self._next_rejection_log = now + 60
            return None

        scopes = _extract_scopes(payload)
        client_id = (
            payload.get('azp')
            or payload.get('client_id')
            or payload.get('sub')
            or 'unknown-client'
        )

        return AccessToken(
            token=token,
            client_id=str(client_id),
            scopes=scopes,
            expires_at=_as_int(payload.get('exp')),
            resource=self.config.resource_url,
            subject=payload.get('sub'),
            claims={'iss': self.config.issuer_url},
        )


def _extract_scopes(payload: dict[str, Any]) -> list[str]:
    scope = payload.get('scope', payload.get('scp'))
    if isinstance(scope, str):
        return _split_scopes(scope)
    if isinstance(scope, list):
        return [item for item in scope if isinstance(item, str)]
    scopes = payload.get('scopes')
    if isinstance(scopes, list):
        return [str(scope) for scope in scopes]
    return []


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
