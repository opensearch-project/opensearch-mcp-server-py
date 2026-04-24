![OpenSearch logo](https://github.com/opensearch-project/opensearch-py/raw/main/OpenSearch.svg)

# OpenSearch MCP Server Python Developer Guide

## Table of Contents
- [Overview](#overview)
- [Development Setup](#development-setup)
- [Local Testing and Development Workflow](#local-testing-and-development-workflow)
- [Running the Server](#running-the-server)
- [Foolproof Build Testing Workflow](#foolproof-build-testing-workflow)
- [Development Configuration](#development-configuration)
- [Managing Dependencies](#managing-dependencies)
- [Adding Custom Tools](#adding-custom-tools)
- [Testing](#testing)

## Overview

This guide is for developers who want to contribute to the OpenSearch MCP Server Python project. It covers local development setup, project structure, and how to add new tools to the server.

## Development Setup

### 1. Clone the Repository

```bash
git clone git@github.com:opensearch-project/opensearch-mcp-server-py.git
cd opensearch-mcp-server-py
```

### 2. Set Up Development Environment

Follow the [Local Testing and Development Workflow](#local-testing-and-development-workflow) section below for complete setup instructions.

## Local Testing and Development Workflow

### Foolproof Local Testing Workflow

**All commands must be run from the project root directory** (where `pyproject.toml` is located).

#### First Time Setup

```bash
# From project root
cd /path/to/opensearch-mcp-server-py

# 1. Update lock file (ensures uv.lock matches pyproject.toml)
uv lock

# 2. Create venv and install everything (dependencies + package in editable mode)
uv sync

# 3. Activate the venv
source .venv/bin/activate

# 4. Run the server
python -m mcp_server_opensearch --transport stream --port 9900 --debug
```

#### Daily Testing (After Setup)

```bash
# From project root
source .venv/bin/activate
python -m mcp_server_opensearch --transport stream --port 9900 --debug
```

#### After Changing Dependencies in pyproject.toml

```bash
# From project root
# 1. Update lock file
uv lock

# 2. Sync environment (updates dependencies and package)
uv sync

# 3. Run the server
source .venv/bin/activate
python -m mcp_server_opensearch --transport stream --port 9900 --debug
```

### Common Questions

**Q: Do I need to run `uv lock` before testing?**  
A: Only if you changed `pyproject.toml`. For code changes in `src/`, just activate venv and run.

**Q: What does `uv sync` do?**  
A: Creates `.venv`, installs all dependencies from `uv.lock`, and installs your package in editable mode. Everything in one command.

**Q: Where do I run commands from?**  
A: Project root (where `pyproject.toml` is located).

**Q: Do I need to rebuild after code changes?**  
A: No. `uv sync` installs the package in editable mode, so changes in `src/` are picked up automatically.

**Q: Can I use a different venv name?**  
A: Yes, but `.venv` is the default. Use `uv sync --python <path>` or set `UV_PROJECT_ENVIRONMENT` environment variable.

**Q: How do I clean/reset my venv and start fresh?**  
A: Delete `.venv` and run `uv sync` again:
```bash
# From project root
rm -rf .venv
uv sync
source .venv/bin/activate
python -m mcp_server_opensearch --transport stream --port 9900 --debug
```
This gives you a completely fresh environment with all dependencies reinstalled.

## Running the Server

After setting up your environment (see above), you can run the server from the project root:

```bash
# Activate venv (if not already activated)
source .venv/bin/activate

# Run streaming server (recommended for testing)
python -m mcp_server_opensearch --transport stream --port 9900 --debug

# Run stdio server (default)
python -m mcp_server_opensearch

# Run with custom AWS profile
python -m mcp_server_opensearch --profile my-profile

# Run in multi mode with config file
python -m mcp_server_opensearch --mode multi --config config/clusters.yml --transport stream
```

## Foolproof Build Testing Workflow

Test the package exactly as end users will install it (before releasing to PyPI).

**All commands must be run from the project root directory.**

#### Complete Build and Test Workflow

```bash
# From project root
cd /path/to/opensearch-mcp-server-py

# Step 1: Build the package
python3 -m venv .venv-clean
source .venv-clean/bin/activate
pip install --upgrade build twine
rm -rf dist/ build/
find . -name "*.egg-info" -type d -exec rm -rf {} + 2>/dev/null || true
python -m build

# Step 2: Test the built package in a fresh environment
python3 -m venv .venv-test-install
source .venv-test-install/bin/activate
pip install dist/opensearch_mcp_server_py-*.whl
opensearch-mcp-server-py --transport stream --port 9900 --debug
```

#### Common Questions

**Q: Why do I need separate venvs for build and test?**  
A: To ensure a clean build without contamination from your dev environment, and a fresh test that matches end-user installation.

**Q: Can I reuse the build/test venvs?**  
A: Yes, but delete and recreate them for truly clean builds before releases.

**Q: What files are created?**  
A: `dist/opensearch_mcp_server_py-X.X.X-py3-none-any.whl` and `.tar.gz` - these are what get published to PyPI.

## Development Configuration

### MCP Configuration for Development

Create an MCP configuration file for your AI agent to connect to your development server:

#### For Q Developer CLI (`~/.aws/amazonq/mcp.json`):
```json
{
    "mcpServers": {
        "opensearch-mcp-server": {
            "command": "uv",
            "args": [
                "--directory",
                "/path/to/your/clone/opensearch-mcp-server-py",
                "run",
                "--",
                "python",
                "-m",
                "mcp_server_opensearch"
            ],
            "env": {
                "OPENSEARCH_URL": "<your_opensearch_domain_url>",
                "OPENSEARCH_USERNAME": "<your_opensearch_domain_username>",
                "OPENSEARCH_PASSWORD": "<your_opensearch_domain_password>"
            }
        }
    }
}
```

#### For Claude Desktop (`claude_desktop_config.json`):
```json
{
    "mcpServers": {
        "opensearch-mcp-server": {
            "command": "uv",
            "args": [
                "--directory",
                "/path/to/your/clone/opensearch-mcp-server-py",
                "run",
                "--",
                "python",
                "-m",
                "mcp_server_opensearch"
            ],
            "env": {
                "OPENSEARCH_URL": "<your_opensearch_domain_url>",
                "OPENSEARCH_USERNAME": "<your_username>",
                "OPENSEARCH_PASSWORD": "<your_password>"
            }
        }
    }
}
```

## Managing Dependencies

### Adding New Dependencies
```bash
# Add a new package (automatically updates pyproject.toml, uv.lock, and installs)
uv add <package-name>

# Add with specific version
uv add <package-name>==1.2.3

# Add as development dependency
uv add --dev <package-name>
```

### Updating Dependencies
```bash
# After manually editing pyproject.toml, update lock file and sync
uv lock
uv sync

# Update all dependencies to latest versions
uv lock --upgrade
uv sync
```

## Adding Custom Tools

Every tool has 4 pieces. Follow the existing patterns exactly — read the referenced files to see how current tools are structured.

### 1. Pydantic params — `src/tools/tool_params.py`

Add your args model here, extending `baseToolArgs`. See existing models like `SearchIndexArgs` or `GetIndexMappingArgs` for the pattern.

```python
class YourToolArgs(baseToolArgs):
    param1: str = Field(description="Description of param1")
    optional_param: Optional[str] = Field(default=None, description="Optional param")
```

### 2. Async helper — `src/opensearch/helper.py`

Add your OpenSearch call here. Helpers should be simple — make the call and let exceptions propagate. **Do not add try/except in helpers**; error handling belongs in the tool function.

```python
async def your_helper(args: YourToolArgs):
    async with get_opensearch_client(args) as client:
        return await client.some_api(param=args.param1)
```

### 3. Async tool function — `src/tools/tools.py`

Add your tool function here. For error handling, **always use `log_tool_error()`** from `src/tools/tool_logging.py`:

```python
async def your_tool_function(args: YourToolArgs) -> list[dict]:
    try:
        await check_tool_compatibility('YourToolName', args)
        result = await your_helper(args)
        formatted = json.dumps(result, separators=(',', ':'))
        return [{'type': 'text', 'text': f'Result:\n{formatted}'}]
    except Exception as e:
        return log_tool_error('YourToolName', e, 'description of what failed')
```

This is critical — `log_tool_error()` returns responses with `is_error: True`, which `tool_executor.py` uses for metrics and monitoring. Without it, errors are silently logged as successes.

### 4. `TOOL_REGISTRY` entry — `src/tools/tools.py`

Add your tool to the static `TOOL_REGISTRY` dict. Look at any existing entry for the format.

```python
'YourToolName': {
    'display_name': 'YourToolName',
    'description': 'What the tool does',
    'input_schema': YourToolArgs.model_json_schema(),
    'function': your_tool_function,
    'args_model': YourToolArgs,
    'http_methods': 'GET',          # Controls write protection filter
    'min_version': '2.0.0',         # Optional: minimum OpenSearch version
},
```

Key fields:
- `display_name` — name exposed to MCP clients (must match the registry key)
- `http_methods` — `'GET'`, `'POST'`, `'PUT'`, `'DELETE'`, or `'GET, POST'`. When write protection is enabled, non-GET tools are filtered out
- `min_version` / `max_version` — optional semver strings for OpenSearch version gating
- `multi_only` — optional bool, if `True` the tool only appears in multi-cluster mode

### 5. Tool category — `src/tools/tool_filter.py`

Add your tool to the appropriate category list (`core_tools`, `search_relevance`, or a new category). Tools not in any enabled category are **filtered out** and invisible to clients. See the `search_relevance` category definition for how to add a new opt-in category.

Categories are enabled via YAML config or environment variable. Only `core_tools` is enabled by default.

**Via YAML config**:
```yaml
tool_filters:
  enabled_categories:
    - search_relevance
    - my_custom_category
```

**Via environment variable**:
```bash
export OPENSEARCH_ENABLED_CATEGORIES="search_relevance,my_custom_category"
```

In multi-cluster mode, all tools are returned without category filtering.

### 6. Tests

Add unit tests in `tests/tools/` following existing test patterns.

### Reference

The Search Relevance Workbench added 18 tools with zero infrastructure changes — all params in `tool_params.py`, helpers in `helper.py`, tool functions in `tools.py`, entries in `TOOL_REGISTRY`, and an opt-in `search_relevance` category in `tool_filter.py`. Use it as a blueprint for adding tool groups.

> **Note**: All new source files must include the Apache 2.0 license header:
> ```python
> # Copyright OpenSearch Contributors
> # SPDX-License-Identifier: Apache-2.0
> ```


## Testing

### Running Unit Tests

```bash
# Run all unit tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=mcp_server_opensearch

# Run specific test file
uv run pytest tests/test_tools.py

# Run tests with verbose output
uv run pytest -v
```

### Running Integration Tests Locally

Integration tests run against a real OpenSearch cluster. Set the following environment variables, then run:

```bash
# Required — OpenSearch cluster endpoint and basic auth credentials
export IT_OPENSEARCH_URL="https://your-opensearch-endpoint"
export IT_BASIC_AUTH_USERNAME="admin"
export IT_BASIC_AUTH_PASSWORD="your-password"

# Required for AWS auth tests — temporary AWS credentials
export IT_AWS_ACCESS_KEY_ID="your-access-key"
export IT_AWS_SECRET_ACCESS_KEY="your-secret-key"
export IT_AWS_SESSION_TOKEN="your-session-token"
export IT_AWS_REGION="us-west-2"

# Required for IAM role assumption tests
export IT_IAM_ROLE_ARN="arn:aws:iam::123456789012:role/your-role"

# Optional — custom test index name (defaults to mcp-integration-test)
export IT_TEST_INDEX="my-test-index"

# Install the package and IT dependencies, then run
pip install dist/*.whl
pip install pytest-asyncio pytest-timeout "httpx[http2]"
python -m pytest integration_tests/ -v --tb=short --timeout=300
```

Tests that require missing environment variables will be automatically skipped.

### Code Quality

```bash
# Format code
uv run ruff format .

# Check code quality
uv run ruff check .

# Run type checking
uv run mypy src/
```

> **Note**: Make sure to run tests and code quality checks before submitting your changes.
