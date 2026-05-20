![OpenSearch logo](https://github.com/opensearch-project/opensearch-py/raw/main/OpenSearch.svg)

- [OpenSearch MCP Server](https://github.com/opensearch-project/opensearch-mcp-server-py#opensearch-mcp-server)
- [Installing opensearch-mcp-server-py](https://github.com/opensearch-project/opensearch-mcp-server-py#installing-opensearch-mcp-server-py)
- [Available tools](https://github.com/opensearch-project/opensearch-mcp-server-py#available-tools)
- [User Guide](https://github.com/opensearch-project/opensearch-mcp-server-py#user-guide)
- [Agent Memory](https://github.com/opensearch-project/opensearch-mcp-server-py#agent-memory)
- [Contributing](https://github.com/opensearch-project/opensearch-mcp-server-py#contributing)
- [Code of Conduct](https://github.com/opensearch-project/opensearch-mcp-server-py#code-of-conduct)
- [License](https://github.com/opensearch-project/opensearch-mcp-server-py#license)
- [Copyright](https://github.com/opensearch-project/opensearch-mcp-server-py#copyright)

## OpenSearch MCP Server

**opensearch-mcp-server-py** is a Model Context Protocol (MCP) server for OpenSearch that enables AI assistants to interact with OpenSearch clusters. It provides a standardized interface for AI models to perform operations like searching indices, retrieving mappings, and managing shards through both stdio and streaming (SSE/Streamable HTTP) protocols.

**Key features:**

- Seamless integration with AI assistants and LLMs through the MCP protocol
- Support for both stdio and streaming server transports (SSE and Streamable HTTP)
- Built-in tools for common OpenSearch operations
- Dynamic per-call connection parameters for targeting different clusters without server reconfiguration
- Easy integration with Claude Desktop and LangChain
- Secure authentication using basic auth, IAM roles, header-based auth, and OpenSearch mTLS

For detailed setup, including Kubernetes deployment and mTLS configuration, see the [User Guide](USER_GUIDE.md).

## Installing opensearch-mcp-server-py

Opensearch-mcp-server-py can be installed from [PyPI](https://pypi.org/project/opensearch-mcp-server-py/) via pip:

```
pip install opensearch-mcp-server-py
```

### Zero-Config Setup

The server can be started with no environment variables at all. Agents provide connection details dynamically on each tool call:

```json
{
  "mcpServers": {
    "opensearch": {
      "command": "uvx",
      "args": ["opensearch-mcp-server-py"]
    }
  }
}
```

With this setup, agents pass `opensearch_url` and authentication parameters directly when calling any tool. This is useful when agents discover endpoints from a knowledge base, runbook, or SOP, or when a single agent needs to work with multiple clusters in one session. See [Dynamic Connection Parameters](USER_GUIDE.md#dynamic-connection-parameters) for details.

## Available Tools

By default, only **core tools** are enabled to provide essential OpenSearch functionality:

### Core Tools (Enabled by Default)

Core tools are grouped under the `core_tools` category and can be disabled at once using `OPENSEARCH_DISABLED_CATEGORIES=core_tools`. Avoid creating custom categories with this name as they will override the built-in category.

- [ListIndexTool](https://docs.opensearch.org/latest/api-reference/cat/cat-indices/): Lists all indices in OpenSearch with full information including docs.count, docs.deleted, store.size, etc. If an index parameter is provided, returns detailed information about that specific index.
- [IndexMappingTool](https://docs.opensearch.org/latest/ml-commons-plugin/agents-tools/tools/index-mapping-tool/): Retrieves index mapping and setting information for an index in OpenSearch.
- [SearchIndexTool](https://docs.opensearch.org/latest/ml-commons-plugin/agents-tools/tools/search-index-tool/): Searches an index using a query written in query domain-specific language (DSL) in OpenSearch.
- [GetShardsTool](https://docs.opensearch.org/latest/api-reference/cat/cat-shards/): Gets information about shards in OpenSearch.
- [ClusterHealthTool](https://docs.opensearch.org/latest/api-reference/cluster-api/cluster-health/): Returns basic information about the health of the cluster.
- [CountTool](https://docs.opensearch.org/latest/api-reference/search-apis/count/): Returns number of documents matching a query.
- [ExplainTool](https://docs.opensearch.org/latest/api-reference/search-apis/explain/): Returns information about why a specific document matches (or doesn't match) a query.
- [MsearchTool](https://docs.opensearch.org/latest/api-reference/search-apis/multi-search/): Allows to execute several search operations in one request.
- [GenericOpenSearchApiTool]: A flexible tool that can call any OpenSearch API endpoint with custom paths, methods, query parameters, and request bodies. Reduces tool explosion by providing a single interface for all OpenSearch APIs. 

### Additional Tools (Disabled by Default)
The following tools are available but disabled by default. To enable them, see the [Tool Filter](USER_GUIDE.md#tool-filter) section in the User Guide.

- [GetClusterStateTool](https://docs.opensearch.org/latest/api-reference/cluster-api/cluster-state/): Gets the current state of the cluster including node information, index settings, and more.
- [GetSegmentsTool](https://docs.opensearch.org/latest/api-reference/cat/cat-segments/): Gets information about Lucene segments in indices, including memory usage, document counts, and segment sizes.
- [CatNodesTool](https://docs.opensearch.org/latest/api-reference/cat/cat-nodes/): Gets information about nodes in the OpenSearch cluster, including system metrics like CPU usage, memory, disk space, and node roles.
- [GetNodesTool](https://docs.opensearch.org/latest/api-reference/nodes-apis/nodes-info/): Gets detailed information about nodes in the OpenSearch cluster, including static information like host system details, JVM info, processor type, node settings, thread pools, installed plugins, and more.
- [GetIndexInfoTool](https://docs.opensearch.org/latest/api-reference/index-apis/get-index/): Gets detailed information about an index including mappings, settings, and aliases. Supports wildcards in index names.
- [GetIndexStatsTool](https://docs.opensearch.org/latest/api-reference/index-apis/stats/): Gets statistics about an index including document count, store size, indexing and search performance metrics.
- [GetQueryInsightsTool](https://docs.opensearch.org/latest/observing-your-data/query-insights/top-n-queries/): Gets query insights from the /\_insights/top_queries endpoint, showing information about query patterns and performance.
- [GetNodesHotThreadsTool](https://docs.opensearch.org/latest/api-reference/nodes-apis/nodes-hot-threads/): Gets information about hot threads in the cluster nodes from the /\_nodes/hot_threads endpoint.
- [GetAllocationTool](https://docs.opensearch.org/latest/api-reference/cat/cat-allocation/): Gets information about shard allocation across nodes in the cluster from the /\_cat/allocation endpoint.
- [GetLongRunningTasksTool](https://docs.opensearch.org/latest/api-reference/cat/cat-tasks/): Gets information about long-running tasks in the cluster, sorted by running time in descending order.

### Agentic Memory Tools (Disabled by Default)

The following tools expose the [OpenSearch Agentic Memory API](https://docs.opensearch.org/latest/ml-commons-plugin/agentic-memory/) — a server-side memory system built into OpenSearch itself. The OpenSearch cluster manages memory containers, sessions, and inference (LLM-based extraction of facts from conversations). These tools require OpenSearch **3.3.0 or later**.

**When to use:** You want OpenSearch to own the full memory lifecycle — including LLM-based inference to extract facts from raw conversations, structured memory types (sessions, working, long-term, history), and server-managed namespacing. Best for production agentic pipelines where memory management should be centralized and not depend on the MCP client.

**Setup:** You must create a memory container in OpenSearch before using these tools (one-time admin operation requiring LLM connector and embedding model configuration). See [Agentic Memory Tools](MEMORY.md#agentic-memory-tools) in the Agent Memory Guide.

Enable with `OPENSEARCH_ENABLED_CATEGORIES=agentic_memory`. When `memory_container_id` is configured via the `agentic_memory` config section or `OPENSEARCH_MEMORY_CONTAINER_ID` environment variable, it is automatically pre-filled in all tool calls.

- [CreateAgenticMemorySessionTool](https://docs.opensearch.org/latest/ml-commons-plugin/api/agentic-memory-apis/create-session/): Creates a new session within a memory container.
- [AddAgenticMemoriesTool](https://docs.opensearch.org/latest/ml-commons-plugin/api/agentic-memory-apis/add-memory/): Adds conversational or structured data memories to a container.
- [GetAgenticMemoryTool](https://docs.opensearch.org/latest/ml-commons-plugin/api/agentic-memory-apis/get-memory/): Retrieves a specific memory by its ID and type.
- [SearchAgenticMemoryTool](https://docs.opensearch.org/latest/ml-commons-plugin/api/agentic-memory-apis/search-memory/): Searches for memories using OpenSearch Query DSL.
- [UpdateAgenticMemoryTool](https://docs.opensearch.org/latest/ml-commons-plugin/api/agentic-memory-apis/update-memory/): Updates an existing memory (supports specific fields based on memory type).
- [DeleteAgenticMemoryByIDTool](https://docs.opensearch.org/latest/ml-commons-plugin/api/agentic-memory-apis/delete-memory/): Deletes a specific memory by its ID.
- [DeleteAgenticMemoryByQueryTool](https://docs.opensearch.org/latest/ml-commons-plugin/api/agentic-memory-apis/delete-memory/): Deletes multiple memories matching a query criteria.

### Search Relevance Workbench Tools (Disabled by Default)
Search Relevance Workbench tools are grouped under the `search_relevance` category and can be enabled at once using `OPENSEARCH_ENABLED_CATEGORIES=search_relevance` or by adding `enabled_categories: [search_relevance]` or explicitly adding individual tools to their config file. See the [Tool Filter](USER_GUIDE.md#tool-filter) section in the User Guide for additional information about how to filter tools.

- [CreateSearchConfigurationTool](https://docs.opensearch.org/latest/search-plugins/search-relevance/search-configurations/#creating-search-configurations): Creates a search configuration consisting of a name, a query body (a query in OpenSearch query domain-specific language), and the target index.
- [GetSearchConfigurationTool](https://docs.opensearch.org/latest/search-plugins/search-relevance/search-configurations/#retrieve-search-configurations): Retrieves a search configuration by ID.
- [DeleteSearchConfigurationTool](https://docs.opensearch.org/latest/search-plugins/search-relevance/search-configurations/#delete-a-search-configuration): Deletes a search configuration by ID.
- [CreateQuerySetTool](https://docs.opensearch.org/latest/search-plugins/search-relevance/query-sets/#example-request-uploading-a-query-set-manually): Creates a query set consisting of a name, a description, and a list of queries.
- [SampleQuerySetTool](https://docs.opensearch.org/latest/search-plugins/search-relevance/query-sets/#creating-query-sets): Samples a query set based on UBI data with different statistical sampling techniques.
- [GetQuerySetTool](https://docs.opensearch.org/latest/search-plugins/search-relevance/query-sets/#retrieve-query-sets): Retrieves a query set by ID.
- [DeleteQuerySetTool](https://docs.opensearch.org/latest/search-plugins/search-relevance/query-sets/#delete-a-query-set): Deletes a query set by ID.
- [CreateJudgmentListTool](https://docs.opensearch.org/latest/search-plugins/search-relevance/judgments/#importing-judgments): Creates a judgment list with judgments originating from an external process.
- [CreateLLMJudgmentListTool](https://docs.opensearch.org/latest/search-plugins/search-relevance/judgments/#creating-ai-assisted-judgments): Creates a judgment list by using an LLM.
- [CreateUBIJudgmentListTool](https://docs.opensearch.org/latest/search-plugins/search-relevance/judgments/#implicit-judgments): Creates a judgment list based on implicit feedback (User Behavior Insights data).
- [GetJudgmentListTool](https://docs.opensearch.org/latest/search-plugins/search-relevance/judgments/): Retrieves a judgment list by ID.
- [DeleteJudgmentListTool](https://docs.opensearch.org/latest/search-plugins/search-relevance/judgments/): Deletes a judgment list by ID.
- [CreateExperimentTool](https://docs.opensearch.org/latest/search-plugins/search-relevance/experiments/): Creates a search relevance experiment. Supports PAIRWISE_COMPARISON (compares 2 search configurations), POINTWISE_EVALUATION (evaluates 1 configuration against judgment lists), and HYBRID_OPTIMIZER (optimizes 1 configuration using judgment lists).
- [GetExperimentTool](https://docs.opensearch.org/latest/search-plugins/search-relevance/experiments/): Retrieves an experiment by ID.
- [DeleteExperimentTool](https://docs.opensearch.org/latest/search-plugins/search-relevance/experiments/): Deletes an experiment by ID.
- [SearchQuerySetsTool](https://docs.opensearch.org/latest/search-plugins/search-relevance/query-sets/): Searches query sets using OpenSearch query DSL. Defaults to match_all if no query body is provided.
- [SearchSearchConfigurationsTool](https://docs.opensearch.org/latest/search-plugins/search-relevance/search-configurations/): Searches search configurations using OpenSearch query DSL. Defaults to match_all if no query body is provided.
- [SearchJudgmentsTool](https://docs.opensearch.org/latest/search-plugins/search-relevance/judgments/): Searches judgments using OpenSearch query DSL. Defaults to match_all if no query body is provided.
- [SearchExperimentsTool](https://docs.opensearch.org/latest/search-plugins/search-relevance/experiments/): Searches experiments using OpenSearch query DSL. Defaults to match_all if no query body is provided.

### Skills Tools (Disabled by Default)

Skills tools are grouped under the `skills` category and can be enabled at once using `OPENSEARCH_ENABLED_CATEGORIES=skills` or by adding `enabled_categories: [skills]` to the config file. See the [Tool Filter](USER_GUIDE.md#tool-filter) section in the User Guide for additional information about how to filter tools.

- [DataDistributionTool](https://docs.opensearch.org/latest/ml-commons-plugin/agents-tools/tools/data-distribution-tool/): Analyzes data distribution patterns and field value frequencies within OpenSearch indices. Supports both single dataset analysis and comparative analysis between two time periods to identify distribution changes.
- [LogPatternAnalysisTool](https://docs.opensearch.org/latest/ml-commons-plugin/agents-tools/tools/log-pattern-analysis-tool/): Detects anomalous log patterns and sequences through comparative analysis between baseline and selection time ranges. Supports log sequence analysis with trace correlation, log pattern difference analysis, and log insights analysis for error detection.

### Memory Tools (Opt-in)

Memory tools give the MCP agent itself persistent, cross-session memory backed by OpenSearch. The agent decides what to save as plain-text statements; OpenSearch stores and semantically indexes them. Enable with `MEMORY_TOOLS_ENABLED=true`. See the [Agent Memory Guide](MEMORY.md) for full setup instructions.

**When to use:** You want a lightweight, agent-driven memory layer that works with any MCP-compatible IDE (Kiro, Claude Code, Cursor). The agent controls what gets remembered — no LLM connectors or embedding models to configure on the OpenSearch side. Requires Amazon OpenSearch Service (managed domain 2.19+ or Serverless) for automatic semantic enrichment. See the [Agent Memory Guide](MEMORY.md#memory-tools) for full setup instructions.

- **SaveMemoryTool**: Saves facts, decisions, and preferences to persistent storage with automatic semantic enrichment.
- **SearchMemoryTool**: Searches memories using natural language with recency-aware ranking.
- **DeleteMemoryTool**: Removes outdated or incorrect memories by document ID.

### Tool Parameters

All tools accept the following **optional connection parameters** that override the server's environment variable configuration on a per-call basis. When omitted, the server falls back to its configured environment variables or cluster config as usual.

| Parameter | Type | Description |
|-----------|------|-------------|
| `opensearch_url` | string | OpenSearch endpoint URL. Overrides `OPENSEARCH_URL`. |
| `opensearch_username` | string | Username for basic auth. Overrides `OPENSEARCH_USERNAME`. |
| `opensearch_password` | string | Password for basic auth. Overrides `OPENSEARCH_PASSWORD`. |
| `opensearch_no_auth` | boolean | Connect without authentication. Overrides `OPENSEARCH_NO_AUTH`. |
| `aws_region` | string | AWS region. Overrides `AWS_REGION`. |
| `aws_iam_arn` | string | IAM role ARN. Overrides `AWS_IAM_ARN`. |
| `aws_profile` | string | AWS profile name. Overrides `AWS_PROFILE`. |
| `aws_opensearch_serverless` | boolean | Use OpenSearch Serverless. Overrides `AWS_OPENSEARCH_SERVERLESS`. |
| `opensearch_ssl_verify` | boolean | SSL certificate verification. Overrides `OPENSEARCH_SSL_VERIFY`. |
| `opensearch_timeout` | integer | Connection timeout in seconds. Overrides `OPENSEARCH_TIMEOUT`. |

This allows agents to dynamically target different clusters per tool call without reconfiguring the server (single mode only). See [Dynamic Connection Parameters](USER_GUIDE.md#dynamic-connection-parameters) in the User Guide for details and examples.

In addition to the common connection parameters above, each tool accepts its own specific parameters:

> **Note:** The `opensearch_url` parameter listed under individual tools below is part of the common connection parameters described above. All common connection parameters (`opensearch_username`, `opensearch_password`, `aws_region`, etc.) are available on every tool but are not repeated in each tool's parameter list for brevity.

- **ListIndexTool**

  - `opensearch_url` (optional): The OpenSearch cluster URL to connect to
  - `index` (optional): The name of the index to get detailed information for. If provided, returns detailed information about this specific index instead of listing all indices.

- **IndexMappingTool**

  - `opensearch_url` (optional): The OpenSearch cluster URL to connect to
  - `index` (required): The name of the index to retrieve mappings for

- **SearchIndexTool**

  - `opensearch_url` (optional): The OpenSearch cluster URL to connect to
  - `index` (required): The name of the index to search in
  - `query_dsl` (required): The search query in OpenSearch Query DSL format
  - `format` (optional): The format of SearchIndexTool response. options are csv and json
  - `size` (optional): The size of SearchIndexTool response. Default is 10, maximum is 100 (configurable). To change the maximum limit, set `max_size_limit` via CLI arguments or config file. See [Tool Customization](USER_GUIDE.md#tool-customization) for details.

- **GetShardsTool**
  - `opensearch_url` (optional): The OpenSearch cluster URL to connect to
  - `index` (required): The name of the index to get shard information for
- **ClusterHealthTool**

  - `opensearch_url` (optional): The OpenSearch cluster URL to connect to
  - `index` (optional): Limit health reporting to a specific index

- **CountTool**

  - `opensearch_url` (optional): The OpenSearch cluster URL to connect to
  - `index` (optional): The name of the index to count documents in
  - `body` (optional): Query in JSON format to filter documents

- **ExplainTool**

  - `opensearch_url` (optional): The OpenSearch cluster URL to connect to
  - `index` (required): The name of the index to retrieve the document from
  - `id` (required): The document ID to explain
  - `body` (required): Query in JSON format to explain against the document

- **MsearchTool**

  - `opensearch_url` (optional): The OpenSearch cluster URL to connect to
  - `index` (optional): Default index to search in
  - `body` (required): Multi-search request body in NDJSON format

- **GetClusterStateTool**

  - `opensearch_url` (optional): The OpenSearch cluster URL to connect to
  - `metric` (optional): Limit the information returned to the specified metrics. Options include: \_all, blocks, metadata, nodes, routing_table, routing_nodes, master_node, version
  - `index` (optional): Limit the information returned to the specified indices

- **GetSegmentsTool**

  - `opensearch_url` (optional): The OpenSearch cluster URL to connect to
  - `index` (optional): Limit the information returned to the specified indices. If not provided, returns segments for all indices

- **CatNodesTool**

  - `opensearch_url` (optional): The OpenSearch cluster URL to connect to
  - `metrics` (optional): A comma-separated list of metrics to display. Available metrics include: id, name, ip, port, role, master, heap.percent, ram.percent, cpu, load_1m, load_5m, load_15m, disk.total, disk.used, disk.avail, disk.used_percent

- **GetNodesTool**

  - `opensearch_url` (optional): The OpenSearch cluster URL to connect to
  - `node_id` (optional): A comma-separated list of node IDs or names to limit the returned information. Supports node filters like \_local, \_master, master:true, data:false, etc. Defaults to \_all.
  - `metric` (optional): A comma-separated list of metric groups to include in the response. Options include: settings, os, process, jvm, thread_pool, transport, http, plugins, ingest, aggregations, indices. Defaults to all metrics.

- **GetIndexInfoTool**

  - `opensearch_url` (optional): The OpenSearch cluster URL to connect to
  - `index` (required): The name of the index to get detailed information for. Wildcards are supported.

- **GetIndexStatsTool**

  - `opensearch_url` (optional): The OpenSearch cluster URL to connect to
  - `index` (required): The name of the index to get statistics for. Wildcards are supported.
  - `metric` (optional): Limit the information returned to the specified metrics. Options include: \_all, completion, docs, fielddata, flush, get, indexing, merge, query_cache, refresh, request_cache, search, segments, store, warmer, bulk

- **GetQueryInsightsTool**

  - `opensearch_url` (optional): The OpenSearch cluster URL to connect to

- **GetNodesHotThreadsTool**

  - `opensearch_url` (optional): The OpenSearch cluster URL to connect to

- **GetAllocationTool**

  - `opensearch_url` (optional): The OpenSearch cluster URL to connect to

- **GetLongRunningTasksTool**
  - `opensearch_url` (optional): The OpenSearch cluster URL to connect to
  - `limit` (optional): The maximum number of tasks to return. Default is 10.

- **CreateAgenticMemorySessionTool**

  - `memory_container_id` (auto-populated): The ID of the memory container where the session will be created. Automatically set when configured via `agentic_memory` config or `OPENSEARCH_MEMORY_CONTAINER_ID` env var. *(Path Parameter)*
  - `session_id` (optional): A custom session ID. If not provided, a random ID is generated. *(Body Parameter)*
  - `summary` (optional): A session summary or description. *(Body Parameter)*
  - `metadata` (optional): Additional metadata for the session provided as key-value pairs. *(Body Parameter)*
  - `namespace` (optional): Namespace information for organizing the session. *(Body Parameter)*

- **AddAgenticMemoriesTool**

  - `memory_container_id` (auto-populated): The ID of the memory container to add the memory to. Automatically set when configured. *(Path Parameter)*
  - `messages` (conditional): A list of messages. Required when `payload_type` is `conversational`. *(Body Parameter)*
  - `structured_data` (conditional): Structured data content. Required when `payload_type` is `data`. *(Body Parameter)*
  - `binary_data` (optional): 	Binary data content encoded as a Base64 string for binary payloads. *(Body Parameter)*
  - `payload_type` (required): The type of payload. Valid values are `conversational` or `data`. See [Payload types](https://docs.opensearch.org/latest/ml-commons-plugin/agentic-memory/#payload-types). *(Body Parameter)*
  - `namespace` (optional): The [namespace](https://docs.opensearch.org/latest/ml-commons-plugin/agentic-memory/#namespaces) context for organizing memories (for example, `user_id`, `session_id`, or `agent_id`). If `session_id` is not specified in the namespace field and `disable_session`: `false` (default is `true`), a new session with a new session ID is created. *(Body Parameter)*
  - `metadata` (optional): Additional metadata for the memory (for example, `status`, `branch`, or custom fields). *(Body Parameter)*
  - `tags` (optional): Tags for categorizing memories. *(Body Parameter)*
  - `infer` (optional): Whether to use an LLM to extract key information (default: `false`). When `true`, the LLM extracts key information from the original text and stores it as a memory. See [Inference mode](https://docs.opensearch.org/latest/ml-commons-plugin/agentic-memory/#inference-mode). *(Body Parameter)*

- **GetAgenticMemoryTool**

  - `memory_container_id` (auto-populated): The ID of the memory container from which to retrieve the memory. Automatically set when configured. *(Path Parameter)*
  - `type` (required): The memory type. Valid values are `sessions`, `working`, `long-term`, and `history`. *(Path Parameter)*
  - `id` (required): The ID of the memory to retrieve. *(Path Parameter)*

- **SearchAgenticMemoryTool**

  - `memory_container_id` (auto-populated): The ID of the memory container. Automatically set when configured. *(Path Parameter)*
  - `type` (required): The memory type. Valid values are `sessions`, `working`, `long-term`, and `history`. *(Path Parameter)*
  - `query` (required): The search query using OpenSearch [query DSL](https://docs.opensearch.org/latest/query-dsl/). *(Body Parameter)*
  - `sort` (optional): Sort specification for the search results. *(Body Parameter)*

- **UpdateAgenticMemoryTool**

  - `memory_container_id` (auto-populated): The ID of the memory container. Automatically set when configured. *(Path Parameter)*
  - `type` (required): The memory type (`sessions`, `working`, or `long-term`).*(Path Parameter)*
  - `id` (required): The ID of the memory to update.*(Path Parameter)*
  - **Session memory request fields:**
    - `summary` (optional): The summary of the session. *(Body Parameter)*
    - `metadata` (optional): Additional metadata for the memory (for example, `status`, `branch`, or custom fields). *(Body Parameter)*
    - `agents` (optional): Additional information about the agents. *(Body Parameter)*
    - `additional_info` (optional): Additional metadata to associate with the session. *(Body Parameter)*
  - **Working memory request fields**
    - `messages` (optional): Updated conversation messages (for conversation type). *(Body Parameter)*
    - `structured_data` (optional): Updated structured data content (for data memory payloads). *(Body Parameter)*
    - `binary_data` (optional): Updated binary data content (for data memory payloads). *(Body Parameter)*
    - `tags` (optional): Updated tags for categorization. *(Body Parameter)*
    - `metadata` (optional): Additional metadata for the memory (for example, `status`, `branch`, or custom fields). *(Body Parameter)*
  - **Long-term memory request fields**
    - `memory` (optional): The updated memory content. *(Body Parameter)*
    - `tags` (optional): Updated tags for categorization. *(Body Parameter)*

- **DeleteAgenticMemoryByIDTool**

  - `memory_container_id` (auto-populated): The ID of the memory container from which to delete the memory. Automatically set when configured. *(Path Parameter)*
  - `type` (required): The type of memory to delete. Valid values are `sessions`, `working`, `long-term`, and `history`. *(Path Parameter)*
  - `id` (required): The ID of the specific memory to delete. *(Path Parameter)*

- **DeleteAgenticMemoryByQueryTool**

  - `memory_container_id` (auto-populated): The ID of the memory container from which to delete the memory. Automatically set when configured. *(Path Parameter)*
  - `type` (required): The type of memory to delete. Valid values are `sessions`, `working`, `long-term`, and `history`. *(Path Parameter)*
  - `query` (required): The OpenSearch [DSL query](https://docs.opensearch.org/latest/query-dsl/) to match memories for deletion. *(Body Parameter)*

- **DataDistributionTool**

  - `index` (required): Target OpenSearch index name.
  - `selectionTimeRangeStart` (required): Start time for analysis target period.
  - `selectionTimeRangeEnd` (required): End time for analysis target period.
  - `timeField` (required): Date/time field for filtering.
  - `baselineTimeRangeStart` (optional): Start time for baseline period.
  - `baselineTimeRangeEnd` (optional): End time for baseline period.
  - `size` (optional): Maximum number of documents to analyze. Default is 1000.

- **LogPatternAnalysisTool**

  - `index` (required): Target OpenSearch index name containing log data.
  - `logFieldName` (required): Field containing raw log messages to analyze.
  - `selectionTimeRangeStart` (required): Start time for analysis target period.
  - `selectionTimeRangeEnd` (required): End time for analysis target period.
  - `timeField` (required): Date/time field for time-based filtering.
  - `traceFieldName` (optional): Field for trace/correlation ID.
  - `baseTimeRangeStart` (optional): Start time for baseline comparison period.
  - `baseTimeRangeEnd` (optional): End time for baseline comparison period.

> More tools coming soon. [Click here](DEVELOPER_GUIDE.md#contributing)

## User Guide

For detailed usage instructions, configuration options, and examples, please see the [User Guide](USER_GUIDE.md).

## Agent Memory

The OpenSearch MCP server includes two distinct memory systems. Both use OpenSearch as the storage backend but differ in who controls the memory lifecycle and what infrastructure they require.

### Choosing the right approach

| | Memory Tools (`MEMORY_TOOLS_ENABLED`) | Agentic Memory Tools (`agentic_memory` category) |
|---|---|---|
| **Who stores memories** | The MCP agent decides what to save as plain-text statements | OpenSearch processes raw conversations and extracts facts via LLM inference |
| **Setup complexity** | Low — index is auto-created on first use | High — requires creating a memory container with LLM connector and embedding model |
| **OpenSearch version** | Amazon OpenSearch Service 2.19+ or Serverless | OpenSearch 3.3.0+ |
| **Semantic search** | Yes, via AWS automatic semantic enrichment | Yes, via configured embedding model |
| **Memory structure** | Flat — each memory is a plain-text statement | Structured — sessions, working, long-term, and history types |
| **LLM inference** | No — agent writes exactly what it wants to remember | Optional (`infer: true`) — OpenSearch uses an LLM to extract facts from conversations |
| **Best for** | IDE agents (Kiro, Claude Code, Cursor) that need quick setup and cross-session continuity | Production agentic pipelines where memory management should be centralized and server-owned |

**Use Memory Tools** when you want a lightweight, agent-driven memory layer that works out of the box with any MCP-compatible IDE. The agent controls what gets remembered. See the [Agent Memory Guide](MEMORY.md#memory-tools) for setup.

**Use Agentic Memory Tools** when you want OpenSearch to own the full memory lifecycle — including LLM-based extraction of facts from raw conversations, structured memory types, and server-managed namespacing. See the [Agent Memory Guide](MEMORY.md#agentic-memory-tools) for setup.

## Contributing

Interested in contributing? Check out our:

- [Development Guide](DEVELOPER_GUIDE.md#opensearch-mcp-server-py-developer-guide) - Setup your development environment
- [Contributing Guidelines](DEVELOPER_GUIDE.md#contributing) - Learn how to contribute

## Code of Conduct

This project has adopted the [Amazon Open Source Code of Conduct](CODE_OF_CONDUCT.md). For more information see the [Code of Conduct FAQ](https://aws.github.io/code-of-conduct-faq), or contact [opensource-codeofconduct@amazon.com](mailto:opensource-codeofconduct@amazon.com) with any additional questions or comments.

## License

This project is licensed under the [Apache v2.0 License](LICENSE.txt).

## Copyright

Copyright 2020-2021 Amazon.com, Inc. or its affiliates. All Rights Reserved.
