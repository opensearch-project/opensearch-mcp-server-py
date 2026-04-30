# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

from enum import Enum
from pydantic import BaseModel, Field, model_validator
from pydantic_core import PydanticCustomError
from tools.tool_params import baseToolArgs
from typing import Any, Dict, List, Literal, Optional, Set


class MemoryType(str, Enum):
    """Specifies the different types of agentic memory."""

    sessions = 'sessions'
    working = 'working'
    long_term = 'long-term'
    history = 'history'


class PayloadType(str, Enum):
    """Specifies the type of payload being added to agentic memory."""

    conversational = 'conversational'
    data = 'data'


ERR_FIELD_NOT_ALLOWED = 'field_not_allowed'
ERR_MISSING_WORKING_FIELD = 'missing_working_field'
ERR_MISSING_LONG_TERM_FIELD = 'missing_long_term_field'
ERR_MESSAGES_REQUIRED = 'messages_required'
ERR_FIELD_PROHIBITED = 'field_prohibited'
ERR_STRUCTURED_DATA_REQUIRED = 'structured_data_required'
ERR_MISSING_CONTENT_FIELD = 'missing_content_field'
ERR_EMBEDDING_DIMENSION_REQUIRED = 'embedding_dimension_required'


class MessageContentItem(BaseModel):
    """Schema for the content part of a message.
    Used for strong typing in 'messages' fields.
    """

    text: str = Field(..., description='The text content of the message.')
    content_type: str = Field(
        ..., description="The type of the content (e.g., 'text'). ", alias='type'
    )


class MessageItem(BaseModel):
    """Schema for a single message in 'messages' field.
    Used for strong typing.
    """

    role: Optional[str] = Field(
        None, description="The role of the entity (e.g., 'user', 'assistant')."
    )
    content: List[MessageContentItem] = Field(
        ..., description='A list of content items for this message.'
    )


class BaseAgenticMemoryContainerArgs(baseToolArgs):
    """Base arguments for tools operating on an existing Agentic Memory Container."""

    memory_container_id: str = Field(..., description='The ID of the memory container.')

    @model_validator(mode='before')
    @classmethod
    def inject_memory_container_id(cls, data):
        """Inject memory_container_id from config/env when not provided by the MCP client."""
        if isinstance(data, dict) and not data.get('memory_container_id'):
            from tools.config import get_memory_container_id_from_config

            container_id = get_memory_container_id_from_config()
            if container_id:
                data['memory_container_id'] = container_id
        return data


class CreateAgenticMemorySessionArgs(BaseAgenticMemoryContainerArgs):
    """Arguments for creating a new session in a agentic memory container."""

    session_id: Optional[str] = Field(
        default=None,
        description='A custom session ID. If provided, this ID is used for the session. If not provided, a random ID is generated.',
    )
    summary: Optional[str] = Field(default=None, description='A session summary or description.')
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description='Additional metadata for the session provided as key-value pairs.',
    )
    namespace: Optional[Dict[str, str]] = Field(
        default=None, description='Namespace information for organizing the session.'
    )

    class Config:
        json_schema_extra = {
            'examples': [
                {
                    'memory_container_id': 'SdjmmpgBOh0h20Y9kWuN',
                    # Optional: Client-provided ID. If omitted, OpenSearch auto-generates one, must be unique within the memory container
                    'session_id': 'abc123',
                    # Optional key-value pairs for session context
                    'metadata': {'key1': 'value1'},
                },
                {
                    'memory_container_id': 'SdjmmpgBOh0h20Y9kWuN',
                    # Human-readable description of the session
                    'summary': 'This is a test session',
                    'metadata': {'key1': 'value1'},
                    # Isolates session to specific user - matches strategy namespace from container
                    'namespace': {'user_id': 'bob'},
                },
                {
                    'memory_container_id': 'SdjmmpgBOh0h20Y9kWuN',
                    'summary': 'Session for user onboarding',
                    # Multi-dimensional namespacing supported
                    'namespace': {
                        'user_id': 'alice',
                        'agent_id': 'onboarding_bot',
                    },
                    # Used for filtering and organization
                    'metadata': {
                        'priority': 'high',
                        'category': 'onboarding',
                    },
                },
            ]
        }


class AddAgenticMemoriesArgs(BaseAgenticMemoryContainerArgs):
    """Arguments for adding memories to the agentic memory container."""

    # --- Payload Fields ---
    messages: Optional[List[MessageItem]] = Field(
        default=None, description='A list of messages for a conversational payload...'
    )
    structured_data: Optional[Dict[str, Any]] = Field(
        default=None,
        description='Structured data content for data memory. Required when payload_type is data.',
    )
    binary_data: Optional[str] = Field(
        default=None,
        description='Binary data content encoded as a Base64 string for binary payloads.',
    )
    payload_type: PayloadType = Field(
        ..., description='The type of payload. Valid values are conversational or data.'
    )

    # --- Optional Fields ---
    namespace: Optional[Dict[str, str]] = Field(
        default=None, description='The namespace context for organizing memories...'
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None, description='Additional metadata for the memory...'
    )
    tags: Optional[Dict[str, Any]] = Field(
        default=None, description='Tags for categorizing and organizing memories.'
    )
    infer: Optional[bool] = Field(
        default=False,
        description='Whether to use a large language model (LLM) to extract key information...',
    )

    @model_validator(mode='after')
    def validate_payload_requirements(self) -> 'AddAgenticMemoriesArgs':
        """Validate that the correct fields are provided based on payload_type."""
        # Getting fields that were actually set
        set_fields = self.model_fields_set

        if self.payload_type == PayloadType.conversational:
            if 'messages' not in set_fields:
                raise PydanticCustomError(
                    ERR_MESSAGES_REQUIRED,
                    "'messages' field is required when payload_type is 'conversational'",
                )
            if 'structured_data' in set_fields:
                raise PydanticCustomError(
                    ERR_FIELD_PROHIBITED,
                    "'structured_data' should not be provided when payload_type is 'conversational'",
                    {'field_name': 'structured_data'},
                )

        elif self.payload_type == PayloadType.data:
            if 'structured_data' not in set_fields:
                raise PydanticCustomError(
                    ERR_STRUCTURED_DATA_REQUIRED,
                    "'structured_data' field is required when payload_type is 'data'",
                )
            if 'messages' in set_fields:
                raise PydanticCustomError(
                    ERR_FIELD_PROHIBITED,
                    "'messages' should not be provided when payload_type is 'data'",
                    {'field_name': 'messages'},
                )

        # Validate that at least one content field is provided
        content_fields = {'messages', 'structured_data', 'binary_data'}
        if not any(field in set_fields for field in content_fields):
            raise PydanticCustomError(
                ERR_MISSING_CONTENT_FIELD,
                'At least one content field (messages, structured_data, or binary_data) must be provided',
            )

        return self

    class Config:
        json_schema_extra = {
            'examples': [
                {
                    'memory_container_id': 'SdjmmpgBOh0h20Y9kWuN',
                    # Conversational exchange between user and assistant
                    'messages': [
                        {
                            # Standard chat roles: 'user', 'assistant'
                            'role': 'user',
                            'content': [
                                {
                                    'text': "I'm Bob, I really like swimming.",
                                    'type': 'text',
                                }
                            ],
                        },
                        {
                            'role': 'assistant',
                            'content': [
                                {
                                    'text': 'Cool, nice. Hope you enjoy your life.',
                                    'type': 'text',
                                }
                            ],
                        },
                    ],
                    # Must match namespace from container strategies
                    'namespace': {'user_id': 'bob'},
                    'metadata': {
                        # Custom workflow state tracking
                        'status': 'checkpoint',
                        # Supports branching conversations for exploration
                        'branch': {
                            # Branch identifier
                            'branch_name': 'high',
                            # Parent conversation point
                            'root_event_id': '228nadfs879mtgk',
                        },
                    },
                    # Enables filtering and categorization
                    'tags': {'topic': 'personal info'},
                    # Enables AI processing (summarization, semantic extraction, etc.)
                    'infer': True,
                    # Determines how AI strategies are applied
                    'payload_type': 'conversational',
                },
                {
                    'memory_container_id': 'SdjmmpgBOh0h20Y9kWuN',
                    # Alternative to messages - for non-conversational data
                    'structured_data': {
                        'time_range': {'start': '2025-09-11', 'end': '2025-09-15'}
                    },
                    'namespace': {'agent_id': 'testAgent1'},
                    # Flexible schema
                    'metadata': {'status': 'checkpoint', 'anyobject': 'abc'},
                    'tags': {'topic': 'agent_state'},
                    # Skips AI processing - stores raw data only
                    'infer': False,
                    # Bypasses conversational AI pipelines
                    'payload_type': 'data',
                },
            ]
        }


class GetAgenticMemoryArgs(BaseAgenticMemoryContainerArgs):
    """Arguments for retrieving a specific agentic memory by its type and ID."""

    memory_type: MemoryType = Field(
        ...,
        alias='type',
        description='The memory type. Valid values are sessions, working, long-term, and history.',
    )
    id: str = Field(..., description='The ID of the memory to retrieve.')

    class Config:
        json_schema_extra = {
            'examples': [
                {
                    'memory_container_id': 'HudqiJkB1SltqOcZusVU',
                    # Active conversation data, agent state, and temporary context used during ongoing interactions
                    'type': 'working',
                    'id': 'XyEuiJkBeh2gPPwzjYWM',
                },
                {
                    'memory_container_id': 'HudqiJkB1SltqOcZusVU',
                    # Processed knowledge and facts extracted from conversations over time via LLM inference
                    'type': 'long-term',
                    'id': 'DcxjTpkBvwXRq366C1Zz',
                },
                {
                    'memory_container_id': 'HudqiJkB1SltqOcZusVU',
                    # Manages conversation sessions and their metadata (start time, participants, state)
                    'type': 'sessions',
                    'id': 'CcxjTpkBvwXRq366A1aE',
                },
                {
                    'memory_container_id': 'HudqiJkB1SltqOcZusVU',
                    # Audit trail of all memory operations (add/update/delete) across the container
                    'type': 'history',
                    # Specific history record ID tracking memory evolution
                    'id': 'eMxnTpkBvwXRq366hmAU',
                },
            ]
        }


class UpdateAgenticMemoryArgs(BaseAgenticMemoryContainerArgs):
    """Arguments for updating a specific agentic memory by its type and ID."""

    # --- Constants for Validation ---
    _SESSION_ONLY_FIELDS: Set[str] = {'summary', 'agents', 'additional_info'}
    _WORKING_ONLY_FIELDS: Set[str] = {'messages', 'structured_data', 'binary_data'}
    _LONG_TERM_ONLY_FIELDS: Set[str] = {'memory'}
    _UPDATABLE_WORKING_FIELDS: Set[str] = {
        'messages',
        'structured_data',
        'binary_data',
        'tags',
        'metadata',
    }
    _UPDATABLE_LONG_TERM_FIELDS: Set[str] = {'memory', 'tags', 'metadata'}

    # --- Required Path Fields ---
    memory_type: Literal[MemoryType.sessions, MemoryType.working, MemoryType.long_term] = Field(
        ...,
        alias='type',
        description='The memory type. Valid values are sessions, working, and long-term. Note that history memory cannot be updated.',
    )
    id: str = Field(..., description='The ID of the memory to update.')

    # --- Session memory fields ---
    summary: Optional[str] = Field(default=None, description='The summary of the session.')
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description='Additional metadata for the memory (for example, status, branch, or custom fields).',
    )
    agents: Optional[Dict[str, Any]] = Field(
        default=None, description='Additional information about the agents.'
    )
    additional_info: Optional[Dict[str, Any]] = Field(
        default=None, description='Additional metadata to associate with the session.'
    )

    # --- Working memory fields ---
    messages: Optional[List[MessageItem]] = Field(
        default=None,
        description='Updated conversation messages (for conversation type).',
    )
    structured_data: Optional[Dict[str, Any]] = Field(
        default=None,
        description='Updated structured data content (for data memory payloads).',
    )
    binary_data: Optional[str] = Field(
        default=None,
        description='Updated binary data content encoded as a Base64 string (for data memory payloads).',
    )
    tags: Optional[Dict[str, Any]] = Field(
        default=None, description='Updated tags for categorization.'
    )

    # --- Long-term memory fields ---
    memory: Optional[str] = Field(default=None, description='The updated memory content.')

    @model_validator(mode='after')
    def validate_memory_type_fields(self) -> 'UpdateAgenticMemoryArgs':
        """Validate that fields match the specified memory_type and minimum requirements.

        Ensures that:
        1. Fields exclusive to one memory type (e.g., 'messages' for 'working') are not
           provided when updating another type (e.g., 'sessions').
        2. 'working' and 'long-term' updates provide at least one
           updatable field.
        """
        set_fields = self.model_fields_set

        def _raise_not_allowed_error(field_name: str, memory_type: str):
            raise PydanticCustomError(
                ERR_FIELD_NOT_ALLOWED,
                "Field '{field_name}' should not be provided when updating {memory_type} memory",
                {'field_name': field_name, 'memory_type': memory_type},
            )

        if self.memory_type == MemoryType.sessions:
            disallowed_fields = self._WORKING_ONLY_FIELDS | self._LONG_TERM_ONLY_FIELDS
            for field in disallowed_fields:
                if field in set_fields:
                    _raise_not_allowed_error(field, MemoryType.sessions)

        elif self.memory_type == MemoryType.working:
            disallowed_fields = self._SESSION_ONLY_FIELDS | self._LONG_TERM_ONLY_FIELDS
            for field in disallowed_fields:
                if field in set_fields:
                    _raise_not_allowed_error(field, MemoryType.working)

            if not any(field in set_fields for field in self._UPDATABLE_WORKING_FIELDS):
                raise PydanticCustomError(
                    ERR_MISSING_WORKING_FIELD,
                    'At least one field ({fields}) must be provided for updating working memory',
                    {'fields': ', '.join(self._UPDATABLE_WORKING_FIELDS)},
                )

        elif self.memory_type == MemoryType.long_term:
            disallowed_fields = self._SESSION_ONLY_FIELDS | self._WORKING_ONLY_FIELDS
            for field in disallowed_fields:
                if field in set_fields:
                    _raise_not_allowed_error(field, MemoryType.long_term)

            if not any(field in set_fields for field in self._UPDATABLE_LONG_TERM_FIELDS):
                raise PydanticCustomError(
                    ERR_MISSING_LONG_TERM_FIELD,
                    'At least one field ({fields}) must be provided for updating long-term memory',
                    {'fields': ', '.join(self._UPDATABLE_LONG_TERM_FIELDS)},
                )

        return self

    class Config:
        json_schema_extra = {
            'examples': [
                {
                    'memory_container_id': 'HudqiJkB1SltqOcZusVU',
                    'type': 'sessions',
                    'id': 'N2CDipkB2Mtr6INFFcX8',
                    'additional_info': {
                        # Flexible object for storing any session-specific metadata
                        'key1': 'value1',
                        # Timestamp of the last activity in the session (ISO 8601 format)
                        'last_activity': '2025-09-15T17:30:00Z',
                    },
                },
                {
                    'memory_container_id': 'HudqiJkB1SltqOcZusVU',
                    'type': 'working',
                    'id': 'XyEuiJkBeh2gPPwzjYWM',
                    # Key-value pairs for categorizing and filtering working memories
                    'tags': {'topic': 'updated_topic', 'priority': 'high'},
                },
                {
                    'memory_container_id': 'HudqiJkB1SltqOcZusVU',
                    'type': 'long-term',
                    'id': 'DcxjTpkBvwXRq366C1Zz',
                    # Actual memory content for long-term storage
                    'memory': "User's name is Bob Smith",
                    # Tags help in organizing and retrieving long-term memories
                    'tags': {'topic': 'personal info', 'updated': 'true'},
                },
                {
                    'memory_container_id': 'HudqiJkB1SltqOcZusVU',
                    'type': 'working',
                    'id': 'another_working_memory_id',
                    # Array of conversation messages (typically used for conversational memory)
                    'messages': [
                        {
                            # Role of the message sender (e.g., 'user', 'assistant')
                            'role': 'user',
                            'content': [
                                # Content supports multiple types and structures
                                {'text': 'Updated user message', 'type': 'text'}
                            ],
                        }
                    ],
                    # Custom key-value pairs for storing operational state or other context
                    'metadata': {'status': 'updated'},
                },
            ]
        }


class DeleteAgenticMemoryByIDArgs(BaseAgenticMemoryContainerArgs):
    """Arguments for deleting a specific agentic memory by its type and ID."""

    memory_type: MemoryType = Field(
        ...,
        alias='type',
        description='The type of memory to delete. Valid values are sessions, working, long-term, and history.',
    )
    id: str = Field(..., description='The ID of the specific memory to delete.')

    class Config:
        json_schema_extra = {
            'examples': [
                {
                    # The unique identifier for the memory container from which the memory will be deleted
                    'memory_container_id': 'HudqiJkB1SltqOcZusVU',
                    # Specifies the type of memory to delete. Valid values are 'sessions', 'working', 'long-term', and 'history'
                    'type': 'working',
                    # The unique identifier of the specific 'working' memory to be deleted
                    'id': 'XyEuiJkBeh2gPPwzjYWM',
                },
                {
                    'memory_container_id': 'HudqiJkB1SltqOcZusVU',
                    # Use to delete a long-term memory, which typically stores factual information
                    'type': 'long-term',
                    'id': 'DcxjTpkBvwXRq366C1Zz',
                },
                {
                    'memory_container_id': 'HudqiJkB1SltqOcZusVU',
                    # Use to delete a session memory, which tracks conversation sessions
                    'type': 'sessions',
                    'id': 'CcxjTpkBvwXRq366A1aE',
                },
                {
                    'memory_container_id': 'HudqiJkB1SltqOcZusVU',
                    # Use to delete a history memory, which maintains an audit trail of memory operations
                    'type': 'history',
                    'id': 'eMxnTpkBvwXRq366hmAU',
                },
            ]
        }


class DeleteAgenticMemoryByQueryArgs(BaseAgenticMemoryContainerArgs):
    """Arguments for deleting agentic memories by query."""

    memory_type: MemoryType = Field(
        ...,
        alias='type',
        description='The type of memory to delete. Valid values are sessions, working, long-term, and history.',
    )
    query: Dict[str, Any] = Field(
        ...,
        description='The query to match the memories you want to delete. This should be a valid OpenSearch query DSL object.',
    )

    class Config:
        json_schema_extra = {
            'examples': [
                {
                    # The unique identifier for the memory container from which memories will be deleted
                    'memory_container_id': 'HudqiJkB1SltqOcZusVU',
                    # The type of memory to delete. Valid values are 'sessions', 'working', 'long-term', and 'history'
                    'type': 'working',
                    # Uses OpenSearch Query DSL to match all 'working' memories where the 'owner_id' field is "admin"
                    'query': {'match': {'owner_id': 'admin'}},
                },
                {
                    'memory_container_id': 'HudqiJkB1SltqOcZusVU',
                    'type': 'long-term',
                    # Deletes 'long-term' memories created before 2025-09-01; useful for data retention policies
                    'query': {'range': {'created_time': {'lt': '2025-09-01'}}},
                },
                {
                    'memory_container_id': 'HudqiJkB1SltqOcZusVU',
                    'type': 'sessions',
                    # Deletes 'sessions' memories for a specific user; 'term' query finds exact matches in the 'namespace.user_id' field
                    'query': {'term': {'namespace.user_id': 'inactive_user'}},
                },
            ]
        }


class SearchAgenticMemoryArgs(BaseAgenticMemoryContainerArgs):
    """Arguments for searching memories of a specific type within a agentic memory container."""

    memory_type: MemoryType = Field(
        ...,
        alias='type',
        description='The memory type. Valid values are sessions, working, long-term, and history.',
    )
    query: Dict[str, Any] = Field(..., description='The search query using OpenSearch query DSL.')
    sort: Optional[List[Dict[str, Any]]] = Field(
        default=None, description='Sort specification for the search results.'
    )

    class Config:
        json_schema_extra = {
            'examples': [
                {
                    # The unique identifier for the memory container to search within
                    'memory_container_id': 'HudqiJkB1SltqOcZusVU',
                    # Specifies the type of memory to search (e.g., sessions, long-term, working, history)
                    'type': 'sessions',
                    # OpenSearch Query DSL: matches all documents in the specified memory type
                    'query': {'match_all': {}},
                    # Sorts results by creation time, newest first
                    'sort': [{'created_time': {'order': 'desc'}}],
                },
                {
                    'memory_container_id': 'HudqiJkB1SltqOcZusVU',
                    'type': 'long-term',
                    'query': {
                        # Term query finds exact matches in the 'namespace.user_id' field for user isolation
                        'bool': {'must': [{'term': {'namespace.user_id': 'bob'}}]}
                    },
                    'sort': [{'created_time': {'order': 'desc'}}],
                },
                {
                    'memory_container_id': 'HudqiJkB1SltqOcZusVU',
                    # 'history' type stores past interactions; typically searched with match_all to review chronologically
                    'type': 'history',
                    'query': {'match_all': {}},
                    'sort': [{'created_time': {'order': 'desc'}}],
                },
                {
                    'memory_container_id': 'HudqiJkB1SltqOcZusVU',
                    'type': 'working',
                    'query': {
                        'bool': {
                            # Finds memories for a specific user
                            'must': [{'term': {'namespace.user_id': 'bob'}}],
                            'must_not': [
                                # Excludes memories that have a 'parent_memory_id' tag
                                {'exists': {'field': 'tags.parent_memory_id'}}
                            ],
                        }
                    },
                    'sort': [{'created_time': {'order': 'desc'}}],
                },
                {
                    'memory_container_id': 'HudqiJkB1SltqOcZusVU',
                    'type': 'working',
                    # Finds memories associated with a specific session
                    'query': {'term': {'namespace.session_id': '123'}},
                    'sort': [{'created_time': {'order': 'desc'}}],
                },
            ]
        }


__all__ = [
    'MemoryType',
    'PayloadType',
    'CreateAgenticMemorySessionArgs',
    'AddAgenticMemoriesArgs',
    'GetAgenticMemoryArgs',
    'UpdateAgenticMemoryArgs',
    'DeleteAgenticMemoryByIDArgs',
    'DeleteAgenticMemoryByQueryArgs',
    'SearchAgenticMemoryArgs',
]
