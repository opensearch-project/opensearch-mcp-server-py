# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""OpenSearch client caching for connection pooling and performance.

This module provides a global cache for OpenSearch clients to enable connection
reuse across multiple requests, significantly improving performance by avoiding
repeated SSL handshakes and connection establishment.
"""

import asyncio
import hashlib
import json
import logging
import os
from opensearchpy import AsyncOpenSearch
from typing import Dict, Optional


logger = logging.getLogger(__name__)

# Global client cache
_client_cache: Dict[str, AsyncOpenSearch] = {}
_cache_lock: Optional[asyncio.Lock] = None


def _is_caching_enabled() -> bool:
    """Check if client caching is enabled.

    Returns False if OPENSEARCH_DISABLE_CLIENT_CACHE environment variable is set.
    This is checked dynamically to support runtime configuration (e.g., in tests).
    """
    return os.environ.get('OPENSEARCH_DISABLE_CLIENT_CACHE', '').lower() not in (
        '1',
        'true',
        'yes',
    )


def _get_cache_lock() -> asyncio.Lock:
    """Get or create the cache lock for the current event loop.

    This ensures the lock is always tied to the active event loop,
    avoiding issues with closed loops in testing scenarios.
    """
    global _cache_lock
    try:
        # Check if we have a lock and it's still valid for the current loop
        if _cache_lock is not None:
            # Get the current event loop
            try:
                current_loop = asyncio.get_running_loop()
            except RuntimeError:
                # No running loop, try to get the default
                current_loop = asyncio.get_event_loop_policy().get_event_loop()

            # Check if the lock's loop matches the current loop and isn't closed
            if hasattr(_cache_lock, '_loop') and _cache_lock._loop == current_loop:
                if not current_loop.is_closed():
                    return _cache_lock
    except (AttributeError, RuntimeError):
        pass

    # Create new lock for current event loop
    _cache_lock = asyncio.Lock()
    return _cache_lock


def _generate_cache_key(
    opensearch_url: str,
    opensearch_username: str = '',
    opensearch_password: str = '',
    opensearch_no_auth: bool = False,
    iam_arn: str = '',
    profile: str = '',
    is_serverless_mode: bool = False,
    aws_region: Optional[str] = None,
    ssl_verify: bool = True,
    opensearch_ca_cert_path: Optional[str] = None,
    opensearch_client_cert_path: Optional[str] = None,
    opensearch_client_key_path: Optional[str] = None,
) -> str:
    """Generate a cache key for OpenSearch client configuration.

    The key is a hash of all configuration parameters that affect connection identity.
    Password is included in the hash but not logged for security.
    """
    config = {
        'url': opensearch_url,
        'username': opensearch_username,
        # Password affects connection but is hashed, not stored
        'password_hash': hashlib.sha256(opensearch_password.encode()).hexdigest()
        if opensearch_password
        else '',
        'no_auth': opensearch_no_auth,
        'iam_arn': iam_arn,
        'profile': profile,
        'serverless': is_serverless_mode,
        'region': aws_region or '',
        'ssl_verify': ssl_verify,
        'ca_cert': opensearch_ca_cert_path or '',
        'client_cert': opensearch_client_cert_path or '',
        'client_key': opensearch_client_key_path or '',
    }

    config_json = json.dumps(config, sort_keys=True)
    cache_key = hashlib.sha256(config_json.encode()).hexdigest()[:16]

    logger.debug(f'Generated cache key {cache_key} for OpenSearch URL: {opensearch_url}')
    return cache_key


async def get_cached_client(cache_key: str) -> Optional[AsyncOpenSearch]:
    """Get a cached OpenSearch client if available.

    Args:
        cache_key: The cache key for the client configuration

    Returns:
        Cached AsyncOpenSearch client or None if not found
    """
    if not _is_caching_enabled():
        return None

    async with _get_cache_lock():
        client = _client_cache.get(cache_key)
        if client:
            logger.debug(f'Cache hit for client {cache_key}')
        else:
            logger.debug(f'Cache miss for client {cache_key}')
        return client


async def cache_client(cache_key: str, client: AsyncOpenSearch) -> None:
    """Cache an OpenSearch client for reuse.

    Args:
        cache_key: The cache key for the client configuration
        client: The AsyncOpenSearch client to cache
    """
    if not _is_caching_enabled():
        return

    async with _get_cache_lock():
        _client_cache[cache_key] = client
        logger.info(f'Cached OpenSearch client {cache_key} (total cached: {len(_client_cache)})')


async def close_all_clients() -> None:
    """Close all cached OpenSearch clients.

    This should be called during server shutdown to ensure proper cleanup.
    """
    async with _get_cache_lock():
        logger.info(f'Closing {len(_client_cache)} cached OpenSearch clients')
        for cache_key, client in _client_cache.items():
            try:
                await client.close()
                logger.debug(f'Closed cached client {cache_key}')
            except Exception as e:
                logger.warning(f'Error closing cached client {cache_key}: {e}')
        _client_cache.clear()
        logger.info('All cached clients closed')


async def get_cache_stats() -> Dict[str, int]:
    """Get statistics about the client cache.

    Returns:
        Dictionary with cache statistics
    """
    async with _get_cache_lock():
        return {
            'cached_clients': len(_client_cache),
        }
