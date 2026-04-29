# Agent Memory for OpenSearch MCP Server

Agent Memory gives AI agents persistent, cross-session memory backed by [Amazon OpenSearch](https://aws.amazon.com/opensearch-service/). Agents can save facts, decisions, and preferences during conversations and recall them later using natural language search powered by [automatic semantic enrichment](https://docs.aws.amazon.com/opensearch-service/latest/developerguide/serverless-semantic-search.html).

## Why Agent Memory?

AI agents lose context between sessions. Every new conversation starts from scratch — the agent doesn't remember your project conventions, past decisions, or debugging history. Agent Memory solves this by giving agents a persistent knowledge store they can read from and write to during conversations.

**Key benefits:**

- **Cross-session continuity** — agents remember decisions, preferences, and project context across conversations
- **Shared memory across agents** — because memory lives in OpenSearch, multiple agents (Kiro, Claude Code, Cursor, or your own custom agents) can read and write to the same memory store
- **Semantic search** — agents find relevant memories using natural language, not exact keyword matches, powered by OpenSearch automatic semantic enrichment
- **Recency-aware ranking** — search results blend semantic relevance with recency so recent memories are prioritized while highly relevant older memories still surface
- **Scoped access** — memories can be scoped by user, agent, or session to control visibility
- **No embedding setup required** — semantic enrichment runs on the OpenSearch side via automatic semantic enrichment; no external embedding model or LLM calls are needed from the MCP server

## Limitations

### Multi-cluster mode not supported

Agent Memory requires single-cluster mode (`--mode single`, the default). Memory tools are not available when the server is started with `--mode multi`.

In multi mode, each tool call routes to a named cluster via `opensearch_cluster_name`. Memory tools rely on a single `OPENSEARCH_URL` for both the opensearch-py client and the boto3 index-creation path, which is incompatible with the per-call cluster routing that multi mode uses.

If you need memory alongside multi-cluster access, run two separate MCP server instances: one in multi mode for cluster operations, and one in single mode (pointing at your memory cluster) with `MEMORY_TOOLS_ENABLED=true`.

## Architecture

```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│    Kiro      │  │ Claude Code │  │   Cursor    │
│   Agent      │  │   Agent     │  │   Agent     │
└──────┬───────┘  └──────┬──────┘  └──────┬──────┘
       │                 │                 │
       └────────────┬────┴────────┬────────┘
                    │             │
              ┌─────▼─────────────▼─────┐
              │   OpenSearch MCP Server  │
              │   (Memory Tools)         │
              └─────────┬───────────────┘
                        │
              ┌─────────▼───────────────┐
              │   Amazon OpenSearch      │
              │   (Serverless or         │
              │    Managed Domain)       │
              │                          │
              │  ┌────────────────────┐  │
              │  │  agent-memory      │  │
              │  │  index             │  │
              │  │  (auto-created)    │  │
              │  └────────────────────┘  │
              └──────────────────────────┘
```

Multiple agents connect to the same OpenSearch cluster and share a single memory index. This means an insight saved by Kiro is available to Claude Code, Cursor, or any MCP-compatible agent — and vice versa. You can also scope memories by `user_id` or `agent_id` to keep them separate when needed.

## Setup

### Prerequisites

- An Amazon OpenSearch cluster (Serverless collection or managed domain)
- AWS credentials configured (via profile, environment variables, or IAM role)
- Python 3.10+

### 1. Install the MCP server

```bash
pip install opensearch-mcp-server-py
```

### 2. Run the interactive installer

The fastest way to set up memory across all your IDEs:

```bash
uvx opensearch-mcp-server-py memory install
```

This will:
- Ask for your OpenSearch Serverless endpoint and AWS profile
- Detect installed IDEs (Kiro, Claude Code, Cursor)
- Configure the MCP server in each IDE
- Install steering files or instructions for automatic memory behavior

### 3. Manual setup

If you prefer manual configuration, enable memory tools by setting the `MEMORY_TOOLS_ENABLED` environment variable to `true` in your MCP client configuration.

#### Kiro

The interactive installer handles this automatically. For manual setup, add to `~/.kiro/settings/mcp.json`:

```json
{
  "mcpServers": {
    "opensearch-mcp-server": {
      "command": "uvx",
      "args": ["opensearch-mcp-server-py"],
      "env": {
        "OPENSEARCH_URL": "https://<collection-id>.<region>.aoss.amazonaws.com",
        "AWS_REGION": "us-east-1",
        "AWS_OPENSEARCH_SERVERLESS": "true",
        "AWS_PROFILE": "your-profile",
        "MEMORY_TOOLS_ENABLED": "true"
      },
      "autoApprove": [
        "SaveMemoryTool",
        "SearchMemoryTool",
        "DeleteMemoryTool"
      ]
    }
  }
}
```

#### Claude Code

The interactive installer handles this automatically. For manual setup, use `claude mcp add`:

```bash
claude mcp add opensearch-mcp-server \
  --command uvx \
  --args opensearch-mcp-server-py \
  --env OPENSEARCH_URL=https://<collection-id>.<region>.aoss.amazonaws.com \
  --env AWS_REGION=us-east-1 \
  --env AWS_OPENSEARCH_SERVERLESS=true \
  --env AWS_PROFILE=your-profile \
  --env MEMORY_TOOLS_ENABLED=true
```

To make Claude Code use memory proactively, add to your `CLAUDE.md`:

```markdown
## Memory

- At the start of every conversation, search memory for relevant context using SearchMemoryTool.
- Save important facts, decisions, and preferences immediately as they arise using SaveMemoryTool.
- Before finishing, do a final check to capture anything missed.
```

#### Cursor

The interactive installer handles this automatically. For manual setup, add to `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "opensearch-mcp-server": {
      "command": "uvx",
      "args": ["opensearch-mcp-server-py"],
      "env": {
        "OPENSEARCH_URL": "https://<collection-id>.<region>.aoss.amazonaws.com",
        "AWS_REGION": "us-east-1",
        "AWS_OPENSEARCH_SERVERLESS": "true",
        "AWS_PROFILE": "your-profile",
        "MEMORY_TOOLS_ENABLED": "true"
      }
    }
  }
}
```

### 4. Index auto-creation

The memory index (`agent-memory` by default) is created automatically on the first `SaveMemoryTool` call. No manual index setup is required. On OpenSearch Serverless, the server also configures the necessary data access policies automatically.

To use a custom index name, set `MEMORY_INDEX_NAME`:

```bash
MEMORY_INDEX_NAME=my-custom-memory-index
```

## Tools

### SaveMemoryTool

Saves a memory to persistent storage. Memories are automatically enriched for semantic search.

**Parameters:**

| Parameter | Required | Description |
|-----------|----------|-------------|
| `memory` | Yes | The text content to remember. Should be a clear, self-contained statement. |
| `user_id` | No | User identifier to scope this memory to a specific user. |
| `agent_id` | No | Agent identifier to scope this memory to a specific agent. |
| `session_id` | No | Session identifier to scope this memory to a specific session. |
| `tags` | No | Comma-separated tags for categorization (e.g. `"preference,dietary"`). |

**Example:**

```json
{
  "memory": "Project uses pytest with asyncio auto mode and ruff for linting",
  "user_id": "alice",
  "agent_id": "kiro",
  "tags": "project,conventions"
}
```

### SearchMemoryTool

Searches stored memories using natural language. Returns results ranked by a blend of semantic relevance and recency.

**Parameters:**

| Parameter | Required | Description |
|-----------|----------|-------------|
| `query` | Yes | Natural language search query. Use `"*"` to list all memories. |
| `user_id` | No | Filter memories by user ID. |
| `agent_id` | No | Filter memories by agent ID. |
| `session_id` | No | Filter memories by session ID. |
| `tags` | No | Comma-separated tags to filter by. |
| `size` | No | Maximum number of results (default 10, max 100). |

**Example:**

```json
{
  "query": "project build conventions",
  "user_id": "alice",
  "size": 5
}
```

### DeleteMemoryTool

Deletes a specific memory by its document ID. Use this to remove outdated or incorrect memories.

**Parameters:**

| Parameter | Required | Description |
|-----------|----------|-------------|
| `memory_id` | Yes | The ID of the memory document to delete (from SearchMemoryTool results). |

## How Agents Use Memory

The tool descriptions include behavioral prompts that guide agents to use memory proactively:

- **SearchMemoryTool** instructs agents to search memory at the start of every conversation and whenever the user asks about topics that may have been previously discussed.
- **SaveMemoryTool** instructs agents to save important facts immediately as they arise, not just at the end of a conversation.

These prompts work across any MCP-compatible client without additional configuration. For stronger guarantees, install lifecycle hooks that automate memory behavior.

### Installing Hooks

The MCP server includes a CLI command to install hooks for your IDE:

```bash
# Kiro (workspace-level — Kiro only reads workspace hooks)
opensearch-mcp-server-py install-hooks --client kiro

# Claude Code (workspace-level)
opensearch-mcp-server-py install-hooks --client claude-code

# Claude Code (user-level, applies to all projects)
opensearch-mcp-server-py install-hooks --client claude-code --scope user
```

This installs two hooks:
- **Search on prompt** — searches memory for relevant context before every response
- **Save on stop** — extracts and saves key facts after every conversation

The command is idempotent — running it again skips hooks that already exist. Restart your IDE after installation.

For clients without hook support, add memory instructions to your agent's system prompt or configuration file (e.g., `CLAUDE.md` for Claude Code).

## Shared Memory Across Agents

Because memory is stored in OpenSearch — not in any single agent's local state — it is inherently shared. Any agent connected to the same OpenSearch cluster can read and write memories.

**Use cases:**

- **IDE agent handoff** — switch between Kiro, Claude Code, and Cursor throughout the day. Each agent picks up where the others left off.
- **Multi-agent workflows** — a planning agent saves architectural decisions that an implementation agent later retrieves.
- **Team knowledge** — multiple developers' agents share a common memory store for project conventions and decisions.

**Scoping memories:**

Use `user_id`, `agent_id`, and `session_id` to control memory visibility:

- Set `user_id` to keep memories per-developer
- Set `agent_id` to keep memories per-agent (e.g. only Kiro sees its own memories)
- Omit scoping fields to make memories globally visible to all agents

## Recency-Aware Ranking

Search results blend semantic relevance with recency using an exponential decay function. This ensures that recent memories are naturally prioritized while highly relevant older memories still surface.

| Memory age | Score multiplier |
|------------|-----------------|
| < 1 day | 1.0 (full score) |
| 7 days | 0.5 |
| 14 days | ~0.25 |
| 30 days | ~0.06 |

When listing all memories (`query: "*"`), results are sorted by creation time (newest first) instead.

## Authentication

Memory tools use the same authentication as the rest of the OpenSearch MCP server. All [supported authentication methods](USER_GUIDE.md) work:

- AWS IAM roles
- AWS profiles
- Basic auth (username/password)
- Header-based auth
- mTLS

For OpenSearch Serverless, the server automatically configures data access policies to grant the current IAM principal access to the memory index.
