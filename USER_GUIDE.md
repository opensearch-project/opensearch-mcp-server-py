![OpenSearch logo](https://github.com/opensearch-project/opensearch-py/raw/main/OpenSearch.svg)

# OpenSearch MCP Server Python User Guide

## Table of Contents
- [Overview](#overview)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Server Modes](#server-modes)
- [Authentication](#authentication)
- [Running the Server](#running-the-server)
- [Tool Filter](#tool-filter)
- [Tool Customization](#tool-customization)
- [Structured Logging](#structured-logging)
- [LangChain Integration](#langchain-integration)

## Overview

The OpenSearch MCP (Model Context Protocol) Server provides a bridge between AI agents and OpenSearch clusters. It supports both single-cluster and multi-cluster configurations with various authentication methods including IAM roles, basic authentication, AWS credentials, and header-based authentication.
The server can be started in both STDIO and streaming modes.

### Streaming Server

The OpenSearch MCP server supports a streaming transport that includes both SSE and HTTP streaming. The previous SSE server is now part of the streaming server and will be deprecated in the future. Use the streaming transport for all new integrations.

## Installation

### Option 1: Using uvx (Recommended - No Installation Required)

Install `uv` via `pip` or [standalone installer](https://github.com/astral-sh/uv?tab=readme-ov-file#installation):
```bash
pip install uv
```

The OpenSearch MCP server can be used directly via `uvx` without installation.

### Option 2: Local Installation

Install from [PyPI](https://pypi.org/project/opensearch-mcp-server-py/):
```bash
pip install opensearch-mcp-server-py
```

## Quick Start

### Prerequisites
1. Install `uv` (see [Installation](#installation))
2. Configure your AI agent of choice

### AI Agent Configuration

#### For Q Developer CLI
Configure `~/.aws/amazonq/mcp.json`. See [here](https://docs.aws.amazon.com/amazonq/latest/qdeveloper-ug/command-line-mcp-configuration.html) for additional configuration options.

#### For Claude Desktop
Configure `claude_desktop_config.json` from Settings > Developer. See [here](https://modelcontextprotocol.io/quickstart/user#2-add-the-filesystem-mcp-server) for more details.

### Basic Setup

#### Single Mode (Recommended for Beginners)
```json
{
  "mcpServers": {
    "opensearch-mcp-server": {
      "command": "uvx",
      "args": ["opensearch-mcp-server-py"],
      "env": {
        "OPENSEARCH_URL": "<your_opensearch_domain_url>",
        "OPENSEARCH_USERNAME": "<your_username>",
        "OPENSEARCH_PASSWORD": "<your_password>"
      }
    }
  }
}
```

**For clusters without authentication:**
```json
{
  "mcpServers": {
    "opensearch-mcp-server": {
      "command": "uvx",
      "args": ["opensearch-mcp-server-py"],
      "env": {
        "OPENSEARCH_URL": "<your_opensearch_domain_url>",
        "OPENSEARCH_NO_AUTH": "true"
      }
    }
  }
}
```
See [Environment Variables](#environment-variables) for supported environment variables. 
See [Authentication](#authentication) section for detailed authentication setup.

#### Multi Mode (For Multiple Clusters)
```json
{
  "mcpServers": {
    "opensearch-mcp-server": {
      "command": "uvx",
      "args": [
        "opensearch-mcp-server-py",
        "--mode", "multi",
        "--config", "/path/to/your/config.yml"
      ],
      "env": {}
    }
  }
}
```

**Example YAML Configuration File (`config.yml`):**
```yaml
version: "1.0"
description: "OpenSearch cluster configurations"

clusters:
  # Cluster name: "local-dev" - used as opensearch_cluster_name parameter in tool calls
  local-dev:
    opensearch_url: "http://localhost:9200"
    opensearch_username: "admin"
    opensearch_password: "admin123"

  # Cluster name: "production" - used as opensearch_cluster_name parameter in tool calls
  production:
    opensearch_url: "https://prod-opensearch.us-east-1.es.amazonaws.com"
    iam_arn: "arn:aws:iam::123456789012:role/OpenSearchProductionRole"
    aws_region: "us-east-1"
    profile: "production"

  # Cluster name: "staging" - used as opensearch_cluster_name parameter in tool calls
  staging:
    opensearch_url: "https://staging-opensearch.us-west-2.es.amazonaws.com"
    profile: "staging"
  
  serverless-cluster:
    opensearch_url: "https://collection-id.us-east-1.aoss.amazonaws.com"
    aws_region: "us-east-1"
    profile: "your-aws-profile"
    is_serverless: true

# Tool customization configurations (supported in both Single and Multi Mode)
tools:
  ListIndexTool:
    display_name: "Index Manager"
    description: "List and manage OpenSearch indices with enhanced functionality"
    args:
      index: "Custom description for the 'index' argument in ListIndexTool."
  SearchIndexTool:
    display_name: "Super Searcher"
  GetShardsTool:
    description: "Retrieve detailed information about OpenSearch shards"
```

**Key Points about Multi Mode:**
- **Cluster Names**: The keys under `clusters` (e.g., `local-dev`, `production`, `staging`) are used as the `opensearch_cluster_name` parameter when calling tools
- **Authentication**: Each cluster can use different authentication methods (basic auth, IAM roles, AWS profiles)
- **Tool Usage**: When using tools, you must specify which cluster to use: `{"opensearch_cluster_name": "production", "index": "users"}`

That's it! You are now ready to use your AI agent with OpenSearch tools.

**Next Steps:**
- For detailed authentication setup, see [Authentication](#authentication)
- For running the server manually, see [Running the Server](#running-the-server)

## Server Modes

The OpenSearch MCP server supports two modes of operation:

### Single Mode (Default)
- Connects to a single OpenSearch cluster
- Uses environment variables for configuration
- Automatically filters tools based on OpenSearch version compatibility
- Simple tool schemas

### Multi Mode
- Supports multiple OpenSearch clusters
- Uses a YAML configuration file to define clusters
- All tools are available regardless of version
- Full tool schemas with all parameters exposed
- **Important**: LLMs must provide an `opensearch_cluster_name` parameter to specify which cluster to use
- If a tool is not compatible with the OpenSearch version, an error is raised during tool execution
- **Fallback**: If no config file is provided, multi mode falls back to single mode behavior

### Cluster Name Parameter in Multi Mode

In multi mode, all tools have an additional parameter:
- `opensearch_cluster_name`: The name of the cluster as defined in your YAML configuration file

The LLM needs to have context about the available cluster names to make informed decisions about which cluster to use for each operation.

#### Example Tool Calls
```json
{
  "opensearch_cluster_name": "local-dev",
  "index": "my_index"
}
```

```json
{
  "opensearch_cluster_name": "production",
  "index": "users",
  "query_dsl": {
    "match": {
      "status": "active"
    }
  }
}
```

The LLM should choose the appropriate cluster based on the operation context (e.g., use `local-dev` for testing, `production` for production data).

## Authentication

### Authentication Methods

The server supports multiple authentication methods with the following priority order:
1. **No Authentication** (only if `OPENSEARCH_NO_AUTH=true` environment variable is set, or `opensearch_no_auth: true` in multi mode config)
2. **Header-Based Authentication** (only if `OPENSEARCH_HEADER_AUTH=true` environment variable is set in single mode, or `opensearch_header_auth: true` in multi mode config)
3. **IAM Role Authentication**
4. **Basic Authentication**
5. **AWS Credentials Authentication**

**Note:** In multi mode, both `opensearch_no_auth` and `opensearch_header_auth` can be configured per-cluster in the YAML configuration file.

### Single Mode Authentication

#### No Authentication (for clusters without authentication)
```bash
export OPENSEARCH_URL="<your_opensearch_domain_url>"
export OPENSEARCH_NO_AUTH="true"
```

#### Header-Based Authentication

Header-based authentication allows you to provide authentication credentials via HTTP request headers. This is useful for dynamic authentication scenarios, especially when using the streaming server transport.

**Enable header-based authentication:**
```bash
export OPENSEARCH_HEADER_AUTH="true"
```

**Headers when making requests:**

For AWS authentication:

- `opensearch-url`: OpenSearch cluster endpoint URL (if not set via env var)
- `aws-region`: AWS region
- `aws-access-key-id`: AWS access key ID
- `aws-secret-access-key`: AWS secret access key
- `aws-session-token`: AWS session token (for temporary credentials)
- `aws-service-name`: AWS service name - `es` for OpenSearch or `aoss` for OpenSearch Serverless (defaults to `es`)

For Basic authentication:

- `Authorization`: HTTP Basic authentication header (format: `Basic <base64(username:password)>`)
  - Example: `Authorization: Basic YWRtaW46cGFzc3dvcmQ=` (where `YWRtaW46cGFzc3dvcmQ=` is base64-encoded `admin:password`)

For Bearer authentication:

- `Authorization`: HTTP Bearer authentication header (format: `Bearer <token>`)

**Note:** When `OPENSEARCH_HEADER_AUTH=true` (single mode) or `opensearch_header_auth: true` (multi mode), headers take priority over environment variables or cluster configuration values. If a header is not provided, the system falls back to the corresponding environment variable (single mode) or cluster configuration value (multi mode).

#### IAM Role Authentication
```bash
export OPENSEARCH_URL="<your_opensearch_domain_url>"
export AWS_IAM_ARN="arn:aws:iam::123456789012:role/YourOpenSearchRole"
export AWS_REGION="<your_aws_region>"
```

#### Basic Authentication
```bash
export OPENSEARCH_URL="<your_opensearch_domain_url>"
export OPENSEARCH_USERNAME="<your_opensearch_domain_username>"
export OPENSEARCH_PASSWORD="<your_opensearch_domain_password>"
```

#### Mutual TLS (mTLS)
```bash
export OPENSEARCH_URL="<your_opensearch_domain_url>"
export OPENSEARCH_USERNAME="<your_opensearch_domain_username>"
export OPENSEARCH_PASSWORD="<your_opensearch_domain_password>"
export OPENSEARCH_CA_CERT_PATH="/path/to/ca.crt"
export OPENSEARCH_CLIENT_CERT_PATH="/path/to/tls.crt"
export OPENSEARCH_CLIENT_KEY_PATH="/path/to/tls.key"
```

`OPENSEARCH_CLIENT_CERT_PATH` and `OPENSEARCH_CLIENT_KEY_PATH` must be provided together. These settings add TLS client certificates to the existing authentication flow, so you can use mTLS alongside basic auth, IAM, or no-auth clusters.

#### AWS Credentials Authentication
```bash
export OPENSEARCH_URL="<your_opensearch_domain_url>"
export AWS_REGION="<your_aws_region>"
export AWS_ACCESS_KEY_ID="<your_aws_access_key>"
export AWS_SECRET_ACCESS_KEY="<your_aws_secret_access_key>"
export AWS_SESSION_TOKEN="<your_aws_session_token>"
```

#### OpenSearch Serverless
```bash
export OPENSEARCH_URL="<your_opensearch_serverless_endpoint>"
export AWS_OPENSEARCH_SERVERLESS="true"
export AWS_REGION="<your_aws_region>"
# Use either AWS credentials or profile
export AWS_PROFILE="<your_aws_profile>"
```

### Multi Mode Authentication

Multi mode uses a YAML configuration file to define authentication for each cluster:

```yaml
version: "1.0"
description: "OpenSearch cluster configurations"

clusters:
  # No Authentication (for clusters without authentication)
  no-auth-cluster:
    opensearch_url: "http://localhost:9200"
    opensearch_no_auth: true

  # Basic Authentication
  local-cluster:
    opensearch_url: "http://localhost:9200"
    opensearch_username: "admin"
    opensearch_password: "your_password_here"

  # Mutual TLS (mTLS)
  mtls-cluster:
    opensearch_url: "https://private-opensearch.example.com:9200"
    opensearch_username: "admin"
    opensearch_password: "your_password_here"
    opensearch_ca_cert_path: "/var/run/opensearch-mtls/ca.crt"
    opensearch_client_cert_path: "/var/run/opensearch-mtls/tls.crt"
    opensearch_client_key_path: "/var/run/opensearch-mtls/tls.key"

  # AWS Credentials Authentication
  remote-cluster:
    opensearch_url: "https://your-opensearch-domain.us-east-2.es.amazonaws.com"
    profile: "your-aws-profile"
  
  # IAM Role Authentication
  remote-cluster-with-iam:
    opensearch_url: "https://your-opensearch-domain.us-east-2.es.amazonaws.com"
    iam_arn: "arn:aws:iam::123456789012:role/YourOpenSearchRole"
    aws_region: "us-east-2"
    profile: "your-aws-profile"

  # OpenSearch Serverless
  serverless-cluster:
    opensearch_url: "https://collection-id.us-east-1.aoss.amazonaws.com"
    aws_region: "us-east-1"
    profile: "your-aws-profile"
    is_serverless: true

  # Header-Based Authentication
  header-auth-cluster:
    opensearch_header_auth: true
    # When opensearch_header_auth is true, headers take priority over config values
```

#### Authentication Methods in Multi Mode:

1. **No Authentication:**
   - Requires: `opensearch_url`, `opensearch_no_auth: true`
   - For OpenSearch clusters that allow anonymous access without authentication

2. **Header-Based Authentication:**
   - Requires: `opensearch_url`, `opensearch_header_auth: true`
   - **Process**: When enabled, authentication parameters are read from HTTP request headers
   - **Headers**: `opensearch-url`, `aws-region`, `aws-access-key-id`, `aws-secret-access-key`, `aws-session-token` (optional), `aws-service-name` (optional)
   - **Priority**: Headers take priority over cluster configuration values
   - **Use Case**: Useful for dynamic authentication in streaming/server environments where credentials are provided per-request

3. **IAM Role Authentication:**
   - Requires: `opensearch_url`, `iam_arn`, `aws_region`, `profile` (optional)
   - **Process**: The server assumes the specified IAM role using AWS STS and then connects to the cluster using those temporary credentials

4. **Basic Authentication:**
   - Requires: `opensearch_url`, `opensearch_username`, `opensearch_password`

5. **Mutual TLS (mTLS):**
   - Optional: `opensearch_ca_cert_path`, `opensearch_client_cert_path`, `opensearch_client_key_path`
   - `opensearch_client_cert_path` and `opensearch_client_key_path` must be configured together
   - Adds TLS client certificates for OpenSearch connections and can be combined with the auth methods above

6. **AWS Credentials Authentication:**
   - Requires: `opensearch_url`, `profile` (optional)
   - Uses AWS credentials from the specified profile or default credentials

### AWS Profile Support

You can specify an AWS profile to use for authentication in both modes:

#### Single Mode
```bash
# Using environment variable
export AWS_PROFILE="my-aws-profile"
python -m mcp_server_opensearch

# Using command line argument
python -m mcp_server_opensearch --profile my-aws-profile
```

#### Multi Mode
```bash
# Profile specified in config file (recommended)
python -m mcp_server_opensearch --mode multi --config clusters.yml

# Profile as fallback if not in config file
export AWS_PROFILE="my-aws-profile"
python -m mcp_server_opensearch --mode multi --config clusters.yml
```

## Running the Server

### Single Mode
```bash
# Stdio Server
python -m mcp_server_opensearch

# Streaming Server (SSE/HTTP streaming)
python -m mcp_server_opensearch --transport stream

# With AWS Profile
python -m mcp_server_opensearch --profile my-aws-profile

# Streaming Server with outbound mTLS
OPENSEARCH_URL="https://private-opensearch.example.com:9200" \
OPENSEARCH_USERNAME="admin" \
OPENSEARCH_PASSWORD="password" \
OPENSEARCH_CA_CERT_PATH="/path/to/ca.crt" \
OPENSEARCH_CLIENT_CERT_PATH="/path/to/tls.crt" \
OPENSEARCH_CLIENT_KEY_PATH="/path/to/tls.key" \
python -m mcp_server_opensearch --transport stream
```

### Multi Mode
```bash
# Stdio Server with config file
python -m mcp_server_opensearch --mode multi --config config.yml

# Streaming Server with config file
python -m mcp_server_opensearch --mode multi --config config.yml --transport stream

# With AWS Profile (fallback if not in config)
python -m mcp_server_opensearch --mode multi --config config.yml --profile my-aws-profile

# Fallback to single mode behavior (no config file)
python -m mcp_server_opensearch --mode multi
```



## Command Line Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `--transport` | string | `stdio` | Transport type: `stdio` or `stream` |
| `--host` | string | `0.0.0.0` | Host to bind to (streaming only) |
| `--port` | integer | `9900` | Port to listen on (streaming only) |
| `--mode` | string | `single` | Server mode: `single` or `multi` |
| `--profile` | string | `''` | AWS profile to use for OpenSearch connection |
| `--config` | string | `''` | Path to a YAML configuration file |
| `--log-format` | string | `text` | Log output format: `text` (human-readable) or `json` (structured) |

## Environment Variables

### Connection & Authentication Variables

`OPENSEARCH_URL` (and each cluster’s `opensearch_url` in multi-cluster YAML) must include a scheme (`http://` or `https://`). The TCP port used is determined as follows:

| Example URL | Port in the URL? | TCP port used |
|---------------|------------------|---------------|
| `https://cluster.example.com` | Omitted | **443** (HTTPS default) |
| `http://cluster.example.com` | Omitted | **80** (HTTP default) |
| `https://cluster.example.com:9200` | Set to `9200` | **9200** |
| `http://localhost:9200` | Set to `9200` | **9200** |
| `https://cluster.example.com:9443` | Set to `9443` (or any other value) | **Same as in the URL** |

If the port is omitted, this server inserts the usual HTTP(S) default so traffic does not fall back to the OpenSearch Python client’s implicit **9200** (Elasticsearch-style default when no port appears in the string). For a typical local OpenSearch process listening on 9200, set the URL to `http://localhost:9200` (or another host) **with `:9200` explicitly**.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENSEARCH_URL` | Yes* | `''` | OpenSearch cluster endpoint URL |
| `OPENSEARCH_USERNAME` | No | `''` | Username for basic authentication |
| `OPENSEARCH_PASSWORD` | No | `''` | Password for basic authentication |
| `AWS_IAM_ARN` | No | `''` | IAM role ARN for role-based authentication |
| `AWS_REGION` | No | `''` | AWS region for the OpenSearch cluster |
| `AWS_ACCESS_KEY_ID` | No | `''` | AWS access key ID |
| `AWS_SECRET_ACCESS_KEY` | No | `''` | AWS secret access key |
| `AWS_SESSION_TOKEN` | No | `''` | AWS session token |
| `AWS_PROFILE` | No | `''` | AWS profile name |
| `AWS_OPENSEARCH_SERVERLESS` | No | `''` | Set to `"true"` for OpenSearch Serverless |
| `OPENSEARCH_NO_AUTH` | No | `''` | Set to `"true"` to connect without authentication |
| `OPENSEARCH_HEADER_AUTH` | No | `''` | Set to `"true"` to enable header-based authentication (headers take priority over env vars) |
| `OPENSEARCH_TIMEOUT` | No | `''` | Connection timeout in seconds for OpenSearch operations |
| `OPENSEARCH_QUERY_TIMEOUT` | No | `''` | Server-side query timeout passed as `cancel_after_time_interval` to search requests (e.g., `"10s"`). Cancels long-running queries after the specified duration. |

### SSL & Security Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENSEARCH_SSL_VERIFY` | No | `"true"` | Control SSL certificate verification (`"true"` or `"false"`) |
| `OPENSEARCH_CA_CERT_PATH` | No | `''` | Path to the CA certificate bundle used to verify the OpenSearch server |
| `OPENSEARCH_CLIENT_CERT_PATH` | No | `''` | Path to the client certificate used for OpenSearch mTLS |
| `OPENSEARCH_CLIENT_KEY_PATH` | No | `''` | Path to the client private key used for OpenSearch mTLS |

### Response Size Control Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENSEARCH_MAX_RESPONSE_SIZE` | No | `10485760` (10MB) | Maximum response size in bytes to prevent memory exhaustion from large responses |

### Tool Filtering Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENSEARCH_ENABLED_TOOLS` | No | `''` | Comma-separated list of enabled tool names |
| `OPENSEARCH_DISABLED_TOOLS` | No | `''` | Comma-separated list of disabled tool names |
| `OPENSEARCH_TOOL_CATEGORIES` | No | `''` | JSON string defining tool categories |
| `OPENSEARCH_ENABLED_CATEGORIES` | No | `''` | Comma-separated list of enabled category names |
| `OPENSEARCH_DISABLED_CATEGORIES` | No | `''` | Comma-separated list of disabled category names |
| `OPENSEARCH_ENABLED_TOOLS_REGEX` | No | `''` | Comma-separated list of regex patterns for enabled tools |
| `OPENSEARCH_DISABLED_TOOLS_REGEX` | No | `''` | Comma-separated list of regex patterns for disabled tools |
| `OPENSEARCH_SETTINGS_ALLOW_WRITE` | No | `"true"` | Enable/disable write operations (`"true"` or `"false"`) |

### Logging & Monitoring Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENSEARCH_MEMORY_MONITOR_INTERVAL` | No | `60` | Interval in seconds between memory usage snapshots (only active with `--log-format json`) |

*Required in single mode or when not using multi-mode config file

## Multi-Mode Cluster Configuration

When using multi-mode, each cluster in your YAML configuration file accepts the following parameters:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `opensearch_url` | string | Yes | OpenSearch cluster endpoint URL |
| `opensearch_username` | string | No* | Username for basic authentication |
| `opensearch_password` | string | No* | Password for basic authentication |
| `iam_arn` | string | No* | IAM role ARN for role-based authentication |
| `aws_region` | string | No* | AWS region for the OpenSearch cluster |
| `profile` | string | No | AWS profile name |
| `is_serverless` | boolean | No | Set to `true` for OpenSearch Serverless |
| `opensearch_no_auth` | boolean | No | Set to `true` to connect without authentication |
| `opensearch_header_auth` | boolean | No | Set to `true` to enable header-based authentication (headers take priority over config values) |
| `opensearch_ca_cert_path` | string | No | Path to the CA certificate bundle used to verify the OpenSearch server |
| `opensearch_client_cert_path` | string | No | Path to the client certificate used for OpenSearch mTLS |
| `opensearch_client_key_path` | string | No | Path to the client private key used for OpenSearch mTLS |
| `timeout` | integer | No | Connection timeout in seconds for OpenSearch operations |
| `max_response_size` | integer | No | Maximum response size in bytes (defaults to 10MB if not specified) |

*Required for respective authentication method (basic auth, IAM role, or AWS credentials)

### Authentication Method Requirements

| Authentication Method | Required Parameters | Optional Parameters |
|----------------------|-------------------|-------------------|
| **No Authentication** | `opensearch_url` | `opensearch_no_auth: true` |
| **Header-Based Authentication** | `opensearch_header_auth: true`, Required from header/config/env: `opensearch_url`, `aws-region`, `aws-access-key-id`, `aws-secret-access-key` | `aws-session-token`, `aws-service-name` |
| **IAM Role Authentication** | `opensearch_url`, `iam_arn`, `aws_region` | `profile` |
| **Basic Authentication** | `opensearch_url`, `opensearch_username`, `opensearch_password` | `profile` |
| **Mutual TLS (mTLS)** | `opensearch_client_cert_path`, `opensearch_client_key_path` | `opensearch_ca_cert_path` |
| **AWS Credentials Authentication** | `opensearch_url` | `aws_region`, `profile` |
| **OpenSearch Serverless** | `opensearch_url`, `aws_region` | `profile`, `is_serverless: true` |

## Tool Filter

OpenSearch MCP server supports tool filtering to enable or disable specific tools by name, category, or operation type. You can configure filtering using either a YAML configuration file or environment variables.

**Important Note: Tool filtering is only supported in Single Mode. In Multi Mode, all tools are available without any filtering.**

### Configuration Methods

1. YAML Configuration File

Create a YAML file with your tool filtering configuration:
```yaml
# Define custom tool categories
tool_category:
  <category_name>:
    - <tool_name>

# Configure tool filters
tool_filters:
  enabled_tools:
    - <tool_name_to_enable>
  disabled_tools:
    - <tool_name_to_disable>
  enabled_categories:
    - <category_name_to_enable>
  disabled_categories:
    - <category_name_to_disable>
  enable_tools_regex:
    - <regex_pattern_to_enable>  # (e.g., search.*)
  disabled_tools_regex:
    - <regex_pattern_to_disable>
  settings:
    allow_write: true  # Enable/disable write-only operations
```

To use your configuration file, start the server with the `--config` flag:

```bash
# Run stdio server with tool filter config file
python -m mcp_server_opensearch --config path/to/config.yml

# Run Streaming server with tool filter config file
python -m mcp_server_opensearch --transport stream --config path/to/config.yml
```

2. Environment Variables

Set environment variables for tool filtering:
```bash
# Tool Categories
export OPENSEARCH_TOOL_CATEGORIES='{"<name_of_category>":["<tool_name>","<tool_name>"]}'

# Enable/Disable Specific Tools
export OPENSEARCH_ENABLED_TOOLS="<tool_name>"
export OPENSEARCH_DISABLED_TOOLS="<tool_name>"

# Enable/Disable Categories
export OPENSEARCH_ENABLED_CATEGORIES="<category_name>"
export OPENSEARCH_DISABLED_CATEGORIES="<category_name>"

# Regex Pattern
export OPENSEARCH_ENABLED_TOOLS_REGEX="<regex_pattern>"
export OPENSEARCH_DISABLED_TOOLS_REGEX="<regex_pattern>"

# Operation Settings
export OPENSEARCH_SETTINGS_ALLOW_WRITE=true
```

### Important Notes
- Tool names are case-insensitive
- All configuration fields are optional
- Disabled filters have higher priority: If a tool is both enabled and disabled, it will be disabled
- When both config file and environment variables are provided, the config file will be prioritized
- Tool filtering is only supported in single mode. In multi mode, tool filtering is not supported

## Tool Customization

OpenSearch MCP server supports tool customization to modify tool display names, descriptions, and other properties. You can customize tools using either a YAML configuration file or runtime parameters.

**Note:** Display names must follow the pattern `^[a-zA-Z0-9_-]+$` (alphanumeric characters, underscores, and hyphens only).

### Configuration Methods

1. **YAML Configuration File**

Create a YAML file with your tool customization settings:
```yaml
tools:
  ListIndexTool:
    display_name: "Index_Manager"
    description: "List and manage OpenSearch indices"
    args:
      index: "Custom description for the 'index' argument in ListIndexTool."
  GetShardsTool:
    description: "Retrieve detailed information about OpenSearch shards"
  SearchIndexTool:
     max_size_limit: 20
```

Use the configuration file when starting the server:
```bash
python -m mcp_server_opensearch --config path/to/config.yml
```

2. **Runtime Parameters**

Customize tools directly via command line arguments:
```bash
python -m mcp_server_opensearch --tool.ListIndexTool.display_name="Index_Manager" --tool.SearchIndexTool.description="Custom search tool" --tool.GetShardsTool.args.index.description="Custom description" --tool.SearchIndexTool.max_size_limit=20
```

### Priority

Configuration file settings have higher priority than runtime parameters. If both are provided, configuration file settings will override the corresponding values in the runtime parameters.

### Important Notes
- Tool customization is available in both single and multi modes
- Only existing tools can be customized; new tools cannot be created
- Changes take effect immediately when the server starts
- Invalid tool names or properties will throw an error

## Response Size Limiting

The OpenSearch MCP server includes built-in response size limiting to prevent memory exhaustion when dealing with large responses from OpenSearch queries. This feature helps maintain server stability and prevents out-of-memory errors.

### How It Works

The server uses a buffered connection that monitors the size of incoming responses. If a response exceeds the configured limit, the connection stops reading additional data and raises a `ResponseSizeExceededError` with a helpful message.

### Configuration

#### Single Mode
Set the `OPENSEARCH_MAX_RESPONSE_SIZE` environment variable:
```bash
export OPENSEARCH_MAX_RESPONSE_SIZE="20971520"  # 20MB limit
```

#### Multi Mode
Configure `max_response_size` per cluster in your YAML configuration:
```yaml
clusters:
  large-cluster:
    opensearch_url: "https://large-cluster.example.com:9200"
    max_response_size: 52428800  # 50MB limit for this cluster
  
  small-cluster:
    opensearch_url: "https://small-cluster.example.com:9200"
    max_response_size: 5242880   # 5MB limit for this cluster
```

### Configuration Priority

The response size limit is determined in the following order (highest to lowest priority):

1. **Cluster-specific configuration** (multi mode only): `max_response_size` in YAML config
2. **Environment variable**: `OPENSEARCH_MAX_RESPONSE_SIZE`
3. **Default value**: 10MB (10,485,760 bytes)

### Default Behavior

- **Default limit**: 10MB (10,485,760 bytes)
- **Invalid values**: If an invalid value is provided (non-numeric, negative, or zero), the server falls back to the default
- **Error handling**: When the limit is exceeded, a clear error message is returned with suggestions for resolution

### Best Practices

- **Set appropriate limits**: Configure limits based on your expected data sizes and available memory
- **Monitor usage**: Large responses may indicate inefficient queries that could be optimized
- **Adjust as needed**: Increase limits for legitimate large data operations, decrease for memory-constrained environments
- **Query optimization**: Consider using pagination, filtering, or field selection to reduce response sizes

### Example Error Message

When the response size limit is exceeded, you'll see an error like:
```
Response size exceeded limit of 10485760 bytes. Stopped reading at 15728640 bytes to prevent memory exhaustion. Consider increasing max_response_size or refining your query to return less data.
```

## Structured Logging

The OpenSearch MCP server supports structured JSON logging for monitoring and metrics. When enabled, every log line is a JSON object with fields that can be directly targeted by metric filters in log aggregation platforms such as Amazon CloudWatch, Datadog, Splunk, Grafana Loki, or the ELK stack.

### Enabling Structured Logging

Use the `--log-format json` flag when starting the server:

```bash
# Stdio server with JSON logging
python -m mcp_server_opensearch --log-format json

# Streaming server with JSON logging
python -m mcp_server_opensearch --transport stream --log-format json

# Capture logs to a file for analysis
python -m mcp_server_opensearch --log-format json 2>server.jsonl
```

The default (`--log-format text`) produces the same human-readable output as before and is fully backward-compatible.

### Event Types

The server emits the following structured event types:

| Event Type | When Emitted | Key Fields |
|-----------|-------------|------------|
| `tool_execution` | Every tool invocation | `tool_name`, `status`, `duration_ms` |
| `tool_error` | Tool failure | `tool_name`, `status_code`, `exception_type`, `root_cause` |
| `opensearch_request` | Every HTTP request to OpenSearch | `http_method`, `endpoint`, `status_code`, `duration_ms` |
| `datasource_connection` | Auth/connection failure | `auth_method`, `datasource_type`, `opensearch_url` |
| `memory_snapshot` | Periodically (default: every 60s) | `memory_rss_mb`, `pid` |

### Example Log Events

**Successful tool execution:**
```json
{
  "timestamp": "2026-02-27T19:50:45.687Z",
  "level": "INFO",
  "logger": "mcp_server_opensearch.tool_executor",
  "message": "Tool executed: ListIndexTool (711.81ms)",
  "event_type": "tool_execution",
  "tool_name": "ListIndexTool",
  "status": "success",
  "duration_ms": 711.81,
  "tool_key": "ListIndexTool"
}
```

**Tool error with root cause:**
```json
{
  "timestamp": "2026-02-27T21:02:02.095Z",
  "level": "ERROR",
  "logger": "tools.tool_logging",
  "message": "Tool error: CountTool - executing CountTool (NotFoundError)",
  "event_type": "tool_error",
  "tool_name": "CountTool",
  "exception_type": "NotFoundError",
  "status": "error",
  "status_code": 404,
  "root_cause": "index_not_found_exception"
}
```

### Filtering Log Events

Use `jq` to filter structured events from the log file:

```bash
# Show all structured events
cat server.jsonl | jq 'select(.event_type)'

# Show only tool errors
cat server.jsonl | jq 'select(.event_type == "tool_error")'

# Show failed tool executions
cat server.jsonl | jq 'select(.event_type == "tool_execution" and .status == "error")'

# Show 403 errors
cat server.jsonl | jq 'select(.status_code == 403)'
```

### Memory Monitor

When structured logging is enabled, the server periodically logs process memory usage as `memory_snapshot` events. The interval can be configured via the `OPENSEARCH_MEMORY_MONITOR_INTERVAL` environment variable (default: 60 seconds).

```bash
# Set memory snapshot interval to 30 seconds
export OPENSEARCH_MEMORY_MONITOR_INTERVAL=30
python -m mcp_server_opensearch --log-format json
```

For a complete RFC with detailed field references, metric filter patterns, and integration test results, see [RFC: Structured JSON Logging for Monitoring and Metrics](https://github.com/opensearch-project/opensearch-mcp-server-py/issues/177).

## LangChain Integration

The OpenSearch MCP server can be easily integrated with LangChain using the SSE server transport.

### Prerequisites
1. Install required packages:
```bash
pip install langchain langchain-mcp-adapters langchain-openai
```

2. Set up OpenAI API key:
```bash
export OPENAI_API_KEY="<your-openai-key>"
```

3. Ensure OpenSearch MCP server is running in streaming mode:
```bash
# Single Mode
python -m mcp_server_opensearch --transport stream

# Multi Mode
python -m mcp_server_opensearch --mode multi --config clusters.yml --transport stream
```

### Example Integration Script
```python
import asyncio
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langchain.agents import AgentType, initialize_agent

# Initialize LLM (can use any LangChain-compatible LLM)
model = ChatOpenAI(model="gpt-4o")

async def main():
    # Connect to MCP server and create agent
    async with MultiServerMCPClient({
        "opensearch-mcp-server": {
            "transport": "sse",
            "url": "http://localhost:9900/sse",  # SSE server endpoint
            "headers": {
                "Authorization": "Bearer secret-token",
            }
        }
    }) as client:
        tools = client.get_tools()
        agent = initialize_agent(
            tools=tools,
            llm=model,
            agent=AgentType.OPENAI_FUNCTIONS,
            verbose=True,  # Enables detailed output of the agent's thought process
        )

        # Example query
        await agent.ainvoke({"input": "List all indices"})

if __name__ == "__main__":
    asyncio.run(main())
```

### Important Notes
- The script is compatible with any LLM that integrates with LangChain and supports tool calling
- Make sure the OpenSearch MCP server is running before executing the script
- Configure authentication and environment variables as needed
- In multi mode, you can specify which cluster to use in your queries by providing the `opensearch_cluster_name` parameter
- The LLM needs to know the available cluster names from your configuration file to make informed decisions

## Important Notes

- In single mode, the `OPENSEARCH_URL` must be set via environment variables
- In multi mode, the `OPENSEARCH_URL` must be provided in the config file for each cluster
- **Multi Mode Requirement**: LLMs must provide an `opensearch_cluster_name` parameter to specify which cluster to use
- The LLM needs context about available cluster names from your configuration file
