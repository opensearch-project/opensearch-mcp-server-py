# Agents Guide

When adding or modifying tools, read the existing code first. The patterns are consistent — follow them.

## Key files

- `src/tools/tools.py` — All tool functions and `TOOL_REGISTRY` (the static dict of every tool)
- `src/tools/tool_params.py` — All Pydantic param models (extend `baseToolArgs`)
- `src/opensearch/helper.py` — All async helpers (OpenSearch calls, no try/except)
- `src/tools/tool_filter.py` — Category system that controls tool visibility
- `src/tools/tool_logging.py` — `log_tool_error()` — the **only** way to return errors from tools
- `src/mcp_server_opensearch/tool_executor.py` — Executes tools, checks `is_error: True` for metrics

## Non-obvious contracts

- **Error handling**: Every tool must use `log_tool_error()` in its except block. It returns `is_error: True` which `tool_executor.py` relies on for monitoring. Without it, errors are silently counted as successes.
- **Helpers don't catch exceptions**: Helpers in `helper.py` let exceptions propagate. The tool function in `tools.py` handles errors.
- **Tool filter categories**: Tools not in any enabled category are invisible. Only `core_tools` is enabled by default. New tool groups need a category in `tool_filter.py`.
- **No special registration**: All tools go in `TOOL_REGISTRY` statically. No tool needs custom startup logic.

## Adding tools

See the [Adding Custom Tools](DEVELOPER_GUIDE.md#adding-custom-tools) section in the Developer Guide.

For adding a large group of tools, use the Search Relevance Workbench as a blueprint — 18 tools added with zero new files or infrastructure changes.
