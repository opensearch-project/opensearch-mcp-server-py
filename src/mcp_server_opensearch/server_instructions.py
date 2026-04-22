# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Server instructions for MCP clients.

Provides dynamic instructions based on server configuration to help LLMs
understand how to use connection parameters efficiently.
"""

import os


# Connection override fields that appear in tool schemas when no URL is pre-configured
CONNECTION_OVERRIDE_FIELDS = {
    'opensearch_url',
    'opensearch_username',
    'opensearch_password',
    'opensearch_no_auth',
    'aws_region',
    'aws_iam_arn',
    'aws_profile',
    'aws_opensearch_serverless',
    'opensearch_ssl_verify',
    'opensearch_timeout',
}

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

    When no connection is pre-configured (no OPENSEARCH_URL and no clusters
    in the registry), returns instructions explaining the dynamic connection
    parameters. Otherwise returns None since the connection params are hidden
    from tool schemas.

    Returns:
        str or None: Instructions text, or None if not needed.
    """
    if has_preconfigured_connection():
        return None
    return _DYNAMIC_CONNECTION_INSTRUCTIONS
