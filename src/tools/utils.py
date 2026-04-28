# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import json
import logging
import yaml
from semver import Version


def format_json(data) -> str:
    """Format data as compact JSON with non-ASCII character preservation.

    All tool responses should use this function instead of calling json.dumps
    directly to ensure consistent formatting across the codebase.
    """
    return json.dumps(data, separators=(',', ':'), ensure_ascii=False)


def is_tool_compatible(current_version: Version | None, tool_info: dict = {}):
    """Check if a tool is compatible with the current OpenSearch version.

    Args:
        current_version (Version): The current OpenSearch version
        tool_info (dict): Tool information containing min_version and max_version

    Returns:
        bool: True if the tool is compatible, False otherwise
    """
    # Find a version equivalent in serverless mode
    if not current_version:
        return True
    min_tool_version = Version.parse(
        tool_info.get('min_version', '0.0.0'), optional_minor_and_patch=True
    )
    max_tool_version = Version.parse(
        tool_info.get('max_version', '99.99.99'), optional_minor_and_patch=True
    )
    return min_tool_version <= current_version <= max_tool_version


def parse_comma_separated(text, separator=','):
    """Parse a comma-separated string into a list of trimmed values."""
    if not text:
        return []
    return [item.strip() for item in text.split(separator) if item.strip()]


def load_yaml_config(filter_path):
    """Load and validate YAML configuration file."""
    if not filter_path:
        return None
    try:
        with open(filter_path, 'r') as f:
            config = yaml.safe_load(f)
        if not isinstance(config, dict):
            logging.warning(f'Invalid tool filter configuration in {filter_path}')
            return None
        return config
    except Exception as e:
        logging.error(f'Error loading filter config: {str(e)}')
        return None


def validate_tools(tool_list, display_lookup, source_name):
    """Validate tools against registry and return valid tools."""
    valid_tools = set()
    for tool in tool_list:
        tool_lower = tool.lower()
        # Check if it matches tool display name
        if tool_lower in display_lookup:
            actual_tool = display_lookup[tool_lower]
            valid_tools.add(actual_tool.lower())
        else:
            logging.warning(f"Ignoring invalid tool from '{source_name}': '{tool}'")
    return valid_tools
