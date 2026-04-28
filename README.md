![OpenSearch logo](https://github.com/opensearch-project/opensearch-py/raw/main/OpenSearch.svg)

- [OpenSearch MCP Server](https://github.com/opensearch-project/opensearch-mcp-server-py#opensearch-mcp-server)
- [Installing opensearch-mcp-server-py](https://github.com/opensearch-project/opensearch-mcp-server-py#installing-opensearch-mcp-server-py)
- [Available tools](https://github.com/opensearch-project/opensearch-mcp-server-py#available-tools)
- [User Guide](https://github.com/opensearch-project/opensearch-mcp-server-py#user-guide)
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
- Easy integration with Claude Desktop and LangChain
- Secure authentication using basic auth, IAM roles, header-based auth, and OpenSearch mTLS

For detailed setup, including Kubernetes deployment and mTLS configuration, see the [User Guide](USER_GUIDE.md).

## Installing opensearch-mcp-server-py

Opensearch-mcp-server-py can be installed from [PyPI](https://pypi.org/project/opensearch-mcp-server-py/) via pip:

```
pip install opensearch-mcp-server-py
```

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

### Tool Parameters

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
