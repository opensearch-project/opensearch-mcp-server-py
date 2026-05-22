# CHANGELOG

Inspired from [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)

## [Unreleased]
### Added
- Add configurable server-side query timeout via `OPENSEARCH_QUERY_TIMEOUT` environment variable, passed as `cancel_after_time_interval` to OpenSearch search requests ([#228](https://github.com/opensearch-project/opensearch-mcp-server-py/issues/228))
- Add dynamic per-call connection parameters for multi-tenant support, allowing agents to target different OpenSearch clusters without server reconfiguration ([#230](https://github.com/opensearch-project/opensearch-mcp-server-py/issues/230))
- Add agent memory tools (`SaveMemoryTool`, `SearchMemoryTool`, `DeleteMemoryTool`) with persistent cross-session memory backed by OpenSearch (automatic semantic enrichment, recency-aware ranking, shared memory across agents), `MEMORY.md` documentation, `install-hooks` CLI for Kiro, Claude Code, and Cursor, and `memory install` interactive setup command
- Add `User-Agent` header (`opensearch-mcp-server-py/<version>`) to all OpenSearch requests for MCP traffic identification in cluster logs ([#207](https://github.com/opensearch-project/opensearch-mcp-server-py/issues/207))
- Add new toolset for the OpenSearch Agentic Memory API: `CreateAgenticMemorySessionTool`, `AddAgenticMemoriesTool`, `GetAgenticMemoryTool`, `UpdateAgenticMemoryTool`, `DeleteAgenticMemoryByIDTool`, `DeleteAgenticMemoryByQueryTool`, and `SearchAgenticMemoryTool`. Agentic memory tools are in the `agentic_memory` category and can be enabled via `enabled_categories: ["agentic_memory"]`. The `memory_container_id` is automatically pre-filled in all tool calls when configured via the `agentic_memory` config section or `OPENSEARCH_MEMORY_CONTAINER_ID` environment variable. ([#138](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/138))
- Add `AGENTS.md` and rewrite `DEVELOPER_GUIDE.md` "Adding Custom Tools" section with detailed 4-piece tool anatomy, error handling contracts, and tool category documentation ([#214](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/214))
- Add OpenSearch mTLS support for single-cluster and multi-cluster configurations, including CA bundle, client certificate, and client key settings ([#204](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/204))
- Add per-category write permissions ([#256](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/256))

### Changed
- Default `--host` for the `stream` transport from `0.0.0.0` to `127.0.0.1` so the streamable HTTP listener binds to loopback by default. Operators who need to expose the listener on other interfaces opt in explicitly with `--host 0.0.0.0` ([#253](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/253))

### Infrastructure
- Add code quality CI job running `ruff format --check` and `ruff check` on every PR ([#241](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/241))
- Fix all ruff linting issues: replace star imports with explicit imports, add missing docstrings, fix docstring formatting ([#241](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/241))

### Fixed
- Fix SigV4 auth callable invoked with wrong positional arguments in `BufferedAsyncHttpConnection`, causing 403 signature mismatch on every GET request with query parameters and silent fallback on every POST/PUT/DELETE ([#237](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/237))
- Add `requires_ml_tool` pytest marker to skip skills integration tests when ML tools are not registered on the cluster
- Switch CI from `pull_request` to `pull_request_target` so integration tests run on fork PRs ([#219](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/219))
- Fix multi-mode IT failing for `ListClustersTool` which has no `opensearch_cluster_name` parameter ([#220](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/220))
- Fix non-ASCII characters (e.g. Chinese, Japanese, accented characters) being escaped to Unicode sequences in all tool JSON responses ([#164](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/164))
- Fix `SearchIndexTool` ignoring `size=0`, causing aggregation-only queries to always return 10 hits ([#217](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/217))
- Infer default TCP port from URL scheme (`http` → 80, `https` → 443) when no port is specified, instead of relying on implicit 9200 behavior ([#170](https://github.com/opensearch-project/opensearch-mcp-server-py/issues/170))
- Move skills tools to disabled-by-default category([#225](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/225/))

### Dependencies
- Bump `mcp` from 1.23.0 to 1.27.0, `python-dotenv` from 1.1.0 to 1.2.2 (CVE-2026-28684), and `python-multipart` from 0.0.22 to 0.0.27 (CVE-2026-40347) ([#233](https://github.com/opensearch-project/opensearch-mcp-server-py/issues/233))

### Removed

## [Released 0.9.0]
### Added

- Add Search Relevance Workbench tools for query set management (add, get, delete) ([#187](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/187))
- Add Search Relevance Workbench tools for judgment list management (create, get, delete) ([#190](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/190))
- Add Search Relevance Workbench tools for experiment management (create, get, delete) ([#192](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/192))
- Add Search Relevance Workbench `_search` API tools for querying query sets, search configurations, judgments, and experiments using OpenSearch query DSL ([#193](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/193))
- Add `ListClustersTool` for discovering available clusters in multi-cluster mode ([#210](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/210))

- Add integration test framework with 93 tests covering 6 auth modes, 19 tools, concurrency, error handling, server modes, tool filtering, and write protection ([#179](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/179))
- Refactor CI to matrix strategy with GitHub OIDC for AWS authentication and integration tests on all 3 platforms ([#179](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/179))

### Improved

- Enhanced SearchIndexTool descriptions to improve LLM query construction consistency ([#194](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/194))
- Added Bearer Authorization support when header authentication is enabled ([#189](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/189))
- Sanitized write-disabled error message in GenericOpenSearchApiTool to avoid exposing internal configuration details ([#196](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/196))

## [Released 0.8.0]
### Added

- Optimize JSON output token usage by removing formatting whitespace across all tools ([#167](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/167))
- Rename SearchIndexTool parameter `query` to `query_dsl` to avoid confusion with nested query objects ([#172](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/172))
- Add structured JSON logging (`--log-format json`) for monitoring and metrics ([#178](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/178))

### Fixed

- Fix SearchIndexTool `AttributeError` after `query` to `query_dsl` rename ([#176](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/176))

### Dependencies

- Bump `aiohttp` from 3.11.18 to 3.13.3 ([#175](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/175))
- Bump `mcp` from 1.9.4 to 1.23.0 ([#180](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/180))
- Bump `starlette` from 0.46.2 to 0.49.1 ([#181](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/181))
- Bump `h11` from 0.14.0 to 0.16.0 ([#182](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/182))
- Bump `requests` from 2.32.3 to 2.32.4 ([#183](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/183))
- Bump `python-multipart` from 0.0.20 to 0.0.22 ([#173](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/173))
- Bump `urllib3` from 2.4.0 to 2.6.3 ([#174](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/174))

### Removed

## [Released 0.7.0]
### Added


- Support basic auth through header in HTTP transport ([#152](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/152))
- Add Search Relevance Workbench tools for search configuration management (add, get, delete) ([#171](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/171))

### Fixed
- Fix _fallback_perform_request using wrong url ([#157](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/157))
- Fix search index tool time format issue. ([#159](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/159))

### Removed

## [Released 0.6.1]
### Added
- Support to define max response size from opensearch cluster for better memory management ([#151](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/151))

### Fixed

### Removed

## [Released 0.6.0]

### Added

- Convert JSON to CSV for search index tool result ([#140](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/140))
- Add Normalize scientific-notation floats in a request body for search index tool ([#142](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/142))
- Limit response size to maximum 100 ([#145](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/145))

### Fixed

- Fix AWS auth issues for cat based tools, pin OpenSearchPy to 2.18.0 ([#135](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/135))
- Fix ListIndexTool `include_detail` flag to consistently control output detail level across all scenarios ([#146](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/146))

### Removed

## [Released 0.5.1]

### Added

### Fixed

- Fix IAM role based auth (#129)

### Removed

## [Released 0.5.0]

### Added

- Add `GenericOpenSearchApiTool` - A flexible, general-purpose tool that can interact with any OpenSearch API endpoint, addressing tool explosion and reducing context size. Supports all HTTP methods with write operation protection via `OPENSEARCH_SETTINGS_ALLOW_WRITE` environment variable. Closes [#109](https://github.com/opensearch-project/opensearch-mcp-server-py/issues/109)
- Add header-based authentication + Code Clean up ([#117](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/117))
- Add skills tools integration ([#121](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/121))

### Fixed

- Fix Concurrency: Use Async OpenSearch client to improve concurrency ([#125](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/125))
- [Fix] Close OpenSearch client gracefully ([#126](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/126))

### Removed

## [Released 0.4.0]

### Added

- Add new operational tools for comprehensive OpenSearch cluster analysis: `GetClusterStateTool`, `GetSegmentsTool`, `CatNodesTool`, `GetNodesTool`, `GetIndexInfoTool`, `GetIndexStatsTool`, `GetQueryInsightsTool`, `GetNodesHotThreadsTool`, `GetAllocationTool`, and `GetLongRunningTasksTool` and test cases ([#78](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/78))
- Add include_detail as optional parameter to ListIndexTool ([#97](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/97))
- Allow customizing tool argument descriptions via configuration ([#100](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/100))
- Enhance tool filtering ([#101](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/101))
- Add core tools as a category ([#103](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/103))
- set stateless=True for streaming server by default ([#104](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/104))

## [Released 0.3.2]

- Add timeout as optional parameter ([#92](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/92))

## [Released 0.3.1]

### Added

- Add stateless HTTP as an optional parameter to `streaming_server` ([#86](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/86))

## [Released 0.3]

### Added

- Allow overriding tool properties via configuration ([#69](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/69))
- Extend list indices tool ([#68](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/68))
- Add `OPENSEARCH_NO_AUTH` environment variable for connecting to clusters without authentication

### Fixed

- Handle Tool Filtering failure gracefully and define priority to the AWS Region definitions ([#74](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/74))
- Fix Tool Renaming Edge cases ([#80](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/80))

## [Released 0.2.2]

### Fixed

- Fix endpoint selection bug in ClusterHealthTool and CountTool ([#59](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/59))
- Fix Serverless issues ([#61](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/61))

## [Released 0.2]

### Added

- Add OpenSearch URl as an optional parameter for tool calls ([#20](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/20))
- Add CI to run unit tests ([#22](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/22))
- Add support for AWS OpenSearch serverless ([#31](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/31))
- Add filtering tools based on OpenSearch version compatibility defined in TOOL_REGISTRY ([#32](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/32))
- Add `ClusterHealthTool`, `CountTool`, `MsearchTool`, and `ExplainTool` through OpenSearch API specification ([#33](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/33))
- Add support for Multiple OpenSearch cluster Connectivity ([#45](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/45))
- Add tool filter feature [#46](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/46)
- Support Streamable HTTP Protocol [#47](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/47)
- Add `OPENSEARCH_SSL_VERIFY` environment variable ([#40](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/40))

### Removed

### Fixed

- Fix AWS auth requiring `AWS_REGION` environment variable to be set, will now support using region set via `~/.aws/config` ([#28](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/28))
- Fix OpenSearch client to use refreshable credentials ([#13](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/13))
- fix publish release ci and bump version on main ([#49](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/49))
- fix OpenAPI tools schema, handle NDJSON ([#52](https://github.com/opensearch-project/opensearch-mcp-server-py/pull/52))

### Security
