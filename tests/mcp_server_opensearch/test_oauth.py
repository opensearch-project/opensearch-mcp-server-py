# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import jwt
import pytest
from mcp_server_opensearch.oauth import JwtTokenVerifier, OAuthConfig, load_oauth_config
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
        assert config.audience is None

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
            options={'verify_aud': True},
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
