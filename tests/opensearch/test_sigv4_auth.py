# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for SigV4 auth callable invocation in BufferedAsyncHttpConnection."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from multidict import CIMultiDict

from opensearch.connection import BufferedAsyncHttpConnection


class AsyncIterChunks:
    """Helper to simulate async iteration over response chunks."""

    def __init__(self, chunks):
        self._chunks = chunks
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._chunks):
            raise StopAsyncIteration
        chunk = self._chunks[self._index]
        self._index += 1
        return chunk


def _make_connection_with_mock_auth():
    """Create a BufferedAsyncHttpConnection with a mocked auth callable and session."""
    connection = BufferedAsyncHttpConnection(host='localhost', port=9200, use_ssl=False)

    auth_mock = MagicMock(return_value={'Authorization': 'AWS4-HMAC-SHA256 ...'})
    connection._http_auth = auth_mock

    mock_response = AsyncMock()
    mock_response.status = 200
    mock_response.headers = CIMultiDict({'content-type': 'application/json'})
    mock_response.content.iter_chunked = lambda _: AsyncIterChunks([b'{"ok":true}'])
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.request = MagicMock(return_value=mock_response)
    connection.session = mock_session
    connection.loop = MagicMock()
    connection.loop.time = MagicMock(return_value=0.0)

    return connection, auth_mock


class TestSigV4AuthCallable:
    """Verify that the auth callable receives correct arguments.

    Regression tests for a bug where query_string was passed as body and
    body was passed as headers due to incorrect positional argument ordering.
    """

    @pytest.mark.asyncio
    async def test_get_with_params_does_not_pass_query_string_as_body(self):
        """Auth callable body must be None for GET, not the query string.

        Previously: self._http_auth(method, url, query_string, body)
        mapped query_string='format=json' to body param, causing wrong payload hash → 403.
        """
        connection, auth_mock = _make_connection_with_mock_auth()

        await connection.perform_request('GET', '/_cat/indices', params={'format': 'json'})

        auth_mock.assert_called_once()
        kwargs = auth_mock.call_args.kwargs
        assert kwargs.get('body') is None, \
            'GET request body must be None, not the query string'

    @pytest.mark.asyncio
    async def test_post_does_not_pass_body_as_headers(self):
        """Auth callable headers must be a dict, not the request body bytes.

        Previously: self._http_auth(method, url, query_string, body)
        mapped body=b'{...}' to headers param, causing AttributeError crash.
        """
        connection, auth_mock = _make_connection_with_mock_auth()

        body = b'{"query":{"match_all":{}}}'
        await connection.perform_request('POST', '/_search', body=body)

        auth_mock.assert_called_once()
        kwargs = auth_mock.call_args.kwargs
        assert kwargs.get('body') == body, \
            'POST request body must be passed as body to auth callable'
        assert isinstance(kwargs.get('headers'), dict), \
            'headers param must be a dict, not request body bytes'

    @pytest.mark.asyncio
    async def test_auth_callable_uses_keyword_arguments(self):
        """Auth callable must be invoked with keyword arguments, not positional."""
        connection, auth_mock = _make_connection_with_mock_auth()

        await connection.perform_request('GET', '/test', params={'x': '1'})

        auth_mock.assert_called_once()
        # Should be called with keyword args (no positional args beyond self)
        assert auth_mock.call_args.kwargs, \
            'Auth callable must be invoked with keyword arguments'
