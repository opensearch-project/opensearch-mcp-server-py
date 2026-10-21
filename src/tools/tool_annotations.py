# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Builders for MCP ``ToolAnnotations`` attached to each registry entry.

Annotations are hints for clients (for example, whether to ask for confirmation
before a call). They do not affect which tools the write filter enables.
"""

from mcp.types import ToolAnnotations


def read_only_annotations(title: str) -> ToolAnnotations:
    """Annotations for a tool that only reads from the connected cluster."""
    return ToolAnnotations(
        title=title,
        read_only_hint=True,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    )


def write_annotations(
    title: str, *, destructive: bool, idempotent: bool, open_world: bool = False
) -> ToolAnnotations:
    """Annotations for a tool that modifies cluster state."""
    return ToolAnnotations(
        title=title,
        read_only_hint=False,
        destructive_hint=destructive,
        idempotent_hint=idempotent,
        open_world_hint=open_world,
    )
