# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import aiohttp
import json
import os
import ssl
import yaml
from .tool_logging import log_tool_error
from .tool_params import baseToolArgs
from .tools import TOOL_REGISTRY, check_tool_compatibility
from mcp.types import TextContent
from pydantic import BaseModel, create_model
from typing import Any, Dict, List


# Constants
BASE_URL = 'https://raw.githubusercontent.com/opensearch-project/opensearch-api-specification/refs/heads/main/spec/namespaces'
SPEC_FILES = ['cluster.yaml', '_core.yaml']
SUPPORTED_OPERATIONS = ['msearch', 'explain', 'count', 'cluster.health']

BODY_DESCRIPTIONS = {
    'msearch': 'Request body as NDJSON format: alternating lines of header and query objects ending with \\n. Alternatively, pass a JSON array [header, query, header, query, ...] and the tool will convert it to NDJSON for you.',
    'explain': 'Request body containing the query to explain.',
}


async def fetch_github_spec(file_name: str) -> Dict:
    """Fetch OpenSearch API specification from GitHub asynchronously."""
    # Use environment variable to control SSL verification
    verify_ssl = os.getenv('OPENSEARCH_SSL_VERIFY', 'true').lower() != 'false'

    url = f'{BASE_URL}/{file_name}'

    # Create SSL context based on verification setting
    if verify_ssl:
        ssl_context = ssl.create_default_context()
    else:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

    # Create connector with SSL context
    connector = aiohttp.TCPConnector(ssl=ssl_context)

    async with aiohttp.ClientSession(connector=connector) as session:
        async with session.get(url) as response:
            # Raise exception for HTTP errors
            response.raise_for_status()
            # Parse YAML into Python dict
            return yaml.safe_load(await response.text())


def group_endpoints_by_operation(paths: Dict[str, Dict]) -> Dict[str, List[Dict]]:
    """Group endpoints by their x-operation-group."""
    grouped_ops = {}
    for path, methods in paths.items():
        for method, details in methods.items():
            op_group = details.get('x-operation-group')
            # TODO: Remove hard-coded logic once we have the tool filtering feature
            if op_group in SUPPORTED_OPERATIONS:
                grouped_ops.setdefault(op_group, []).append(
                    {'path': path, 'method': method, 'details': details}
                )
    return grouped_ops


def extract_parameters(endpoints: list[dict]) -> tuple[dict[str, dict], set, set]:
    """Extract parameters from endpoints."""
    # Add baseToolArgs to all tools, will be filtered out later in single mode
    base_schema = baseToolArgs.model_json_schema()
    all_parameters = base_schema.get('properties', {})
    path_parameters = set()
    required_parameters = set()

    # Track which path parameters appear in which endpoints
    param_to_endpoints = {}

    # Extract parameters from endpoints
    for i, endpoint in enumerate(endpoints):
        path = endpoint['path']
        details = endpoint['details']

        # Extract path parameters (parameters in the URL path like {index})
        for part in path.split('/'):
            if part.startswith('{') and part.endswith('}'):
                param_name = part[1:-1]
                path_parameters.add(param_name)
                all_parameters[param_name] = {
                    'title': param_name.title(),
                    'type': 'string',
                }
                param_to_endpoints.setdefault(param_name, set()).add(i)

        # Add parameters from the endpoint details
        for param in details.get('parameters', []):
            param_name = param.get('name')
            if param_name and param_name not in all_parameters:
                param_schema = param.get('schema', {})
                all_parameters[param_name] = {
                    'title': param_name.title(),
                    'type': param_schema.get('type', 'string'),
                    'description': param.get('description', ''),
                }
                # Check if the parameter is required according to the OpenAPI spec
                if param.get('required', False):
                    required_parameters.add(param_name)

        op_group = endpoints[0]['details'].get('x-operation-group', '')
        # Add body parameter if needed
        if 'requestBody' in details:
            all_parameters['body'] = {
                'title': 'Body',
                'description': BODY_DESCRIPTIONS.get(op_group, 'Request body'),
            }

    # Mark path parameters as required only if they appear in all endpoints
    for param, endpoint_indices in param_to_endpoints.items():
        if len(endpoint_indices) == len(endpoints):
            required_parameters.add(param)

    # Mark body as required for ExplainTool and MsearchTool
    # TODO: Remove hard-coded logic once we found a better way to determine required request body
    if op_group in ['explain', 'msearch'] and 'body' in all_parameters:
        required_parameters.add('body')

    return all_parameters, path_parameters, required_parameters


def process_body(body: Any, tool_name: str) -> Any:
    """Process request body based on tool type and format.

    Args:
        body: The request body to process
        tool_name: Name of the tool (e.g., 'MsearchTool')

    Returns:
        Processed body in the appropriate format for the tool
    """
    if body is None:
        return None

    # Handle string body
    if isinstance(body, str):
        # Multi search tool (msearch) requires request body to be in NDJSON format
        if tool_name == 'MsearchTool':
            try:
                # Check if it's a JSON array string
                parsed = json.loads(body)
                if isinstance(parsed, list):
                    # Convert JSON array to NDJSON format
                    return ''.join(json.dumps(item) + '\n' for item in parsed)
            except json.JSONDecodeError:
                pass  # Fall through to treat as NDJSON
            # Treat as NDJSON string - ensure it ends with newline
            return body if body.endswith('\n') else body + '\n'

        # For other tools, parse JSON string to object
        if body.strip():
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                raise ValueError(f'Invalid JSON in body parameter: {str(body)[:100]}...')
        return None

    # Handle non-string body (list, dict, etc.)
    if isinstance(body, list) and tool_name == 'MsearchTool':
        # Direct JSON array (from MCP tools)
        return ''.join(json.dumps(item) + '\n' for item in body)

    return body


def select_endpoint(endpoints: list[dict], params: dict) -> dict:
    """Select the most appropriate endpoint based on parameters."""
    # Filter out empty or None values from params
    valid_params = {k: v for k, v in params.items() if v not in (None, '', {}, [])}

    # Sort endpoints by number of path parameters that have valid values
    sorted_endpoints = sorted(
        endpoints,
        key=lambda ep: sum(
            1
            for p in ep['path'].split('/')
            if p.startswith('{') and p.endswith('}') and p[1:-1] in valid_params
        ),
        reverse=True,
    )

    # Return the first endpoint where all required path parameters have valid values
    for endpoint in sorted_endpoints:
        path_params = [
            p[1:-1] for p in endpoint['path'].split('/') if p.startswith('{') and p.endswith('}')
        ]
        if all(param in valid_params for param in path_params):
            return endpoint

    # Fall back to simplest endpoint or first endpoint
    return next(
        (ep for ep in endpoints if not any('{' in p for p in ep['path'].split('/'))), endpoints[0]
    )


def generate_tool_from_group(base_name: str, endpoints: List[Dict]) -> Dict[str, Any]:
    """Generate a single tool from a group of related endpoints."""
    # Use the description from the first endpoint in the group
    details = endpoints[0]['details']
    description = details.get('description', '')

    # Extract version information
    min_version = details.get('x-version-added', '0.0.0')
    max_version = details.get('x-version-deprecated', '99.99.99')

    # Get the HTTP method(s) used by the endpoints
    methods = {endpoint['method'].upper() for endpoint in endpoints}
    http_methods = ', '.join(sorted(methods))

    all_parameters, path_parameters, required_parameters = extract_parameters(endpoints)
    # Create Pydantic model for arguments
    field_definitions = {
        name: (Any if name == 'body' else str, info.get('default'))
        for name, info in all_parameters.items()
    }
    args_model = create_model(f'{base_name}Args', __base__=baseToolArgs, **field_definitions)

    # Create the tool function that will execute the OpenSearch API
    async def tool_func(params: BaseModel) -> list[TextContent]:
        tool_name = f'{base_name.replace("_", "")}Tool'
        try:
            from opensearch.client import get_opensearch_client

            params_dict = params.model_dump() if hasattr(params, 'model_dump') else {}

            try:
                # Extract all baseToolArgs fields from params_dict
                base_args = {}
                base_fields = baseToolArgs.model_fields.keys()
                for field in base_fields:
                    if field in params_dict:
                        base_args[field] = params_dict.pop(field)
                    else:
                        # Provide default empty string for required fields in single mode
                        base_args[field] = ''

                args = baseToolArgs(**base_args)
            except Exception as e:
                return log_tool_error(tool_name, e, 'initializing OpenSearch client')

            # Use context manager to ensure proper client cleanup
            async with get_opensearch_client(args) as request_client:
                await check_tool_compatibility(tool_name, args)
                # Process body and select endpoint
                body = process_body(params_dict.pop('body', None), tool_name)
                selected_endpoint = select_endpoint(endpoints, params_dict)

                # Prepare request
                formatted_path = selected_endpoint['path']
                for param_name in path_parameters:
                    if param_name in params_dict:
                        formatted_path = formatted_path.replace(
                            f'{{{param_name}}}', str(params_dict[param_name])
                        )
                        del params_dict[param_name]
                method = selected_endpoint['method'].upper()  # HTTP method (GET, POST, etc.)
                api_path = f'/{formatted_path.lstrip("/")}'  # Ensure path starts with /

                # Execute the OpenSearch API request
                response = await request_client.transport.perform_request(
                    method=method, url=api_path, params=params_dict, body=body
                )

                return [
                    TextContent(
                        type='text',
                        text=json.dumps(response) if not isinstance(response, str) else response,
                    )
                ]

        except Exception as e:
            return log_tool_error(tool_name, e, f'executing {tool_name}')

    # Create input schema with required fields
    input_schema = {'type': 'object', 'title': f'{base_name}Args', 'properties': all_parameters}

    # Add required fields
    required_fields = list(required_parameters)
    if required_fields:
        input_schema['required'] = required_fields

    return {
        'display_name': f'{base_name}Tool',
        'description': description,
        'input_schema': input_schema,
        'function': tool_func,
        'args_model': args_model,
        'min_version': min_version,
        'max_version': max_version,
        'http_methods': http_methods,
    }


async def generate_tools_from_openapi() -> Dict[str, Dict[str, Any]]:
    """Generate tools from OpenSearch API specification and append to TOOL_REGISTRY."""
    try:
        for spec_file in SPEC_FILES:
            spec = await fetch_github_spec(spec_file)
            grouped_ops = group_endpoints_by_operation(spec.get('paths', {}))
            # Generate tools for each operation group
            for group_name, endpoints in grouped_ops.items():
                base_name = ''.join(part.title() for part in group_name.split('.'))
                tool_name = f'{base_name.replace("_", "")}Tool'
                TOOL_REGISTRY[tool_name] = generate_tool_from_group(base_name, endpoints)

    except Exception as e:
        print(f'Error generating tools: {e}')

    return TOOL_REGISTRY
