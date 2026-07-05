# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import copy
import logging
import os
import re
import yaml
from tools.tools import TOOL_REGISTRY as default_tool_registry
from typing import Any, Dict


# Constants for field names
DISPLAY_NAME_STRING = 'display_name'
DESCRIPTION_STRING = 'description'
ARGS_STRING = 'args'
MAX_SIZE_LIMIT = 'max_size_limit'

# Regex pattern for tool display name validation
DISPLAY_NAME_PATTERN = r'^[a-zA-Z0-9_-]+$'


def is_valid_display_name_pattern(name: str) -> bool:
    """Check if a display name follows the required pattern.

    :param name: The name to validate
    :return: True if valid, False otherwise
    """
    return re.match(DISPLAY_NAME_PATTERN, name) is not None


def _parse_args_map(tool_name: str, raw_args: Any) -> dict[str, dict[str, str]]:
    if not isinstance(raw_args, dict):
        logging.warning(
            f"Invalid 'args' for tool '{tool_name}'. Must be a mapping of arg -> string."
        )
        return {}
    parsed: dict[str, dict[str, str]] = {}
    for arg_name, value in raw_args.items():
        if isinstance(value, str):
            parsed[arg_name] = {DESCRIPTION_STRING: value}
        else:
            raise ValueError(
                f"Description for argument '{arg_name}' in tool '{tool_name}' must be a string."
            )
    return parsed


def _load_config_from_file(config_from_file: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    file_configs: dict[str, dict[str, Any]] = {}
    for tool_name, custom in (config_from_file or {}).items():
        out: dict[str, Any] = {}

        for key, value in (custom or {}).items():
            if key == ARGS_STRING:
                if parsed_args := _parse_args_map(tool_name, value):
                    out.setdefault(ARGS_STRING, {}).update(parsed_args)
                continue
            if key in (DISPLAY_NAME_STRING, DESCRIPTION_STRING, MAX_SIZE_LIMIT):
                out[key] = value
                continue
            # Disallow non-standard top-level fields in YAML config
            raise ValueError(
                f"Invalid field '{key}' for tool '{tool_name}' in config file. "
                f"Only '{DISPLAY_NAME_STRING}', '{DESCRIPTION_STRING}' and '{ARGS_STRING}' are supported."
            )

        file_configs[tool_name] = out

    return file_configs


def _put_nested_dict(nested: dict, keys: list[str], value: Any) -> dict:
    current = nested
    for key in keys[:-1]:
        if not isinstance(current.get(key), dict):
            current[key] = {}
        current = current[key]
    # Coerce common scalar types using YAML parser (bool/int/float/null/quoted strings, etc.)
    if isinstance(value, str) and value.strip():
        try:
            coerced = yaml.safe_load(value)
        except Exception:
            coerced = value
    else:
        coerced = value
    current[keys[-1]] = coerced
    return nested


def parse_cli_to_nested_config(cli_tool_overrides: Dict[str, str]) -> Dict[str, Dict[str, Any]]:
    """Parse generic CLI overrides of the form 'tool.<ToolName>.<path>=<value>' into a nested dict.

    Examples:
    - tool.ListIndexTool.http_methods=POST
      -> { 'ListIndexTool': { 'http_methods': 'POST' } }

    - tool.ListIndexTool.args.index.required=true
      -> { 'ListIndexTool': { 'args': { 'index': { 'required': True } } } }

    :param cli_tool_overrides: Mapping of CLI key -> value
    :return: Nested overrides per tool name
    """
    if not cli_tool_overrides:
        return {}

    nested = {}
    for full_key, raw_value in cli_tool_overrides.items():
        nested_keys = [key for key in full_key.split('.') if key != '']
        if len(nested_keys) < 3 or nested_keys[0] != 'tool':
            continue
        # Only allow top-level fields: display_name, description, args
        top_field = nested_keys[2]
        if top_field not in (DISPLAY_NAME_STRING, DESCRIPTION_STRING, ARGS_STRING, MAX_SIZE_LIMIT):
            continue
        nested = _put_nested_dict(nested, nested_keys[1:], raw_value)

    return nested


def _validate_config(
    config: Dict[str, Dict[str, Any]], reference_registry: Dict[str, Any]
) -> None:
    """Validate the configuration.

    Checks:
    1. All tool names exist in the default registry
    2. No duplicate display names will be created
    3. All display names follow the required pattern

    :param config: The configuration to validate
    """
    # Track available tool names (original names minus configured ones)
    # Build available tool names from both reference and default registries
    available_tool_names = set(default_tool_registry.keys()) | set(reference_registry.keys())

    # Validate that all configured tools exist
    for original_name in config.keys():
        if original_name not in available_tool_names:
            raise ValueError(f"Tool '{original_name}' is not a valid tool name.")
        available_tool_names.remove(original_name)

    # Check for duplicate display names
    for original_name, custom_config in config.items():
        custom_display_name = custom_config.get(DISPLAY_NAME_STRING)
        if custom_display_name:
            if custom_display_name in available_tool_names:
                raise ValueError(
                    f"Display name '{custom_display_name}' conflicts with another tool."
                )
            available_tool_names.add(custom_display_name)

    # Validate display name patterns
    for original_name, custom_config in config.items():
        custom_display_name = custom_config.get(DISPLAY_NAME_STRING)
        if custom_display_name and not is_valid_display_name_pattern(custom_display_name):
            raise ValueError(
                f"Display name '{custom_display_name}' for tool '{original_name}' "
                f"does not follow the required pattern '{DISPLAY_NAME_PATTERN}'."
            )

    # Validate args customizations
    for original_name, custom_config in config.items():
        if ARGS_STRING in custom_config:
            # Prefer registry that contains input_schema properties
            tool_info_ref = reference_registry.get(original_name)
            tool_info_def = default_tool_registry.get(original_name)
            def_has_props = bool((tool_info_def or {}).get('input_schema', {}).get('properties'))
            ref_has_props = bool((tool_info_ref or {}).get('input_schema', {}).get('properties'))
            if ref_has_props:
                tool_info = tool_info_ref
            elif def_has_props:
                tool_info = tool_info_def
            else:
                tool_info = tool_info_ref or tool_info_def
            if not tool_info:
                raise ValueError(f"Tool '{original_name}' is not a valid tool name.")
            properties = (tool_info.get('input_schema') or {}).get('properties') or {}
            for arg_name, overrides in custom_config[ARGS_STRING].items():
                if arg_name not in properties:
                    raise ValueError(
                        f"Argument '{arg_name}' does not exist on tool '{original_name}'."
                    )
                # Only description supported now
                desc_val = overrides.get(DESCRIPTION_STRING)
                if desc_val is not None and not isinstance(desc_val, str):
                    raise ValueError(
                        f"Description for argument '{arg_name}' in tool '{original_name}' must be a string."
                    )


def _apply_validated_configs(
    custom_registry: Dict[str, Any], configs: Dict[str, Dict[str, Any]]
) -> None:
    """Apply validated configurations to the registry.

    :param custom_registry: The registry to modify
    :param configs: Dictionary of tool names and their custom configurations
    """
    for original_tool_name, custom_config in configs.items():
        if original_tool_name not in custom_registry:
            continue

        tool_info = custom_registry[original_tool_name]

        for field_name, field_value in custom_config.items():
            if field_name == ARGS_STRING:
                # Start from the tool's existing schema, falling back to default registry if missing
                base_schema = (
                    tool_info.get('input_schema')
                    or (default_tool_registry.get(original_tool_name) or {}).get('input_schema')
                    or {}
                )
                input_schema = copy.deepcopy(base_schema)
                properties = input_schema.get('properties') or {}
                args_model = tool_info.get('args_model')

                for arg_name, overrides in field_value.items():
                    if DESCRIPTION_STRING in overrides and arg_name in properties:
                        properties[arg_name]['description'] = overrides[DESCRIPTION_STRING]
                        try:
                            if (
                                args_model
                                and hasattr(args_model, 'model_fields')
                                and arg_name in args_model.model_fields
                            ):
                                args_model.model_fields[arg_name].description = overrides[
                                    DESCRIPTION_STRING
                                ]
                        except Exception:
                            pass
                tool_info['input_schema'] = input_schema
            else:
                tool_info[field_name] = field_value


def _apply_memory_container_defaults(custom_registry: Dict[str, Any], container_id: str) -> None:
    """Set memory_container_id as a default in the input_schema of all agentic memory tools.

    This modifies the JSON schema so that:
    1. MCP clients see the default value (and the field is no longer required)
    2. validate_args_for_mode can inject it at runtime when agents omit it

    :param custom_registry: The registry to modify
    :param container_id: The memory container ID to set as default
    """
    agentic_memory_tool_names = [
        'CreateAgenticMemorySessionTool',
        'AddAgenticMemoriesTool',
        'GetAgenticMemoryTool',
        'UpdateAgenticMemoryTool',
        'DeleteAgenticMemoryByIDTool',
        'DeleteAgenticMemoryByQueryTool',
        'SearchAgenticMemoryTool',
    ]

    for tool_name in agentic_memory_tool_names:
        if tool_name not in custom_registry:
            continue

        tool_info = custom_registry[tool_name]
        base_schema = tool_info.get('input_schema') or {}
        input_schema = copy.deepcopy(base_schema)
        properties = input_schema.get('properties') or {}

        if 'memory_container_id' in properties:
            properties['memory_container_id']['default'] = container_id
            if 'required' in input_schema and 'memory_container_id' in input_schema['required']:
                input_schema['required'].remove('memory_container_id')

        tool_info['input_schema'] = input_schema


def apply_custom_tool_config(
    tool_registry: Dict[str, Any],
    config_file_path: str,
    cli_tool_overrides: Dict[str, str],
) -> Dict[str, Any]:
    """Apply custom configurations to the tool registry from YAML file and command-line arguments.

    Priority order:
    1. Config file settings (if config file is provided, CLI is completely ignored)
    2. CLI argument settings (only used if no config file is provided)

    Additionally, if memory_container_id is configured (via config file or environment variable),
    it will be automatically set as a default value for all agentic memory tools.

    :param tool_registry: The original tool registry
    :param config_file_path: Path to the YAML configuration file
    :param cli_tool_overrides: Dictionary of tool overrides from command line
    :return: A new tool registry with custom configurations applied
    """
    custom_registry = copy.deepcopy(tool_registry)

    # Apply memory_container_id defaults to agentic memory tools
    container_id = get_memory_container_id_from_config(config_file_path)
    if container_id:
        _apply_memory_container_defaults(custom_registry, container_id)

    # Load configuration from file
    config_from_file = {}
    if config_file_path:
        try:
            with open(config_file_path, 'r') as f:
                config = yaml.safe_load(f)
                if config and 'tools' in config:
                    config_from_file = config['tools']
        except Exception as e:
            logging.error(f'Error loading tool config file: {e}')

    # Load configurations from appropriate source
    if config_from_file:
        # Use config file and completely ignore CLI
        file_configs = _load_config_from_file(config_from_file)
        if file_configs:
            _validate_config(file_configs, custom_registry)
            _apply_validated_configs(custom_registry, file_configs)
    else:
        # Use CLI arguments only if no config file
        cli_configs = parse_cli_to_nested_config(cli_tool_overrides)
        if cli_configs:
            _validate_config(cli_configs, custom_registry)
            _apply_validated_configs(custom_registry, cli_configs)

    # Update the default registry
    default_tool_registry.update(custom_registry)

    return custom_registry


def get_memory_container_id_from_config(config_file_path: str = '') -> str:
    """Get memory container ID from config file or environment variable.

    Priority order:
    1. Config file (if provided and contains agentic_memory.memory_container_id)
    2. Environment variable OPENSEARCH_MEMORY_CONTAINER_ID

    :param config_file_path: Path to the YAML configuration file
    :return: Memory container ID or empty string if not found
    """
    container_id = ''

    if config_file_path:
        try:
            with open(config_file_path, 'r') as f:
                config = yaml.safe_load(f)
                if config:
                    agentic_memory_config = config.get('agentic_memory', {})
                    if isinstance(agentic_memory_config, dict):
                        container_id = agentic_memory_config.get('memory_container_id', '')
                        if container_id:
                            logging.info(
                                f'Using memory_container_id from config file: {container_id}'
                            )
                            return container_id
        except Exception as e:
            logging.debug(
                f'Could not load memory_container_id from config file {config_file_path}: {e}'
            )

    container_id = os.getenv('OPENSEARCH_MEMORY_CONTAINER_ID', '')
    if container_id:
        logging.info(f'Using memory_container_id from environment variable: {container_id}')

    return container_id
