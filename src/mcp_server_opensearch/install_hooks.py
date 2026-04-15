# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Install memory hooks for supported AI coding assistants.

Provides a CLI command to install lifecycle hooks that make memory tools
work automatically — searching for relevant context at session start and
saving key facts at session end.

Supported clients:
- Kiro: Writes JSON hook files to .kiro/hooks/ or ~/.kiro/hooks/
- Claude Code: Patches hooks array in .claude/settings.json or ~/.claude/settings.json

Usage:
    opensearch-mcp-server-py install-hooks --client kiro
    opensearch-mcp-server-py install-hooks --client claude-code
    opensearch-mcp-server-py install-hooks --client kiro --scope user
"""

import json
import logging
from pathlib import Path


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hook definitions
# ---------------------------------------------------------------------------

SEARCH_PROMPT = (
    'Before responding, search memory for any relevant context about the '
    'topics in the user\'s message using SearchMemoryTool. This ensures '
    'continuity across sessions.'
)

SAVE_PROMPT = (
    'Before finishing, review the conversation for important facts, decisions, '
    'user preferences, or insights that should persist. Save each as a separate '
    'memory using SaveMemoryTool with appropriate tags.'
)

# Kiro hook definitions
KIRO_SEARCH_HOOK = {
    'name': 'Memory: Search on prompt',
    'version': '1.0.0',
    'description': (
        'Searches memory for relevant context before every response. '
        'Installed by opensearch-mcp-server-py.'
    ),
    'when': {
        'type': 'promptSubmit',
    },
    'then': {
        'type': 'askAgent',
        'prompt': SEARCH_PROMPT,
    },
}

KIRO_SAVE_HOOK = {
    'name': 'Memory: Save on stop',
    'version': '1.0.0',
    'description': (
        'Saves important facts and decisions to memory after every conversation. '
        'Installed by opensearch-mcp-server-py.'
    ),
    'when': {
        'type': 'agentStop',
    },
    'then': {
        'type': 'askAgent',
        'prompt': SAVE_PROMPT,
    },
}

# Claude Code hook definitions
CLAUDE_CODE_SEARCH_HOOK = {
    'matcher': '',
    'event': 'UserPromptSubmit',
    'type': 'command',
    'command': (
        'echo \'{"additionalContext": "' + SEARCH_PROMPT.replace("'", "\\'") + '"}\''
    ),
}

CLAUDE_CODE_SAVE_HOOK = {
    'matcher': '',
    'event': 'Stop',
    'type': 'command',
    'command': (
        'echo \'{"additionalContext": "' + SAVE_PROMPT.replace("'", "\\'") + '"}\''
    ),
}


# ---------------------------------------------------------------------------
# Kiro installation
# ---------------------------------------------------------------------------


def _get_kiro_hooks_dir(scope: str) -> Path:
    """Return the Kiro hooks directory for the given scope.

    Note: Kiro only reads hooks from the workspace .kiro/hooks/ directory.
    The user scope is not supported — hooks are always workspace-scoped.
    """
    if scope == 'user':
        logger.warning(
            'Kiro only reads hooks from workspace .kiro/hooks/. '
            'Installing at workspace scope instead.'
        )
    return Path('.kiro') / 'hooks'


def _install_kiro_hooks(scope: str) -> list[str]:
    """Install Kiro memory hooks. Returns list of created file paths."""
    hooks_dir = _get_kiro_hooks_dir(scope)
    hooks_dir.mkdir(parents=True, exist_ok=True)

    created = []
    hooks = {
        'memory-search-on-prompt.json': KIRO_SEARCH_HOOK,
        'memory-save-on-stop.json': KIRO_SAVE_HOOK,
    }

    for filename, hook_def in hooks.items():
        hook_path = hooks_dir / filename
        if hook_path.exists():
            logger.info(f'Hook already exists, skipping: {hook_path}')
            continue

        hook_path.write_text(json.dumps(hook_def, indent=2) + '\n')
        created.append(str(hook_path))
        logger.info(f'Created hook: {hook_path}')

    return created


# ---------------------------------------------------------------------------
# Claude Code installation
# ---------------------------------------------------------------------------


def _get_claude_settings_path(scope: str) -> Path:
    """Return the Claude Code settings.json path for the given scope."""
    if scope == 'user':
        return Path.home() / '.claude' / 'settings.json'
    return Path('.claude') / 'settings.json'


def _hook_already_installed(existing_hooks: list, new_hook: dict) -> bool:
    """Check if a hook with the same event and memory-related command already exists."""
    for hook in existing_hooks:
        if hook.get('event') != new_hook.get('event'):
            continue
        command = hook.get('command', '')
        if 'SearchMemoryTool' in command or 'SaveMemoryTool' in command:
            return True
    return False


def _install_claude_code_hooks(scope: str) -> list[str]:
    """Install Claude Code memory hooks. Returns list of actions taken."""
    settings_path = _get_claude_settings_path(scope)
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing settings or start fresh
    if settings_path.exists():
        settings = json.loads(settings_path.read_text())
    else:
        settings = {}

    existing_hooks = settings.get('hooks', [])
    actions = []

    for hook_def in [CLAUDE_CODE_SEARCH_HOOK, CLAUDE_CODE_SAVE_HOOK]:
        if _hook_already_installed(existing_hooks, hook_def):
            logger.info(f'Hook already installed for event: {hook_def["event"]}')
            continue
        existing_hooks.append(hook_def)
        actions.append(f'Added {hook_def["event"]} hook')
        logger.info(f'Added {hook_def["event"]} hook to {settings_path}')

    if actions:
        settings['hooks'] = existing_hooks
        settings_path.write_text(json.dumps(settings, indent=2) + '\n')

    return actions


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

SUPPORTED_CLIENTS = ['kiro', 'claude-code']


def install_hooks(client: str, scope: str = 'workspace') -> None:
    """Install memory hooks for the specified client.

    Args:
        client: The AI client to install hooks for ('kiro' or 'claude-code').
        scope: Where to install — 'workspace' (project-level) or 'user' (global).
    """
    if client not in SUPPORTED_CLIENTS:
        print(f'Error: Unsupported client "{client}". Supported: {", ".join(SUPPORTED_CLIENTS)}')
        return

    if scope not in ('workspace', 'user'):
        print(f'Error: Unsupported scope "{scope}". Use "workspace" or "user".')
        return

    print(f'Installing memory hooks for {client} (scope: {scope})...')

    if client == 'kiro':
        created = _install_kiro_hooks(scope)
        if created:
            print(f'Created {len(created)} hook(s):')
            for path in created:
                print(f'  {path}')
        else:
            print('All hooks already installed.')

    elif client == 'claude-code':
        actions = _install_claude_code_hooks(scope)
        if actions:
            settings_path = _get_claude_settings_path(scope)
            print(f'Updated {settings_path}:')
            for action in actions:
                print(f'  {action}')
        else:
            print('All hooks already installed.')

    print('\nRestart your IDE to activate the hooks.')
