# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Interactive installer for OpenSearch MCP Server with agent memory.

Sets up the MCP server configuration and memory hooks for supported AI
coding assistants. Detects installed IDEs and configures each one.

Usage:
    uvx opensearch-mcp-server-py install
    pip run opensearch-mcp-server-py install
    opensearch-mcp-server-py install
"""

import json
import logging
from .install_hooks import (
    SAVE_PROMPT,
    SEARCH_PROMPT,
)
from pathlib import Path


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# IDE detection
# ---------------------------------------------------------------------------

IDE_CONFIGS = {
    'kiro': {
        'name': 'Kiro',
        'mcp_path': Path.home() / '.kiro' / 'settings' / 'mcp.json',
        'steering_path': Path.home() / '.kiro' / 'steering' / 'opensearch-memory.md',
    },
    'claude-code': {
        'name': 'Claude Code',
        'mcp_path': Path.home() / '.claude.json',
    },
    'cursor': {
        'name': 'Cursor',
        'mcp_path': Path.home() / '.cursor' / 'mcp.json',
    },
}


def _detect_ides() -> list[str]:
    """Detect which IDEs are installed by checking config directories."""
    detected = []
    ide_dirs = {
        'kiro': Path.home() / '.kiro',
        'claude-code': Path.home() / '.claude',
        'cursor': Path.home() / '.cursor',
    }
    for ide_id, config_dir in ide_dirs.items():
        if config_dir.exists():
            detected.append(ide_id)
    return detected


# ---------------------------------------------------------------------------
# MCP server configuration
# ---------------------------------------------------------------------------


def _build_mcp_server_config(
    opensearch_url: str,
    aws_region: str,
    aws_profile: str,
    from_git: str = '',
    from_local: str = '',
) -> dict:
    """Build the MCP server configuration block.

    Args:
        opensearch_url: The OpenSearch endpoint URL.
        aws_region: AWS region for the OpenSearch cluster.
        aws_profile: AWS profile name, or empty for default credentials.
        from_git: If set, use ``uvx --from "git+<url>"`` instead of the
            PyPI release.  Useful for testing pre-release branches.
        from_local: If set, use ``uv run --directory <path>`` to run from
            a local source checkout.  Useful for local development.
    """
    env = {
        'OPENSEARCH_URL': opensearch_url,
        'AWS_REGION': aws_region,
        'AWS_OPENSEARCH_SERVERLESS': 'true',
        'MEMORY_TOOLS_ENABLED': 'true',
        'OPENSEARCH_DISABLED_CATEGORIES': 'core_tools,skills',
    }
    if aws_profile:
        env['AWS_PROFILE'] = aws_profile

    if from_local:
        command = 'uv'
        args = ['run', '--directory', from_local, 'opensearch-mcp-server-py']
    elif from_git:
        command = 'uvx'
        args = ['--from', f'git+{from_git}', 'opensearch-mcp-server-py']
    else:
        command = 'uvx'
        args = ['opensearch-mcp-server-py']

    return {
        'command': command,
        'args': args,
        'env': env,
        # autoApprove is NOT included here — it's Kiro-specific
    }


def _configure_kiro_mcp(mcp_config: dict) -> str:
    """Configure MCP server in Kiro settings. Returns action description."""
    mcp_path = IDE_CONFIGS['kiro']['mcp_path']
    mcp_path.parent.mkdir(parents=True, exist_ok=True)

    if mcp_path.exists():
        settings = json.loads(mcp_path.read_text())
    else:
        settings = {'mcpServers': {}}

    if 'mcpServers' not in settings:
        settings['mcpServers'] = {}

    server_key = 'opensearch-memory'
    if server_key in settings['mcpServers']:
        return f'  MCP server already configured in {mcp_path}'

    # Add Kiro-specific autoApprove for SearchMemoryTool only
    # (Save/Delete require explicit approval for security)
    kiro_config = dict(mcp_config)
    kiro_config['autoApprove'] = ['SearchMemoryTool']
    settings['mcpServers'][server_key] = kiro_config
    mcp_path.write_text(json.dumps(settings, indent=2) + '\n')
    return f'  Configured MCP server in {mcp_path}'


def _configure_claude_code_mcp(mcp_config: dict) -> str:
    """Configure MCP server in Claude Code settings. Returns action description.

    Writes to ~/.claude.json, which is Claude Code's user-level MCP config.
    Merges into the existing file without clobbering other top-level keys
    (e.g. projects, oauthAccount, numStartups).
    """
    mcp_path = IDE_CONFIGS['claude-code']['mcp_path']
    # ~/.claude.json lives directly in home — no subdirectory to create
    if mcp_path.parent != Path.home():
        mcp_path.parent.mkdir(parents=True, exist_ok=True)

    if mcp_path.exists():
        try:
            settings = json.loads(mcp_path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f'Could not read {mcp_path}: {e}. Skipping Claude Code MCP config.')
            return f'  Skipped {mcp_path} (could not parse existing file)'
    else:
        settings = {}

    if 'mcpServers' not in settings:
        settings['mcpServers'] = {}

    server_key = 'opensearch-memory'
    if server_key in settings['mcpServers']:
        return f'  MCP server already configured in {mcp_path}'

    settings['mcpServers'][server_key] = mcp_config
    mcp_path.write_text(json.dumps(settings, indent=2) + '\n')
    return f'  Configured MCP server in {mcp_path}'


def _configure_cursor_mcp(mcp_config: dict) -> str:
    """Configure MCP server in Cursor settings. Returns action description."""
    mcp_path = IDE_CONFIGS['cursor']['mcp_path']
    mcp_path.parent.mkdir(parents=True, exist_ok=True)

    if mcp_path.exists():
        settings = json.loads(mcp_path.read_text())
    else:
        settings = {'mcpServers': {}}

    if 'mcpServers' not in settings:
        settings['mcpServers'] = {}

    server_key = 'opensearch-memory'
    if server_key in settings['mcpServers']:
        return f'  MCP server already configured in {mcp_path}'

    settings['mcpServers'][server_key] = mcp_config
    mcp_path.write_text(json.dumps(settings, indent=2) + '\n')
    return f'  Configured MCP server in {mcp_path}'


# ---------------------------------------------------------------------------
# Steering / hooks installation
# ---------------------------------------------------------------------------

KIRO_STEERING_CONTENT = f"""\
---
inclusion: always
---

# OpenSearch Agent Memory

This steering file enables persistent memory for AI agents via OpenSearch.

## Memory Behavior

- **At conversation start**: Search memory for relevant context about the
  topics in the user's message using SearchMemoryTool.
- **During conversation**: Save important facts, decisions, user preferences,
  and insights immediately as they arise using SaveMemoryTool with appropriate
  tags. Don't wait until the end.
- **Before finishing**: Do a final check to capture anything missed.

## Tool Reference

- **SearchMemoryTool**: {SEARCH_PROMPT}
- **SaveMemoryTool**: {SAVE_PROMPT}
"""


def _install_kiro_steering() -> str:
    """Install global Kiro steering file for memory behavior."""
    steering_path = IDE_CONFIGS['kiro']['steering_path']
    steering_path.parent.mkdir(parents=True, exist_ok=True)

    if steering_path.exists():
        return f'  Steering file already exists: {steering_path}'

    steering_path.write_text(KIRO_STEERING_CONTENT)
    return f'  Created steering file: {steering_path}'


CLAUDE_MD_CONTENT = f"""\

## OpenSearch Agent Memory

- {SEARCH_PROMPT}
- {SAVE_PROMPT}
"""


def _install_claude_md() -> str:
    """Append memory instructions to CLAUDE.md if not already present."""
    claude_md = Path.home() / '.claude' / 'CLAUDE.md'
    claude_md.parent.mkdir(parents=True, exist_ok=True)

    if claude_md.exists():
        content = claude_md.read_text()
        if 'OpenSearch Agent Memory' in content:
            return f'  Memory instructions already in {claude_md}'
        with open(claude_md, 'a') as f:
            f.write(CLAUDE_MD_CONTENT)
        return f'  Appended memory instructions to {claude_md}'

    claude_md.write_text(CLAUDE_MD_CONTENT.lstrip())
    return f'  Created {claude_md} with memory instructions'


# ---------------------------------------------------------------------------
# Interactive installer
# ---------------------------------------------------------------------------


def _prompt(message: str, default: str = '') -> str:
    """Prompt user for input with optional default."""
    if default:
        user_input = input(f'{message} [{default}]: ').strip()
        return user_input or default
    return input(f'{message}: ').strip()


def _prompt_yes_no(message: str, default: bool = True) -> bool:
    """Prompt user for yes/no with default."""
    suffix = '[Y/n]' if default else '[y/N]'
    response = input(f'{message} {suffix}: ').strip().lower()
    if not response:
        return default
    return response in ('y', 'yes')


def run_install(from_git: str = '', from_local: str = '') -> None:
    """Run the interactive installer.

    Args:
        from_git: Git URL to install from (e.g. a fork/branch) instead of PyPI.
        from_local: Local source path to run from (e.g. current workspace).
    """
    print()
    print('OpenSearch MCP Server — Memory Setup')
    print('=' * 40)
    print()

    # Step 1: Collect OpenSearch connection details
    print('Step 1: OpenSearch Connection')
    print('-' * 30)
    opensearch_url = _prompt(
        'OpenSearch Serverless endpoint URL',
        '',
    )
    if not opensearch_url:
        print('Error: OpenSearch URL is required.')
        return

    # Extract region from URL if possible
    default_region = 'us-east-1'
    if '.aoss.amazonaws.com' in opensearch_url:
        parts = opensearch_url.split('.')
        for i, part in enumerate(parts):
            if part == 'aoss':
                default_region = parts[i - 1]
                break

    aws_region = _prompt('AWS region', default_region)
    aws_profile = _prompt('AWS profile (leave empty for default credentials)', '')
    print()

    # Step 2: Detect IDEs
    print('Step 2: IDE Detection')
    print('-' * 30)
    detected = _detect_ides()

    if not detected:
        print('No supported IDEs detected (Kiro, Claude Code, Cursor).')
        print('You can manually configure the MCP server. See MEMORY.md for details.')
        return

    ide_names = [IDE_CONFIGS[ide]['name'] for ide in detected]
    print(f'Detected: {", ".join(ide_names)}')
    print()

    # Step 3: Configure each IDE
    print('Step 3: Configuration')
    print('-' * 30)

    mcp_config = _build_mcp_server_config(
        opensearch_url, aws_region, aws_profile, from_git, from_local
    )
    actions = []

    for ide_id in detected:
        ide_name = IDE_CONFIGS[ide_id]['name']
        if not _prompt_yes_no(f'Configure {ide_name}?'):
            continue

        # Configure MCP server
        if ide_id == 'kiro':
            actions.append(_configure_kiro_mcp(mcp_config))
            actions.append(_install_kiro_steering())
        elif ide_id == 'claude-code':
            actions.append(_configure_claude_code_mcp(mcp_config))
            actions.append(_install_claude_md())
        elif ide_id == 'cursor':
            actions.append(_configure_cursor_mcp(mcp_config))
            # Install Cursor hooks for memory search/save
            from .install_hooks import _install_cursor_hooks

            cursor_hook_actions = _install_cursor_hooks('user')
            actions.extend(
                cursor_hook_actions
                if cursor_hook_actions
                else ['  Cursor hooks already installed.']
            )

    print()
    print('Done!')
    print('-' * 30)
    for action in actions:
        print(action)

    print()
    print('Restart your IDE(s) to activate agent memory.')
    print()
