# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import json
import logging
import os
from typing import Any, Dict, Optional
from urllib.parse import urlencode

from .tool_logging import log_tool_error
from .utils import format_json
from .tool_params import baseToolArgs
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class GenericOpenSearchApiArgs(baseToolArgs):
    """Arguments for the generic OpenSearch API tool."""

    path: str = Field(
        description='The API endpoint path (e.g., "/_search", "/_cat/indices", "/my_index/_doc/1"). Should start with "/".'
    )
    method: str = Field(
        default='GET', description='HTTP method to use (GET, POST, PUT, DELETE, HEAD, PATCH)'
    )
    query_params: Optional[Dict[str, Any]] = Field(
        default=None,
        description='Query parameters to include in the request URL as key-value pairs',
    )
    body: Optional[Any] = Field(
        default=None,
        description='Request body for GET/POST/PUT requests. Can be a JSON object, string, or None',
    )
    headers: Optional[Dict[str, str]] = Field(
        default=None, description='Additional HTTP headers to include in the request'
    )

    class Config:
        json_schema_extra = {
            'examples': [
                {'path': '/_search', 'method': 'GET', 'query_params': {'size': 10, 'from': 0}},
                {
                    'path': '/_cat/indices',
                    'method': 'GET',
                    'query_params': {'format': 'json', 'v': True},
                },
                {
                    'path': '/my_index/_doc',
                    'method': 'POST',
                    'body': {'title': 'Test Document', 'content': 'This is a test'},
                },
                {
                    'path': '/my_index/_search',
                    'method': 'POST',
                    'body': {'query': {'match': {'title': 'search term'}}},
                },
                {'path': '/_cluster/health', 'method': 'GET'},
            ]
        }


async def generic_opensearch_api_tool(args: GenericOpenSearchApiArgs) -> list[dict]:
    """Generic OpenSearch API tool that can call any OpenSearch endpoint.

    This tool provides a flexible interface to interact with any OpenSearch API endpoint.
    It leverages the LLM's knowledge of OpenSearch APIs to construct appropriate requests.

    Use this tool when you need to:
    - Call OpenSearch APIs that don't have dedicated tools
    - Perform complex API operations with custom parameters
    - Access newer OpenSearch features not yet covered by specific tools
    - Combine multiple API calls in a workflow

    The tool supports all HTTP methods and can handle query parameters, request bodies,
    and custom headers. It uses the same authentication and connection logic as other tools.

    Write operations (POST, PUT, DELETE, PATCH) are only allowed when write
    operations are enabled via configuration.

    Args:
        args: GenericOpenSearchApiArgs containing the API request details

    Returns:
        list[dict]: API response in MCP format
    """
    try:
        # Validate method
        valid_methods = ['GET', 'POST', 'PUT', 'DELETE', 'HEAD', 'PATCH']
        method = args.method.upper()
        if method not in valid_methods:
            return log_tool_error(
                'GenericOpenSearchApiTool',
                ValueError(
                    f'Invalid HTTP method "{args.method}". Valid methods are: {", ".join(valid_methods)}'
                ),
                'validating request',
            )

        # Check if write operations are allowed using the global setting
        # Import here to avoid circular import (tool_filter -> tools -> generic_api_tool -> tool_filter)
        from .tool_filter import get_allow_write_setting

        allow_write = get_allow_write_setting()
        write_methods = ['POST', 'PUT', 'DELETE', 'PATCH']

        if method in write_methods and not allow_write:
            return log_tool_error(
                'GenericOpenSearchApiTool',
                PermissionError(
                    f'Write operations are disabled. Method "{method}" is not allowed.'
                ),
                'validating request',
            )

        # Validate path
        if not args.path.startswith('/'):
            return log_tool_error(
                'GenericOpenSearchApiTool',
                ValueError('API path must start with "/"'),
                'validating request',
            )

        # Initialize OpenSearch client with context manager for proper cleanup
        from opensearch.client import get_opensearch_client

        async with get_opensearch_client(args) as client:
            # Build the request URL
            url = args.path
            if args.query_params:
                # Convert query parameters to URL-encoded string
                query_string = urlencode(args.query_params)
                url = f'{args.path}?{query_string}'

            # Prepare request parameters
            request_params = {'method': method, 'url': url}

            # Add body for methods that support it
            if args.body is not None and method in ['POST', 'PUT', 'PATCH']:
                if isinstance(args.body, (dict, list)):
                    request_params['body'] = json.dumps(args.body)
                else:
                    request_params['body'] = args.body

            # Add custom headers if provided
            if args.headers:
                request_params['headers'] = args.headers

            # Make the API request using the transport layer
            logger.info(f'Making {method} request to {url}')
            response = await client.transport.perform_request(**request_params)

            # Format the response
            if isinstance(response, str):
                # Some APIs return plain text (like hot_threads)
                formatted_response = response
            else:
                # Most APIs return JSON
                formatted_response = format_json(response)

            # Create descriptive message
            message = f'OpenSearch API Response ({method} {args.path})'
            if args.query_params:
                message += f' with query params: {args.query_params}'

            return [{'type': 'text', 'text': f'{message}:\n{formatted_response}'}]

    except Exception as e:
        return log_tool_error(
            'GenericOpenSearchApiTool',
            e,
            f'calling OpenSearch API ({args.method} {args.path})',
            method=args.method,
            path=args.path,
        )
