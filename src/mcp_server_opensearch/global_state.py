# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Global state management for the OpenSearch MCP Server.

This module provides a centralized way to store and access the current server mode,
profile, and config file path that need to be available throughout the application.
"""

import logging
from typing import Optional


# Global variables
_current_mode: Optional[str] = None
_current_profile: Optional[str] = None
_current_config_file_path: Optional[str] = None

logger = logging.getLogger(__name__)


def set_mode(mode: str) -> None:
    """Set the current server mode.

    Args:
        mode: The server mode ('single' or 'multi')
    """
    global _current_mode
    _current_mode = mode
    logger.debug(f'Set global mode to: {mode}')


def get_mode() -> str:
    """Get the current server mode.

    Returns:
        str: The current server mode ('single' or 'multi'). Defaults to 'single' if not set.
    """
    global _current_mode
    if _current_mode is None:
        logger.debug('Mode not set, defaulting to "single" mode')
        return 'single'
    return _current_mode


def set_profile(profile: str) -> None:
    """Set the current AWS profile.

    Args:
        profile: The AWS profile name
    """
    global _current_profile
    _current_profile = profile
    logger.debug(f'Set global profile to: {profile}')


def get_profile() -> str:
    """Get the current AWS profile.

    Returns:
        str: The current AWS profile. Returns empty string if not set.
    """
    global _current_profile
    return _current_profile or ''


def set_config_file_path(config_file_path: str) -> None:
    """Set the current config file path.

    Args:
        config_file_path: The path to the configuration file
    """
    global _current_config_file_path
    _current_config_file_path = config_file_path
    logger.debug(f'Set global config_file_path to: {config_file_path}')


def get_config_file_path() -> str:
    """Get the current config file path.

    Returns:
        str: The current config file path. Returns empty string if not set.
    """
    global _current_config_file_path
    return _current_config_file_path or ''
