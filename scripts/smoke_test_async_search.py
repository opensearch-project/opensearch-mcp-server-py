#!/usr/bin/env python3
# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import argparse
import asyncio
import json
import sys
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from typing import Any


ASYNC_TOOL_NAMES = (
    'SubmitAsyncSearchTool',
    'GetAsyncSearchTool',
    'DeleteAsyncSearchTool',
)
GENERIC_TOOL_NAME = 'GenericOpenSearchApiTool'


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the smoke test."""
    parser = argparse.ArgumentParser(
        description='Smoke test the Async Search MCP tools against a running local MCP server.'
    )
    parser.add_argument(
        '--server-url',
        default='http://localhost:9900/mcp',
        help='Streamable HTTP MCP endpoint. Default: http://localhost:9900/mcp',
    )
    parser.add_argument(
        '--index',
        help='Target index name or pattern for SubmitAsyncSearchTool.',
    )
    parser.add_argument(
        '--query',
        default='{"query":{"match_all":{}}}',
        help='Query DSL as a JSON string. Default: {"query":{"match_all":{}}}',
    )
    parser.add_argument(
        '--cluster-name',
        default='',
        help='OpenSearch cluster name to include when the MCP server is running in multi mode.',
    )
    parser.add_argument(
        '--wait-for-completion-timeout',
        default='1s',
        help='Value for wait_for_completion_timeout on SubmitAsyncSearchTool.',
    )
    parser.add_argument(
        '--keep-alive',
        default='5m',
        help='Value for keep_alive on SubmitAsyncSearchTool.',
    )
    parser.add_argument(
        '--size',
        type=int,
        default=10,
        help='Result size for SubmitAsyncSearchTool. Default: 10',
    )
    parser.add_argument(
        '--skip-delete',
        action='store_true',
        help='Do not call DeleteAsyncSearchTool after the smoke test.',
    )
    parser.add_argument(
        '--list-only',
        action='store_true',
        help='Only connect and list the available tool names.',
    )
    parser.add_argument(
        '--generic-path',
        help='If provided, call GenericOpenSearchApiTool with this API path before the async-search flow.',
    )
    parser.add_argument(
        '--generic-method',
        default='GET',
        help='HTTP method for GenericOpenSearchApiTool. Default: GET',
    )
    parser.add_argument(
        '--generic-body',
        help='Optional body for GenericOpenSearchApiTool. Accepts JSON or raw text.',
    )
    parser.add_argument(
        '--generic-query-params',
        help='Optional query params for GenericOpenSearchApiTool as a JSON object string.',
    )
    parser.add_argument(
        '--generic-headers',
        help='Optional headers for GenericOpenSearchApiTool as a JSON object string.',
    )
    parser.add_argument(
        '--generic-only',
        action='store_true',
        help='Run only GenericOpenSearchApiTool and skip the async-search flow.',
    )
    return parser.parse_args()


def parse_query(query_text: str) -> dict[str, Any]:
    """Parse the query JSON string into a dict."""
    try:
        query = json.loads(query_text)
    except json.JSONDecodeError as exc:
        raise SystemExit(f'Invalid --query JSON: {exc}') from exc
    if not isinstance(query, dict):
        raise SystemExit('--query must decode to a JSON object')
    return query


def parse_optional_json_object(text: str | None, arg_name: str) -> dict[str, Any] | None:
    """Parse an optional JSON object argument."""
    if text is None:
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SystemExit(f'Invalid {arg_name} JSON: {exc}') from exc
    if not isinstance(value, dict):
        raise SystemExit(f'{arg_name} must decode to a JSON object')
    return value


def parse_optional_json_or_text(text: str | None, arg_name: str) -> Any:
    """Parse JSON when possible, otherwise keep the original text."""
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def build_tool_args(base_args: dict[str, Any], cluster_name: str) -> dict[str, Any]:
    """Add cluster_name only when it is needed."""
    if cluster_name:
        return {'opensearch_cluster_name': cluster_name, **base_args}
    return base_args


def extract_text_content(result: Any) -> str:
    """Join all text items from an MCP CallToolResult."""
    parts: list[str] = []
    for item in getattr(result, 'content', []):
        if getattr(item, 'type', None) == 'text':
            parts.append(getattr(item, 'text', ''))
    return '\n'.join(part for part in parts if part)


def ensure_tool_success(result: Any, tool_name: str) -> str:
    """Return text content or raise a clean error for tool-level failures."""
    text = extract_text_content(result)
    if getattr(result, 'isError', False) or text.startswith('Error '):
        raise RuntimeError(f'{tool_name} failed: {text}')
    return text


def extract_json_payload(result: Any) -> dict[str, Any]:
    """Parse the JSON payload embedded in the tool's text response."""
    text = extract_text_content(result)
    if not text:
        raise RuntimeError('Tool returned no text content')
    _, _, payload = text.partition('\n')
    json_text = payload or text
    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f'Could not parse tool response as JSON: {text}') from exc
    if not isinstance(data, dict):
        raise RuntimeError(f'Expected JSON object from tool response, got: {type(data).__name__}')
    return data


async def call_generic_api(session: ClientSession, args: argparse.Namespace) -> None:
    """Call GenericOpenSearchApiTool using CLI arguments."""
    generic_args = build_tool_args(
        {
            'path': args.generic_path,
            'method': args.generic_method,
            'query_params': parse_optional_json_object(
                args.generic_query_params, '--generic-query-params'
            ),
            'body': parse_optional_json_or_text(args.generic_body, '--generic-body'),
            'headers': parse_optional_json_object(args.generic_headers, '--generic-headers'),
        },
        args.cluster_name,
    )
    print(f'\nCalling {GENERIC_TOOL_NAME}...')
    generic_result = await session.call_tool(GENERIC_TOOL_NAME, generic_args)
    print(ensure_tool_success(generic_result, GENERIC_TOOL_NAME))


async def main() -> int:
    """Run the async-search smoke test against the local MCP server."""
    args = parse_args()

    async with streamablehttp_client(args.server_url) as (
        read_stream,
        write_stream,
        _get_session_id,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            init_result = await session.initialize()
            print(
                f'Connected to MCP server: {init_result.serverInfo.name} '
                f'{init_result.serverInfo.version or ""}'.strip()
            )

            tools_result = await session.list_tools()
            tool_names = [tool.name for tool in tools_result.tools]
            print(f'Available tools ({len(tool_names)}):')
            for tool_name in tool_names:
                print(f'  - {tool_name}')

            if args.list_only:
                return 0

            if args.generic_path:
                if GENERIC_TOOL_NAME not in tool_names:
                    raise RuntimeError(f'{GENERIC_TOOL_NAME} is not exposed by the MCP server')
                await call_generic_api(session, args)
                if args.generic_only:
                    return 0

            missing_tools = [name for name in ASYNC_TOOL_NAMES if name not in tool_names]
            if missing_tools:
                print('\nMissing async search tools:')
                for tool_name in missing_tools:
                    print(f'  - {tool_name}')
                print(
                    '\nIf the server is running in single mode, enable them with '
                    'OPENSEARCH_ENABLED_TOOLS or run the server in multi mode.'
                )
                return 2

            if not args.index:
                raise SystemExit('--index is required unless --list-only is used')

            submit_args = build_tool_args(
                {
                    'index': args.index,
                    'query_dsl': parse_query(args.query),
                    'wait_for_completion_timeout': args.wait_for_completion_timeout,
                    'keep_alive': args.keep_alive,
                    'size': args.size,
                },
                args.cluster_name,
            )

            print('\nSubmitting async search...')
            submit_result = await session.call_tool('SubmitAsyncSearchTool', submit_args)
            submit_text = ensure_tool_success(submit_result, 'SubmitAsyncSearchTool')
            print(submit_text)
            submit_payload = extract_json_payload(submit_result)
            if 'error' in submit_payload:
                raise RuntimeError(
                    'SubmitAsyncSearchTool returned an async search error: '
                    f'{json.dumps(submit_payload["error"], separators=(",", ":"))}'
                )
            search_id = submit_payload.get('id')
            if not search_id:
                print(
                    '\nSubmitAsyncSearchTool did not return an async search id. '
                    'This can happen when the query completes immediately.'
                )
                return 3

            get_args = build_tool_args({'search_id': search_id}, args.cluster_name)
            print(f'\nFetching async search status for {search_id}...')
            get_result = await session.call_tool('GetAsyncSearchTool', get_args)
            print(ensure_tool_success(get_result, 'GetAsyncSearchTool'))

            if args.skip_delete:
                print('\nSkipping delete step.')
                return 0

            print(f'\nDeleting async search {search_id}...')
            delete_result = await session.call_tool('DeleteAsyncSearchTool', get_args)
            print(ensure_tool_success(delete_result, 'DeleteAsyncSearchTool'))

    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        print('\nInterrupted.', file=sys.stderr)
        raise SystemExit(130)
    except RuntimeError as exc:
        print(f'\n{exc}', file=sys.stderr)
        raise SystemExit(1)
