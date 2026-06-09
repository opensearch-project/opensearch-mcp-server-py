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

_SKILLS_TOOLS_INSTRUCTIONS = """\
This server provides advanced analysis tools for anomaly investigation. \
These tools complement SearchIndexTool — use them together for best results:

- DataDistributionTool: Discovers which categorical field values (service names, error codes, \
status values) shifted most between a baseline and an anomaly window. Note: this tool analyzes \
frequency distribution of field values, not latency or duration. For latency-based investigation, \
use SearchIndexTool with sort by duration.

- MetricChangeAnalysisTool: Use for metric investigation. Compares percentile distributions \
of ALL numeric fields between a baseline and an anomaly window, returns top fields ranked \
by change score. Replaces manual field-by-field comparison. ALWAYS pass timeField: discover \
the time field and try the best to ensure it is correct. Omitting timeField, or passing a \
field absent from the index, causes a "No data found" error and leads to a wrong conclusion.

- LogPatternAnalysisTool: Clusters raw log messages into patterns using ML, highlights which \
patterns are new or surging compared to a baseline period.

Important: Always cross-validate findings from these tools against SearchIndexTool results \
(e.g. traces sorted by duration, error logs) before drawing conclusions.\
"""


def are_skills_enabled() -> bool:
    """Check whether skills tools are enabled based on environment/config.

    Skills are enabled when 'skills' appears in OPENSEARCH_ENABLED_CATEGORIES
    and NOT in OPENSEARCH_DISABLED_CATEGORIES.
    """
    enabled_cats = os.getenv('OPENSEARCH_ENABLED_CATEGORIES', '').lower()
    disabled_cats = os.getenv('OPENSEARCH_DISABLED_CATEGORIES', '').lower()
    if 'skills' in disabled_cats:
        return False
    if 'skills' in enabled_cats:
        return True
    return False


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

    Combines applicable instruction sections:
    - Dynamic connection instructions (single mode, no pre-configured endpoint)
    - Skills tools instructions (when skills category is enabled)

    Returns:
        str or None: Instructions text, or None if not needed.
    """
    from mcp_server_opensearch.global_state import get_mode

    parts = []

    if get_mode() == 'single' and is_dynamic_mode_enabled():
        parts.append(_DYNAMIC_CONNECTION_INSTRUCTIONS)

    if are_skills_enabled():
        parts.append(_SKILLS_TOOLS_INSTRUCTIONS)

    return '\n\n'.join(parts) if parts else None
