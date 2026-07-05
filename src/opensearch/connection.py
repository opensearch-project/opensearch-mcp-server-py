# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Custom OpenSearch connection classes with enhanced functionality.

This module provides custom connection classes that extend the standard
OpenSearch connection classes with additional features like response size limiting.
"""

import logging
import time
from opensearchpy import AsyncHttpConnection


# Configure logging
logger = logging.getLogger(__name__)

# Constants
DEFAULT_MAX_RESPONSE_SIZE = None  # No limit by default - only enforce when explicitly set


# Base exception class (to avoid circular imports)
class OpenSearchClientError(Exception):
    """Base exception for OpenSearch client errors."""

    pass


class ResponseSizeExceededError(OpenSearchClientError):
    """Exception raised when response size exceeds the configured limit."""

    pass


def _log_request_event(
    method: str,
    endpoint: str,
    status_code: int | None,
    duration_ms: float,
    status: str,
    response_size: int | None = None,
    error: str | None = None,
) -> None:
    """Emit a structured log event for OpenSearch HTTP requests."""
    log_extra: dict[str, object] = {
        'event_type': 'opensearch_request',
        'http_method': method,
        'endpoint': endpoint,
        'status': status,
        'duration_ms': duration_ms,
    }
    if status_code is not None:
        log_extra['status_code'] = status_code
    if response_size is not None:
        log_extra['response_size'] = response_size
    if error:
        log_extra['error'] = error

    if status == 'success':
        logger.info(
            f'OpenSearch request: {method} {endpoint} -> {status_code} ({duration_ms}ms)',
            extra=log_extra,
        )
    else:
        logger.error(
            f'OpenSearch request failed: {method} {endpoint} -> {status_code} ({duration_ms}ms)',
            extra=log_extra,
        )


class BufferedAsyncHttpConnection(AsyncHttpConnection):
    """Async HTTP connection that buffers responses with size limiting.

    This connection class prevents large responses from being loaded into memory
    by streaming the response and checking size limits during processing. If the
    response exceeds max_response_size, it stops reading and raises an exception
    before the complete response is downloaded.
    """

    def __init__(self, *args, max_response_size=DEFAULT_MAX_RESPONSE_SIZE, **kwargs):
        """Initialize buffered connection with response size limit.

        Args:
            *args: Arguments passed to parent AsyncHttpConnection.
            max_response_size: Maximum allowed response size in bytes (default: None - no limit).
            **kwargs: Keyword arguments passed to parent AsyncHttpConnection.
        """
        super().__init__(*args, **kwargs)
        self.max_response_size = max_response_size
        if max_response_size is not None:
            logger.debug(
                f'Initialized BufferedAsyncHttpConnection with max_response_size={max_response_size} bytes'
            )
        else:
            logger.debug('Initialized BufferedAsyncHttpConnection with no response size limit')

    async def perform_request(
        self, method, url, params=None, body=None, timeout=None, ignore=(), headers=None
    ):
        """Perform HTTP request with response size limiting.

        This implementation leverages the parent class for authentication and session management
        but implements streaming response size checking to prevent memory exhaustion from large responses.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL
            params: Query parameters
            body: Request body
            timeout: Request timeout
            ignore: HTTP status codes to ignore
            headers: Additional headers

        Returns:
            Tuple of (status, headers, response_data)

        Raises:
            ResponseSizeExceededError: If response exceeds max_response_size during streaming
        """
        logger.debug(
            f'Making size-limited request: {method} {url} (max_size={self.max_response_size})'
        )
        original_url = url
        try:
            # Import required modules
            import aiohttp
            import yarl
            from urllib.parse import urlencode

            # Ensure session is created (from parent class)
            if self.session is None:
                await self._create_aiohttp_session()
            assert self.session is not None

            # Build URL and prepare request (following parent class logic)
            orig_body = body
            url_path = self.url_prefix + url
            if params:
                query_string = urlencode(params)
            else:
                query_string = ''

            url = self.url_prefix + url
            if query_string:
                url = f'{url}?{query_string}'
            url = self.host + url

            timeout_obj = aiohttp.ClientTimeout(
                total=timeout if timeout is not None else self.timeout
            )

            # Prepare headers (following parent class logic)
            req_headers = self.headers.copy()
            if headers:
                req_headers.update(headers)

            if self.http_compress and body:
                body = self._gzip_compress(body)
                req_headers['content-encoding'] = 'gzip'

            # Handle authentication (following parent class logic)
            auth = self._http_auth if isinstance(self._http_auth, aiohttp.BasicAuth) else None
            if callable(self._http_auth):
                req_headers = {
                    **req_headers,
                    **self._http_auth(method=method, url=url, body=body, headers=req_headers),
                }

            start = self.loop.time()

            # Make request with streaming response handling
            async with self.session.request(
                method,
                yarl.URL(url, encoded=True),
                data=body,
                auth=auth,
                headers=req_headers,
                timeout=timeout_obj,
                fingerprint=self.ssl_assert_fingerprint,
            ) as response:
                # Stream the response with optional size checking
                chunks = []
                total_size = 0

                async for chunk in response.content.iter_chunked(8192):
                    # Only check size limit if max_response_size is set
                    if (
                        self.max_response_size is not None
                        and total_size + len(chunk) > self.max_response_size
                    ):
                        duration = self.loop.time() - start
                        self.log_request_fail(
                            method,
                            str(url),
                            url_path,
                            orig_body,
                            duration,
                            exception=f'Response size exceeded {self.max_response_size} bytes',
                        )
                        logger.error(
                            f'Response size exceeded limit during streaming: '
                            f'{total_size + len(chunk)} > {self.max_response_size} bytes'
                        )
                        raise ResponseSizeExceededError(
                            f'Response size exceeded limit of {self.max_response_size} bytes. '
                            f'Stopped reading at {total_size} bytes to prevent memory exhaustion. '
                            f'Consider increasing max_response_size or refining your query to return less data.'
                        )

                    chunks.append(chunk)
                    total_size += len(chunk)

                # Combine all chunks and decode
                response_data = b''.join(chunks)
                try:
                    raw_data = response_data.decode('utf-8')
                except UnicodeDecodeError:
                    # For binary data, convert to string representation
                    raw_data = str(response_data)

                duration = self.loop.time() - start

            # Handle warnings (following parent class logic)
            warning_headers = response.headers.getall('warning', ())
            self._raise_warnings(warning_headers)

            # Handle errors (following parent class logic)
            duration_ms = round(duration * 1000, 2)
            if not (200 <= response.status < 300) and response.status not in ignore:
                self.log_request_fail(
                    method,
                    str(url),
                    url_path,
                    orig_body,
                    duration,
                    status_code=response.status,
                    response=raw_data,
                )
                _log_request_event(
                    method,
                    original_url,
                    response.status,
                    duration_ms,
                    'error',
                    response_size=total_size,
                )
                self._raise_error(response.status, raw_data)

            # Log success
            self.log_request_success(
                method, str(url), url_path, orig_body, response.status, raw_data, duration
            )
            _log_request_event(
                method,
                original_url,
                response.status,
                duration_ms,
                'success',
                response_size=total_size,
            )

            return response.status, response.headers, raw_data

        except ResponseSizeExceededError:
            raise
        except Exception as e:
            # For connection errors and other failures, fall back to parent implementation
            logger.warning(
                f'Streaming request failed ({type(e).__name__}: {e}), falling back to parent implementation'
            )
            return await self._fallback_perform_request(
                method, original_url, params, body, timeout, ignore, headers
            )

    async def _fallback_perform_request(
        self, method, url, params=None, body=None, timeout=None, ignore=(), headers=None
    ):
        """Fallback to parent implementation with post-download size checking.

        This is used when streaming is not available or fails.
        """
        fallback_start = time.monotonic()
        try:
            # Use parent implementation for the actual request (preserves auth)
            status, response_headers, response_data = await super().perform_request(
                method, url, params, body, timeout, ignore, headers
            )

            # Check response size after getting the data (only if limit is set)
            if isinstance(response_data, str):
                data_size = len(response_data.encode('utf-8'))
            elif isinstance(response_data, bytes):
                data_size = len(response_data)
            else:
                # Unknown data type, convert to string and measure
                data_size = len(str(response_data).encode('utf-8'))

            if self.max_response_size is not None and data_size > self.max_response_size:
                logger.error(
                    f'Response size exceeded limit: {data_size} > {self.max_response_size} bytes'
                )
                raise ResponseSizeExceededError(
                    f'Response size exceeded limit of {self.max_response_size} bytes. '
                    f'Received {data_size} bytes. '
                    f'Consider increasing max_response_size or refining your query to return less data.'
                )

            fallback_duration_ms = round((time.monotonic() - fallback_start) * 1000, 2)
            _log_request_event(
                method,
                url,
                status,
                fallback_duration_ms,
                'success',
                response_size=data_size,
            )

            return status, response_headers, response_data

        except ResponseSizeExceededError:
            raise
        except Exception as e:
            fallback_duration_ms = round((time.monotonic() - fallback_start) * 1000, 2)
            raw_status = getattr(e, 'status_code', None)
            exc_status_code = raw_status if isinstance(raw_status, int) else None
            _log_request_event(
                method,
                url,
                exc_status_code,
                fallback_duration_ms,
                'error',
                error=str(e),
            )
            raise
