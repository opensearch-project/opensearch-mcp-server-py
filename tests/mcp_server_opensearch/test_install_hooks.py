# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import json
import pytest
from mcp_server_opensearch.install_hooks import (
    KIRO_SAVE_HOOK,
    KIRO_SEARCH_HOOK,
    install_hooks,
)
from unittest.mock import patch


@pytest.fixture
def tmp_workspace(tmp_path):
    """Provide a temporary workspace directory."""
    return tmp_path


class TestInstallKiroHooks:
    """Tests for Kiro hook installation."""

    def test_creates_hook_files(self, tmp_workspace):
        """Install creates both hook files in .kiro/hooks/."""
        hooks_dir = tmp_workspace / '.kiro' / 'hooks'
        with patch(
            'mcp_server_opensearch.install_hooks._get_kiro_hooks_dir',
            return_value=hooks_dir,
        ):
            install_hooks(client='kiro', scope='workspace')

        search_hook = hooks_dir / 'memory-search-on-prompt.json'
        save_hook = hooks_dir / 'memory-save-on-stop.json'

        assert search_hook.exists()
        assert save_hook.exists()

        search_data = json.loads(search_hook.read_text())
        assert search_data['when']['type'] == 'promptSubmit'
        assert search_data['then']['type'] == 'askAgent'
        assert 'SearchMemoryTool' in search_data['then']['prompt']

        save_data = json.loads(save_hook.read_text())
        assert save_data['when']['type'] == 'agentStop'
        assert save_data['then']['type'] == 'askAgent'
        assert 'SaveMemoryTool' in save_data['then']['prompt']

    def test_idempotent_skips_existing(self, tmp_workspace):
        """Running install twice does not overwrite existing hooks."""
        hooks_dir = tmp_workspace / '.kiro' / 'hooks'
        hooks_dir.mkdir(parents=True)

        # Write a hook with custom content
        existing = hooks_dir / 'memory-search-on-prompt.json'
        existing.write_text('{"custom": true}')

        with patch(
            'mcp_server_opensearch.install_hooks._get_kiro_hooks_dir',
            return_value=hooks_dir,
        ):
            install_hooks(client='kiro', scope='workspace')

        # Original content preserved
        assert json.loads(existing.read_text()) == {'custom': True}
        # Second hook still created
        assert (hooks_dir / 'memory-save-on-stop.json').exists()

    def test_creates_directory_if_missing(self, tmp_workspace):
        """Install creates the hooks directory if it doesn't exist."""
        hooks_dir = tmp_workspace / 'new' / 'path' / 'hooks'
        assert not hooks_dir.exists()

        with patch(
            'mcp_server_opensearch.install_hooks._get_kiro_hooks_dir',
            return_value=hooks_dir,
        ):
            install_hooks(client='kiro', scope='workspace')

        assert hooks_dir.exists()
        assert (hooks_dir / 'memory-search-on-prompt.json').exists()

    def test_hook_schema_valid(self):
        """Hook definitions follow the required Kiro schema."""
        for hook in [KIRO_SEARCH_HOOK, KIRO_SAVE_HOOK]:
            assert 'name' in hook
            assert 'version' in hook
            assert 'when' in hook
            assert 'type' in hook['when']
            assert 'then' in hook
            assert hook['then']['type'] in ('askAgent', 'runCommand')
            if hook['then']['type'] == 'askAgent':
                assert 'prompt' in hook['then']


class TestInstallClaudeCodeHooks:
    """Tests for Claude Code hook installation."""

    def test_creates_settings_with_hooks(self, tmp_workspace):
        """Install creates settings.json with hooks map in the correct Claude Code schema."""
        settings_path = tmp_workspace / '.claude' / 'settings.json'
        with patch(
            'mcp_server_opensearch.install_hooks._get_claude_settings_path',
            return_value=settings_path,
        ):
            install_hooks(client='claude-code', scope='workspace')

        assert settings_path.exists()
        settings = json.loads(settings_path.read_text())
        assert 'hooks' in settings
        # hooks is a map keyed by event name
        assert isinstance(settings['hooks'], dict)
        assert 'UserPromptSubmit' in settings['hooks']
        assert 'Stop' in settings['hooks']

        # UserPromptSubmit: matcher groups with inner hooks
        matcher_groups = settings['hooks']['UserPromptSubmit']
        assert isinstance(matcher_groups, list)
        assert len(matcher_groups) == 1
        group = matcher_groups[0]
        assert 'matcher' in group
        assert 'hooks' in group
        hook = group['hooks'][0]
        assert hook['type'] == 'command'
        assert 'SearchMemoryTool' in hook['command']

        # Stop: loop-guarded via stop_hook_active check
        stop_groups = settings['hooks']['Stop']
        assert len(stop_groups) == 1
        stop_hook = stop_groups[0]['hooks'][0]
        assert stop_hook['type'] == 'command'
        assert 'stop_hook_active' in stop_hook['command']

    def test_preserves_existing_settings(self, tmp_workspace):
        """Install preserves existing settings and merges hooks into the map."""
        settings_path = tmp_workspace / '.claude' / 'settings.json'
        settings_path.parent.mkdir(parents=True)
        existing_hooks = {
            'PreToolUse': [
                {'matcher': 'Write', 'hooks': [{'type': 'command', 'command': 'echo ok'}]}
            ]
        }
        settings_path.write_text(
            json.dumps(
                {
                    'model': 'claude-sonnet-4-20250514',
                    'hooks': existing_hooks,
                }
            )
        )

        with patch(
            'mcp_server_opensearch.install_hooks._get_claude_settings_path',
            return_value=settings_path,
        ):
            install_hooks(client='claude-code', scope='workspace')

        settings = json.loads(settings_path.read_text())
        assert settings['model'] == 'claude-sonnet-4-20250514'
        # Original PreToolUse event preserved, UserPromptSubmit added
        assert 'PreToolUse' in settings['hooks']
        assert 'UserPromptSubmit' in settings['hooks']

    def test_idempotent_skips_existing_hooks(self, tmp_workspace):
        """Running install twice does not duplicate hooks."""
        settings_path = tmp_workspace / '.claude' / 'settings.json'
        with patch(
            'mcp_server_opensearch.install_hooks._get_claude_settings_path',
            return_value=settings_path,
        ):
            install_hooks(client='claude-code', scope='workspace')
            install_hooks(client='claude-code', scope='workspace')

        settings = json.loads(settings_path.read_text())
        # Still only one matcher group for UserPromptSubmit
        assert len(settings['hooks']['UserPromptSubmit']) == 1

    def test_migrates_old_flat_list_format(self, tmp_workspace):
        """Install migrates old flat-list hooks format to the correct nested map."""
        settings_path = tmp_workspace / '.claude' / 'settings.json'
        settings_path.parent.mkdir(parents=True)
        # Old (incorrect) flat-list format
        settings_path.write_text(
            json.dumps(
                {
                    'hooks': [
                        {
                            'event': 'UserPromptSubmit',
                            'matcher': '',
                            'type': 'command',
                            'command': 'echo old',
                        }
                    ]
                }
            )
        )

        with patch(
            'mcp_server_opensearch.install_hooks._get_claude_settings_path',
            return_value=settings_path,
        ):
            install_hooks(client='claude-code', scope='workspace')

        settings = json.loads(settings_path.read_text())
        # Migrated to map format with memory hooks added
        assert isinstance(settings['hooks'], dict)
        assert 'UserPromptSubmit' in settings['hooks']


class TestInstallHooksValidation:
    """Tests for input validation."""

    def test_unsupported_client(self, capsys):
        """Unsupported client prints error."""
        install_hooks(client='vim', scope='workspace')
        captured = capsys.readouterr()
        assert 'Unsupported client' in captured.out

    def test_unsupported_scope(self, capsys):
        """Unsupported scope prints error."""
        install_hooks(client='kiro', scope='global')
        captured = capsys.readouterr()
        assert 'Unsupported scope' in captured.out


class TestInstallCursorHooks:
    """Tests for Cursor hook installation."""

    def test_creates_hooks_json(self, tmp_workspace):
        """Install creates hooks.json with correct Cursor schema."""
        hooks_path = tmp_workspace / '.cursor' / 'hooks.json'
        with patch(
            'mcp_server_opensearch.install_hooks._get_cursor_hooks_path',
            return_value=hooks_path,
        ):
            install_hooks(client='cursor', scope='workspace')

        assert hooks_path.exists()
        config = json.loads(hooks_path.read_text())

        # Top-level schema
        assert config['version'] == 1
        assert 'hooks' in config
        assert isinstance(config['hooks'], dict)

        # sessionStart hook injects additional_context
        assert 'sessionStart' in config['hooks']
        session_hook = config['hooks']['sessionStart'][0]
        assert 'command' in session_hook
        # Command uses plain echo — verify it contains the tool name
        assert 'SearchMemoryTool' in session_hook['command']

        # stop hook emits followup_message
        assert 'stop' in config['hooks']
        stop_hook = config['hooks']['stop'][0]
        assert 'command' in stop_hook
        # Command uses plain echo — verify it contains the tool name
        assert 'SaveMemoryTool' in stop_hook['command']
        # loop_limit prevents infinite save loops
        assert stop_hook.get('loop_limit') == 1

    def test_preserves_existing_hooks(self, tmp_workspace):
        """Install merges into existing hooks.json without overwriting."""
        hooks_path = tmp_workspace / '.cursor' / 'hooks.json'
        hooks_path.parent.mkdir(parents=True)
        hooks_path.write_text(
            json.dumps(
                {
                    'version': 1,
                    'hooks': {
                        'afterFileEdit': [{'command': 'echo formatted'}],
                    },
                }
            )
        )

        with patch(
            'mcp_server_opensearch.install_hooks._get_cursor_hooks_path',
            return_value=hooks_path,
        ):
            install_hooks(client='cursor', scope='workspace')

        config = json.loads(hooks_path.read_text())
        # Original hook preserved
        assert 'afterFileEdit' in config['hooks']
        # Memory hooks added
        assert 'sessionStart' in config['hooks']
        assert 'stop' in config['hooks']

    def test_idempotent_skips_existing_hooks(self, tmp_workspace):
        """Running install twice does not duplicate hooks."""
        hooks_path = tmp_workspace / '.cursor' / 'hooks.json'
        with patch(
            'mcp_server_opensearch.install_hooks._get_cursor_hooks_path',
            return_value=hooks_path,
        ):
            install_hooks(client='cursor', scope='workspace')
            install_hooks(client='cursor', scope='workspace')

        config = json.loads(hooks_path.read_text())
        assert len(config['hooks']['sessionStart']) == 1
        assert len(config['hooks']['stop']) == 1
