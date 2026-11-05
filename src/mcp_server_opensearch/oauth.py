# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import asyncio
import jwt
import logging
import os
from dataclasses import dataclass
from mcp.server.auth.provider import AccessToken, TokenVerifier
from typing import Any


logger = logging.getLogger(__name__)


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

    issuer_url = os.getenv('MCP_OAUTH_ISSUER_URL', '').strip().rstrip('/')
    if not issuer_url:
        raise ValueError('MCP_OAUTH_ISSUER_URL must be set when MCP_OAUTH_ENABLED=true')

    default_host = 'localhost' if host == '0.0.0.0' else host
    resource_url = os.getenv(
        'MCP_OAUTH_RESOURCE_URL',
        f'http://{default_host}:{port}/mcp/',
    ).strip()
    jwks_url = os.getenv(
        'MCP_OAUTH_JWKS_URL',
        f'{issuer_url}/protocol/openid-connect/certs',
    ).strip()

    return OAuthConfig(
        enabled=True,
        issuer_url=issuer_url,
        resource_url=resource_url,
        jwks_url=jwks_url,
        required_scopes=_split_scopes(os.getenv('MCP_OAUTH_REQUIRED_SCOPES')),
        audience=os.getenv('MCP_OAUTH_AUDIENCE', '').strip() or None,
        algorithms=tuple(_split_scopes(os.getenv('MCP_OAUTH_ALGORITHMS', 'RS256'))),
    )


class JwtTokenVerifier(TokenVerifier):
    """Verify JWT bearer tokens issued by the configured OAuth/OIDC provider."""

    def __init__(self, config: OAuthConfig):
        """Create a verifier for the configured OAuth issuer and JWKS endpoint."""
        self.config = config
        self._jwks_client = jwt.PyJWKClient(config.jwks_url)

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
                audience=self.config.audience,
                issuer=self.config.issuer_url,
                options={'require': ['exp', 'iss', 'aud']},
            )
        except jwt.PyJWTError as e:
            logger.debug('Bearer token verification failed: %s', e)
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
