# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

"""Agentic memory tools for the OpenSearch MCP server.

Provides persistent memory capabilities for AI agents using OpenSearch as the
storage backend. Leverages AWS OpenSearch Service automatic semantic enrichment
for semantic search over memories without requiring an external LLM or
embedding model.

The memory index is auto-created on first use via the AWS OpenSearch Service
API (boto3). Document CRUD uses the standard opensearch-py client.

Supported backends:
- Amazon OpenSearch Service (managed domains, version 2.19+)
- Amazon OpenSearch Serverless (AOSS)

These tools bypass write protection since memory operations are inherently
write-oriented and are a distinct capability from cluster administration.
"""

import json
import logging
import os
from .tool_logging import log_tool_error
from .tool_params import baseToolArgs
from datetime import datetime, timezone
from pydantic import Field
from typing import Any, Optional


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_MEMORY_INDEX_NAME = 'agent-memory'

# Index schema with automatic semantic enrichment
MEMORY_INDEX_SCHEMA = {
    'mappings': {
        'properties': {
            'memory_text': {
                'type': 'text',
                'semantic_enrichment': {
                    'status': 'ENABLED',
                    'language_options': 'english',
                },
            },
            'user_id': {'type': 'keyword'},
            'agent_id': {'type': 'keyword'},
            'session_id': {'type': 'keyword'},
            'tags': {'type': 'keyword'},
            'created_at': {'type': 'date'},
            'updated_at': {'type': 'date'},
        }
    }
}


def _get_memory_index_name() -> str:
    """Return the memory index name from env or default."""
    return os.getenv('MEMORY_INDEX_NAME', DEFAULT_MEMORY_INDEX_NAME)


# ---------------------------------------------------------------------------
# Index lifecycle helpers (boto3)
# ---------------------------------------------------------------------------


def _is_serverless(opensearch_url: str) -> bool:
    """Detect whether the OpenSearch URL points to AOSS."""
    return 'aoss.' in (opensearch_url or '')


def _get_boto3_session():
    """Create a boto3 session using the same logic as the rest of the MCP server."""
    import boto3
    from mcp_server_opensearch.global_state import get_profile

    profile = get_profile() or os.getenv('AWS_PROFILE', '').strip()
    try:
        return boto3.Session(profile_name=profile) if profile else boto3.Session()
    except Exception:
        return boto3.Session()


def _get_domain_name_from_url(opensearch_url: str) -> Optional[str]:
    """Extract the domain name from an AWS OpenSearch Service URL.

    AWS managed domain URLs follow the pattern:
        https://<domain-name>-<hash>.<region>.es.amazonaws.com
    or for custom endpoints, the user must set AWS_OPENSEARCH_DOMAIN_NAME.
    """
    # Allow explicit override
    domain_name = os.getenv('AWS_OPENSEARCH_DOMAIN_NAME', '').strip()
    if domain_name:
        return domain_name

    # Try to parse from URL
    from urllib.parse import urlparse

    parsed = urlparse(opensearch_url)
    hostname = parsed.hostname or ''

    # Pattern: search-<domain>-<hash>.<region>.es.amazonaws.com
    if '.es.amazonaws.com' in hostname:
        # hostname = search-my-domain-abc123.us-east-1.es.amazonaws.com
        prefix = hostname.split('.')[0]  # search-my-domain-abc123
        if prefix.startswith('search-'):
            prefix = prefix[len('search-'):]
        # Remove the trailing hash (last segment after the last hyphen that looks like a hash)
        parts = prefix.rsplit('-', 1)
        if len(parts) == 2 and len(parts[1]) >= 10:
            return parts[0]
        return prefix

    return None


def _get_collection_id_from_url(opensearch_url: str) -> Optional[str]:
    """Extract the collection ID from an AOSS URL.

    AOSS URLs follow the pattern:
        https://<collection-id>.<region>.aoss.amazonaws.com
    """
    # Allow explicit override
    collection_id = os.getenv('AWS_OPENSEARCH_COLLECTION_ID', '').strip()
    if collection_id:
        return collection_id

    from urllib.parse import urlparse

    parsed = urlparse(opensearch_url)
    hostname = parsed.hostname or ''

    # Pattern: <collection-id>.<region>.aoss.amazonaws.com
    if '.aoss.amazonaws.com' in hostname:
        return hostname.split('.')[0]

    return None


MEMORY_DATA_ACCESS_POLICY_NAME = 'mcp-memory-access'


def _is_memory_enabled() -> bool:
    """Check if memory tools are enabled via environment variable."""
    return os.getenv('MEMORY_TOOLS_ENABLED', 'false').lower() == 'true'


def _get_caller_principal_arn(session) -> str:
    """Get the IAM principal ARN of the current caller.

    For assumed roles (e.g. ``arn:aws:sts::123:assumed-role/Admin/session``),
    converts to the IAM role ARN (``arn:aws:iam::123:role/Admin``) because
    AOSS data access policies require IAM role ARNs, not STS session ARNs.
    """
    sts = session.client('sts')
    identity = sts.get_caller_identity()
    arn = identity['Arn']

    # Convert assumed-role STS ARN to IAM role ARN
    # arn:aws:sts::123456:assumed-role/RoleName/SessionName
    # -> arn:aws:iam::123456:role/RoleName
    if ':assumed-role/' in arn:
        parts = arn.split(':')
        account = parts[4]
        role_path = parts[5]  # assumed-role/RoleName/SessionName
        role_name = role_path.split('/')[1]
        return f'arn:aws:iam::{account}:role/{role_name}'

    return arn


def _get_collection_name(aoss_client, collection_id: str) -> str:
    """Resolve collection name from ID via batch_get_collection."""
    resp = aoss_client.batch_get_collection(ids=[collection_id])
    details = resp.get('collectionDetails', [])
    if not details:
        raise ValueError(f'AOSS collection {collection_id} not found')
    return details[0]['name']


def _ensure_aoss_data_access_policy(session, aoss_client, collection_id: str, region: str) -> None:
    """Create or update an AOSS data access policy for the memory index.

    Grants the current caller's IAM role full access to the collection and
    all indices within it. This is required for ``create_index`` with semantic
    enrichment, which needs ML connector permissions behind the scenes.

    The policy is named ``mcp-memory-access`` and is idempotent — if it
    already exists and covers the current principal, no changes are made.
    """
    policy_name = MEMORY_DATA_ACCESS_POLICY_NAME
    principal_arn = _get_caller_principal_arn(session)
    collection_name = _get_collection_name(aoss_client, collection_id)

    # Check if policy already exists
    try:
        existing = aoss_client.get_access_policy(type='data', name=policy_name)
        policy_doc = existing['accessPolicyDetail']['policy']
        policy_version = existing['accessPolicyDetail']['policyVersion']

        # Check if the current principal is already covered
        existing_principals = set()
        for rule_set in policy_doc:
            for p in rule_set.get('Principal', []):
                existing_principals.add(p)

        if principal_arn in existing_principals:
            logger.debug(
                f'AOSS data access policy "{policy_name}" already covers {principal_arn}'
            )
            return

        # Principal not covered — add it to the existing policy
        for rule_set in policy_doc:
            if principal_arn not in rule_set.get('Principal', []):
                rule_set['Principal'].append(principal_arn)

        aoss_client.update_access_policy(
            type='data',
            name=policy_name,
            policyVersion=policy_version,
            policy=json.dumps(policy_doc),
        )
        logger.info(f'Updated AOSS data access policy "{policy_name}" to include {principal_arn}')
        return

    except aoss_client.exceptions.ResourceNotFoundException:
        pass  # Policy doesn't exist, create it below
    except Exception as e:
        if 'ResourceNotFoundException' in str(e):
            pass  # Policy doesn't exist, create it below
        else:
            logger.warning(f'Error checking AOSS data access policy: {e}')
            # Don't fail — the index creation will fail with a clear error if
            # permissions are actually missing
            return

    # Create new policy
    policy_doc = [
        {
            'Rules': [
                {
                    'Resource': [f'collection/{collection_name}'],
                    'Permission': ['aoss:*'],
                    'ResourceType': 'collection',
                },
                {
                    'Resource': [f'index/{collection_name}/*'],
                    'Permission': ['aoss:*'],
                    'ResourceType': 'index',
                },
            ],
            'Principal': [principal_arn],
            'Description': 'Auto-created by OpenSearch MCP server for agentic memory',
        }
    ]

    try:
        aoss_client.create_access_policy(
            type='data',
            name=policy_name,
            policy=json.dumps(policy_doc),
            description='Data access policy for MCP agentic memory tools',
        )
        logger.info(
            f'Created AOSS data access policy "{policy_name}" for {principal_arn} '
            f'on collection {collection_name}'
        )
    except aoss_client.exceptions.ConflictException:
        # Race condition — another process created it
        logger.debug(f'AOSS data access policy "{policy_name}" already exists (race)')
    except Exception as e:
        logger.warning(f'Failed to create AOSS data access policy: {e}')


async def _ensure_memory_index(args: baseToolArgs) -> None:
    """Create the memory index if it does not already exist.

    Uses boto3 to call the AWS OpenSearch create-index API which supports
    the semantic_enrichment parameter. Falls back gracefully if the index
    already exists.

    For AOSS, also ensures a data access policy exists that grants the
    current caller full access to the collection and its indices.
    """
    index_name = _get_memory_index_name()

    # First, check if the index already exists using opensearch-py
    from opensearch.client import get_opensearch_client

    async with get_opensearch_client(args) as client:
        try:
            exists = await client.indices.exists(index=index_name)
            if exists:
                logger.debug(f'Memory index "{index_name}" already exists')
                return
        except Exception:
            # If we can't check, try to create anyway
            pass

    # Index doesn't exist — create it via boto3
    opensearch_url = os.getenv('OPENSEARCH_URL', '').strip()
    session = _get_boto3_session()
    region = (
        os.getenv('AWS_REGION', '').strip()
        or session.region_name
        or 'us-east-1'
    )

    schema = MEMORY_INDEX_SCHEMA

    if _is_serverless(opensearch_url):
        collection_id = _get_collection_id_from_url(opensearch_url)
        if not collection_id:
            raise ValueError(
                'Cannot determine AOSS collection ID from OPENSEARCH_URL. '
                'Set AWS_OPENSEARCH_COLLECTION_ID environment variable.'
            )

        aoss_client = session.client('opensearchserverless', region_name=region)

        # Ensure data access policy exists for the current caller
        _ensure_aoss_data_access_policy(session, aoss_client, collection_id, region)

        try:
            aoss_client.create_index(
                id=collection_id,
                indexName=index_name,
                indexSchema=schema,
            )
            logger.info(f'Created AOSS memory index "{index_name}" on collection {collection_id}')
        except aoss_client.exceptions.ConflictException:
            logger.debug(f'Memory index "{index_name}" already exists (AOSS)')
        except Exception as e:
            error_str = str(e)
            if 'already exists' in error_str.lower() or 'ResourceAlreadyExistsException' in error_str:
                logger.debug(f'Memory index "{index_name}" already exists (AOSS)')
            else:
                raise
    else:
        domain_name = _get_domain_name_from_url(opensearch_url)
        if not domain_name:
            raise ValueError(
                'Cannot determine OpenSearch domain name from OPENSEARCH_URL. '
                'Set AWS_OPENSEARCH_DOMAIN_NAME environment variable.'
            )
        client = session.client('opensearch', region_name=region)
        try:
            client.create_index(
                domainName=domain_name,
                indexName=index_name,
                indexSchema=json.dumps(MEMORY_INDEX_SCHEMA),
            )
            logger.info(f'Created memory index "{index_name}" on domain {domain_name}')
        except client.exceptions.ConflictException:
            logger.debug(f'Memory index "{index_name}" already exists')
        except Exception as e:
            error_str = str(e)
            if 'already exists' in error_str.lower() or 'ResourceAlreadyExistsException' in error_str:
                logger.debug(f'Memory index "{index_name}" already exists')
            else:
                raise


# ---------------------------------------------------------------------------
# Argument models
# ---------------------------------------------------------------------------


class SaveMemoryArgs(baseToolArgs):
    """Arguments for saving a memory."""

    memory: str = Field(
        description='The text content to remember. Should be a clear, self-contained statement.'
    )
    user_id: Optional[str] = Field(
        default=None,
        description='User identifier to scope this memory to a specific user.',
    )
    agent_id: Optional[str] = Field(
        default=None,
        description='Agent identifier to scope this memory to a specific agent.',
    )
    session_id: Optional[str] = Field(
        default=None,
        description='Session identifier to scope this memory to a specific session.',
    )
    tags: Optional[str] = Field(
        default=None,
        description='Comma-separated tags for categorizing the memory (e.g. "preference,food").',
    )

    class Config:
        json_schema_extra = {
            'examples': [
                {
                    'memory': 'User prefers vegetarian food and is allergic to nuts',
                    'user_id': 'user-123',
                    'tags': 'preference,dietary',
                },
                {
                    'memory': 'Project deadline is March 15, 2026',
                    'user_id': 'user-123',
                    'agent_id': 'project-assistant',
                    'tags': 'project,deadline',
                },
            ]
        }


class SearchMemoryArgs(baseToolArgs):
    """Arguments for searching memories."""

    query: str = Field(
        description='Natural language search query to find relevant memories. Use "*" to list all memories.'
    )
    user_id: Optional[str] = Field(
        default=None,
        description='Filter memories by user ID.',
    )
    agent_id: Optional[str] = Field(
        default=None,
        description='Filter memories by agent ID.',
    )
    session_id: Optional[str] = Field(
        default=None,
        description='Filter memories by session ID.',
    )
    tags: Optional[str] = Field(
        default=None,
        description='Comma-separated tags to filter by (e.g. "preference,food").',
    )
    size: int = Field(
        default=10,
        description='Maximum number of memories to return (default 10, max 100).',
    )

    class Config:
        json_schema_extra = {
            'examples': [
                {
                    'query': 'dietary preferences',
                    'user_id': 'user-123',
                },
                {
                    'query': 'project deadlines',
                    'user_id': 'user-123',
                    'tags': 'project',
                    'size': 5,
                },
            ]
        }


class DeleteMemoryArgs(baseToolArgs):
    """Arguments for deleting a memory."""

    memory_id: str = Field(
        description='The ID of the memory document to delete.'
    )

    class Config:
        json_schema_extra = {
            'examples': [
                {'memory_id': 'abc123xyz'},
            ]
        }


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------


async def save_memory_tool(args: SaveMemoryArgs) -> list[dict]:
    """Save a memory to the OpenSearch memory index."""
    try:
        await _ensure_memory_index(args)

        index_name = _get_memory_index_name()
        now = datetime.now(timezone.utc).isoformat()

        doc = {
            'memory_text': args.memory,
            'created_at': now,
            'updated_at': now,
        }
        if args.user_id:
            doc['user_id'] = args.user_id
        if args.agent_id:
            doc['agent_id'] = args.agent_id
        if args.session_id:
            doc['session_id'] = args.session_id
        if args.tags:
            doc['tags'] = [t.strip() for t in args.tags.split(',') if t.strip()]

        from opensearch.client import get_opensearch_client

        async with get_opensearch_client(args) as client:
            response = await client.index(index=index_name, body=doc)

        memory_id = response.get('_id', 'unknown')
        return [
            {
                'type': 'text',
                'text': f'Memory saved (id: {memory_id}):\n"{args.memory}"',
            }
        ]
    except Exception as e:
        return log_tool_error('SaveMemoryTool', e, 'saving memory')


async def search_memory_tool(args: SearchMemoryArgs) -> list[dict]:
    """Search memories using natural language (semantic search via automatic enrichment)."""
    try:
        index_name = _get_memory_index_name()
        effective_size = min(args.size, 100) if args.size else 10

        # Build filter clauses
        filters = []
        if args.user_id:
            filters.append({'term': {'user_id': args.user_id}})
        if args.agent_id:
            filters.append({'term': {'agent_id': args.agent_id}})
        if args.session_id:
            filters.append({'term': {'session_id': args.session_id}})
        if args.tags:
            tag_list = [t.strip() for t in args.tags.split(',') if t.strip()]
            for tag in tag_list:
                filters.append({'term': {'tags': tag}})

        # Build query — use match on the semantic-enriched field.
        # AWS automatic semantic enrichment rewrites match queries to
        # neural sparse queries transparently.
        # Special case: if query is "*" or empty, use match_all to list memories.
        is_list_all = args.query.strip() in ('*', '')

        if is_list_all and filters:
            query = {
                'bool': {
                    'must': {'match_all': {}},
                    'filter': filters,
                }
            }
        elif is_list_all:
            query = {'match_all': {}}
        elif filters:
            query = {
                'bool': {
                    'must': {'match': {'memory_text': args.query}},
                    'filter': filters,
                }
            }
        else:
            query = {'match': {'memory_text': args.query}}

        # For semantic queries, wrap in script_score to blend relevance with
        # recency. Uses exponential decay: memories within 1 day get full score,
        # then decay to 50% at 7 days. This ensures recent memories are
        # prioritized while highly relevant older memories still surface.
        if not is_list_all:
            recency_script = (
                'double relevance = _score;'
                'long now = new Date().getTime();'
                'long created = doc[\'created_at\'].value.toInstant().toEpochMilli();'
                'double ageHours = (now - created) / 3600000.0;'
                'double decay = Math.exp(-0.693 * Math.max(0, ageHours - 24) / 168.0);'
                'return relevance * decay;'
            )
            query = {
                'script_score': {
                    'query': query,
                    'script': {
                        'source': recency_script,
                        'lang': 'painless',
                    },
                }
            }

        body = {
            'query': query,
            'size': effective_size,
            'sort': (
                [{'created_at': {'order': 'desc'}}]
                if is_list_all
                else [{'_score': {'order': 'desc'}}]
            ),
            '_source': True,
        }

        from opensearch.client import get_opensearch_client

        async with get_opensearch_client(args) as client:
            # Check if index exists first
            exists = await client.indices.exists(index=index_name)
            if not exists:
                return [
                    {
                        'type': 'text',
                        'text': 'No memories found. The memory index has not been created yet. Use SaveMemoryTool to store your first memory.',
                    }
                ]

            response = await client.search(index=index_name, body=body)

        hits = response.get('hits', {}).get('hits', [])
        if not hits:
            return [{'type': 'text', 'text': 'No matching memories found.'}]

        # Format results
        results = []
        for hit in hits:
            source = hit.get('_source', {})
            entry = {
                'id': hit['_id'],
                'memory': source.get('memory_text', ''),
                'score': hit.get('_score'),
                'created_at': source.get('created_at'),
            }
            if source.get('user_id'):
                entry['user_id'] = source['user_id']
            if source.get('agent_id'):
                entry['agent_id'] = source['agent_id']
            if source.get('session_id'):
                entry['session_id'] = source['session_id']
            if source.get('tags'):
                entry['tags'] = source['tags']
            results.append(entry)

        formatted = json.dumps(results, separators=(',', ':'))
        return [
            {
                'type': 'text',
                'text': f'Found {len(results)} matching memories:\n{formatted}',
            }
        ]
    except Exception as e:
        return log_tool_error('SearchMemoryTool', e, 'searching memories')


async def delete_memory_tool(args: DeleteMemoryArgs) -> list[dict]:
    """Delete a memory by its document ID."""
    try:
        index_name = _get_memory_index_name()

        from opensearch.client import get_opensearch_client

        async with get_opensearch_client(args) as client:
            response = await client.delete(index=index_name, id=args.memory_id)

        result = response.get('result', 'unknown')
        return [
            {
                'type': 'text',
                'text': f'Memory {args.memory_id} deleted (result: {result}).',
            }
        ]
    except Exception as e:
        return log_tool_error('DeleteMemoryTool', e, 'deleting memory')


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

MEMORY_TOOLS_REGISTRY: dict[str, dict[str, Any]] = (
    {
        'SaveMemoryTool': {
            'display_name': 'SaveMemoryTool',
            'description': (
                'Saves a memory to persistent storage in OpenSearch. Use this to remember '
                'important facts, user preferences, decisions, plans, or any information '
                'that should persist across conversations. Memories are automatically '
                'enriched for semantic search. Scope memories using user_id, agent_id, '
                'and session_id. Add tags for categorization. '
                'IMPORTANT: Save important facts, decisions, user preferences, and insights '
                'immediately as they arise during the conversation — don\'t wait until the '
                'end. Also do a final check before finishing to capture anything missed.'
            ),
            'input_schema': SaveMemoryArgs.model_json_schema(),
            'function': save_memory_tool,
            'args_model': SaveMemoryArgs,
            'min_version': '1.0.0',
            'http_methods': 'GET, POST, PUT',
            'bypass_write_filter': True,
        },
        'SearchMemoryTool': {
            'display_name': 'SearchMemoryTool',
            'description': (
                'Searches stored memories using natural language. Returns the most '
                'relevant memories ranked by semantic similarity. Use this to recall '
                'previously stored information such as user preferences, past decisions, '
                'project details, or any facts saved with SaveMemoryTool. Filter results '
                'by user_id, agent_id, session_id, or tags. '
                'IMPORTANT: Always call this tool at the start of a conversation to check '
                'for relevant context. Also search memory whenever the user asks about '
                'bugs, decisions, features, configurations, or any topic that may have '
                'been previously discussed or worked on — even if they don\'t explicitly '
                'reference a prior conversation.'
            ),
            'input_schema': SearchMemoryArgs.model_json_schema(),
            'function': search_memory_tool,
            'args_model': SearchMemoryArgs,
            'min_version': '1.0.0',
            'http_methods': 'GET',
        },
        'DeleteMemoryTool': {
            'display_name': 'DeleteMemoryTool',
            'description': (
                'Deletes a specific memory by its ID. Use this to remove outdated, '
                'incorrect, or no longer relevant memories. Get the memory ID from '
                'SearchMemoryTool results.'
            ),
            'input_schema': DeleteMemoryArgs.model_json_schema(),
            'function': delete_memory_tool,
            'args_model': DeleteMemoryArgs,
            'min_version': '1.0.0',
            'http_methods': 'GET, DELETE',
            'bypass_write_filter': True,
        },
    }
    if _is_memory_enabled()
    else {}
)
