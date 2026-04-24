# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import json
from .params import (
    AddAgenticMemoriesArgs,
    CreateAgenticMemorySessionArgs,
    DeleteAgenticMemoryByIDArgs,
    DeleteAgenticMemoryByQueryArgs,
    GetAgenticMemoryArgs,
    SearchAgenticMemoryArgs,
    UpdateAgenticMemoryArgs,
)
from opensearch.helper import (
    add_agentic_memories,
    create_agentic_memory_session,
    delete_agentic_memory_by_id,
    delete_agentic_memory_by_query,
    get_agentic_memory,
    search_agentic_memory,
    update_agentic_memory,
)
from tools.tool_logging import log_tool_error


async def create_agentic_memory_session_tool(
    args: CreateAgenticMemorySessionArgs,
) -> list[dict]:
    """Tool to create a new session in an agentic memory container."""
    try:
        from tools.tools import check_tool_compatibility

        await check_tool_compatibility('CreateAgenticMemorySessionTool', args)
        result = await create_agentic_memory_session(args)
        formatted = json.dumps(result, separators=(',', ':'))
        return [{'type': 'text', 'text': f'Session created:\n{formatted}'}]
    except Exception as e:
        return log_tool_error('CreateAgenticMemorySessionTool', e, 'creating session')


async def add_agentic_memories_tool(args: AddAgenticMemoriesArgs) -> list[dict]:
    """Tool to add memories to an agentic memory container."""
    try:
        from tools.tools import check_tool_compatibility

        await check_tool_compatibility('AddAgenticMemoriesTool', args)
        result = await add_agentic_memories(args)
        formatted = json.dumps(result, separators=(',', ':'))
        return [{'type': 'text', 'text': f'Memories added:\n{formatted}'}]
    except Exception as e:
        return log_tool_error('AddAgenticMemoriesTool', e, 'adding memories')


async def get_agentic_memory_tool(args: GetAgenticMemoryArgs) -> list[dict]:
    """Tool to retrieve a specific agentic memory by its type and ID."""
    try:
        from tools.tools import check_tool_compatibility

        await check_tool_compatibility('GetAgenticMemoryTool', args)
        result = await get_agentic_memory(args)
        formatted = json.dumps(result, separators=(',', ':'))
        return [{'type': 'text', 'text': f'Memory {args.id} ({args.memory_type.value}):\n{formatted}'}]
    except Exception as e:
        return log_tool_error('GetAgenticMemoryTool', e, 'retrieving memory')


async def update_agentic_memory_tool(args: UpdateAgenticMemoryArgs) -> list[dict]:
    """Tool to update a specific agentic memory by its type and ID."""
    try:
        from tools.tools import check_tool_compatibility

        await check_tool_compatibility('UpdateAgenticMemoryTool', args)
        result = await update_agentic_memory(args)
        formatted = json.dumps(result, separators=(',', ':'))
        return [{'type': 'text', 'text': f'Memory updated:\n{formatted}'}]
    except Exception as e:
        return log_tool_error('UpdateAgenticMemoryTool', e, 'updating memory')


async def delete_agentic_memory_by_id_tool(
    args: DeleteAgenticMemoryByIDArgs,
) -> list[dict]:
    """Tool to delete a specific agentic memory by its type and ID."""
    try:
        from tools.tools import check_tool_compatibility

        await check_tool_compatibility('DeleteAgenticMemoryByIDTool', args)
        result = await delete_agentic_memory_by_id(args)
        formatted = json.dumps(result, separators=(',', ':'))
        return [{'type': 'text', 'text': f'Memory deleted:\n{formatted}'}]
    except Exception as e:
        return log_tool_error('DeleteAgenticMemoryByIDTool', e, 'deleting memory')


async def delete_agentic_memory_by_query_tool(
    args: DeleteAgenticMemoryByQueryArgs,
) -> list[dict]:
    """Tool to delete agentic memories matching an OpenSearch query DSL."""
    try:
        from tools.tools import check_tool_compatibility

        await check_tool_compatibility('DeleteAgenticMemoryByQueryTool', args)
        result = await delete_agentic_memory_by_query(args)
        formatted = json.dumps(result, separators=(',', ':'))
        return [{'type': 'text', 'text': f'Memories deleted by query:\n{formatted}'}]
    except Exception as e:
        return log_tool_error('DeleteAgenticMemoryByQueryTool', e, 'deleting memories by query')


async def search_agentic_memory_tool(args: SearchAgenticMemoryArgs) -> list[dict]:
    """Tool to search for agentic memories using an OpenSearch query DSL."""
    try:
        from tools.tools import check_tool_compatibility

        await check_tool_compatibility('SearchAgenticMemoryTool', args)
        result = await search_agentic_memory(args)
        formatted = json.dumps(result, separators=(',', ':'))
        return [{'type': 'text', 'text': f'Search results ({args.memory_type.value}):\n{formatted}'}]
    except Exception as e:
        return log_tool_error('SearchAgenticMemoryTool', e, 'searching memory')


# Agentic memory tools registry - spread into TOOL_REGISTRY like SKILLS_TOOLS_REGISTRY
AGENTIC_MEMORY_TOOLS_REGISTRY = {
    'CreateAgenticMemorySessionTool': {
        'display_name': 'CreateAgenticMemorySessionTool',
        'description': 'Create a new session in a memory container.',
        'input_schema': CreateAgenticMemorySessionArgs.model_json_schema(),
        'function': create_agentic_memory_session_tool,
        'args_model': CreateAgenticMemorySessionArgs,
        'min_version': '3.3.0',
        'http_methods': 'POST',
    },
    'AddAgenticMemoriesTool': {
        'display_name': 'AddAgenticMemoriesTool',
        'description': 'Add an agentic memory to a memory container.',
        'input_schema': AddAgenticMemoriesArgs.model_json_schema(),
        'function': add_agentic_memories_tool,
        'args_model': AddAgenticMemoriesArgs,
        'min_version': '3.3.0',
        'http_methods': 'POST',
    },
    'GetAgenticMemoryTool': {
        'display_name': 'GetAgenticMemoryTool',
        'description': 'Retrieve a specific memory by its type and ID.',
        'input_schema': GetAgenticMemoryArgs.model_json_schema(),
        'function': get_agentic_memory_tool,
        'args_model': GetAgenticMemoryArgs,
        'min_version': '3.3.0',
        'http_methods': 'GET',
    },
    'UpdateAgenticMemoryTool': {
        'display_name': 'UpdateAgenticMemoryTool',
        'description': 'Update a specific memory by its type and ID.',
        'input_schema': UpdateAgenticMemoryArgs.model_json_schema(),
        'function': update_agentic_memory_tool,
        'args_model': UpdateAgenticMemoryArgs,
        'min_version': '3.3.0',
        'http_methods': 'PUT',
    },
    'DeleteAgenticMemoryByIDTool': {
        'display_name': 'DeleteAgenticMemoryByIDTool',
        'description': 'Deletes specific agentic memory container by its type and ID.',
        'input_schema': DeleteAgenticMemoryByIDArgs.model_json_schema(),
        'function': delete_agentic_memory_by_id_tool,
        'args_model': DeleteAgenticMemoryByIDArgs,
        'min_version': '3.3.0',
        'http_methods': 'DELETE',
    },
    'DeleteAgenticMemoryByQueryTool': {
        'display_name': 'DeleteAgenticMemoryByQueryTool',
        'description': 'Deletes specific agentic memory by query.',
        'input_schema': DeleteAgenticMemoryByQueryArgs.model_json_schema(),
        'function': delete_agentic_memory_by_query_tool,
        'args_model': DeleteAgenticMemoryByQueryArgs,
        'min_version': '3.3.0',
        'http_methods': 'POST',
    },
    'SearchAgenticMemoryTool': {
        'display_name': 'SearchAgenticMemoryTool',
        'description': 'Search for memories of a specific type within a memory container.',
        'input_schema': SearchAgenticMemoryArgs.model_json_schema(),
        'function': search_agentic_memory_tool,
        'args_model': SearchAgenticMemoryArgs,
        'min_version': '3.3.0',
        'http_methods': 'GET',
    },
}
