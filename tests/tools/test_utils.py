# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

from tools.utils import is_read_only_tool


def test_is_read_only_tool_uses_read_only_hint_only():
    """Read-only status comes only from the explicit hint."""
    assert is_read_only_tool({'http_methods': 'GET, POST', 'read_only_hint': True}) is True
    assert is_read_only_tool({'http_methods': 'POST', 'read_only_hint': True}) is True
    assert is_read_only_tool({'http_methods': 'GET', 'read_only_hint': False}) is False
    assert is_read_only_tool({'http_methods': 'GET'}) is False
