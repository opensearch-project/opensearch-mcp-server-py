# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import re
import os
import json
import logging
from .tool_params import baseToolArgs
from .tools import TOOL_REGISTRY
from .skills_tools import SKILLS_TOOLS_REGISTRY
from .utils import (
    is_tool_compatible,
    parse_comma_separated,
    load_yaml_config,
    validate_tools,
)
from opensearch.helper import get_opensearch_version
from mcp_server_opensearch.global_state import get_mode

# Global variable to store the resolved allow_write setting
# This is set during server initialization and used by individual tools
_resolved_allow_write_setting = None


def process_regex_patterns(regex_list, tool_names):
    """Process regex patterns and return matching tool names."""
    matching_tools = []
    for regex in regex_list:
        for tool_name in tool_names:
            if re.match(regex, tool_name, re.IGNORECASE):
                matching_tools.append(tool_name)
    return matching_tools


def set_allow_write_setting(allow_write: bool) -> None:
    """Set the global allow_write setting.

    This function is called during server initialization to store the resolved
    allow_write setting for use by individual tools.

    Args:
        allow_write: The resolved allow_write setting
    """
    global _resolved_allow_write_setting
    _resolved_allow_write_setting = allow_write
    logging.debug(f'Set global allow_write setting to: {allow_write}')


def get_allow_write_setting() -> bool:
    """Get the allow_write setting.

    This function returns the allow_write setting that was resolved during
    server initialization. If not set, falls back to environment variable.

    Returns:
        bool: True if write operations are allowed, False otherwise
    """
    global _resolved_allow_write_setting

    # If the setting was resolved during server initialization, use it
    if _resolved_allow_write_setting is not None:
        return _resolved_allow_write_setting

    # Fallback to environment variable if not set during initialization
    return os.getenv('OPENSEARCH_SETTINGS_ALLOW_WRITE', 'true').lower() == 'true'


def _resolve_allow_write_setting(config_file_path: str = None) -> bool:
    """Resolve the allow_write setting from environment variable or config file.

    This is an internal function used during server initialization to determine
    the final allow_write setting.

    Args:
        config_file_path: Optional path to config file

    Returns:
        bool: True if write operations are allowed, False otherwise
    """
    # Start with environment variable (default is true)
    allow_write = os.getenv('OPENSEARCH_SETTINGS_ALLOW_WRITE', 'true').lower() == 'true'

    # Check config file if provided
    if config_file_path and os.path.exists(config_file_path):
        try:
            config = load_yaml_config(config_file_path)
            if config:
                # Use the same logic as process_tool_filter
                tool_filters = config.get('tool_filters', {})
                settings = tool_filters.get('settings', {})
                if 'allow_write' in settings:
                    # Config file setting overrides environment variable
                    allow_write = settings.get('allow_write', True)
                    logging.debug(
                        f'Using allow_write setting from config file: {config_file_path}'
                    )
        except Exception as e:
            logging.debug(f'Could not load config file {config_file_path}: {e}')

    return allow_write


def apply_write_filter(registry):
    """Apply allow_write filters to the registry."""
    for tool_name in list(registry.keys()):
        http_methods = registry[tool_name].get('http_methods', [])
        if 'GET' not in http_methods:
            registry.pop(tool_name, None)


def process_categories(category_list, category_to_tools):
    """Process categories and return tools from those categories."""
    tools = []
    for category in category_list:
        if category in category_to_tools:
            tools.extend(category_to_tools[category])
        else:
            logging.warning(f"Category '{category}' not found in tool categories")
    return tools


def process_tool_filter(
    enabled_tools: str = None,
    disabled_tools: str = None,
    tool_categories: str = None,
    enabled_categories: str = None,
    disabled_categories: str = None,
    enabled_tools_regex: str = None,
    disabled_tools_regex: str = None,
    allow_write: bool = None,
    filter_path: str = None,
    tool_registry: dict = None,
) -> None:
    """Process tool filter configuration from a YAML file and environment variables.

    Args:
        enabled_tools: Comma-separated list of enabled tool names
        disabled_tools: Comma-separated list of disabled tool names
        tool_categories: JSON string defining tool categories, e.g. '{"critical":["ListIndexTool","MsearchTool"]}'
        enabled_categories: Comma-separated list of enabled category names
        disabled_categories: Comma-separated list of disabled category names
        enabled_tools_regex: Comma-separates list of enabled tools regex
        disabled_tools_regex: Comma-separated list of disabled tools regex
        allow_write: If True, allow tools with PUT/POST methods
        filter_path: Path to the YAML filter configuration file
        tool_registry: The tool registry to filter.
    """
    try:
        # Create display name lookup
        display_name = {
            tool_info.get('display_name', '').lower(): k for k, tool_info in tool_registry.items()
        }

        # Initialize collections
        category_to_tools = {}
        enabled_tool_list = []
        disabled_tool_list = []
        enabled_category_list = ['core_tools']
        disabled_category_list = []
        enabled_tools_regex_list = []
        disabled_tools_regex_list = []
        core_tools_display_name = []

        # Initialize core tool names
        core_tools = [
            'ListIndexTool',
            'IndexMappingTool',
            'SearchIndexTool',
            'GetShardsTool',
            'ClusterHealthTool',
            'CountTool',
            'ExplainTool',
            'MsearchTool',
            'GenericOpenSearchApiTool',
        ]

        # Build core tools list using display names
        for tool_name in core_tools:
            if tool_name in tool_registry:
                tool_display_name = tool_registry[tool_name].get('display_name', tool_name)
                core_tools_display_name.append(tool_display_name)

        # Add core_tools as a built-in category using display name
        category_to_tools['core_tools'] = core_tools_display_name

        # Initialize search_relevance tool names
        search_relevance_tools = [
            'CreateSearchConfigurationTool',
            'GetSearchConfigurationTool',
            'DeleteSearchConfigurationTool',
            'GetQuerySetTool',
            'CreateQuerySetTool',
            'SampleQuerySetTool',
            'DeleteQuerySetTool',
            'GetJudgmentListTool',
            'CreateJudgmentListTool',
            'CreateUBIJudgmentListTool',
            'CreateLLMJudgmentListTool',
            'DeleteJudgmentListTool',
            'GetExperimentTool',
            'CreateExperimentTool',
            'DeleteExperimentTool',
            'SearchQuerySetsTool',
            'SearchSearchConfigurationsTool',
            'SearchJudgmentsTool',
            'SearchExperimentsTool',
        ]

        # Build search_relevance tools list using display names
        search_relevance_display_names = []
        for tool_name in search_relevance_tools:
            if tool_name in tool_registry:
                tool_display_name = tool_registry[tool_name].get('display_name', tool_name)
                search_relevance_display_names.append(tool_display_name)

        # Add search_relevance as a built-in category (not enabled by default)
        category_to_tools['search_relevance'] = search_relevance_display_names

        # Add skills as a built-in category (not enabled by default)
        skills_display_names = [
            info.get('display_name', name) for name, info in SKILLS_TOOLS_REGISTRY.items()
        ]
        category_to_tools['skills'] = skills_display_names

        # Process YAML config file if provided
        config = load_yaml_config(filter_path)
        if config:
            # Extract configuration values
            category_to_tools.update(config.get('tool_category', {}))
            tool_filters = config.get('tool_filters', {})

            # Get lists from config
            enabled_tool_list = tool_filters.get('enabled_tools', [])
            disabled_tool_list = tool_filters.get('disabled_tools', [])
            enabled_category_list.extend(tool_filters.get('enabled_categories', []))
            disabled_category_list = tool_filters.get('disabled_categories', [])
            enabled_tools_regex_list = tool_filters.get('enabled_tools_regex', [])
            disabled_tools_regex_list = tool_filters.get('disabled_tools_regex', [])

            # Get settings
            settings = tool_filters.get('settings', {})
            if settings:
                allow_write = settings.get('allow_write', True)

        # Process environment variables
        if tool_categories:
            try:
                category_to_tools.update(
                    json.loads(tool_categories) if isinstance(tool_categories, str) else {}
                )
            except json.JSONDecodeError:
                logging.warning(f'Invalid JSON in tool_categories: {tool_categories}')

        # Parse comma-separated strings from environment variables
        if enabled_tools:
            enabled_tool_list.extend(parse_comma_separated(enabled_tools))
        if disabled_tools:
            disabled_tool_list.extend(parse_comma_separated(disabled_tools))
        if enabled_categories:
            enabled_category_list.extend(parse_comma_separated(enabled_categories))
        if disabled_categories:
            disabled_category_list.extend(parse_comma_separated(disabled_categories))
        if enabled_tools_regex:
            enabled_tools_regex_list.extend(parse_comma_separated(enabled_tools_regex))
        if disabled_tools_regex:
            disabled_tools_regex_list.extend(parse_comma_separated(disabled_tools_regex))

        # Apply allow_write filter first
        if not allow_write:
            apply_write_filter(tool_registry)

        # Process tools from categories and regex patterns
        enabled_tools_from_categories = process_categories(
            enabled_category_list, category_to_tools
        )
        disabled_tools_from_categories = process_categories(
            disabled_category_list, category_to_tools
        )

        # Get current tool names after allow_write filtering
        current_tool_names = [tool['display_name'] for tool in tool_registry.values()]
        enabled_tools_from_regex = process_regex_patterns(
            enabled_tools_regex_list, current_tool_names
        )
        disabled_tools_from_regex = process_regex_patterns(
            disabled_tools_regex_list, current_tool_names
        )

        # Apply enabled tools filter
        if enabled_tool_list or enabled_tools_from_categories or enabled_tools_from_regex:
            # Validate and collect all enabled tools
            all_enabled_tools = set()
            all_enabled_tools.update(
                validate_tools(enabled_tool_list, display_name, 'enabled_tools')
            )
            all_enabled_tools.update(
                validate_tools(enabled_tools_from_categories, display_name, 'enabled_categories')
            )
            all_enabled_tools.update(
                validate_tools(enabled_tools_from_regex, display_name, 'enabled_tools_regex')
            )

            # Remove tools not in the enabled list
            for tool_name in list(tool_registry.keys()):
                if tool_name.lower() not in all_enabled_tools:
                    tool_registry.pop(tool_name, None)

        # Apply disabled tools filter
        if disabled_tool_list or disabled_tools_from_categories or disabled_tools_from_regex:
            # Validate and collect all disabled tools
            all_disabled_tools = set()
            all_disabled_tools.update(
                validate_tools(disabled_tool_list, display_name, 'disabled_tools')
            )
            all_disabled_tools.update(
                validate_tools(disabled_tools_from_categories, display_name, 'disabled_categories')
            )
            all_disabled_tools.update(
                validate_tools(disabled_tools_from_regex, display_name, 'disabled_tools_regex')
            )

            # Remove tools in the disabled list
            for tool_name in list(tool_registry.keys()):
                if tool_name.lower() in all_disabled_tools:
                    tool_registry.pop(tool_name, None)

        # Log results
        source = filter_path if filter_path else 'environment variables'
        logging.info(f'Applied tool filter from {source}')

    except Exception as e:
        logging.error(f'Error processing tool filter: {str(e)}')


async def get_tools(tool_registry: dict, config_file_path: str = '') -> dict:
    """Filter and return available tools based on server mode and OpenSearch version.

    In 'multi' mode, returns all tools without filtering. In 'single' mode, filters tools
    based on OpenSearch version compatibility and removes base tool arguments from schemas.

    Args:
        tool_registry (dict): The tool registry to filter.
        config_file_path (str): Path to a YAML configuration file

    Returns:
        dict: Dictionary of enabled tools with their configurations
    """
    # Get the current mode from global state
    mode = get_mode()

    # Resolve and set the global allow_write setting for use by individual tools
    # This needs to be done in both single and multi mode
    resolved_allow_write = _resolve_allow_write_setting(config_file_path)
    set_allow_write_setting(resolved_allow_write)

    # In multi mode, return all tools without any filtering
    if mode == 'multi':
        return tool_registry

    enabled = {}

    # Get OpenSearch version for compatibility checking (only in single mode)
    version = await get_opensearch_version(baseToolArgs(opensearch_cluster_name=''))
    logging.info(f'Connected OpenSearch version: {version}')

    env_config = {
        'enabled_tools': os.getenv('OPENSEARCH_ENABLED_TOOLS', ''),
        'disabled_tools': os.getenv('OPENSEARCH_DISABLED_TOOLS', ''),
        'tool_categories': os.getenv('OPENSEARCH_TOOL_CATEGORIES', ''),
        'enabled_categories': os.getenv('OPENSEARCH_ENABLED_CATEGORIES', ''),
        'disabled_categories': os.getenv('OPENSEARCH_DISABLED_CATEGORIES', ''),
        'enabled_tools_regex': os.getenv('OPENSEARCH_ENABLED_TOOLS_REGEX', ''),
        'disabled_tools_regex': os.getenv('OPENSEARCH_DISABLED_TOOLS_REGEX', ''),
        'allow_write': os.getenv('OPENSEARCH_SETTINGS_ALLOW_WRITE', 'true').lower() == 'true',
    }

    # Check if both config and env variables are set
    if config_file_path and any(env_config.values()):
        logging.warning('Both config file and environment variables are set. Using config file.')

    # Apply tool filtering, update the TOOL_REGISTRY
    process_tool_filter(
        tool_registry=tool_registry,
        filter_path=config_file_path if config_file_path else None,
        **{k: v for k, v in env_config.items() if not config_file_path},
    )

    for name, info in tool_registry.items():
        # Create a copy to avoid modifying the original tool info
        tool_info = info.copy()
        tool_name = tool_info['display_name']

        # Skip multi-only tools in single mode
        if info.get('multi_only') and mode != 'multi':
            continue

        # If tool is not compatible with the current OpenSearch version, skip, don't enable
        if not is_tool_compatible(version, info):
            continue

        # Remove baseToolArgs fields from input schema for single mode
        # This simplifies the schema since base args are handled internally
        schema = tool_info['input_schema'].copy()
        if 'properties' in schema:
            base_fields = baseToolArgs.model_fields.keys()
            for field in base_fields:
                schema['properties'].pop(field, None)
                # Also remove from required array if present
                if 'required' in schema and field in schema['required']:
                    schema['required'].remove(field)
        tool_info['input_schema'] = schema

        enabled[tool_name] = tool_info

    return enabled
