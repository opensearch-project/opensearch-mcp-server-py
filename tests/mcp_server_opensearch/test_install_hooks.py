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
        """Install creates settings.json with hooks array."""
        settings_path = tmp_workspace / '.claude' / 'settings.json'
        with patch(
            'mcp_server_opensearch.install_hooks._get_claude_settings_path',
            return_value=settings_path,
        ):
            install_hooks(client='claude-code', scope='workspace')

        assert settings_path.exists()
        settings = json.loads(settings_path.read_text())
        assert 'hooks' in settings
        assert len(settings['hooks']) == 2

        events = [h['event'] for h in settings['hooks']]
        assert 'UserPromptSubmit' in events
        assert 'Stop' in events

    def test_preserves_existing_settings(self, tmp_workspace):
        """Install preserves existing settings and appends hooks."""
        settings_path = tmp_workspace / '.claude' / 'settings.json'
        settings_path.parent.mkdir(parents=True)
        settings_path.write_text(json.dumps({
            'model': 'claude-sonnet-4-20250514',
            'hooks': [{'event': 'PreToolUse', 'matcher': 'Write', 'type': 'command', 'command': 'echo ok'}],
        }))

        with patch(
            'mcp_server_opensearch.install_hooks._get_claude_settings_path',
            return_value=settings_path,
        ):
            install_hooks(client='claude-code', scope='workspace')

        settings = json.loads(settings_path.read_text())
        assert settings['model'] == 'claude-sonnet-4-20250514'
        # Original hook + 2 new hooks
        assert len(settings['hooks']) == 3

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
        assert len(settings['hooks']) == 2


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
