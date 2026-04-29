# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Server instructions for MCP clients.

Provides dynamic instructions based on server configuration to help LLMs
understand how to use connection parameters efficiently.
"""

import os


# Connection override fields that appear in tool schemas when no URL is pre-configured.
# Derived from baseToolArgs to avoid drift when new fields are added.
def _build_connection_override_fields() -> frozenset:
    from tools.tool_params import baseToolArgs

    _non_override = {'opensearch_cluster_name'}
    return frozenset(baseToolArgs.model_fields.keys()) - _non_override


CONNECTION_OVERRIDE_FIELDS = _build_connection_override_fields()

_DYNAMIC_CONNECTION_INSTRUCTIONS = """\
This OpenSearch MCP server has no pre-configured endpoint. \
You must provide connection parameters on each tool call.

Every tool accepts these optional connection parameters:
- opensearch_url (required): OpenSearch endpoint URL
- opensearch_username / opensearch_password: For basic auth
- opensearch_no_auth: Set true to skip authentication
- aws_region: AWS region for IAM or Serverless auth
- aws_iam_arn: IAM role ARN for role assumption
- aws_profile: AWS profile name for credentials
- aws_opensearch_serverless: Set true for OpenSearch Serverless
- opensearch_ssl_verify: Set false to skip SSL verification
- opensearch_timeout: Connection timeout in seconds

Provide opensearch_url plus the appropriate auth parameters for your target cluster. \
Parameters not provided fall back to server environment variables (if any).\
"""


def is_dynamic_mode_enabled() -> bool:
    """Determine whether dynamic (per-call) connection mode is active.

    Checks ``OPENSEARCH_DYNAMIC_CONNECTION`` first for an explicit override,
    then falls back to auto-detection based on whether a connection is
    pre-configured.

    ``OPENSEARCH_DYNAMIC_CONNECTION`` accepted values (case-insensitive):
    - ``"true"`` / ``"1"``  → force dynamic mode on (expose override fields)
    - ``"false"`` / ``"0"`` → force dynamic mode off (hide override fields)
    - unset / empty         → auto-detect (on when no URL or YAML config found)

    Returns:
        bool: True if dynamic mode is active, False otherwise.
    """
    explicit = os.getenv('OPENSEARCH_DYNAMIC_CONNECTION', '').strip().lower()
    if explicit in ('true', '1'):
        return True
    if explicit in ('false', '0'):
        return False
    # Auto-detect: dynamic when nothing is pre-configured
    return not has_preconfigured_connection()


def has_preconfigured_connection() -> bool:
    """Check whether the server has any pre-configured OpenSearch connection.

    Returns True when either:
    - OPENSEARCH_URL environment variable is set (single mode), or
    - Clusters have been loaded into the cluster registry (multi mode with YAML config).

    Returns:
        bool: True if a connection is pre-configured, False otherwise.
    """
    if bool(os.getenv('OPENSEARCH_URL', '').strip()):
        return True

    from mcp_server_opensearch.clusters_information import cluster_registry

    if cluster_registry:
        return True

    return False


def get_server_instructions() -> str | None:
    """Return server instructions based on current configuration.

    Only applies in single mode. In multi mode, dynamic connection params
    are not supported, so no instructions are needed.

    When dynamic mode is active in single mode (no pre-configured connection,
    or ``OPENSEARCH_DYNAMIC_CONNECTION=true``), returns instructions explaining
    the per-call connection parameters. Otherwise returns None.

    Returns:
        str or None: Instructions text, or None if not needed.
    """
    from mcp_server_opensearch.global_state import get_mode

    if get_mode() != 'single':
        return None
    if not is_dynamic_mode_enabled():
        return None
    return _DYNAMIC_CONNECTION_INSTRUCTIONS
