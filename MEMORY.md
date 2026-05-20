# Agent Memory for OpenSearch MCP Server

The OpenSearch MCP server includes two memory systems that give AI agents persistent, cross-session memory backed by OpenSearch. They differ in who controls the memory lifecycle and what infrastructure they require.

## Choosing the Right Approach

| | [Memory Tools](#memory-tools) | [Agentic Memory Tools](#agentic-memory-tools) |
|---|---|---|
| **Who stores memories** | The MCP agent decides what to save as plain-text statements | OpenSearch processes raw conversations and extracts facts via LLM inference |
| **Setup complexity** | Low — index is auto-created on first use | High — requires creating a memory container with LLM connector and embedding model |
| **OpenSearch version** | Amazon OpenSearch Service 2.19+ or Serverless | OpenSearch 3.3.0+ |
| **Semantic search** | Yes, via AWS automatic semantic enrichment | Yes, via configured embedding model |
| **Memory structure** | Flat — each memory is a plain-text statement | Structured — sessions, working, long-term, and history types |
| **LLM inference** | No — agent writes exactly what it wants to remember | Optional (`infer: true`) — OpenSearch uses an LLM to extract facts from conversations |
| **Multi-cluster mode** | Not supported | Supported |
| **Best for** | IDE agents (Kiro, Claude Code, Cursor) that need quick setup and cross-session continuity | Production agentic pipelines where memory management should be centralized and server-owned |

---

## Memory Tools

Memory Tools give the MCP agent itself persistent, cross-session memory. The agent decides what to save as plain-text statements; OpenSearch stores and semantically indexes them. Requires Amazon OpenSearch Service (managed domain 2.19+ or Serverless) for automatic semantic enrichment.

### Why Memory Tools?

AI agents lose context between sessions. Every new conversation starts from scratch — the agent doesn't remember your project conventions, past decisions, or debugging history. Memory Tools solve this by giving agents a persistent knowledge store they can read from and write to during conversations.

**Key benefits:**

- **Cross-session continuity** — agents remember decisions, preferences, and project context across conversations
- **Shared memory across agents** — multiple agents (Kiro, Claude Code, Cursor, or custom agents) can read and write to the same memory store
- **Semantic search** — agents find relevant memories using natural language, powered by OpenSearch automatic semantic enrichment
- **Recency-aware ranking** — search results blend semantic relevance with recency so recent memories are prioritized while highly relevant older memories still surface
- **Scoped access** — memories can be scoped by user, agent, or session to control visibility
- **No embedding setup required** — semantic enrichment runs on the OpenSearch side; no external embedding model or LLM calls needed

### Limitations

Memory Tools require single-cluster mode (`--mode single`, the default). They are not available in `--mode multi`.

If you need memory alongside multi-cluster access, run two separate MCP server instances: one in multi mode for cluster operations, and one in single mode (pointing at your memory cluster) with `MEMORY_TOOLS_ENABLED=true`.

### Architecture

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
              └──┴────────────────────┴──┘
```

Multiple agents connect to the same OpenSearch cluster and share a single memory index. An insight saved by Kiro is available to Claude Code, Cursor, or any MCP-compatible agent. Use `user_id` or `agent_id` scoping to keep memories separate when needed.

### Setup

#### Prerequisites

- An Amazon OpenSearch cluster (Serverless collection or managed domain 2.19+)
- AWS credentials configured (via profile, environment variables, or IAM role)
- Python 3.10+

#### 1. Install the MCP server

```bash
pip install opensearch-mcp-server-py
```

#### 2. Run the interactive installer

The fastest way to set up memory across all your IDEs:

```bash
uvx opensearch-mcp-server-py memory install
```

This will:
- Ask for your OpenSearch Serverless endpoint and AWS profile
- Detect installed IDEs (Kiro, Claude Code, Cursor)
- Configure the MCP server in each IDE
- Install steering files or instructions for automatic memory behavior

#### 3. Manual setup

Enable memory tools by setting `MEMORY_TOOLS_ENABLED=true` in your MCP client configuration.

**Kiro** — add to `~/.kiro/settings/mcp.json`:

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
      "autoApprove": ["SaveMemoryTool", "SearchMemoryTool", "DeleteMemoryTool"]
    }
  }
}
```

**Claude Code** — use `claude mcp add`:

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

**Cursor** — add to `.cursor/mcp.json`:

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

#### 4. Index auto-creation

The memory index (`agent-memory` by default) is created automatically on the first `SaveMemoryTool` call. No manual index setup is required. On OpenSearch Serverless, the server also configures the necessary data access policies automatically.

To use a custom index name, set `MEMORY_INDEX_NAME`:

```bash
MEMORY_INDEX_NAME=my-custom-memory-index
```

### Tools

#### SaveMemoryTool

Saves a memory to persistent storage. Memories are automatically enriched for semantic search.

| Parameter | Required | Description |
|-----------|----------|-------------|
| `memory` | Yes | The text content to remember. Should be a clear, self-contained statement. |
| `user_id` | No | User identifier to scope this memory to a specific user. |
| `agent_id` | No | Agent identifier to scope this memory to a specific agent. |
| `session_id` | No | Session identifier to scope this memory to a specific session. |
| `tags` | No | Comma-separated tags for categorization (e.g. `"preference,dietary"`). |

```json
{
  "memory": "Project uses pytest with asyncio auto mode and ruff for linting",
  "user_id": "alice",
  "agent_id": "kiro",
  "tags": "project,conventions"
}
```

#### SearchMemoryTool

Searches stored memories using natural language. Returns results ranked by a blend of semantic relevance and recency.

| Parameter | Required | Description |
|-----------|----------|-------------|
| `query` | Yes | Natural language search query. Use `"*"` to list all memories. |
| `user_id` | No | Filter memories by user ID. |
| `agent_id` | No | Filter memories by agent ID. |
| `session_id` | No | Filter memories by session ID. |
| `tags` | No | Comma-separated tags to filter by. |
| `size` | No | Maximum number of results (default 10, max 100). |
| `recency_offset_hours` | No | Memories newer than this many hours get full relevance score (default 24). |
| `recency_half_life_hours` | No | Score halves every this many hours past the offset (default 168 = 7 days). |

```json
{
  "query": "project build conventions",
  "user_id": "alice",
  "size": 5
}
```

#### DeleteMemoryTool

Deletes a specific memory by its document ID. Use this to remove outdated or incorrect memories.

| Parameter | Required | Description |
|-----------|----------|-------------|
| `memory_id` | Yes | The ID of the memory document to delete (from `SearchMemoryTool` results). |

### How Agents Use Memory

The tool descriptions include behavioral prompts that guide agents to use memory proactively:

- **SearchMemoryTool** instructs agents to search memory at the start of every conversation and whenever the user asks about topics that may have been previously discussed.
- **SaveMemoryTool** instructs agents to save important facts immediately as they arise, not just at the end of a conversation.

These prompts work across any MCP-compatible client without additional configuration. For stronger guarantees, install lifecycle hooks.

#### Installing Hooks

```bash
# Kiro (workspace-level)
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

### Shared Memory Across Agents

Because memory is stored in OpenSearch — not in any single agent's local state — it is inherently shared. Any agent connected to the same cluster can read and write memories.

- **IDE agent handoff** — switch between Kiro, Claude Code, and Cursor throughout the day. Each agent picks up where the others left off.
- **Multi-agent workflows** — a planning agent saves architectural decisions that an implementation agent later retrieves.
- **Team knowledge** — multiple developers' agents share a common memory store for project conventions and decisions.

Use `user_id`, `agent_id`, and `session_id` to control visibility:

- Set `user_id` to keep memories per-developer
- Set `agent_id` to keep memories per-agent (e.g. only Kiro sees its own memories)
- Omit scoping fields to make memories globally visible to all agents

### Recency-Aware Ranking

Search results blend semantic relevance with recency using an exponential decay function.

| Memory age | Score multiplier |
|------------|-----------------|
| < 1 day | 1.0 (full score) |
| 7 days | 0.5 |
| 14 days | ~0.25 |
| 30 days | ~0.06 |

When listing all memories (`query: "*"`), results are sorted by creation time (newest first) instead.

### Authentication

Memory Tools use the same authentication as the rest of the MCP server. All [supported authentication methods](USER_GUIDE.md#authentication) work: AWS IAM roles, AWS profiles, basic auth, header-based auth, and mTLS.

For OpenSearch Serverless, the server automatically configures data access policies to grant the current IAM principal access to the memory index.

---

## Agentic Memory Tools

Agentic Memory Tools wrap the [OpenSearch Agentic Memory API](https://docs.opensearch.org/latest/ml-commons-plugin/agentic-memory/) — a server-side memory system built into OpenSearch itself. The OpenSearch cluster manages memory containers, sessions, and optional LLM-based inference to extract facts from raw conversations. Requires OpenSearch **3.3.0 or later**.

### Why Agentic Memory Tools?

Where Memory Tools put the agent in charge of what gets remembered, Agentic Memory Tools put OpenSearch in charge. The agent feeds raw conversational messages or structured data into a memory container; OpenSearch processes them, optionally running an LLM to extract key facts, and organizes the results into typed memory stores.

**Key benefits:**

- **Server-side inference** — with `infer: true`, OpenSearch uses a configured LLM to extract and summarize facts from raw conversation messages automatically
- **Structured memory types** — memories are organized into sessions, working, long-term, and history stores, each with distinct semantics
- **Namespace isolation** — memories are scoped by namespace (e.g. `user_id`, `session_id`) at the container level
- **Full audit trail** — the history store records every memory operation
- **Centralized management** — memory lifecycle is owned by the OpenSearch cluster, not the MCP client

### Prerequisites

Before using Agentic Memory Tools, you must create a memory container in OpenSearch. This is a one-time admin operation that requires configuring embedding models, LLM connectors, strategies, and index settings — not something agents do at runtime.

Create a memory container using the [OpenSearch Create Container API](https://docs.opensearch.org/latest/ml-commons-plugin/api/agentic-memory-apis/create-container/) or the OpenSearch dashboard. Note the `memory_container_id` returned — you will need it for configuration.

### Enabling Agentic Memory Tools

Agentic Memory Tools are grouped under the `agentic_memory` category and are **disabled by default**. Enable them by adding `agentic_memory` to `enabled_categories`, and configure the `memory_container_id` so it is pre-filled in all tool calls.

**Option 1: Config file (recommended)**

```yaml
enabled_categories:
  - agentic_memory

agentic_memory:
  memory_container_id: "your-container-id-here"
```

Start the server with the config file:

```bash
python -m mcp_server_opensearch --config path/to/config.yml
```

**Option 2: Environment variables**

```bash
export OPENSEARCH_ENABLED_CATEGORIES=agentic_memory
export OPENSEARCH_MEMORY_CONTAINER_ID="your-container-id-here"
```

When configured, `memory_container_id` is **automatically populated** into all tool calls — agents do not need to pass it manually.

### Tools

#### CreateAgenticMemorySessionTool

Creates a new session within a memory container. Sessions group related memories and can carry metadata and namespace context.

```json
{
  "session_id": "summer-trip-2025",
  "namespace": { "user_id": "alice" },
  "metadata": { "vibe": "relaxing but fun", "budget": "medium" }
}
```

#### AddAgenticMemoriesTool

Adds conversational or structured data memories to a container. Set `infer: true` to have OpenSearch extract key facts via LLM.

| Parameter | Required | Description |
|-----------|----------|-------------|
| `payload_type` | Yes | `conversational` or `data` |
| `messages` | When `payload_type` is `conversational` | List of `{role, content}` message objects |
| `structured_data` | When `payload_type` is `data` | Arbitrary key-value object |
| `namespace` | No | Scoping context (e.g. `user_id`, `session_id`) |
| `infer` | No | If `true`, OpenSearch uses an LLM to extract facts (default: `false`) |
| `tags` | No | Key-value tags for categorization |

```json
{
  "payload_type": "conversational",
  "namespace": { "user_id": "alice", "session_id": "summer-trip-2025" },
  "messages": [
    {
      "role": "user",
      "content": [{"type": "text", "text": "I love gelato and quiet museums."}]
    },
    {
      "role": "assistant",
      "content": [{"type": "text", "text": "Florence would be perfect for both!"}]
    }
  ],
  "infer": true
}
```

#### GetAgenticMemoryTool

Retrieves a specific memory by its type and ID.

| Parameter | Required | Description |
|-----------|----------|-------------|
| `type` | Yes | `sessions`, `working`, `long-term`, or `history` |
| `id` | Yes | The memory ID |

#### SearchAgenticMemoryTool

Searches for memories of a specific type using OpenSearch Query DSL.

| Parameter | Required | Description |
|-----------|----------|-------------|
| `type` | Yes | `sessions`, `working`, `long-term`, or `history` |
| `query` | Yes | OpenSearch Query DSL object |
| `sort` | No | Sort specification |

```json
{
  "type": "working",
  "query": { "match": { "text": "food preferences" } },
  "sort": [{ "created_time": { "order": "desc" } }]
}
```

#### UpdateAgenticMemoryTool

Updates an existing memory. Supported types: `sessions`, `working`, `long-term`.

```json
{
  "type": "sessions",
  "id": "<session_id>",
  "summary": "Planning a trip to Italy focused on nightlife and grappa.",
  "metadata": { "vibe": "nightlife & party" }
}
```

#### DeleteAgenticMemoryByIDTool

Deletes a specific memory by its type and ID.

#### DeleteAgenticMemoryByQueryTool

Deletes all memories of a given type that match an OpenSearch query.

```json
{
  "type": "working",
  "query": { "match": { "text": "museums art galleries" } }
}
```

> The `memory_container_id` field is omitted from all examples above because it is automatically populated from your configuration. You can still pass it explicitly to override.

### Memory Types

| Type | Description |
|------|-------------|
| `sessions` | Conversation sessions and their metadata (start time, participants, state) |
| `working` | Active conversation data, agent state, and temporary context used during ongoing interactions |
| `long-term` | Processed knowledge and facts extracted from conversations over time via LLM inference |
| `history` | Audit trail of all memory operations (add/update/delete) across the container — read-only |

### Typical Workflow

1. **Create a session** with `CreateAgenticMemorySessionTool` to group related memories
2. **Add memories** with `AddAgenticMemoriesTool` — pass raw conversation messages with `infer: true` to let OpenSearch extract facts automatically
3. **Search memories** with `SearchAgenticMemoryTool` using Query DSL to retrieve relevant context
4. **Update or delete** stale memories as the conversation evolves

### Authentication

Agentic Memory Tools use the same authentication as the rest of the MCP server. See [Authentication](USER_GUIDE.md#authentication) in the User Guide.
