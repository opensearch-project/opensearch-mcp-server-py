import pytest
from tools.agentic_memory.params import MemoryType, PayloadType


# --- Agentic Memory: parametrized test input cases for Pydantic model validation ---

UPDATE_HAPPY_PATH_CASES = [
    pytest.param(
        MemoryType.sessions,
        'N2CDipkB2Mtr6INFFcX8',
        {
            'additional_info': {
                'key1': 'value1',
                'last_activity': '2025-09-15T17:30:00Z',
            }
        },
        {'result': 'updated', '_id': 'N2CDipkB2Mtr6INFFcX8', '_version': 2},
    ),
    pytest.param(
        MemoryType.working,
        'XyEuiJkBeh2gPPwzjYWM',
        {'tags': {'topic': 'updated_topic', 'priority': 'high'}},
        {'result': 'updated', '_id': 'XyEuiJkBeh2gPPwzjYWM', '_version': 3},
    ),
    pytest.param(
        MemoryType.long_term,
        'DcxjTpkBvwXRq366C1Zz',
        {
            'memory': "User's name is Bob Smith",
            'tags': {'topic': 'personal info', 'updated': 'true'},
        },
        {'result': 'updated', '_id': 'DcxjTpkBvwXRq366C1Zz', '_version': 2},
    ),
    pytest.param(
        MemoryType.working,
        'another_working_memory_id',
        {
            'messages': [
                {
                    'role': 'user',
                    'content': [{'text': 'Updated user message', 'type': 'text'}],
                }
            ],
            'metadata': {'status': 'updated'},
        },
        {'result': 'updated', '_id': 'another_working_memory_id', '_version': 2},
    ),
    pytest.param(
        MemoryType.sessions,
        'session_id_123',
        {
            'summary': 'Updated session summary',
            'metadata': {'status': 'active', 'branch': 'main'},
            'agents': {
                'primary_agent': 'assistant',
                'secondary_agents': ['tool1', 'tool2'],
            },
        },
        {'result': 'updated', '_id': 'session_id_123', '_version': 2},
    ),
    pytest.param(
        MemoryType.working,
        'working_struct_id',
        {
            'structured_data': {'updated_state': {'status': 'completed', 'progress': 100}},
            'tags': {'type': 'state_update'},
        },
        {'result': 'updated', '_id': 'working_struct_id', '_version': 2},
    ),
    pytest.param(
        MemoryType.long_term,
        'long_term_minimal',
        {'memory': 'Updated memory content only'},
        {'result': 'updated', '_id': 'long_term_minimal', '_version': 2},
    ),
]

ADD_MEMORIES_HAPPY_PATH_CASES = [
    pytest.param(
        {
            'messages': [
                {
                    'role': 'user',
                    'content': [{'text': "I'm Bob, I really like swimming.", 'type': 'text'}],
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
            'namespace': {'user_id': 'bob'},
            'metadata': {
                'status': 'checkpoint',
                'branch': {'branch_name': 'high', 'root_event_id': '228nadfs879mtgk'},
            },
            'tags': {'topic': 'personal info'},
            'infer': True,
            'payload_type': PayloadType.conversational,
        },
        {
            'session_id': 'XSEuiJkBeh2gPPwzjYVh',
            'working_memory_id': 'XyEuiJkBeh2gPPwzjYWM',
        },
        id='conversational_with_infer',  # lets pytest fill missing parameters via fixtures when not provided by parametrize
    ),
    pytest.param(
        {
            'structured_data': {'time_range': {'start': '2025-09-11', 'end': '2025-09-15'}},
            'namespace': {'agent_id': 'testAgent1'},
            'metadata': {'status': 'checkpoint', 'anyobject': 'abc'},
            'tags': {'topic': 'agent_state'},
            'infer': False,
            'payload_type': PayloadType.data,
        },
        {'working_memory_id': 'Z8xeTpkBvwXRq366l0iA'},
        id='data_payload',
    ),
    pytest.param(
        {
            'structured_data': {
                'tool_invocations': [
                    {
                        'tool_name': 'ListIndexTool',
                        'tool_input': {'filter': '*,-.plugins*'},
                        'tool_output': '...',
                    }
                ]
            },
            'namespace': {
                'user_id': 'bob',
                'agent_id': 'testAgent1',
                'session_id': '123',
            },
            'metadata': {'status': 'checkpoint'},
            'tags': {'topic': 'personal info'},
            'infer': False,
            'payload_type': PayloadType.data,
        },
        {'working_memory_id': 'Z8xeTpkBvwXRq366l0iA'},
        id='data_payload_tool_invocation',
    ),
    pytest.param(
        {
            'messages': [{'content': [{'text': 'Hello, world!', 'type': 'text'}]}],
            'payload_type': PayloadType.conversational,
        },
        {'session_id': 'minimal_session', 'working_memory_id': 'minimal_memory'},
        id='minimal_conversational',
    ),
]

CREATE_SESSION_HAPPY_PATH_CASES = [
    pytest.param(
        {'session_id': 'abc123', 'metadata': {'key1': 'value1'}},
        {'session_id': 'abc123', 'status': 'created'},
        id='with_custom_id',
    ),
    pytest.param(
        {
            'summary': 'This is a test session',
            'metadata': {'key1': 'value1'},
            'namespace': {'user_id': 'bob'},
        },
        {'session_id': 'jTYm35kBt8CyICnjxJl9', 'status': 'created'},
        id='with_autogenerated_id',
    ),
    pytest.param(
        {
            'session_id': 'custom_session_123',
            'summary': 'Session for user onboarding',
            'namespace': {'user_id': 'alice', 'agent_id': 'onboarding_bot'},
            'metadata': {'priority': 'high', 'category': 'onboarding'},
        },
        {'session_id': 'custom_session_123', 'status': 'created'},
        id='with_all_fields',
    ),
    pytest.param(
        {},  # Empty pld
        {'session_id': 'auto_generated_id_123', 'status': 'created'},
        id='minimal',
    ),
]

GET_MEMORY_HAPPY_PATH_CASES = [
    pytest.param(
        MemoryType.working,
        'XyEuiJkBeh2gPPwzjYWM',
        {'_id': 'XyEuiJkBeh2gPPwzjYWM', 'namespace': {'user': 'test'}, 'messages': []},
        id='get_working_memory',
    ),
    pytest.param(
        MemoryType.long_term,
        'DcxjTpkBvwXRq366C1Zz',
        {
            '_id': 'DcxjTpkBvwXRq366C1Zz',
            'namespace': {'user': 'test'},
            'memory': 'some data',
        },
        id='get_long_term_memory',
    ),
    pytest.param(
        MemoryType.sessions,
        'CcxjTpkBvwXRq366A1aE',
        {'_id': 'CcxjTpkBvwXRq366A1aE', 'summary': 'A session'},
        id='get_session_memory',
    ),
    pytest.param(
        MemoryType.history,
        'eMxnTpkBvwXRq366hmAU',
        {'_id': 'eMxnTpkBvwXRq366hmAU', 'trace_id': 'trace-123'},
        id='get_history_memory',
    ),
]


SEARCH_SESSIONS_RESPONSE = {
    'took': 5,
    'hits': {
        'hits': [
            {
                '_id': 'CcxjTpkBvwXRq366A1aE',
                '_source': {'namespace': {'user_id': 'bob'}},
            }
        ]
    },
}
SEARCH_LONG_TERM_RESPONSE = {
    'took': 3,
    'hits': {'hits': [{'_id': 'abc123'}, {'_id': 'def456'}]},
}
SEARCH_WORKING_COMPLEX_RESPONSE = {
    'took': 4,
    'hits': {'hits': [{'_id': 'working_mem_123'}]},
}
SEARCH_HISTORY_RESPONSE = {'took': 2, 'hits': {'total': {'value': 0}, 'hits': []}}
SEARCH_NO_SORT_RESPONSE = {
    'took': 1,
    'hits': {'hits': [{'_id': 'no_sort_id', '_score': 1.0}]},
}
SEARCH_SESSION_ID_RESPONSE = {
    'took': 3,
    'hits': {
        'hits': [
            {
                '_id': 'session_trace_123',
                '_source': {'namespace': {'session_id': '123'}},
            }
        ]
    },
}

SEARCH_MEMORY_HAPPY_PATH_CASES = [
    pytest.param(
        MemoryType.sessions,
        {'query': {'match_all': {}}, 'sort': [{'created_time': {'order': 'desc'}}]},
        SEARCH_SESSIONS_RESPONSE,
        id='search_sessions_match_all',
    ),
    pytest.param(
        MemoryType.long_term,
        {
            'query': {'bool': {'must': [{'term': {'namespace.user_id': 'bob'}}]}},
            'sort': [{'created_time': {'order': 'desc'}}],
        },
        SEARCH_LONG_TERM_RESPONSE,
        id='search_long_term_with_namespace',
    ),
    pytest.param(
        MemoryType.working,
        {
            'query': {
                'bool': {
                    'must': [{'term': {'namespace.user_id': 'bob'}}],
                    'must_not': [{'exists': {'field': 'tags.parent_memory_id'}}],
                }
            },
            'sort': [{'created_time': {'order': 'desc'}}],
        },
        SEARCH_WORKING_COMPLEX_RESPONSE,
        id='search_working_complex_query',
    ),
    pytest.param(
        MemoryType.history,
        {'query': {'match_all': {}}, 'sort': [{'created_time': {'order': 'desc'}}]},
        SEARCH_HISTORY_RESPONSE,
        id='search_history_no_results',
    ),
    pytest.param(
        MemoryType.sessions,
        {'query': {'match_all': {}}},  # Without 'sort'
        SEARCH_NO_SORT_RESPONSE,
        id='search_without_sort',
    ),
    pytest.param(
        MemoryType.working,
        {
            'query': {'term': {'namespace.session_id': '123'}},
            'sort': [{'created_time': {'order': 'desc'}}],
        },
        SEARCH_SESSION_ID_RESPONSE,
        id='search_working_by_session_id',
    ),
]


DELETE_MEMORY_ID_HAPPY_PATH_CASES = [
    pytest.param(
        MemoryType.working,
        'XyEuiJkBeh2gPPwzjYWM',
        {'result': 'deleted', '_id': 'XyEuiJkBeh2gPPwzjYWM', '_version': 2},
        id='delete_working_memory',
    ),
    pytest.param(
        MemoryType.long_term,
        'DcxjTpkBvwXRq366C1Zz',
        {'result': 'deleted', '_id': 'DcxjTpkBvwXRq366C1Zz', '_version': 1},
        id='delete_long_term_memory',
    ),
    pytest.param(
        MemoryType.sessions,
        'CcxjTpkBvwXRq366A1aE',
        {'result': 'deleted', '_id': 'CcxjTpkBvwXRq366A1aE', '_version': 3},
        id='delete_session_memory',
    ),
    pytest.param(
        MemoryType.history,
        'eMxnTpkBvwXRq366hmAU',
        {'result': 'deleted', '_id': 'eMxnTpkBvwXRq366hmAU', '_version': 1},
        id='delete_history_memory',
    ),
]

DELETE_QUERY_WORKING_RESP = {'deleted': 6, 'total': 6, 'failures': [], 'took': 159}
DELETE_QUERY_LONG_TERM_RESP = {'deleted': 10, 'total': 10, 'failures': [], 'took': 85}
DELETE_QUERY_SESSIONS_RESP = {'deleted': 3, 'total': 3, 'failures': [], 'took': 42}
DELETE_QUERY_COMPLEX_RESP = {'deleted': 5, 'total': 5, 'failures': [], 'took': 120}
DELETE_QUERY_NO_RESULTS_RESP = {'deleted': 0, 'total': 0, 'failures': [], 'took': 15}

DELETE_MEMORY_QUERY_HAPPY_PATH_CASES = [
    pytest.param(
        MemoryType.working,
        {'query': {'match': {'owner_id': 'admin'}}},
        DELETE_QUERY_WORKING_RESP,
        id='delete_working_by_match',
    ),
    pytest.param(
        MemoryType.long_term,
        {'query': {'range': {'created_time': {'lt': '2025-09-01'}}}},
        DELETE_QUERY_LONG_TERM_RESP,
        id='delete_long_term_by_range',
    ),
    pytest.param(
        MemoryType.sessions,
        {'query': {'term': {'namespace.user_id': 'inactive_user'}}},
        DELETE_QUERY_SESSIONS_RESP,
        id='delete_sessions_by_term',
    ),
    pytest.param(
        MemoryType.working,
        {
            'query': {
                'bool': {
                    'must': [{'term': {'namespace.agent_id': 'test_agent'}}],
                    'must_not': [{'exists': {'field': 'tags.important'}}],
                }
            }
        },
        DELETE_QUERY_COMPLEX_RESP,
        id='delete_working_complex_bool',
    ),
    pytest.param(
        MemoryType.history,
        {'query': {'term': {'namespace.user_id': 'non_existent_user'}}},
        DELETE_QUERY_NO_RESULTS_RESP,
        id='delete_history_no_results',
    ),
]

BASIC_CONFIG_PAYLOAD = {
    'name': 'agentic memory test',
    'description': 'Store conversations with semantic search and summarization',
    'configuration': {
        'embedding_model_type': 'TEXT_EMBEDDING',
        'embedding_model_id': 'embedding-model-123',
        'embedding_dimension': 1024,
        'llm_id': 'llm-model-456',
        'strategies': [{'type': 'SEMANTIC', 'namespace': ['user_id']}],
    },
}
BASIC_CONFIG_EXPECTED_BODY = {
    'name': 'agentic memory test',
    'description': 'Store conversations with semantic search and summarization',
    'configuration': {
        'embedding_model_type': 'TEXT_EMBEDDING',
        'embedding_model_id': 'embedding-model-123',
        'embedding_dimension': 1024,
        'llm_id': 'llm-model-456',
        'use_system_index': True,
        'disable_history': False,
        'disable_session': True,
        'strategies': [{'type': 'SEMANTIC', 'namespace': ['user_id'], 'enabled': True}],
    },
}

ADVANCED_CONFIG_PAYLOAD = {
    'name': 'advanced memory container',
    'description': 'Advanced memory container with multiple strategies',
    'configuration': {
        'embedding_model_type': 'TEXT_EMBEDDING',
        'embedding_model_id': 'embedding-model-789',
        'embedding_dimension': 1024,
        'llm_id': 'llm-model-456',
        'index_prefix': 'my_custom_prefix',
        'use_system_index': False,
        'disable_history': True,
        'disable_session': False,
        'max_infer_size': 50,
        'strategies': [
            {
                'type': 'SEMANTIC',
                'namespace': ['agent_id'],
                'configuration': {
                    'llm_result_path': '$.output.message.content[0].text',
                    'system_prompt': 'Extract semantic information from user conversations',
                    'llm_id': 'strategy-llm-id',
                },
                'enabled': True,
            },
            {
                'type': 'USER_PREFERENCE',
                'namespace': ['agent_id'],
                'configuration': {'llm_result_path': '$.choices[0].message.content'},
            },
        ],
        'parameters': {'llm_result_path': '$.output.message.content[0].text'},
        'index_settings': {
            'session_index': {'index': {'number_of_shards': '2', 'number_of_replicas': '2'}},
            'short_term_memory_index': {
                'index': {'number_of_shards': '3', 'number_of_replicas': '1'}
            },
        },
    },
}
ADVANCED_CONFIG_EXPECTED_BODY = {
    'name': 'advanced memory container',
    'description': 'Advanced memory container with multiple strategies',
    'configuration': {
        'embedding_model_type': 'TEXT_EMBEDDING',
        'embedding_model_id': 'embedding-model-789',
        'embedding_dimension': 1024,
        'llm_id': 'llm-model-456',
        'index_prefix': 'my_custom_prefix',
        'use_system_index': False,
        'disable_history': True,
        'disable_session': False,
        'max_infer_size': 50,
        'strategies': [
            {
                'type': 'SEMANTIC',
                'namespace': ['agent_id'],
                'configuration': {
                    'llm_result_path': '$.output.message.content[0].text',
                    'system_prompt': 'Extract semantic information from user conversations',
                    'llm_id': 'strategy-llm-id',
                },
                'enabled': True,
            },
            {
                'type': 'USER_PREFERENCE',
                'namespace': ['agent_id'],
                'configuration': {'llm_result_path': '$.choices[0].message.content'},
                'enabled': True,
            },
        ],
        'parameters': {'llm_result_path': '$.output.message.content[0].text'},
        'index_settings': {
            'session_index': {'index': {'number_of_shards': '2', 'number_of_replicas': '2'}},
            'short_term_memory_index': {
                'index': {'number_of_shards': '3', 'number_of_replicas': '1'}
            },
        },
    },
}

MINIMAL_CONFIG_PAYLOAD = {
    'name': 'minimal container',
    'configuration': {
        'embedding_model_type': 'SPARSE_ENCODING',
        'embedding_model_id': 'sparse-model-123',
    },
}
MINIMAL_CONFIG_EXPECTED_BODY = {
    'name': 'minimal container',
    'configuration': {
        'embedding_model_type': 'SPARSE_ENCODING',
        'embedding_model_id': 'sparse-model-123',
        'use_system_index': True,
        'disable_history': False,
        'disable_session': True,
    },
}

__all__ = [
    'UPDATE_HAPPY_PATH_CASES',
    'ADD_MEMORIES_HAPPY_PATH_CASES',
    'CREATE_SESSION_HAPPY_PATH_CASES',
    'GET_MEMORY_HAPPY_PATH_CASES',
    'SEARCH_SESSIONS_RESPONSE',
    'SEARCH_LONG_TERM_RESPONSE',
    'SEARCH_WORKING_COMPLEX_RESPONSE',
    'SEARCH_HISTORY_RESPONSE',
    'SEARCH_NO_SORT_RESPONSE',
    'SEARCH_SESSION_ID_RESPONSE',
    'SEARCH_MEMORY_HAPPY_PATH_CASES',
    'DELETE_MEMORY_ID_HAPPY_PATH_CASES',
    'DELETE_QUERY_WORKING_RESP',
    'DELETE_QUERY_LONG_TERM_RESP',
    'DELETE_QUERY_SESSIONS_RESP',
    'DELETE_QUERY_COMPLEX_RESP',
    'DELETE_QUERY_NO_RESULTS_RESP',
    'DELETE_MEMORY_QUERY_HAPPY_PATH_CASES',
    'BASIC_CONFIG_PAYLOAD',
    'BASIC_CONFIG_EXPECTED_BODY',
    'ADVANCED_CONFIG_PAYLOAD',
    'ADVANCED_CONFIG_EXPECTED_BODY',
    'MINIMAL_CONFIG_PAYLOAD',
    'MINIMAL_CONFIG_EXPECTED_BODY',
]
