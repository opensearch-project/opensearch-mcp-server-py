# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import copy
import json
import logging
import os
import re
from .tool_params import baseToolArgs
from .utils import (
    is_tool_compatible,
    load_yaml_config,
    parse_comma_separated,
    validate_tools,
)
from mcp_server_opensearch.global_state import get_mode
from opensearch.helper import get_opensearch_version


# Global variable to store the resolved allow_write setting
# This is set during server initialization and used by individual tools
_resolved_allow_write_setting = None


def _strip_schema_fields(schema: dict, fields) -> dict:
    """Return a deep copy of ``schema`` with ``fields`` removed from properties and required.

    Deep-copied so the static TOOL_REGISTRY schema objects are never mutated.
    """
    schema = copy.deepcopy(schema)
    if 'properties' in schema:
        for field in fields:
            schema['properties'].pop(field, None)
            if 'required' in schema and field in schema['required']:
                schema['required'].remove(field)
    return schema


# Tools OpenSearch Serverless (AOSS) can serve. This is an allowlist because AOSS
# supports far fewer tools than it rejects: it implements the index, document and
# search data plane plus PPL, but not the cluster, node, monitoring, Search
# Relevance Workbench or ml-commons memory APIs. Any tool not listed here is treated
# as serverless-incompatible, so a newly added tool is excluded on AOSS until it is
# explicitly verified and added. Membership was confirmed live against an AOSS
# collection. See:
# https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-genref.html
SERVERLESS_COMPATIBLE_TOOLS: frozenset = frozenset(
    {
        'ListIndexTool',  # GET /_cat/indices
        'IndexMappingTool',  # GET /<index>/_mapping
        'GetIndexInfoTool',  # GET /<index>
        'SearchIndexTool',  # POST /<index>/_search
        'PPLQueryTool',  # POST /_plugins/_ppl
        'DataDistributionTool',  # client-side analysis over _search/_count
        'LogPatternAnalysisTool',  # client-side analysis over _search/_count
        'MetricChangeAnalysisTool',  # client-side analysis over _search/_count
        'GenericOpenSearchApiTool',  # passthrough; valid endpoints only
        'ListClustersTool',  # server-side datasource listing, no backend call
    }
)


def filter_serverless_incompatible(registry: dict) -> None:
    """Remove tools that OpenSearch Serverless cannot serve from ``registry`` in place."""
    for key in list(registry.keys()):
        if key not in SERVERLESS_COMPATIBLE_TOOLS:
            registry.pop(key, None)


def _is_serverless_single_mode() -> bool:
    """Detect a serverless connection in single mode from env/URL configuration."""
    if os.getenv('AWS_OPENSEARCH_SERVERLESS', '').lower() == 'true':
        return True
    return 'aoss.amazonaws.com' in os.getenv('OPENSEARCH_URL', '').strip().lower()


def _is_serverless_multi_mode() -> bool:
    """True only when every configured multi-mode cluster is serverless.

    Tools are advertised once for all clusters, so incompatible tools can only be
    dropped at list time when there is no non-serverless cluster that could serve
    them. Mixed deployments rely on the call-time guard instead.
    """
    from mcp_server_opensearch.clusters_information import cluster_registry

    clusters = list(cluster_registry.values())
    return bool(clusters) and all(c.is_serverless for c in clusters)


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
                    if os.getenv('OPENSEARCH_SETTINGS_ALLOW_WRITE'):
                        logging.warning(
                            'OPENSEARCH_SETTINGS_ALLOW_WRITE is set but the config file sets '
                            f'allow_write; using the config file value ({str(allow_write).lower()}).'
                        )
                    else:
                        logging.debug(
                            f'Using allow_write setting from config file: {config_file_path}'
                        )
        except Exception as e:
            logging.debug(f'Could not load config file {config_file_path}: {e}')

    return allow_write


def apply_write_filter(registry, exempt_tools=None):
    """Apply allow_write filters to the registry.

    Removes tools that only have write HTTP methods, unless the tool
    has ``bypass_write_filter`` set to True (e.g. memory tools) or in the exempt_tools set.

    Args:
        registry: The tool registry to filter
        exempt_tools: Set of tool names (registry keys) exempt from the write filter
    """
    if exempt_tools is None:
        exempt_tools = set()
    for tool_name in list(registry.keys()):
        if registry[tool_name].get('bypass_write_filter') or tool_name in exempt_tools:
            continue
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


# Single source of truth: built-in category → registry key lists.
# Used by build_category_map and to stamp tool_info['category'] at startup.
#
# 'observability' and 'skills' are fine-grained categories that existed before
# the unified 'analytics' category was introduced.  'analytics' is a superset
# that contains every tool from both.  All three are first-class categories —
# enabling 'skills' gives the 3 skills tools, enabling 'observability' gives
# PPLQueryTool, and enabling 'analytics' gives all 4.
_SKILLS_TOOLS: list[str] = [
    'DataDistributionTool',
    'LogPatternAnalysisTool',
    'MetricChangeAnalysisTool',
]

_OBSERVABILITY_TOOLS: list[str] = [
    'PPLQueryTool',
]

BUILTIN_CATEGORY_TOOLS: dict[str, list[str]] = {
    'core_tools': [
        'ListIndexTool',
        'IndexMappingTool',
        'SearchIndexTool',
        'GetShardsTool',
        'ClusterHealthTool',
        'CountTool',
        'ExplainTool',
        'MsearchTool',
        'GenericOpenSearchApiTool',
    ],
    'memory': [
        'SaveMemoryTool',
        'SearchMemoryTool',
        'DeleteMemoryTool',
    ],
    'search_relevance': [
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
    ],
    'agentic_memory': [
        'CreateAgenticMemorySessionTool',
        'AddAgenticMemoriesTool',
        'GetAgenticMemoryTool',
        'UpdateAgenticMemoryTool',
        'DeleteAgenticMemoryByIDTool',
        'DeleteAgenticMemoryByQueryTool',
        'SearchAgenticMemoryTool',
    ],
    'observability': _OBSERVABILITY_TOOLS,
    'skills': _SKILLS_TOOLS,
    'analytics': _OBSERVABILITY_TOOLS + _SKILLS_TOOLS,
}


def build_category_map(tool_registry: dict) -> dict[str, list[str]]:
    """Return a category → list-of-display-names map for the given registry.

    All categories come from BUILTIN_CATEGORY_TOOLS.  User-defined categories
    (from YAML or env vars) are merged on top by the caller.
    """
    return {
        category: [
            tool_registry[k].get('display_name', k) for k in tool_keys if k in tool_registry
        ]
        for category, tool_keys in BUILTIN_CATEGORY_TOOLS.items()
    }


def process_tool_filter(
    enabled_tools: str = None,
    disabled_tools: str = None,
    tool_categories: str = None,
    enabled_categories: str = None,
    disabled_categories: str = None,
    enabled_tools_regex: str = None,
    disabled_tools_regex: str = None,
    allow_write: bool = None,
    allow_write_categories: list = None,
    filter_path: str = None,
    tool_registry: dict = None,
) -> dict:
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
        allow_write_categories: List of category names whose tools are exempt from the write filter
        filter_path: Path to the YAML filter configuration file
        tool_registry: The tool registry to filter.
    """
    try:
        # Create display name lookup
        display_name = {
            tool_info.get('display_name', '').lower(): k for k, tool_info in tool_registry.items()
        }

        # Initialize collections
        enabled_tool_list = []
        disabled_tool_list = []
        enabled_category_list = ['core_tools']
        disabled_category_list = []
        enabled_tools_regex_list = []
        disabled_tools_regex_list = []

        # Build built-in category map (category → list of display names)
        category_to_tools = build_category_map(tool_registry)

        # Auto-enable memory category when memory tools are registered
        if category_to_tools.get('memory'):
            enabled_category_list.append('memory')

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
                if 'allow_write' in settings:
                    allow_write = settings['allow_write']
                if 'allow_write_categories' in settings:
                    allow_write_categories = settings.get('allow_write_categories', [])

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
            exempt_tools = set()
            if allow_write_categories:
                display_to_key = {
                    info.get('display_name', '').lower(): key
                    for key, info in tool_registry.items()
                }
                for category in allow_write_categories:
                    category_tool_names = category_to_tools.get(category, [])
                    for tool_display_name in category_tool_names:
                        key = display_to_key.get(tool_display_name.lower())
                        if key:
                            exempt_tools.add(key)
                logging.debug(
                    f'Tools exempt from write filter via allow_write_categories: {exempt_tools}'
                )
            apply_write_filter(tool_registry, exempt_tools=exempt_tools)

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
        return category_to_tools

    except Exception as e:
        logging.error(f'Error processing tool filter: {str(e)}')
        # Fall back to built-in category map so _meta.category stamping
        # still works even when filter processing fails.
        return build_category_map(tool_registry) if tool_registry else {}


async def get_tools(tool_registry: dict, config_file_path: str = '') -> dict:
    """Filter and return available tools based on server mode and OpenSearch version.

    In 'multi' mode, returns tools without version filtering or schema stripping,
    but excludes memory tools (which require single-mode OPENSEARCH_URL config).
    In 'single' mode, filters tools based on OpenSearch version compatibility and
    removes base tool arguments from schemas.

    Args:
        tool_registry (dict): The tool registry to filter.
        config_file_path (str): Path to a YAML configuration file

    Returns:
        dict: Dictionary of enabled tools with their configurations
    """
    # Inline import to avoid circular dependency at module load time
    # (server_instructions imports clusters_information which is loaded after tools)
    from mcp_server_opensearch.server_instructions import (
        CONNECTION_OVERRIDE_FIELDS,
        is_dynamic_mode_enabled,
        is_header_auth_enabled,
    )

    # Get the current mode from global state
    mode = get_mode()

    # Resolve and set the global allow_write setting for use by individual tools
    # This needs to be done in both single and multi mode
    resolved_allow_write = _resolve_allow_write_setting(config_file_path)
    set_allow_write_setting(resolved_allow_write)

    # In multi mode, always strip connection override fields — dynamic per-call
    # connection params are a single-mode feature. Multi mode uses
    # opensearch_cluster_name to select a pre-configured cluster.
    # Memory tools are also excluded — they require OPENSEARCH_URL and single-mode
    # connection setup, and are not supported in multi mode.
    if mode == 'multi':
        non_memory = {
            name: info for name, info in tool_registry.items() if not info.get('memory_tool')
        }
        # Drop serverless-incompatible tools when every configured cluster is
        # serverless. Mixed deployments keep them and rely on the call-time guard.
        if _is_serverless_multi_mode():
            filter_serverless_incompatible(non_memory)
        category_to_tools = build_category_map(non_memory)
        tool_to_category = {
            dn.lower(): cat for cat, dns in category_to_tools.items() for dn in dns
        }
        filtered_registry = {}
        for name, info in non_memory.items():
            schema = _strip_schema_fields(info['input_schema'], CONNECTION_OVERRIDE_FIELDS)
            entry = {**info, 'input_schema': schema}
            entry['category'] = tool_to_category.get(info.get('display_name', name).lower(), '')
            filtered_registry[name] = entry
        return filtered_registry

    enabled = {}

    # Get OpenSearch version for compatibility checking (only in single mode)
    version = await get_opensearch_version(baseToolArgs(opensearch_cluster_name=''))
    logging.info(f'Connected OpenSearch version: {version}')

    # A serverless connection cannot answer the version probe (GET / is unsupported),
    # so it returns None and version gating is skipped. Log it and filter the tools
    # serverless cannot serve instead of silently advertising the full catalog.
    serverless = _is_serverless_single_mode()
    if version is None:
        logging.warning(
            'Could not determine OpenSearch version; version-based tool gating is '
            'skipped for this connection.'
            + (' Applying serverless-aware tool filtering.' if serverless else '')
        )

    env_config = {
        'enabled_tools': os.getenv('OPENSEARCH_ENABLED_TOOLS', ''),
        'disabled_tools': os.getenv('OPENSEARCH_DISABLED_TOOLS', ''),
        'tool_categories': os.getenv('OPENSEARCH_TOOL_CATEGORIES', ''),
        'enabled_categories': os.getenv('OPENSEARCH_ENABLED_CATEGORIES', ''),
        'disabled_categories': os.getenv('OPENSEARCH_DISABLED_CATEGORIES', ''),
        'enabled_tools_regex': os.getenv('OPENSEARCH_ENABLED_TOOLS_REGEX', ''),
        'disabled_tools_regex': os.getenv('OPENSEARCH_DISABLED_TOOLS_REGEX', ''),
        'allow_write_categories': parse_comma_separated(
            os.getenv('OPENSEARCH_SETTINGS_ALLOW_WRITE_CATEGORIES', '')
        )
        or None,
    }

    # Check if both config and env variables are set
    if config_file_path and any(env_config.values()):
        logging.warning('Both config file and environment variables are set. Using config file.')

    # Apply tool filtering, update the TOOL_REGISTRY. allow_write comes from
    # _resolve_allow_write_setting so the tool list matches the write check
    # GenericOpenSearchApiTool makes when it's called.
    category_to_tools = process_tool_filter(
        tool_registry=tool_registry,
        allow_write=resolved_allow_write,
        filter_path=config_file_path if config_file_path else None,
        **{k: v for k, v in env_config.items() if not config_file_path},
    )
    tool_to_category = {dn.lower(): cat for cat, dns in category_to_tools.items() for dn in dns}

    for name, info in tool_registry.items():
        # Create a copy to avoid modifying the original tool info
        tool_info = info.copy()
        tool_name = tool_info['display_name']

        # Skip multi-only tools in single mode
        if info.get('multi_only') and mode != 'multi':
            continue

        # Skip tools OpenSearch Serverless cannot serve when connected to a
        # serverless endpoint (version gating can't catch these — the probe fails).
        if serverless and name not in SERVERLESS_COMPATIBLE_TOOLS:
            continue

        # If tool is not compatible with the current OpenSearch version, skip, don't enable
        if not is_tool_compatible(version, info):
            continue

        # Remove baseToolArgs fields from the schema for single mode. opensearch_cluster_name
        # is always hidden (multi-mode only). Connection overrides are hidden unless dynamic
        # mode is on; header auth hides everything since URL/creds come from headers.
        dynamic = is_dynamic_mode_enabled()
        use_header_auth = is_header_auth_enabled()
        if use_header_auth:
            fields_to_strip = set(CONNECTION_OVERRIDE_FIELDS) | {'opensearch_cluster_name'}
        else:
            fields_to_strip = {'opensearch_cluster_name'} | (
                set() if dynamic else CONNECTION_OVERRIDE_FIELDS
            )
        schema = _strip_schema_fields(tool_info['input_schema'], fields_to_strip)

        # In dynamic mode opensearch_url is functionally required at runtime, so mark it
        # required for strict MCP clients — but only when there is no OPENSEARCH_URL fallback
        # and header auth is off (otherwise the URL comes from env or headers, not tool args).
        has_url_fallback = bool(os.getenv('OPENSEARCH_URL', '').strip())
        if (
            dynamic
            and not use_header_auth
            and not has_url_fallback
            and 'opensearch_url' in schema.get('properties', {})
        ):
            schema.setdefault('required', [])
            if 'opensearch_url' not in schema['required']:
                schema['required'].append('opensearch_url')
        tool_info['input_schema'] = schema
        tool_info['category'] = tool_to_category.get(tool_name.lower(), '')

        enabled[tool_name] = tool_info

    return enabled
