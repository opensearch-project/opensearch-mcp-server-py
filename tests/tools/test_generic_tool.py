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


def test_filter_caller_headers_allowlist():
    """Only benign headers survive. Privilege-bearing headers are dropped."""
    from tools.generic_api_tool import _filter_caller_headers

    supplied = {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'X-Opaque-Id': 'trace-1',
        'Authorization': 'Bearer attacker-token',
        'es-security-runas-user': 'admin',
        'X-Amz-Security-Token': 'stolen',
    }
    filtered = _filter_caller_headers(supplied)

    assert set(filtered) == {'Content-Type', 'Accept', 'X-Opaque-Id'}
    assert 'Authorization' not in filtered
    assert 'es-security-runas-user' not in filtered
    assert 'X-Amz-Security-Token' not in filtered


@pytest.mark.asyncio
async def test_privileged_headers_never_reach_the_request(caplog):
    """The filter is not just a helper: the outgoing request must carry only safe headers."""
    import logging
    from unittest.mock import AsyncMock, patch

    mock_client = AsyncMock()
    mock_client.transport.perform_request.return_value = {'status': 'green'}
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    args = GenericOpenSearchApiArgs(
        opensearch_cluster_name='',
        path='/_cluster/health',
        method='GET',
        headers={
            'Content-Type': 'application/json',
            'Authorization': 'Basic YWRtaW46YWRtaW4=',
            'es-security-runas-user': 'admin',
            'X-Amz-Security-Token': 'stolen',
        },
    )

    with (
        caplog.at_level(logging.WARNING),
        patch('opensearch.client.get_opensearch_client', return_value=mock_client),
    ):
        result = await generic_opensearch_api_tool(args)

    assert not result[0].get('is_error'), result[0]['text']
    sent = mock_client.transport.perform_request.call_args.kwargs['headers']
    assert sent == {'Content-Type': 'application/json'}

    warnings = '\n'.join(r.message for r in caplog.records if r.levelno == logging.WARNING)
    assert 'Dropped disallowed request header(s)' in warnings
    for dropped in ('Authorization', 'es-security-runas-user', 'X-Amz-Security-Token'):
        assert dropped in warnings


@pytest.mark.asyncio
async def test_no_headers_sent_when_all_are_disallowed():
    """Dropping every header must send none, not fall back to the caller's set."""
    from unittest.mock import AsyncMock, patch

    mock_client = AsyncMock()
    mock_client.transport.perform_request.return_value = {'status': 'green'}
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    args = GenericOpenSearchApiArgs(
        opensearch_cluster_name='',
        path='/_cluster/health',
        method='GET',
        headers={'Authorization': 'Bearer attacker-token'},
    )

    with patch('opensearch.client.get_opensearch_client', return_value=mock_client):
        await generic_opensearch_api_tool(args)

    assert 'headers' not in mock_client.transport.perform_request.call_args.kwargs


if __name__ == '__main__':
    print('Testing GenericOpenSearchApiTool...')
    print('Note: This test requires a running OpenSearch instance and proper configuration.')
    print('Set OPENSEARCH_URL and authentication environment variables as needed.\n')

    asyncio.run(test_generic_tool())
