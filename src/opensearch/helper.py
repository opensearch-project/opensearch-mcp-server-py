# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import json
import logging
import csv
import io
import math
from decimal import Decimal
import json
from semver import Version
from tools.tool_params import *

# Configure logging
logger = logging.getLogger(__name__)


# List all the helper functions, these functions perform a single rest call to opensearch
# these functions will be used in tools folder to eventually write more complex tools
async def list_indices(args: ListIndicesArgs) -> json:
    from .client import get_opensearch_client

    async with get_opensearch_client(args) as client:
        # Pass index parameter if provided to filter results by pattern or specific index
        index_param = args.index if args.index else None
        response = await client.cat.indices(index=index_param, format='json')
        return response


async def get_index(args: ListIndicesArgs) -> json:
    """Get detailed information about a specific index.

    Args:
        args: ListIndicesArgs containing the index name

    Returns:
        json: Detailed index information including settings and mappings
    """
    from .client import get_opensearch_client

    async with get_opensearch_client(args) as client:
        response = await client.indices.get(index=args.index)
        return response


async def get_index_mapping(args: GetIndexMappingArgs) -> json:
    from .client import get_opensearch_client

    async with get_opensearch_client(args) as client:
        response = await client.indices.get_mapping(index=args.index)
        return response


async def search_index(args: SearchIndexArgs) -> json:
    from .client import get_opensearch_client
    from tools.tools import TOOL_REGISTRY

    if isinstance(args.query_dsl, str):
        validate_json_string(args.query_dsl)

    async with get_opensearch_client(args) as client:
        query = normalize_scientific_notation(args.query_dsl)

        # Limit size to maximum of 100
        tool_info = TOOL_REGISTRY.get('SearchIndexTool', {})
        max_size_limit = tool_info.get('max_size_limit', 100)  # Default to 100 if not configured

        effective_size = min(args.size, max_size_limit) if args.size is not None else 10
        query['size'] = effective_size

        response = await client.search(index=args.index, body=query)
        return response


async def get_shards(args: GetShardsArgs) -> json:
    from .client import get_opensearch_client

    async with get_opensearch_client(args) as client:
        response = await client.cat.shards(index=args.index, format='json')
        return response


async def get_segments(args: GetSegmentsArgs) -> json:
    """Get information about Lucene segments in indices.

    Args:
        args: GetSegmentsArgs containing optional index filter

    Returns:
        json: Segment information for the specified indices or all indices
    """
    from .client import get_opensearch_client

    async with get_opensearch_client(args) as client:
        # If index is provided, filter by that index
        index_param = args.index if args.index else None

        response = await client.cat.segments(index=index_param, format='json')
        return response


async def get_cluster_state(args: GetClusterStateArgs) -> json:
    """Get the current state of the cluster.

    Args:
        args: GetClusterStateArgs containing optional metric and index filters

    Returns:
        json: Cluster state information based on the requested metrics and indices
    """
    from .client import get_opensearch_client

    async with get_opensearch_client(args) as client:
        # Build parameters dictionary with non-None values
        params = {}
        if args.metric:
            params['metric'] = args.metric
        if args.index:
            params['index'] = args.index

        response = await client.cluster.state(**params)
        return response


async def get_nodes(args: CatNodesArgs) -> json:
    """Get information about nodes in the cluster.

    Args:
        args: GetNodesArgs containing optional metrics filter

    Returns:
        json: Node information for the cluster
    """
    from .client import get_opensearch_client

    async with get_opensearch_client(args) as client:
        # If metrics is provided, use it as a parameter
        metrics_param = args.metrics if args.metrics else None

        response = await client.cat.nodes(format='json', h=metrics_param)
        return response


async def get_index_info(args: GetIndexInfoArgs) -> json:
    """Get detailed information about an index including mappings, settings, and aliases.

    Args:
        args: GetIndexInfoArgs containing the index name

    Returns:
        json: Detailed index information
    """
    from .client import get_opensearch_client

    async with get_opensearch_client(args) as client:
        response = await client.indices.get(index=args.index)
        return response


async def get_index_stats(args: GetIndexStatsArgs) -> json:
    """Get statistics about an index.

    Args:
        args: GetIndexStatsArgs containing the index name and optional metric filter

    Returns:
        json: Index statistics
    """
    from .client import get_opensearch_client

    async with get_opensearch_client(args) as client:
        # Build parameters dictionary with non-None values
        params = {}
        if args.metric:
            params['metric'] = args.metric

        response = await client.indices.stats(index=args.index, **params)
        return response


async def get_query_insights(args: GetQueryInsightsArgs) -> json:
    """Get insights about top queries in the cluster.

    Args:
        args: GetQueryInsightsArgs containing connection parameters

    Returns:
        json: Query insights from the /_insights/top_queries endpoint
    """
    from .client import get_opensearch_client

    async with get_opensearch_client(args) as client:
        # Use the transport.perform_request method to make a direct REST API call
        # since the Python client might not have a dedicated method for this endpoint
        response = await client.transport.perform_request(
            method='GET', url='/_insights/top_queries'
        )

        return response


async def get_nodes_hot_threads(args: GetNodesHotThreadsArgs) -> str:
    """Get information about hot threads in the cluster nodes.

    Args:
        args: GetNodesHotThreadsArgs containing connection parameters

    Returns:
        str: Hot threads information from the /_nodes/hot_threads endpoint
    """
    from .client import get_opensearch_client

    async with get_opensearch_client(args) as client:
        # Use the transport.perform_request method to make a direct REST API call
        # The hot_threads API returns text, not JSON
        response = await client.transport.perform_request(method='GET', url='/_nodes/hot_threads')

        return response


async def get_allocation(args: GetAllocationArgs) -> json:
    """Get information about shard allocation across nodes in the cluster.

    Args:
        args: GetAllocationArgs containing connection parameters

    Returns:
        json: Allocation information from the /_cat/allocation endpoint
    """
    from .client import get_opensearch_client

    async with get_opensearch_client(args) as client:
        # Use the cat.allocation method with JSON format
        response = await client.cat.allocation(format='json')

        return response


async def get_long_running_tasks(args: GetLongRunningTasksArgs) -> json:
    """Get information about long-running tasks in the cluster, sorted by running time.

    Args:
        args: GetLongRunningTasksArgs containing limit parameter

    Returns:
        json: Task information from the /_cat/tasks endpoint, sorted by running time
    """
    from .client import get_opensearch_client

    async with get_opensearch_client(args) as client:
        # Use the transport.perform_request method to make a direct REST API call
        # since we need to sort by running_time which might not be directly supported by the client
        response = await client.transport.perform_request(
            method='GET',
            url='/_cat/tasks',
            params={
                's': 'running_time:desc',  # Sort by running time in descending order
                'format': 'json',
            },
        )

        # Limit the number of tasks returned if specified
        if args.limit and isinstance(response, list):
            return response[: args.limit]

        return response


async def get_nodes_info(args: GetNodesArgs) -> json:
    """Get detailed information about nodes in the cluster.

    Args:
        args: GetNodesArgs containing optional node_id, metric filters, and other parameters

    Returns:
        json: Detailed node information from the /_nodes endpoint
    """
    from .client import get_opensearch_client

    async with get_opensearch_client(args) as client:
        # Build the URL path based on provided parameters
        url_parts = ['/_nodes']

        # Add node_id if provided
        if args.node_id:
            url_parts.append(args.node_id)

        # Add metric if provided
        if args.metric:
            url_parts.append(args.metric)

        url = '/'.join(url_parts)

        # Use the transport.perform_request method to make a direct REST API call
        response = await client.transport.perform_request(method='GET', url=url)

        return response


async def get_query_set(args: GetQuerySetArgs) -> json:
    """Get a specific query set by ID from the Search Relevance plugin.

    Args:
        args: GetQuerySetArgs containing the query_set_id

    Returns:
        json: Query set details
    """
    from .client import get_opensearch_client

    async with get_opensearch_client(args) as client:
        response = await client.plugins.search_relevance.get_query_sets(
            query_set_id=args.query_set_id
        )
        return response


async def create_query_set(args: CreateQuerySetArgs) -> json:
    """Create a new query set with a list of queries in the Search Relevance plugin.

    Args:
        args: CreateQuerySetArgs containing name, queries (JSON string), and optional description

    Returns:
        json: Result of the creation operation with query set ID
    """
    import json as _json

    from .client import get_opensearch_client

    queries = _json.loads(args.queries) if isinstance(args.queries, str) else args.queries
    if not isinstance(queries, list):
        raise ValueError(
            'queries must be a JSON array of strings or objects with queryText, e.g. ["q1", "q2"]'
        )

    query_set_queries = []
    for q in queries:
        if isinstance(q, str):
            query_set_queries.append({'queryText': q})
        elif isinstance(q, dict) and 'queryText' in q:
            query_set_queries.append(q)
        else:
            query_set_queries.append({'queryText': str(q)})

    body = {
        'name': args.name,
        'description': args.description or f'Query set: {args.name}',
        'sampling': 'manual',
        'querySetQueries': query_set_queries,
    }

    async with get_opensearch_client(args) as client:
        response = await client.plugins.search_relevance.put_query_sets(body=body)
        return response


async def sample_query_set(args: SampleQuerySetArgs) -> json:
    """Create a query set by sampling the top N most frequent queries from UBI data.

    Args:
        args: SampleQuerySetArgs containing name, query_set_size, and optional description

    Returns:
        json: Result of the sampling operation with the created query set ID
    """
    from .client import get_opensearch_client

    body = {
        'name': args.name,
        'description': args.description or f'Query set: {args.name} ({args.sampling}, size={args.query_set_size})',
        'sampling': args.sampling,
        'querySetSize': args.query_set_size,
    }

    async with get_opensearch_client(args) as client:
        response = await client.plugins.search_relevance.post_query_sets(body=body)
        return response


async def delete_query_set(args: DeleteQuerySetArgs) -> json:
    """Delete a query set by ID from the Search Relevance plugin.

    Args:
        args: DeleteQuerySetArgs containing the query_set_id

    Returns:
        json: Result of the deletion operation
    """
    from .client import get_opensearch_client

    async with get_opensearch_client(args) as client:
        response = await client.plugins.search_relevance.delete_query_sets(
            query_set_id=args.query_set_id
        )
        return response


async def get_experiment(args: GetExperimentArgs) -> json:
    """Retrieve an experiment by ID via the Search Relevance plugin.

    Args:
        args: GetExperimentArgs containing the experiment_id

    Returns:
        json: OpenSearch response with the experiment details
    """
    from .client import get_opensearch_client

    async with get_opensearch_client(args) as client:
        response = await client.plugins.search_relevance.get_experiments(
            experiment_id=args.experiment_id
        )
        return response


async def _srw_search(args, entity: str) -> json:
    """Execute a _search request against a Search Relevance Workbench entity index.

    Args:
        args: Tool args containing the optional query_body
        entity: The SRW entity name, e.g. 'query_sets', 'search_configurations',
                'judgments', or 'experiment'

    Returns:
        json: OpenSearch search response
    """
    from .client import get_opensearch_client

    if args.query_body is None:
        body = {'query': {'match_all': {}}}
    elif isinstance(args.query_body, str):
        validate_json_string(args.query_body)
        body = json.loads(args.query_body)
    else:
        body = args.query_body
    async with get_opensearch_client(args) as client:
        response = await client.transport.perform_request(
            method='POST',
            url=f'/_plugins/_search_relevance/{entity}/_search',
            body=json.dumps(body),
        )
        return response


async def create_experiment(args: CreateExperimentArgs) -> json:
    """Create an experiment via the Search Relevance plugin.

    Validates configuration counts for each experiment type and requires
    judgment lists for POINTWISE_EVALUATION and HYBRID_OPTIMIZER.

    Args:
        args: CreateExperimentArgs containing query_set_id, search_configuration_ids,
              experiment_type, size, and optional judgment_list_ids

    Returns:
        json: OpenSearch response with the created experiment ID
    """
    from .client import get_opensearch_client

    search_configuration_ids = (
        json.loads(args.search_configuration_ids)
        if isinstance(args.search_configuration_ids, str)
        else args.search_configuration_ids
    )
    if not isinstance(search_configuration_ids, list):
        raise ValueError('search_configuration_ids must be a JSON array of configuration ID strings')

    if args.experiment_type == 'PAIRWISE_COMPARISON' and len(search_configuration_ids) != 2:
        raise ValueError('PAIRWISE_COMPARISON requires exactly 2 search configuration IDs')
    if args.experiment_type in ('POINTWISE_EVALUATION', 'HYBRID_OPTIMIZER') and len(search_configuration_ids) != 1:
        raise ValueError(f'{args.experiment_type} requires exactly 1 search configuration ID')

    body: dict = {
        'querySetId': args.query_set_id,
        'searchConfigurationList': search_configuration_ids,
        'size': args.size,
        'type': args.experiment_type,
    }

    if args.experiment_type in ('POINTWISE_EVALUATION', 'HYBRID_OPTIMIZER'):
        if not args.judgment_list_ids:
            raise ValueError(
                f'{args.experiment_type} requires judgment_list_ids. '
                'Provide one or more judgment list IDs as a JSON array, '
                'e.g. ["judgment-id-1"] or ["judgment-id-1", "judgment-id-2"]'
            )
        judgment_list_ids = (
            json.loads(args.judgment_list_ids)
            if isinstance(args.judgment_list_ids, str)
            else args.judgment_list_ids
        )
        if not isinstance(judgment_list_ids, list) or len(judgment_list_ids) == 0:
            raise ValueError('judgment_list_ids must be a non-empty JSON array of judgment list ID strings')
        body['judgmentList'] = judgment_list_ids

    async with get_opensearch_client(args) as client:
        response = await client.plugins.search_relevance.put_experiments(body=body)
        return response


async def delete_experiment(args: DeleteExperimentArgs) -> json:
    """Delete an experiment by ID via the Search Relevance plugin.

    Args:
        args: DeleteExperimentArgs containing the experiment_id

    Returns:
        json: OpenSearch response confirming deletion
    """
    from .client import get_opensearch_client

    async with get_opensearch_client(args) as client:
        response = await client.plugins.search_relevance.delete_experiments(
            experiment_id=args.experiment_id
        )
        return response


async def search_query_sets(args: SearchQuerySetsArgs) -> json:
    """Search query sets using OpenSearch query DSL.

    Args:
        args: SearchQuerySetsArgs containing an optional query_body

    Returns:
        json: OpenSearch search response
    """
    return await _srw_search(args, 'query_sets')


async def search_search_configurations(args: SearchSearchConfigurationsArgs) -> json:
    """Search search configurations using OpenSearch query DSL.

    Args:
        args: SearchSearchConfigurationsArgs containing an optional query_body

    Returns:
        json: OpenSearch search response
    """
    return await _srw_search(args, 'search_configurations')


async def search_judgments(args: SearchJudgmentsArgs) -> json:
    """Search judgments using OpenSearch query DSL.

    Args:
        args: SearchJudgmentsArgs containing an optional query_body

    Returns:
        json: OpenSearch search response
    """
    return await _srw_search(args, 'judgments')


async def search_experiments(args: SearchExperimentsArgs) -> json:
    """Search experiments using OpenSearch query DSL.

    Args:
        args: SearchExperimentsArgs containing an optional query_body

    Returns:
        json: OpenSearch search response
    """
    return await _srw_search(args, 'experiment')


def convert_search_results_to_csv(search_results: dict) -> str:
    """Convert OpenSearch search results to CSV format.

    Args:
        search_results: The JSON response from search_index function

    Returns:
        str: CSV formatted string of the search results
    """
    if not search_results:
        return "No search results to convert"

    has_hits = 'hits' in search_results and search_results['hits']['hits']
    has_aggregations = 'aggregations' in search_results

    # Handle aggregations-only queries
    if has_aggregations and not has_hits:
        return json.dumps(search_results['aggregations'], separators=(',', ':'))

    # Handle hits-only queries
    if has_hits and not has_aggregations:
        return _convert_hits_to_csv(search_results['hits']['hits'])

    # Handle queries with both hits and aggregations
    if has_hits and has_aggregations:
        hits_csv = _convert_hits_to_csv(search_results['hits']['hits'])
        aggregations_json = json.dumps(search_results['aggregations'], separators=(',', ':'))
        return f"SEARCH HITS:\n{hits_csv}\n\nAGGREGATIONS:\n{aggregations_json}"

    return "No search results to convert"


def _convert_hits_to_csv(hits: list) -> str:
    """Convert search hits to CSV format.

    Args:
        hits: List of search hits

    Returns:
        str: CSV formatted string
    """
    if not hits:
        return "No documents found in search results"

    # Extract all unique field names from all documents (flattened)
    all_fields = set()
    for hit in hits:
        if '_source' in hit:
            _flatten_fields(hit['_source'], all_fields)
        # Also include metadata fields
        all_fields.update(['_index', '_id', '_score'])

    # Convert to sorted list for consistent column order
    fieldnames = sorted(list(all_fields))

    # Create CSV in memory
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    # Write each document as a row
    for hit in hits:
        row = {}
        # Add metadata fields
        row['_index'] = hit.get('_index', '')
        row['_id'] = hit.get('_id', '')
        row['_score'] = hit.get('_score', '')

        # Add source fields (flattened)
        if '_source' in hit:
            _flatten_object(hit['_source'], row)

        writer.writerow(row)

    return output.getvalue()


def _flatten_fields(obj: dict, fields: set, prefix: str = '') -> None:
    """Extract all field names from nested objects.

    Args:
        obj: Object to extract field names from
        fields: Set to add field names to
        prefix: Current field prefix
    """
    for key, value in obj.items():
        field_name = f'{prefix}{key}' if prefix else key
        if isinstance(value, dict):
            _flatten_fields(value, fields, f'{field_name}.')
        elif isinstance(value, list) and value and isinstance(value[0], dict):
            # For arrays of objects, flatten the first object to get field structure
            _flatten_fields(value[0], fields, f'{field_name}.')
            fields.add(field_name)  # Also keep the array field itself
        else:
            fields.add(field_name)


def _flatten_object(obj: dict, row: dict, prefix: str = '') -> None:
    """Flatten nested objects into separate columns.

    Args:
        obj: Object to flatten
        row: Row dictionary to add flattened fields to
        prefix: Current field prefix
    """
    for key, value in obj.items():
        field_name = f'{prefix}{key}' if prefix else key
        if isinstance(value, dict):
            _flatten_object(value, row, f'{field_name}.')
        elif isinstance(value, list):
            if value and isinstance(value[0], dict):
                # For arrays of objects, flatten first object and keep array as JSON
                _flatten_object(value[0], row, f'{field_name}.')
                row[field_name] = json.dumps(value)
            else:
                # For simple arrays, convert to JSON
                row[field_name] = json.dumps(value)
        else:
            row[field_name] = str(value) if value is not None else ''


_version_cache: dict[str, Version] = {}


def clear_version_cache():
    """Clear the cached OpenSearch version(s).

    Useful for testing or when cluster version changes.
    """
    _version_cache.clear()


async def get_opensearch_version(args: baseToolArgs) -> Version:
    """Get the version of OpenSearch cluster.

    Returns the cached version if available, otherwise fetches it from the
    cluster and caches the result. Failed lookups (None) are not cached.

    Returns:
        Version: The version of OpenSearch cluster (SemVer style)
    """
    from .client import get_opensearch_client

    cache_key = args.opensearch_cluster_name or ''
    if cache_key in _version_cache:
        return _version_cache[cache_key]

    try:
        async with get_opensearch_client(args) as client:
            response = await client.info()
            version = Version.parse(response['version']['number'])
            _version_cache[cache_key] = version
            return version
    except Exception as e:
        logger.error(f'Error getting OpenSearch version: {e}')
        return None

def plain_float(value):
    """Convert a float to a non-scientific notation number.

    This function is intended to normalize floating-point values so that
    when they are serialized to JSON they do not appear in scientific
    notation (e.g., `1.23E10`), which some APIs (like OpenSearch) may
    reject for numeric fields such as epoch millis.

    Args:
        value (float | None): The input floating-point value to normalize.
            If None, NaN, or an infinite value is passed, it is treated
            as invalid.

    Returns:
        int | float | None:
            - `None` if `value` is None, NaN, or infinite.
            - An `int` if the normalized representation has no fractional
              part (e.g., `1.000E3` → `1000`).
            - A `float` if the normalized representation has a fractional
              part (e.g., `1.234E2` → `123.4`).
    """
    if value is None or math.isnan(value) or math.isinf(value):
        return None

    d = Decimal(str(value)).normalize()
    s = format(d, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    if s == "" or s == "-":
        s = "0"

    if "." not in s:
        return int(s)
    else:
        return float(s)


def _convert_value(v):
    """Recursively normalize scientific-notation floats inside a structure.

    This is an internal helper that walks nested Python objects and applies
    `plain_float` to all `float` values. Only `float` instances are touched;
    strings and other scalar types are left unchanged.

    Args:
        v (Any): A value that may be a dict, list, float, or any other type.
            - If `v` is a `dict`, all values are processed recursively.
            - If `v` is a `list`, all elements are processed recursively.
            - If `v` is a `float`, it is passed through `plain_float`.
            - Any other type is returned as-is.

    Returns:
        Any: A new structure of the same shape with all `float` values
        normalized (non-scientific notation) where possible.
    """
    if isinstance(v, dict):
        return {k: _convert_value(sub) for k, sub in v.items()}
    elif isinstance(v, list):
        return [_convert_value(sub) for sub in v]
    elif isinstance(v, float):
        return plain_float(v)
    else:
        return v


async def create_search_configuration(args: CreateSearchConfigurationArgs) -> json:
    """Create a search configuration via the Search Relevance plugin.

    Args:
        args: CreateSearchConfigurationArgs containing name, index, and query

    Returns:
        json: OpenSearch response with the created configuration ID
    """
    from .client import get_opensearch_client

    validate_json_string(args.query)

    async with get_opensearch_client(args) as client:
        body = {
            'name': args.name,
            'index': args.index,
            'query': args.query,  # must remain a JSON string, not a dict
        }
        response = await client.plugins.search_relevance.put_search_configurations(body=body)
        return response


async def get_search_configuration(args: GetSearchConfigurationArgs) -> json:
    """Retrieve a search configuration by ID via the Search Relevance plugin.

    Args:
        args: GetSearchConfigurationArgs containing the search_configuration_id

    Returns:
        json: OpenSearch response with the search configuration details
    """
    from .client import get_opensearch_client

    async with get_opensearch_client(args) as client:
        response = await client.plugins.search_relevance.get_search_configurations(
            search_configuration_id=args.search_configuration_id
        )
        return response


async def delete_search_configuration(args: DeleteSearchConfigurationArgs) -> json:
    """Delete a search configuration by ID via the Search Relevance plugin.

    Args:
        args: DeleteSearchConfigurationArgs containing the search_configuration_id

    Returns:
        json: OpenSearch response confirming deletion
    """
    from .client import get_opensearch_client

    async with get_opensearch_client(args) as client:
        response = await client.plugins.search_relevance.delete_search_configurations(
            search_configuration_id=args.search_configuration_id
        )
        return response


async def get_judgment_list(args: GetJudgmentListArgs) -> json:
    """Retrieve a judgment by ID via the Search Relevance plugin.

    Args:
        args: GetJudgmentListArgs containing the judgment_id

    Returns:
        json: OpenSearch response with the judgment details
    """
    from .client import get_opensearch_client

    async with get_opensearch_client(args) as client:
        response = await client.plugins.search_relevance.get_judgments(
            judgment_id=args.judgment_id
        )
        return response


async def create_judgment_list(args: CreateJudgmentListArgs) -> json:
    """Create a judgment list with manual relevance ratings via the Search Relevance plugin.

    Args:
        args: CreateJudgmentListArgs containing name, judgment_ratings (JSON string), and optional description

    Returns:
        json: OpenSearch response with the created judgment ID
    """
    from .client import get_opensearch_client

    judgment_ratings = (
        json.loads(args.judgment_ratings)
        if isinstance(args.judgment_ratings, str)
        else args.judgment_ratings
    )
    if not isinstance(judgment_ratings, list):
        raise ValueError(
            'judgment_ratings must be a JSON array of query-ratings objects, '
            'e.g. [{"query": "laptop", "ratings": [{"docId": "doc1", "rating": 3}]}]'
        )

    body = {
        'name': args.name,
        'type': 'IMPORT_JUDGMENT',
        'judgmentRatings': judgment_ratings,
    }
    if args.description:
        body['description'] = args.description

    async with get_opensearch_client(args) as client:
        response = await client.plugins.search_relevance.put_judgments(body=body)
        return response


async def create_ubi_judgment_list(args: CreateUBIJudgmentListArgs) -> json:
    """Create a judgment list by mining relevance signals from UBI click data.

    Args:
        args: CreateUBIJudgmentListArgs containing name, click_model, max_rank, and optional date range

    Returns:
        json: OpenSearch response with the created judgment ID and processing status
    """
    from .client import get_opensearch_client

    body = {
        'name': args.name,
        'type': 'UBI_JUDGMENT',
        'clickModel': args.click_model,
        'maxRank': args.max_rank,
    }
    if args.start_date:
        body['startDate'] = args.start_date
    if args.end_date:
        body['endDate'] = args.end_date

    async with get_opensearch_client(args) as client:
        response = await client.plugins.search_relevance.put_judgments(body=body)
        return response


async def create_llm_judgment_list(args: CreateLLMJudgmentListArgs) -> json:
    """Create a judgment list using an LLM model via the Search Relevance plugin.

    For each query in the query set, the top k documents are retrieved using the
    specified search configuration and rated by the LLM model.

    Args:
        args: CreateLLMJudgmentListArgs containing name, query_set_id, search_configuration_id,
              model_id, size, and optional context_fields

    Returns:
        json: OpenSearch response with the created judgment ID and processing status
    """
    from .client import get_opensearch_client

    context_fields = (
        json.loads(args.context_fields)
        if isinstance(args.context_fields, str)
        else args.context_fields
    )
    if not isinstance(context_fields, list):
        raise ValueError('context_fields must be a JSON array of field name strings, e.g. ["title", "description"]')

    body = {
        'name': args.name,
        'type': 'LLM_JUDGMENT',
        'querySetId': args.query_set_id,
        'searchConfigurationList': [args.search_configuration_id],
        'modelId': args.model_id,
        'size': args.size,
        'contextFields': context_fields,
    }

    async with get_opensearch_client(args) as client:
        response = await client.plugins.search_relevance.put_judgments(body=body)
        return response


async def delete_judgment_list(args: DeleteJudgmentListArgs) -> json:
    """Delete a judgment by ID via the Search Relevance plugin.

    Args:
        args: DeleteJudgmentListArgs containing the judgment_id

    Returns:
        json: OpenSearch response confirming deletion
    """
    from .client import get_opensearch_client

    async with get_opensearch_client(args) as client:
        response = await client.plugins.search_relevance.delete_judgments(
            judgment_id=args.judgment_id
        )
        return response


def validate_json_string(value: str) -> None:
    """Validate that a string is valid JSON, raising ValueError with a concise message if not.

    Intended to be called early (before any API call) so the LLM receives a small,
    precise error rather than a verbose OpenSearch response.

    Args:
        value: The string to validate as JSON.

    Raises:
        ValueError: If the string is not valid JSON. The message includes the parse
            error description, line, and column so the problem is immediately obvious.
    """
    try:
        json.loads(value)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"query is not valid JSON: {e.msg} (line {e.lineno}, col {e.colno})"
        ) from e


def normalize_scientific_notation(body):
    """Normalize scientific-notation floats in a request body.

    This function is meant to be used before sending a request body to
    OpenSearch (or similar APIs) to ensure that numeric values do not
    appear in scientific notation, which can cause parsing errors for
    date/epoch fields.

    The function supports both Python objects and JSON strings:

    - If `body` is a `dict` or `list`, it is processed recursively.
    - If `body` is a JSON `str`, it is first deserialized with
      `json.loads`, then processed, and the resulting Python object
      is returned.

    Args:
        body (dict | list | str): The request body to normalize. It can be:
            - A nested Python structure (`dict` / `list`) containing floats.
            - A JSON string representing such a structure.

    Returns:
        dict | list:
            The normalized Python structure (usually a dict) with all floats
            converted to non-scientific notation numeric values where possible.
            This object can be passed directly to `opensearch-py` as `body`.

    Raises:
        json.JSONDecodeError: If `body` is a string that is not valid JSON.
    """
    if isinstance(body, str):
        # Treat as JSON string
        data = json.loads(body)
        return _convert_value(data)
    else:
        # Treat as Python object (dict / list / etc.)
        return _convert_value(body)
