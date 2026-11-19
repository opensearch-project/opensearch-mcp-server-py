#!/usr/bin/env python3
"""Simple test script for the GenericOpenSearchApiTool."""

import asyncio
import os
import pytest
import sys


# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from tools.generic_api_tool import GenericOpenSearchApiArgs, generic_opensearch_api_tool


@pytest.mark.asyncio
async def test_generic_tool():
    """Test the generic OpenSearch API tool with a simple cluster health check."""
    # Test 1: Simple cluster health check
    print('Test 1: Cluster Health Check')
    args = GenericOpenSearchApiArgs(
        opensearch_cluster_name='',  # Use default/environment config
        path='/_cluster/health',
        method='GET',
    )

    try:
        result = await generic_opensearch_api_tool(args)
        print(
            'Result:',
            result[0]['text'][:200] + '...' if len(result[0]['text']) > 200 else result[0]['text'],
        )
        print('✓ Test 1 passed\n')
    except Exception as e:
        print(f'✗ Test 1 failed: {e}\n')

    # Test 2: List indices with query parameters
    print('Test 2: List Indices with Query Parameters')
    args = GenericOpenSearchApiArgs(
        opensearch_cluster_name='',
        path='/_cat/indices',
        method='GET',
        query_params={'format': 'json', 'v': True},
    )

    try:
        result = await generic_opensearch_api_tool(args)
        print(
            'Result:',
            result[0]['text'][:200] + '...' if len(result[0]['text']) > 200 else result[0]['text'],
        )
        print('✓ Test 2 passed\n')
    except Exception as e:
        print(f'✗ Test 2 failed: {e}\n')

    # Test 3: Search with POST body
    print('Test 3: Search with POST Body')
    args = GenericOpenSearchApiArgs(
        opensearch_cluster_name='',
        path='/_search',
        method='POST',
        body={'query': {'match_all': {}}, 'size': 5},
    )

    try:
        result = await generic_opensearch_api_tool(args)
        print(
            'Result:',
            result[0]['text'][:200] + '...' if len(result[0]['text']) > 200 else result[0]['text'],
        )
        print('✓ Test 3 passed\n')
    except Exception as e:
        print(f'✗ Test 3 failed: {e}\n')

    # Test 4: Write protection test
    print('Test 4: Write Protection Test')
    # Temporarily disable write operations
    original_allow_write = os.environ.get('OPENSEARCH_SETTINGS_ALLOW_WRITE', 'true')
    os.environ['OPENSEARCH_SETTINGS_ALLOW_WRITE'] = 'false'

    args = GenericOpenSearchApiArgs(
        opensearch_cluster_name='',
        path='/test_index/_doc/1',
        method='PUT',
        body={'test': 'document'},
    )

    try:
        result = await generic_opensearch_api_tool(args)
        if 'Write operations are disabled' in result[0]['text']:
            print('✓ Test 4 passed - Write operations correctly blocked')
        else:
            print('✗ Test 4 failed - Write operations should be blocked')
    except Exception as e:
        print(f'✗ Test 4 failed: {e}')
    finally:
        # Restore original setting
        os.environ['OPENSEARCH_SETTINGS_ALLOW_WRITE'] = original_allow_write
        print()


@pytest.mark.asyncio
async def test_write_disabled_message_does_not_leak_config():
    """Test that the write-disabled error message does not expose config settings."""
    from tools.tool_filter import set_allow_write_setting

    original_allow_write = os.environ.get('OPENSEARCH_SETTINGS_ALLOW_WRITE', 'true')
    os.environ['OPENSEARCH_SETTINGS_ALLOW_WRITE'] = 'false'
    set_allow_write_setting(False)

    try:
        for method in ['PUT', 'POST', 'DELETE', 'PATCH']:
            args = GenericOpenSearchApiArgs(
                opensearch_cluster_name='',
                path='/test_index/_doc/1',
                method=method,
            )
            result = await generic_opensearch_api_tool(args)
            error_text = result[0]['text']

            assert 'Write operations are disabled' in error_text, (
                f'Expected write-disabled message for {method}'
            )
            assert 'OPENSEARCH_SETTINGS_ALLOW_WRITE' not in error_text, (
                f'Error message for {method} should not expose env var name'
            )
            assert 'allow_write' not in error_text, (
                f'Error message for {method} should not expose config setting name'
            )
    finally:
        os.environ['OPENSEARCH_SETTINGS_ALLOW_WRITE'] = original_allow_write
        set_allow_write_setting(None)


@pytest.mark.asyncio
async def test_boolean_query_params_are_sent_lowercase():
    """OpenSearch rejects "True"/"False"; booleans must be encoded as "true"/"false"."""
    from unittest.mock import AsyncMock, patch
    from urllib.parse import parse_qs, urlparse

    mock_client = AsyncMock()
    mock_client.transport.perform_request = AsyncMock(return_value={'status': 'green'})
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    args = GenericOpenSearchApiArgs(
        opensearch_cluster_name='',
        path='/_cat/indices',
        method='GET',
        query_params={'format': 'json', 'v': True, 'local': False, 'size': 10},
    )

    with patch('opensearch.client.get_opensearch_client', return_value=mock_client):
        await generic_opensearch_api_tool(args)

    url = mock_client.transport.perform_request.call_args.kwargs['url']
    params = parse_qs(urlparse(url).query)
    assert params == {'format': ['json'], 'v': ['true'], 'local': ['false'], 'size': ['10']}


@pytest.mark.asyncio
@pytest.mark.parametrize('method', ['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
async def test_body_is_sent_for_methods_that_accept_one(method):
    """A request body must reach the transport for every method except HEAD.

    GET /index/_search with a body is valid; dropping it silently turns the search
    into a match_all.
    """
    import json
    from unittest.mock import AsyncMock, patch

    mock_client = AsyncMock()
    mock_client.transport.perform_request = AsyncMock(return_value={})
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    body = {'query': {'match': {'title': 'x'}}}
    args = GenericOpenSearchApiArgs(
        opensearch_cluster_name='', path='/idx/_search', method=method, body=body
    )

    with (
        patch('opensearch.client.get_opensearch_client', return_value=mock_client),
        patch('tools.tool_filter.get_allow_write_setting', return_value=True),
    ):
        await generic_opensearch_api_tool(args)

    sent = mock_client.transport.perform_request.call_args.kwargs
    assert json.loads(sent['body']) == body


@pytest.mark.asyncio
async def test_body_is_not_sent_for_head():
    """HEAD responses and requests carry no body."""
    from unittest.mock import AsyncMock, patch

    mock_client = AsyncMock()
    mock_client.transport.perform_request = AsyncMock(return_value={})
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    args = GenericOpenSearchApiArgs(
        opensearch_cluster_name='', path='/idx', method='HEAD', body={'a': 1}
    )

    with patch('opensearch.client.get_opensearch_client', return_value=mock_client):
        await generic_opensearch_api_tool(args)

    assert 'body' not in mock_client.transport.perform_request.call_args.kwargs


if __name__ == '__main__':
    print('Testing GenericOpenSearchApiTool...')
    print('Note: This test requires a running OpenSearch instance and proper configuration.')
    print('Set OPENSEARCH_URL and authentication environment variables as needed.\n')

    asyncio.run(test_generic_tool())
