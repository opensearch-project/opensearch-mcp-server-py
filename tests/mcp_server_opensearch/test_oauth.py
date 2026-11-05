# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import asyncio
import jwt
import pytest
import threading
import time
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from dataclasses import replace
from mcp.server import Server
from mcp_server_opensearch.oauth import JwtTokenVerifier, OAuthConfig, load_oauth_config
from mcp_server_opensearch.streaming_server import MCPStarletteApp
from starlette.responses import PlainTextResponse
from starlette.testclient import TestClient
from unittest.mock import Mock, patch


class TestOAuthConfig:
    def test_load_oauth_config_disabled(self, monkeypatch):
        monkeypatch.delenv('MCP_OAUTH_ENABLED', raising=False)

        assert load_oauth_config('127.0.0.1', 9900) is None

    def test_load_oauth_config_defaults(self, monkeypatch):
        monkeypatch.setenv('MCP_OAUTH_ENABLED', 'true')
        monkeypatch.setenv('MCP_OAUTH_ISSUER_URL', 'http://localhost:8080/realms/opensearch/')
        monkeypatch.setenv('MCP_OAUTH_REQUIRED_SCOPES', 'openid,profile email')
        monkeypatch.delenv('MCP_OAUTH_RESOURCE_URL', raising=False)
        monkeypatch.delenv('MCP_OAUTH_JWKS_URL', raising=False)
        monkeypatch.delenv('MCP_OAUTH_AUDIENCE', raising=False)

        config = load_oauth_config('0.0.0.0', 9900)

        assert config is not None
        assert config.enabled is True
        assert config.issuer_url == 'http://localhost:8080/realms/opensearch'
        assert config.resource_url == 'http://localhost:9900/mcp/'
        assert (
            config.jwks_url
            == 'http://localhost:8080/realms/opensearch/protocol/openid-connect/certs'
        )
        assert config.required_scopes == ['openid', 'profile', 'email']
        assert config.audience == config.resource_url

    def test_load_oauth_config_requires_issuer(self, monkeypatch):
        monkeypatch.setenv('MCP_OAUTH_ENABLED', 'true')
        monkeypatch.delenv('MCP_OAUTH_ISSUER_URL', raising=False)

        with pytest.raises(ValueError, match='MCP_OAUTH_ISSUER_URL'):
            load_oauth_config('127.0.0.1', 9900)


class TestJwtTokenVerifier:
    @pytest.mark.asyncio
    async def test_verify_token(self):
        config = OAuthConfig(
            enabled=True,
            issuer_url='http://localhost:8080/realms/opensearch',
            resource_url='http://127.0.0.1:9900/mcp/',
            jwks_url='http://localhost:8080/realms/opensearch/protocol/openid-connect/certs',
            required_scopes=['openid'],
            audience='opensearch-mcp',
        )

        signing_key = Mock()
        signing_key.key = 'public-key'

        with (
            patch('mcp_server_opensearch.oauth.jwt.PyJWKClient') as mock_jwks_client,
            patch('mcp_server_opensearch.oauth.jwt.decode') as mock_decode,
        ):
            mock_jwks_client.return_value.get_signing_key_from_jwt.return_value = signing_key
            mock_decode.return_value = {
                'azp': 'opensearch-mcp',
                'scope': 'openid profile email',
                'exp': 12345,
            }

            verifier = JwtTokenVerifier(config)
            access_token = await verifier.verify_token('encoded-token')

        assert access_token is not None
        assert access_token.token == 'encoded-token'
        assert access_token.client_id == 'opensearch-mcp'
        assert access_token.scopes == ['openid', 'profile', 'email']
        assert access_token.expires_at == 12345
        mock_decode.assert_called_once_with(
            'encoded-token',
            'public-key',
            algorithms=['RS256'],
            audience='opensearch-mcp',
            issuer='http://localhost:8080/realms/opensearch',
            options={'require': ['exp', 'iss', 'aud']},
        )

    @pytest.mark.asyncio
    async def test_verify_token_returns_none_for_invalid_token(self):
        config = OAuthConfig(
            enabled=True,
            issuer_url='http://localhost:8080/realms/opensearch',
            resource_url='http://127.0.0.1:9900/mcp/',
            jwks_url='http://localhost:8080/realms/opensearch/protocol/openid-connect/certs',
            required_scopes=[],
        )

        with patch('mcp_server_opensearch.oauth.jwt.PyJWKClient') as mock_jwks_client:
            mock_jwks_client.return_value.get_signing_key_from_jwt.side_effect = jwt.PyJWTError(
                'bad token'
            )

            verifier = JwtTokenVerifier(config)
            access_token = await verifier.verify_token('encoded-token')

        assert access_token is None


@pytest.mark.parametrize('value', ['enabled', 'treu', '2'])
def test_invalid_enabled_value_fails_startup(monkeypatch, value):
    monkeypatch.setenv('MCP_OAUTH_ENABLED', value)
    with pytest.raises(ValueError, match='MCP_OAUTH_ENABLED'):
        load_oauth_config('localhost', 9900)


@pytest.mark.parametrize('value', ['', 'false', '0', 'no', 'off'])
def test_disabled_values(monkeypatch, value):
    monkeypatch.setenv('MCP_OAUTH_ENABLED', value)
    assert load_oauth_config('localhost', 9900) is None


@pytest.mark.parametrize('algorithms', ['none', 'HS256', 'RS256,HS256', '', 'bogus'])
def test_reject_unsafe_or_unknown_algorithms(monkeypatch, algorithms):
    monkeypatch.setenv('MCP_OAUTH_ENABLED', 'true')
    monkeypatch.setenv('MCP_OAUTH_ISSUER_URL', 'https://issuer.example')
    monkeypatch.setenv('MCP_OAUTH_ALGORITHMS', algorithms)
    with pytest.raises(ValueError, match='MCP_OAUTH_ALGORITHMS'):
        load_oauth_config('localhost', 9900)


@pytest.fixture
def oauth_config():
    return OAuthConfig(
        enabled=True,
        issuer_url='https://issuer.example',
        resource_url='https://mcp.example/mcp',
        jwks_url='https://issuer.example/jwks',
        required_scopes=['read'],
    )


@pytest.fixture(scope='module')
def rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.mark.parametrize('algorithm', ['RS256', 'PS256', 'ES256'])
@pytest.mark.parametrize(
    'scope_claim', [{'scope': 'read write'}, {'scp': 'read write'}, {'scp': ['read', 'write']}]
)
async def test_signed_tokens(oauth_config, rsa_key, algorithm, scope_claim):
    key = ec.generate_private_key(ec.SECP256R1()) if algorithm == 'ES256' else rsa_key
    verifier = JwtTokenVerifier(replace(oauth_config, algorithms=(algorithm,)))
    token = jwt.encode(
        {
            'iss': oauth_config.issuer_url,
            'aud': oauth_config.resource_url,
            'exp': int(time.time()) + 300,
            'sub': 'user',
            **scope_claim,
        },
        key,
        algorithm=algorithm,
    )
    with patch.object(
        verifier._jwks_client, 'get_signing_key_from_jwt', return_value=Mock(key=key.public_key())
    ):
        result = await verifier.verify_token(token)
    assert result is not None
    assert result.client_id == 'user'
    assert result.scopes == ['read', 'write']


@pytest.mark.parametrize(
    'claim,value',
    [
        ('aud', None),
        ('aud', 'other-service'),
        ('iss', 'https://other.example'),
        ('exp', None),
        ('exp', 1),
    ],
)
async def test_reject_invalid_claims(oauth_config, rsa_key, claim, value):
    payload = {
        'iss': oauth_config.issuer_url,
        'aud': oauth_config.resource_url,
        'exp': int(time.time()) + 300,
    }
    if value is None:
        payload.pop(claim)
    else:
        payload[claim] = value
    verifier = JwtTokenVerifier(oauth_config)
    token = jwt.encode(payload, rsa_key, algorithm='RS256')
    with patch.object(
        verifier._jwks_client,
        'get_signing_key_from_jwt',
        return_value=Mock(key=rsa_key.public_key()),
    ):
        assert await verifier.verify_token(token) is None


async def test_jwks_lookup_does_not_block_event_loop(oauth_config):
    verifier = JwtTokenVerifier(oauth_config)
    loop_thread = threading.get_ident()

    def lookup(token):
        assert threading.get_ident() != loop_thread
        raise jwt.PyJWKClientError('unavailable')

    with patch.object(verifier._jwks_client, 'get_signing_key_from_jwt', side_effect=lookup):
        assert await asyncio.wait_for(verifier.verify_token('token'), timeout=2) is None


@pytest.mark.parametrize(
    'path,method',
    [
        ('/mcp', 'POST'),
        ('/mcp/', 'POST'),
        ('/mcp', 'GET'),
        ('/mcp', 'DELETE'),
        ('/sse', 'GET'),
        ('/messages/', 'POST'),
    ],
)
@pytest.mark.parametrize('scopes,status', [(None, 401), ('other', 403), ('read', 200)])
def test_protected_routes(oauth_config, rsa_key, path, method, scopes, status):
    handler = MCPStarletteApp(Server('test'), oauth_config=oauth_config)

    async def asgi_ok(scope, receive, send):
        await PlainTextResponse('ok')(scope, receive, send)

    async def sse_ok(request):
        return PlainTextResponse('ok')

    handler.session_manager.handle_request = asgi_ok
    handler.sse.handle_post_message = asgi_ok
    handler.handle_sse = sse_ok
    headers = {}
    if scopes is not None:
        token = jwt.encode(
            {
                'iss': oauth_config.issuer_url,
                'aud': oauth_config.resource_url,
                'exp': int(time.time()) + 300,
                'sub': 'user',
                'scp': scopes,
            },
            rsa_key,
            algorithm='RS256',
        )
        headers['Authorization'] = f'Bearer {token}'

    with patch('mcp_server_opensearch.oauth.jwt.PyJWKClient') as jwks:
        jwks.return_value.get_signing_key_from_jwt.return_value = Mock(key=rsa_key.public_key())
        client = TestClient(handler.create_app())
        response = client.request(method, path, headers=headers, follow_redirects=False)
    assert response.status_code == status
    if status != 200:
        assert 'resource_metadata=' in response.headers['www-authenticate']


async def test_reject_invalid_signature(oauth_config, rsa_key):
    verifier = JwtTokenVerifier(oauth_config)
    token = jwt.encode(
        {
            'iss': oauth_config.issuer_url,
            'aud': oauth_config.resource_url,
            'exp': int(time.time()) + 300,
        },
        rsa_key,
        algorithm='RS256',
    )
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with patch.object(
        verifier._jwks_client,
        'get_signing_key_from_jwt',
        return_value=Mock(key=other_key.public_key()),
    ):
        assert await verifier.verify_token(token) is None
