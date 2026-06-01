# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import json
import logging
from datetime import datetime, timezone
from opensearchpy import AsyncOpenSearch
from typing import Any, Dict, List, Set


logger = logging.getLogger(__name__)

DATE_FORMAT_PATTERN = '%Y-%m-%d %H:%M:%S'
QUERY_TYPE_PPL = 'ppl'
QUERY_TYPE_DSL = 'dsl'
DEFAULT_TIME_FIELD = '@timestamp'
DEFAULT_SIZE = 1000
MAX_SIZE_LIMIT = 10000

NUMBER_FIELD_TYPES = {
    'byte',
    'short',
    'integer',
    'long',
    'float',
    'double',
    'half_float',
    'scaled_float',
}


class AnalysisParameters:
    """Parsed and validated parameters for analysis tools."""

    def __init__(self, parameters: Dict[str, str]):
        """Initialize from raw parameter dict."""
        self.index = parameters.get('index', '')
        self.time_field = parameters.get('timeField', DEFAULT_TIME_FIELD)
        self.selection_time_range_start = parameters.get('selectionTimeRangeStart', '')
        self.selection_time_range_end = parameters.get('selectionTimeRangeEnd', '')
        self.baseline_time_range_start = parameters.get('baselineTimeRangeStart', '')
        self.baseline_time_range_end = parameters.get('baselineTimeRangeEnd', '')

        size_str = parameters.get('size', str(DEFAULT_SIZE))
        try:
            parsed_size = int(float(size_str))
            if parsed_size <= 0 or parsed_size > MAX_SIZE_LIMIT:
                raise ValueError(
                    f'Invalid size: must be between 1 and {MAX_SIZE_LIMIT}, got {size_str}'
                )
        except (ValueError, TypeError):
            raise ValueError(f"Invalid 'size' parameter: '{size_str}', must be a valid integer")
        self.size = parsed_size

        self.query_type = parameters.get('queryType', QUERY_TYPE_DSL)

        filter_param = parameters.get('filter', '')
        if not filter_param:
            self.filter: List[str] = []
        else:
            try:
                self.filter = json.loads(filter_param)
            except Exception:
                raise ValueError("Invalid 'filter' parameter: must be a valid JSON array")

        self.dsl = parameters.get('dsl', '')
        self.ppl = parameters.get('ppl', '')

    def validate(self):
        """Validate required parameters are present."""
        if not self.index:
            raise ValueError("Missing required parameter: 'index'")
        if not self.selection_time_range_start or not self.selection_time_range_end:
            raise ValueError(
                "Missing required parameters: 'selectionTimeRangeStart' and 'selectionTimeRangeEnd'"
            )
        if self.query_type not in (QUERY_TYPE_DSL, QUERY_TYPE_PPL):
            raise ValueError(
                f"Invalid 'queryType': must be 'dsl' or 'ppl', got '{self.query_type}'"
            )

    def has_baseline_time_range(self) -> bool:
        """Return True if both baseline start and end times are provided."""
        return bool(self.baseline_time_range_start) and bool(self.baseline_time_range_end)


def format_time_string(time_string: str) -> str:
    """Format time string to ISO 8601 for OpenSearch compatibility."""
    # Normalize trailing 'Z' to '+00:00' for fromisoformat (Python 3.10 compat)
    normalized = time_string.replace('Z', '+00:00') if time_string.endswith('Z') else time_string

    if time_string.endswith('Z'):
        try:
            dt = datetime.strptime(time_string, '%Y-%m-%d %H:%M:%SZ')
            dt = dt.replace(tzinfo=timezone.utc)
            return dt.strftime('%Y-%m-%dT%H:%M:%S.000Z')
        except ValueError:
            pass

    try:
        dt = datetime.strptime(time_string, DATE_FORMAT_PATTERN)
        dt = dt.replace(tzinfo=timezone.utc)
        return dt.strftime('%Y-%m-%dT%H:%M:%S.000Z')
    except ValueError:
        pass

    try:
        dt = datetime.strptime(time_string, '%Y-%m-%d %H:%M:%S.%f')
        dt = dt.replace(tzinfo=timezone.utc)
        return dt.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
    except ValueError:
        pass

    try:
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.strftime('%Y-%m-%dT%H:%M:%S.000Z')
    except ValueError:
        pass

    raise RuntimeError(f'Invalid time format: {time_string}')


async def get_field_types(client: AsyncOpenSearch, index: str) -> Dict[str, str]:
    """Retrieve field type mappings from the specified index."""
    response = await client.indices.get_mapping(index=index)
    field_types: Dict[str, str] = {}

    for index_name, mapping_data in response.items():
        mappings = mapping_data.get('mappings', {})
        properties = mappings.get('properties', {})
        _extract_field_types(properties, '', field_types)

    return field_types


def _extract_field_types(properties: Dict[str, Any], prefix: str, field_types: Dict[str, str]):
    for field_name, field_props in properties.items():
        full_name = f'{prefix}.{field_name}' if prefix else field_name

        if 'type' in field_props:
            field_types[full_name] = field_props['type']

        if 'properties' in field_props:
            _extract_field_types(field_props['properties'], full_name, field_types)


async def fetch_index_data_dsl(
    client: AsyncOpenSearch,
    time_range_start: str,
    time_range_end: str,
    params: AnalysisParameters,
) -> List[Dict[str, Any]]:
    """Fetch data from index using DSL query with time range filter."""
    bool_query: Dict[str, Any] = {'must': []}

    time_range_query = {
        'range': {
            params.time_field: {
                'gte': format_time_string(time_range_start),
                'lte': format_time_string(time_range_end),
                'format': 'strict_date_optional_time||epoch_millis',
            }
        }
    }
    bool_query['must'].append(time_range_query)

    if params.dsl:
        dsl_map = json.loads(params.dsl.replace("'", '"'))
        bool_query['must'].append(dsl_map)
    elif params.filter:
        for filter_str in params.filter:
            filter_map = json.loads(filter_str.replace("'", '"'))
            bool_query['must'].append(filter_map)

    search_body = {
        'query': {'bool': bool_query},
        'size': params.size,
        '_source': True,
    }

    response = await client.search(index=params.index, body=search_body)
    data = []
    for hit in response.get('hits', {}).get('hits', []):
        data.append(hit.get('_source', {}))
    return data


async def execute_ppl_query(client: AsyncOpenSearch, ppl: str) -> Dict[str, Any]:
    """Execute a PPL query and return the raw response."""
    response = await client.transport.perform_request(
        'POST',
        '/_plugins/_ppl',
        body={'query': ppl},
        params={'format': 'jdbc'},
    )
    return response


async def execute_ppl_and_parse_docs(client: AsyncOpenSearch, ppl: str) -> List[Dict[str, Any]]:
    """Execute PPL query and parse result into list of documents."""
    response = await execute_ppl_query(client, ppl)

    if 'error' in response:
        error_obj = response['error']
        if isinstance(error_obj, dict):
            reason = error_obj.get('reason', str(error_obj))
        else:
            reason = str(error_obj)
        raise RuntimeError(f'PPL query error: {reason}')

    datarows = response.get('datarows', [])
    schema = response.get('schema', [])

    if not isinstance(datarows, list) or not isinstance(schema, list):
        return []

    field_names = [field.get('name', '') for field in schema]

    documents = []
    for row in datarows:
        doc = {}
        for i in range(min(len(row), len(field_names))):
            doc[field_names[i]] = row[i]
        documents.append(doc)
    return documents


async def execute_ppl_and_parse_datarows(client: AsyncOpenSearch, ppl: str) -> List[List[Any]]:
    """Execute PPL query and return raw datarows."""
    response = await execute_ppl_query(client, ppl)

    if 'error' in response:
        error_obj = response['error']
        if isinstance(error_obj, dict):
            reason = error_obj.get('reason', str(error_obj))
        else:
            reason = str(error_obj)
        raise RuntimeError(f'PPL query error: {reason}')

    datarows = response.get('datarows', [])
    if not isinstance(datarows, list):
        return []
    return datarows


def get_number_fields(field_types: Dict[str, str]) -> Set[str]:
    """Filter numeric fields from field type mappings."""
    return {name for name, ftype in field_types.items() if ftype in NUMBER_FIELD_TYPES}


def get_flattened_value(doc: Dict[str, Any], field: str) -> Any:
    """Extract nested field value using dot notation."""
    if doc is None or field is None:
        return None

    parts = field.split('.')
    current = doc

    for part in parts:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
        if current is None:
            return None

    return current
