# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Install memory hooks for supported AI coding assistants.

Provides a CLI command to install lifecycle hooks that make memory tools
work automatically — searching for relevant context at session start and
saving key facts at session end.

Supported clients:
- Kiro: Writes JSON hook files to .kiro/hooks/
- Claude Code: Patches hooks map in .claude/settings.json
- Cursor: Writes hooks.json to ~/.cursor/hooks.json or .cursor/hooks.json

Usage:
    opensearch-mcp-server-py install-hooks --client kiro
    opensearch-mcp-server-py install-hooks --client claude-code
    opensearch-mcp-server-py install-hooks --client cursor
    opensearch-mcp-server-py install-hooks --client kiro --scope user
"""

import json
import logging
from pathlib import Path


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hook prompt text
# Prompts are written without apostrophes so plain echo is safe to use.
# ---------------------------------------------------------------------------

SEARCH_PROMPT = (
    'Before responding, search memory for relevant context about the '
    'topics in the current message using SearchMemoryTool. This ensures '
    'continuity across sessions.'
)

SAVE_PROMPT = (
    'Before finishing, review the conversation for important facts, decisions, '
    'user preferences, or insights that should persist. Save each as a separate '
    'memory using SaveMemoryTool with appropriate tags.'
)

# ---------------------------------------------------------------------------
# Kiro hook definitions
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Claude Code hook definitions
#
# Schema (verified against https://code.claude.com/docs/en/hooks):
#   settings.json: { "hooks": { EventName: [ { matcher, hooks: [{type, command}] } ] } }
#
# UserPromptSubmit: plain stdout is added as context before Claude responds.
#
# Stop: Claude Code sends { "stop_hook_active": true } in the stdin payload when
#   Claude is already continuing due to a Stop hook. We use this as the loop guard:
#   - First stop (stop_hook_active=false): emit decision:block with the save prompt
#   - Second stop (stop_hook_active=true): exit 0 silently — save already happened
#
# This is the same pattern recommended in the Claude Code hooks docs and used by
# tools like claude-mem to prevent infinite Stop hook loops.
# ---------------------------------------------------------------------------

# No apostrophes in prompts, so plain echo is safe
CLAUDE_CODE_SEARCH_COMMAND = f"echo '{SEARCH_PROMPT}'"

# Stop hook script: reads stop_hook_active from stdin, only blocks on first stop.
# Uses python3 -c to parse stdin JSON — no external dependencies needed.
# The payload is base64-encoded to avoid quoting issues with the JSON content.
import base64 as _base64
_stop_payload = json.dumps({'decision': 'block', 'reason': SAVE_PROMPT})
_stop_payload_b64 = _base64.b64encode(_stop_payload.encode()).decode()
CLAUDE_CODE_STOP_COMMAND = (
    f"python3 -c \""
    f"import json,sys,base64; "
    f"data=json.load(sys.stdin); "
    f"sys.stdout.write('' if data.get('stop_hook_active') "
    f"else base64.b64decode('{_stop_payload_b64}').decode())"
    f"\""
)

# Claude Code settings.json hook map (nested map keyed by event name).
# Each event maps to a list of matcher groups; each group has an inner hooks list.
CLAUDE_CODE_HOOKS_CONFIG = {
    # UserPromptSubmit: plain stdout is added as context before Claude responds.
    'UserPromptSubmit': [
        {
            'matcher': '',
            'hooks': [
                {
                    'type': 'command',
                    'command': CLAUDE_CODE_SEARCH_COMMAND,
                }
            ],
        }
    ],
    # Stop: ask Claude to save memories, but only on the first stop.
    # stop_hook_active=true means we already triggered once — exit silently.
    'Stop': [
        {
            'hooks': [
                {
                    'type': 'command',
                    'command': CLAUDE_CODE_STOP_COMMAND,
                }
            ],
        }
    ],
}

# ---------------------------------------------------------------------------
# Cursor hook definitions
#
# Schema (verified against https://cursor.com/docs/hooks.md):
#   ~/.cursor/hooks.json or .cursor/hooks.json
#   { "version": 1, "hooks": { eventName: [ { "command": "..." } ] } }
#
# sessionStart: output field "additional_context" injects context at session start.
# stop: output field "followup_message" auto-submits a follow-up message.
#
# Prompts contain no apostrophes, so plain echo is safe.
# ---------------------------------------------------------------------------

CURSOR_SESSION_START_COMMAND = f"echo '{json.dumps({'additional_context': SEARCH_PROMPT})}'"
CURSOR_STOP_COMMAND = f"echo '{json.dumps({'followup_message': SAVE_PROMPT})}'"

CURSOR_HOOKS_CONFIG = {
    'version': 1,
    'hooks': {
        # sessionStart: inject search prompt as additional_context at session start.
        'sessionStart': [
            {
                'command': CURSOR_SESSION_START_COMMAND,
            }
        ],
        # stop: emit followup_message to trigger memory save when agent finishes.
        'stop': [
            {
                'command': CURSOR_STOP_COMMAND,
                # loop_limit=1 prevents infinite save loops
                'loop_limit': 1,
            }
        ],
    },
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


def _claude_hooks_already_installed(hooks_map: dict) -> bool:
    """Check if memory hooks are already present in the Claude Code hooks map.

    The hooks map is keyed by event name; each value is a list of matcher
    groups, each of which has an inner ``hooks`` list of {type, command} dicts.
    Detects both the current plain-echo format and any legacy base64 format.
    """
    for _event, matcher_groups in hooks_map.items():
        for group in matcher_groups:
            for hook in group.get('hooks', []):
                command = hook.get('command', '')
                # Check for tool names directly in the command string
                if 'SearchMemoryTool' in command or 'SaveMemoryTool' in command:
                    return True
                # Check legacy base64-encoded format
                if 'base64' in command:
                    try:
                        import base64
                        import re
                        match = re.search(r"b64decode\('([A-Za-z0-9+/=]+)'\)", command)
                        if match:
                            decoded = base64.b64decode(match.group(1)).decode()
                            if 'SearchMemoryTool' in decoded or 'SaveMemoryTool' in decoded:
                                return True
                    except Exception as e:
                        logger.debug(f'Could not decode hook command for idempotency check: {e}')
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

    # hooks is a map keyed by event name in the correct Claude Code schema
    existing_hooks = settings.get('hooks', {})
    if isinstance(existing_hooks, list):
        # Migrate from old flat-list format to the correct nested map format
        existing_hooks = {}

    if _claude_hooks_already_installed(existing_hooks):
        logger.info('Memory hooks already installed in Claude Code settings')
        return []

    # Merge our hook config into the existing map
    for event_name, matcher_groups in CLAUDE_CODE_HOOKS_CONFIG.items():
        if event_name not in existing_hooks:
            existing_hooks[event_name] = []
        existing_hooks[event_name].extend(matcher_groups)

    settings['hooks'] = existing_hooks
    settings_path.write_text(json.dumps(settings, indent=2) + '\n')
    actions = [
        f'Added UserPromptSubmit memory search hook to {settings_path}',
        f'Added Stop memory save hook (with loop guard) to {settings_path}',
    ]
    logger.info(f'Added Claude Code memory hooks to {settings_path}')
    return actions


# ---------------------------------------------------------------------------
# Cursor installation
# ---------------------------------------------------------------------------


def _get_cursor_hooks_path(scope: str) -> Path:
    """Return the Cursor hooks.json path for the given scope."""
    if scope == 'user':
        return Path.home() / '.cursor' / 'hooks.json'
    return Path('.cursor') / 'hooks.json'


def _cursor_hooks_already_installed(hooks_config: dict) -> bool:
    """Check if memory hooks are already present in the Cursor hooks config.

    Detects both the current plain-echo format and any legacy base64 format.
    """
    hooks = hooks_config.get('hooks', {})
    for _event, hook_list in hooks.items():
        for hook in hook_list:
            command = hook.get('command', '')
            if 'SearchMemoryTool' in command or 'SaveMemoryTool' in command:
                return True
            if 'base64' in command:
                try:
                    import base64
                    import re
                    match = re.search(r"b64decode\('([A-Za-z0-9+/=]+)'\)", command)
                    if match:
                        decoded = base64.b64decode(match.group(1)).decode()
                        if 'SearchMemoryTool' in decoded or 'SaveMemoryTool' in decoded:
                            return True
                except Exception as e:
                    logger.debug(f'Could not decode hook command for idempotency check: {e}')
    return False


def _install_cursor_hooks(scope: str) -> list[str]:
    """Install Cursor memory hooks. Returns list of actions taken."""
    hooks_path = _get_cursor_hooks_path(scope)
    hooks_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing hooks config or start fresh
    if hooks_path.exists():
        existing = json.loads(hooks_path.read_text())
    else:
        existing = {'version': 1, 'hooks': {}}

    if _cursor_hooks_already_installed(existing):
        logger.info('Memory hooks already installed in Cursor hooks config')
        return []

    # Ensure version is set
    existing['version'] = 1
    if 'hooks' not in existing:
        existing['hooks'] = {}

    # Merge our hooks into the existing config
    for event_name, hook_list in CURSOR_HOOKS_CONFIG['hooks'].items():
        if event_name not in existing['hooks']:
            existing['hooks'][event_name] = []
        existing['hooks'][event_name].extend(hook_list)

    hooks_path.write_text(json.dumps(existing, indent=2) + '\n')
    actions = [
        f'Added sessionStart memory search hook to {hooks_path}',
        f'Added stop memory save hook to {hooks_path}',
    ]
    logger.info(f'Added Cursor memory hooks to {hooks_path}')
    return actions


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

SUPPORTED_CLIENTS = ['kiro', 'claude-code', 'cursor']


def install_hooks(client: str, scope: str = 'workspace') -> None:
    """Install memory hooks for the specified client.

    Args:
        client: The AI client to install hooks for
                ('kiro', 'claude-code', or 'cursor').
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

    elif client == 'cursor':
        actions = _install_cursor_hooks(scope)
        if actions:
            hooks_path = _get_cursor_hooks_path(scope)
            print(f'Updated {hooks_path}:')
            for action in actions:
                print(f'  {action}')
        else:
            print('All hooks already installed.')

    print('\nRestart your IDE to activate the hooks.')
