# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

from mcp_server_opensearch.global_state import get_mode
from pydantic import BaseModel, Field
from typing import Any, Dict, Literal, Optional, Type, TypeVar



T = TypeVar('T', bound=BaseModel)


def validate_args_for_mode(args_dict: Dict[str, Any], args_model_class: Type[T]) -> T:
    """Validation middleware that handles mode-specific validation.

    Args:
        args_dict: Dictionary of arguments provided by the user
        args_model_class: The Pydantic model class to validate against

    Returns:
        Validated instance of args_model_class
    """
    # Get the current mode from global state
    mode = get_mode()

    args_dict = args_dict.copy()  # Don't modify the original

    if mode == 'single':
        # In single mode, add default values for base fields
        args_dict.setdefault('opensearch_cluster_name', '')

    try:
        return args_model_class(**args_dict)
    except Exception as e:
        # Create a consistent error message format for both modes
        import re

        error_str = str(e)

        # Extract missing field names and create a clearer error message
        missing_fields = re.findall(r'^(\w+)\n  Field required', error_str, re.MULTILINE)
        if missing_fields:
            field_list = ', '.join(f"'{field}'" for field in missing_fields)
            if len(missing_fields) == 1:
                error_msg = f'Missing required field: {field_list}'
            else:
                error_msg = f'Missing required fields: {field_list}'

            # For single mode, show user input without opensearch_cluster_name
            if mode == 'single':
                user_input = {k: v for k, v in args_dict.items() if k != 'opensearch_cluster_name'}
                error_msg += f'\n\nProvided: {user_input}'
            else:
                error_msg += f'\n\nProvided: {args_dict}'

            raise ValueError(error_msg) from e

        raise e


class baseToolArgs(BaseModel):
    """Base class for all tool arguments that contains common OpenSearch connection parameters."""

    opensearch_cluster_name: str = Field(description='The name of the OpenSearch cluster')

    # Optional connection override parameters.
    # When provided, these take precedence over environment variables / server config,
    # allowing agents to dynamically target different clusters per tool call.
    opensearch_url: Optional[str] = Field(
        default=None,
        description='OpenSearch endpoint URL.',
    )
    opensearch_username: Optional[str] = Field(
        default=None,
        description='Username for basic authentication.',
    )
    opensearch_password: Optional[str] = Field(
        default=None,
        description='Password for basic authentication.',
    )
    opensearch_no_auth: Optional[bool] = Field(
        default=None,
        description='If true, connect without authentication.',
    )
    aws_region: Optional[str] = Field(
        default=None,
        description='AWS region for IAM/Serverless authentication.',
    )
    aws_iam_arn: Optional[str] = Field(
        default=None,
        description='IAM role ARN for role-based authentication.',
    )
    aws_profile: Optional[str] = Field(
        default=None,
        description='AWS profile name for authentication.',
    )
    aws_opensearch_serverless: Optional[bool] = Field(
        default=None,
        description='If true, use OpenSearch Serverless service.',
    )
    opensearch_ssl_verify: Optional[bool] = Field(
        default=None,
        description='If false, disable SSL certificate verification.',
    )
    opensearch_timeout: Optional[int] = Field(
        default=None,
        description='Connection timeout in seconds.',
    )


class ListClustersArgs(BaseModel):
    """Arguments for the ListClustersTool. No parameters required."""

    pass


class ListIndicesArgs(baseToolArgs):
    index: str = Field(
        default='',
        description='The name of the index or index pattern to get information for.',
    )
    include_detail: bool = Field(
        default=True,
        description='Whether to include detailed information. If False, returns only index name(s). If True, returns full metadata.',
    )


class GetIndexMappingArgs(baseToolArgs):
    index: str = Field(description='The name of the index to get mapping information for')


class SearchIndexArgs(baseToolArgs):
    index: str = Field(description='The name of the index to search in')
    query_dsl: Any = Field(description='The search query in OpenSearch query DSL format. For keyword-type fields (mapping shows "type": "keyword"), use field name DIRECTLY - do NOT add .keyword suffix. For text-type fields with .keyword subfields, use the .keyword suffix for exact matches. For date/time range queries, MUST include "format" parameter (commonly "format": "strict_date_optional_time||epoch_millis"), e.g. {"range": {"timestamp": {"gte": "2025-12-29T17:15:12Z", "lte": "2025-12-30T08:15:12Z", "format": "strict_date_optional_time||epoch_millis"}}}; if using non-ISO formats, adjust "format" accordingly.')
    format: str = Field(default='json', description='Output format: "json" or "csv"')
    size: int = Field(default=10, description='Number of search results to return. The maximum allowed value is 100, unless overridden by configuration.')


class GetShardsArgs(baseToolArgs):
    index: str = Field(description='The name of the index to get shard information for')


class GetClusterStateArgs(baseToolArgs):
    """Arguments for the GetClusterStateTool."""

    metric: Optional[str] = Field(
        default=None,
        description='Limit the information returned to the specified metrics. Options include: _all, blocks, metadata, nodes, routing_table, routing_nodes, master_node, version',
    )
    index: Optional[str] = Field(
        default=None, description='Limit the information returned to the specified indices'
    )

    class Config:
        json_schema_extra = {
            'examples': [{'metric': 'nodes', 'index': 'my_index'}, {'metric': '_all'}]
        }


class GetSegmentsArgs(baseToolArgs):
    """Arguments for the GetSegmentsTool."""

    index: Optional[str] = Field(
        default=None,
        description='Limit the information returned to the specified indices. If not provided, returns segments for all indices.',
    )

    class Config:
        json_schema_extra = {
            'examples': [
                {'index': 'my_index'},
                {},  # Empty example to show all segments
            ]
        }


class CatNodesArgs(baseToolArgs):
    """Arguments for the CatNodesTool."""

    metrics: Optional[str] = Field(
        default=None,
        description='A comma-separated list of metrics to display. Available metrics include: id, name, ip, port, role, master, heap.percent, ram.percent, cpu, load_1m, load_5m, load_15m, disk.total, disk.used, disk.avail, disk.used_percent',
    )

    class Config:
        json_schema_extra = {
            'examples': [
                {'metrics': 'name,ip,heap.percent,cpu,load_1m'},
                {},  # Empty example to show all node metrics
            ]
        }


class GetIndexInfoArgs(baseToolArgs):
    """Arguments for the GetIndexInfoTool."""

    index: str = Field(
        description='The name of the index to get detailed information for. Wildcards are supported.'
    )

    class Config:
        json_schema_extra = {
            'examples': [
                {'index': 'my_index'},
                {
                    'index': 'my_index*'  # Using wildcard
                },
            ]
        }


class GetIndexStatsArgs(baseToolArgs):
    """Arguments for the GetIndexStatsTool."""

    index: str = Field(
        description='The name of the index to get statistics for. Wildcards are supported.'
    )
    metric: Optional[str] = Field(
        default=None,
        description='Limit the information returned to the specified metrics. Options include: _all, completion, docs, fielddata, flush, get, indexing, merge, query_cache, refresh, request_cache, search, segments, store, warmer, bulk',
    )

    class Config:
        json_schema_extra = {
            'examples': [{'index': 'my_index'}, {'index': 'my_index', 'metric': 'search,indexing'}]
        }


class GetQueryInsightsArgs(baseToolArgs):
    """Arguments for the GetQueryInsightsTool."""

    # No additional parameters needed for the basic implementation
    # The tool will simply call GET /_insights/top_queries without parameters

    class Config:
        json_schema_extra = {
            'examples': [
                {}  # Empty example as no additional parameters are required
            ]
        }


class GetNodesHotThreadsArgs(baseToolArgs):
    """Arguments for the GetNodesHotThreadsTool."""

    # No additional parameters needed for the basic implementation
    # The tool will simply call GET /_nodes/hot_threads without parameters

    class Config:
        json_schema_extra = {
            'examples': [
                {}  # Empty example as no additional parameters are required
            ]
        }


class GetAllocationArgs(baseToolArgs):
    """Arguments for the GetAllocationTool."""

    # No additional parameters needed for the basic implementation
    # The tool will simply call GET /_cat/allocation without parameters

    class Config:
        json_schema_extra = {
            'examples': [
                {}  # Empty example as no additional parameters are required
            ]
        }


class GetLongRunningTasksArgs(baseToolArgs):
    """Arguments for the GetLongRunningTasksTool."""

    limit: Optional[int] = Field(
        default=10, description='The maximum number of tasks to return. Default is 10.'
    )

    class Config:
        json_schema_extra = {
            'examples': [
                {},  # Default example to show top 10 long-running tasks
                {
                    'limit': 5  # Example to show top 5 long-running tasks
                },
            ]
        }


class GetNodesArgs(baseToolArgs):
    """Arguments for the GetNodesTool."""

    node_id: Optional[str] = Field(
        default=None,
        description='A comma-separated list of node IDs or names to limit the returned information. Supports node filters like _local, _master, master:true, data:false, etc. Defaults to _all.',
    )
    metric: Optional[str] = Field(
        default=None,
        description='A comma-separated list of metric groups to include in the response. Options include: settings, os, process, jvm, thread_pool, transport, http, plugins, ingest, aggregations, indices. Defaults to all metrics.',
    )

    class Config:
        json_schema_extra = {
            'examples': [
                {},  # Get all nodes with all metrics
                {'node_id': 'master:true', 'metric': 'process,transport'},
                {'node_id': '_local', 'metric': 'jvm,os'},
            ]
        }


class CreateSearchConfigurationArgs(baseToolArgs):
    """Arguments for the CreateSearchConfigurationTool."""

    name: str = Field(description='Name of the search configuration')
    index: str = Field(description='The index to search')
    query: str = Field(
        description='The search query in OpenSearch DSL format, provided as a JSON string. '
        'Use %SearchText% as a placeholder for the search term, e.g. '
        '\'{"query":{"match":{"title":"%SearchText%"}}}\''
    )

    class Config:
        json_schema_extra = {
            'examples': [
                {
                    'name': 'my-config',
                    'index': 'my-index',
                    'query': '{"query":{"match":{"title":"%SearchText%"}}}',
                }
            ]
        }


class GetSearchConfigurationArgs(baseToolArgs):
    """Arguments for the GetSearchConfigurationTool."""

    search_configuration_id: str = Field(description='ID of the search configuration to retrieve')

    class Config:
        json_schema_extra = {'examples': [{'search_configuration_id': 'abc123'}]}


class DeleteSearchConfigurationArgs(baseToolArgs):
    """Arguments for the DeleteSearchConfigurationTool."""

    search_configuration_id: str = Field(description='ID of the search configuration to delete')

    class Config:
        json_schema_extra = {'examples': [{'search_configuration_id': 'abc123'}]}


class GetQuerySetArgs(baseToolArgs):
    """Arguments for the GetQuerySetTool."""

    query_set_id: str = Field(description='ID of the query set to retrieve')

    class Config:
        json_schema_extra = {
            'examples': [
                {'query_set_id': 'my-query-set-id'},
            ]
        }


class CreateQuerySetArgs(baseToolArgs):
    """Arguments for the CreateQuerySetTool."""

    name: str = Field(description='Name of the query set')
    queries: str = Field(
        description='JSON array of queries, e.g. ["query1", "query2"] or [{"queryText": "query1"}]'
    )
    description: str = Field(default='', description='Optional description of the query set')

    class Config:
        json_schema_extra = {
            'examples': [
                {
                    'name': 'my-query-set',
                    'queries': '["laptop", "wireless headphones", "4k monitor"]',
                    'description': 'Sample product search queries',
                },
            ]
        }


class SampleQuerySetArgs(baseToolArgs):
    """Arguments for the SampleQuerySetTool."""

    name: str = Field(description='Name of the query set')
    query_set_size: int = Field(
        default=20, description='Number of top queries to sample (default: 20)', ge=1
    )
    sampling: Literal['topn', 'random', 'pptss', 'all'] = Field(
        default='topn',
        description=(
            'Sampling method: "topn" (most frequent N queries), '
            '"random" (random sample), '
            '"pptss" (probability-proportional-to-size sampling), '
            '"all" (all queries)'
        ),
    )
    description: str = Field(default='', description='Optional description of the query set')

    class Config:
        json_schema_extra = {
            'examples': [
                {'name': 'top-queries', 'query_set_size': 20},
                {
                    'name': 'top-50-queries',
                    'query_set_size': 50,
                    'description': 'Top 50 most frequent user queries',
                },
                {
                    'name': 'random-queries',
                    'query_set_size': 30,
                    'sampling': 'random',
                    'description': 'Random sample of 30 queries',
                },
            ]
        }


class DeleteQuerySetArgs(baseToolArgs):
    """Arguments for the DeleteQuerySetTool."""

    query_set_id: str = Field(description='ID of the query set to delete')

    class Config:
        json_schema_extra = {
            'examples': [
                {'query_set_id': 'my-query-set-id'},
            ]
        }


class GetJudgmentListArgs(baseToolArgs):
    """Arguments for the GetJudgmentListTool."""

    judgment_id: str = Field(description='ID of the judgment list to retrieve')

    class Config:
        json_schema_extra = {'examples': [{'judgment_id': 'abc123'}]}


class CreateJudgmentListArgs(baseToolArgs):
    """Arguments for the CreateJudgmentListTool."""

    name: str = Field(description='Name of the judgment list')
    judgment_ratings: str = Field(
        description='JSON array of query-ratings objects. Each object must have '
        '"query" (string) and "ratings" (array of {"docId": string, "rating": number}). '
        'Example: [{"query": "laptop", "ratings": [{"docId": "doc1", "rating": 3}, {"docId": "doc2", "rating": 1}]}]'
    )
    description: str = Field(default='', description='Optional description of the judgment list')

    class Config:
        json_schema_extra = {
            'examples': [
                {
                    'name': 'my-judgments',
                    'judgment_ratings': '[{"query": "laptop", "ratings": [{"docId": "doc1", "rating": 3}, {"docId": "doc2", "rating": 1}]}]',
                },
                {
                    'name': 'product-judgments',
                    'description': 'Manual relevance judgments for product search',
                    'judgment_ratings': '[{"query": "wireless headphones", "ratings": [{"docId": "prod-001", "rating": 3}, {"docId": "prod-002", "rating": 2}]}, {"query": "4k monitor", "ratings": [{"docId": "prod-010", "rating": 3}]}]',
                },
            ]
        }


class CreateUBIJudgmentListArgs(baseToolArgs):
    """Arguments for the CreateUBIJudgmentListTool."""

    name: str = Field(description='Name of the judgment list')
    click_model: str = Field(
        description='Click model used to derive relevance from UBI click data. '
        'Common value: "coec" (Clicks Over Expected Clicks)'
    )
    max_rank: int = Field(
        default=20,
        description='Maximum rank position to consider when computing click signals (default: 20)',
        ge=1,
    )
    start_date: Optional[str] = Field(
        default=None,
        description='Start date for UBI event filtering in ISO format (YYYY-MM-DD)',
    )
    end_date: Optional[str] = Field(
        default=None,
        description='End date for UBI event filtering in ISO format (YYYY-MM-DD)',
    )

    class Config:
        json_schema_extra = {
            'examples': [
                {'name': 'ubi-judgments', 'click_model': 'coec'},
                {
                    'name': 'ubi-judgments-q1',
                    'click_model': 'coec',
                    'max_rank': 20,
                    'start_date': '2024-01-01',
                    'end_date': '2024-03-31',
                },
            ]
        }


class CreateLLMJudgmentListArgs(baseToolArgs):
    """Arguments for the CreateLLMJudgmentListTool."""

    name: str = Field(description='Name of the judgment list')
    query_set_id: str = Field(description='ID of the query set to use for generating judgments')
    search_configuration_id: str = Field(
        description='ID of the search configuration that defines how documents are retrieved'
    )
    model_id: str = Field(
        description='ID of the ML Commons model connector used to generate LLM relevance ratings'
    )
    size: int = Field(
        default=5,
        description='Number of top documents to retrieve per query for rating (default: 5)',
        ge=1,
    )
    context_fields: str = Field(
        default='[]',
        description='JSON array of document field names to include as context for the LLM, e.g. ["title", "description"]. Defaults to all fields.',
    )

    class Config:
        json_schema_extra = {
            'examples': [
                {
                    'name': 'llm-judgments',
                    'query_set_id': '5f0115ad-94b9-403a-912f-3e762870ccf6',
                    'search_configuration_id': '2f90d4fd-bd5e-450f-95bb-eabe4a740bd1',
                    'model_id': 'N8AE1osB0jLkkocYjz7D',
                    'size': 5,
                },
                {
                    'name': 'llm-judgments-with-context',
                    'query_set_id': '5f0115ad-94b9-403a-912f-3e762870ccf6',
                    'search_configuration_id': '2f90d4fd-bd5e-450f-95bb-eabe4a740bd1',
                    'model_id': 'N8AE1osB0jLkkocYjz7D',
                    'size': 10,
                    'context_fields': '["title", "description"]',
                },
            ]
        }


class DeleteJudgmentListArgs(baseToolArgs):
    """Arguments for the DeleteJudgmentListTool."""

    judgment_id: str = Field(description='ID of the judgment list to delete')

    class Config:
        json_schema_extra = {'examples': [{'judgment_id': 'abc123'}]}


class GetExperimentArgs(baseToolArgs):
    """Arguments for the GetExperimentTool."""

    experiment_id: str = Field(description='ID of the experiment to retrieve')

    class Config:
        json_schema_extra = {'examples': [{'experiment_id': 'abc123'}]}


class CreateExperimentArgs(baseToolArgs):
    """Arguments for the CreateExperimentTool."""

    query_set_id: str = Field(description='ID of the query set to use for the experiment')
    search_configuration_ids: str = Field(
        description='JSON array of search configuration IDs. '
        'PAIRWISE_COMPARISON requires exactly 2, '
        'POINTWISE_EVALUATION and HYBRID_OPTIMIZER require exactly 1. '
        'Example: ["config-id-1", "config-id-2"]'
    )
    experiment_type: Literal['PAIRWISE_COMPARISON', 'POINTWISE_EVALUATION', 'HYBRID_OPTIMIZER'] = Field(
        description=(
            'Type of experiment: '
            '"PAIRWISE_COMPARISON" (compares 2 search configurations, no judgment lists required), '
            '"POINTWISE_EVALUATION" (evaluates 1 configuration against judgment lists), '
            '"HYBRID_OPTIMIZER" (optimizes 1 configuration using judgment lists)'
        )
    )
    size: int = Field(
        default=10,
        description='Number of results to retrieve per query (default: 10)',
        ge=1,
    )
    judgment_list_ids: Optional[str] = Field(
        default=None,
        description='JSON array of judgment list IDs. Required for POINTWISE_EVALUATION and HYBRID_OPTIMIZER. '
        'Example: ["judgment-id-1"] or ["judgment-id-1", "judgment-id-2"]',
    )

    class Config:
        json_schema_extra = {
            'examples': [
                {
                    'query_set_id': 'qs-123',
                    'search_configuration_ids': '["config-1", "config-2"]',
                    'experiment_type': 'PAIRWISE_COMPARISON',
                    'size': 10,
                },
                {
                    'query_set_id': 'qs-123',
                    'search_configuration_ids': '["config-1"]',
                    'experiment_type': 'POINTWISE_EVALUATION',
                    'judgment_list_ids': '["judgment-1"]',
                },
            ]
        }


class DeleteExperimentArgs(baseToolArgs):
    """Arguments for the DeleteExperimentTool."""

    experiment_id: str = Field(description='ID of the experiment to delete')

    class Config:
        json_schema_extra = {'examples': [{'experiment_id': 'abc123'}]}


_SRW_SEARCH_QUERY_BODY_DESCRIPTION = (
    'OpenSearch query DSL body to filter, sort, and paginate results. '
    'Defaults to {"query": {"match_all": {}}} if not provided. '
    'Example: {"query": {"match": {"name": "my-config"}}, "size": 20}'
)

_SRW_SEARCH_QUERY_BODY_EXAMPLES = [
    {},
    {'query_body': {'query': {'match_all': {}}, 'size': 20}},
    {'query_body': {'query': {'match': {'name': 'my-name'}}}},
]


class SearchQuerySetsArgs(baseToolArgs):
    """Arguments for the SearchQuerySetsTool."""

    query_body: Optional[Any] = Field(
        default=None, description=_SRW_SEARCH_QUERY_BODY_DESCRIPTION
    )

    class Config:
        json_schema_extra = {'examples': _SRW_SEARCH_QUERY_BODY_EXAMPLES}


class SearchSearchConfigurationsArgs(baseToolArgs):
    """Arguments for the SearchSearchConfigurationsTool."""

    query_body: Optional[Any] = Field(
        default=None, description=_SRW_SEARCH_QUERY_BODY_DESCRIPTION
    )

    class Config:
        json_schema_extra = {'examples': _SRW_SEARCH_QUERY_BODY_EXAMPLES}


class SearchJudgmentsArgs(baseToolArgs):
    """Arguments for the SearchJudgmentsTool."""

    query_body: Optional[Any] = Field(
        default=None, description=_SRW_SEARCH_QUERY_BODY_DESCRIPTION
    )

    class Config:
        json_schema_extra = {'examples': _SRW_SEARCH_QUERY_BODY_EXAMPLES}


class SearchExperimentsArgs(baseToolArgs):
    """Arguments for the SearchExperimentsTool."""

    query_body: Optional[Any] = Field(
        default=None, description=_SRW_SEARCH_QUERY_BODY_DESCRIPTION
    )

    class Config:
        json_schema_extra = {'examples': _SRW_SEARCH_QUERY_BODY_EXAMPLES}
