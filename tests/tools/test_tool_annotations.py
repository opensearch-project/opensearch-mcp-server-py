# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import os
import pytest
import sys
from mcp import Client
from mcp.types import ToolAnnotations
from semver import Version
from unittest.mock import AsyncMock, patch


HINTS = ('read_only_hint', 'destructive_hint', 'idempotent_hint', 'open_world_hint')


def _registry_with_memory_tools() -> dict:
    """Build the static tool registry with the env-gated memory tools included."""
    from tools.tools import TOOL_REGISTRY

    original = sys.modules.pop('tools.memory_tools', None)
    try:
        with patch.dict(os.environ, {'MEMORY_TOOLS_ENABLED': 'true'}):
            from tools.memory_tools import MEMORY_TOOLS_REGISTRY
    finally:
        if original is not None:
            sys.modules['tools.memory_tools'] = original

    return {**TOOL_REGISTRY, **MEMORY_TOOLS_REGISTRY}


REGISTRY = _registry_with_memory_tools()


@pytest.mark.parametrize('name', sorted(REGISTRY))
def test_every_tool_has_complete_annotations(name):
    annotations = REGISTRY[name].get('annotations')
    assert isinstance(annotations, ToolAnnotations), f'{name} has no annotations'
    assert annotations.title
    for hint in HINTS:
        assert isinstance(getattr(annotations, hint), bool), f'{name} missing {hint}'


@pytest.mark.parametrize('name', sorted(REGISTRY))
def test_annotations_are_consistent_with_http_methods(name):
    info = REGISTRY[name]
    annotations = info['annotations']
    if annotations.read_only_hint:
        assert not annotations.destructive_hint
        assert annotations.idempotent_hint
    # The write filter drops non-GET tools unless they opt out, so those must not claim read-only.
    if 'GET' not in info['http_methods'] and not info.get('bypass_write_filter'):
        assert not annotations.read_only_hint, f'{name} is filtered as a write tool'
    if name.startswith('Delete'):
        assert annotations.destructive_hint


@pytest.mark.parametrize(
    'name, read_only, destructive, idempotent, open_world',
    [
        ('SearchIndexTool', True, False, True, False),
        ('PPLQueryTool', True, False, True, False),
        ('DataDistributionTool', True, False, True, False),
        ('CreateQuerySetTool', False, False, False, False),
        ('DeleteExperimentTool', False, True, True, False),
        ('GenericOpenSearchApiTool', False, True, False, True),
        ('CreateLLMJudgmentListTool', False, False, False, True),
        ('SaveMemoryTool', False, False, False, False),
        ('AddAgenticMemoriesTool', False, True, False, True),
        ('UpdateAgenticMemoryTool', False, True, True, False),
    ],
)
def test_selected_tool_annotations(name, read_only, destructive, idempotent, open_world):
    annotations = REGISTRY[name]['annotations']
    assert annotations.read_only_hint is read_only
    assert annotations.destructive_hint is destructive
    assert annotations.idempotent_hint is idempotent
    assert annotations.open_world_hint is open_world


def test_every_generated_operation_has_annotations():
    from tools.tool_generator import OPERATION_ANNOTATIONS, SUPPORTED_OPERATIONS

    assert set(OPERATION_ANNOTATIONS) == set(SUPPORTED_OPERATIONS)


def test_generated_tool_carries_operation_annotations():
    from tools.tool_generator import OPERATION_ANNOTATIONS, generate_tool_from_group

    endpoints = [
        {
            'path': '/_count',
            'method': 'post',
            'details': {'description': 'Count', 'x-operation-group': 'count'},
        }
    ]
    tool = generate_tool_from_group('Count', endpoints)
    assert tool['annotations'] is OPERATION_ANNOTATIONS['count']
    assert tool['annotations'].read_only_hint is True


async def _list_tools(mode: str) -> dict:
    """Start the server in-process and return tools/list output keyed by tool name."""
    from mcp_server_opensearch.streaming_server import create_mcp_server

    with (
        # Other tests mutate the global TOOL_REGISTRY, so serve a snapshot taken at import.
        patch.dict('mcp_server_opensearch.streaming_server.TOOL_REGISTRY', REGISTRY, clear=True),
        patch(
            'mcp_server_opensearch.streaming_server.generate_tools_from_openapi',
            new_callable=AsyncMock,
        ),
        patch(
            'mcp_server_opensearch.streaming_server.load_clusters_from_yaml',
            new_callable=AsyncMock,
        ),
        patch(
            'tools.tool_filter.get_opensearch_version',
            new_callable=AsyncMock,
            return_value=Version.parse('3.5.0'),
        ),
    ):
        server = await create_mcp_server(mode=mode)
    async with Client(server) as client:
        result = await client.list_tools()
    return {tool.name: tool for tool in result.tools}


@pytest.mark.parametrize('mode', ['single', 'multi'])
async def test_tools_list_includes_annotations(mode):
    tools = await _list_tools(mode)
    assert 'SearchIndexTool' in tools
    for name, tool in tools.items():
        assert tool.annotations == REGISTRY[name]['annotations'], name

    wire = tools['SearchIndexTool'].model_dump(by_alias=True, exclude_none=True)
    assert wire['annotations'] == {
        'title': 'Search Index',
        'readOnlyHint': True,
        'destructiveHint': False,
        'idempotentHint': True,
        'openWorldHint': False,
    }
