import agentic_memory_data
import json
import pytest
from pydantic import ValidationError
from tools.agentic_memory.params import (
    ERR_FIELD_NOT_ALLOWED,
    ERR_FIELD_PROHIBITED,
    ERR_MESSAGES_REQUIRED,
    ERR_MISSING_LONG_TERM_FIELD,
    ERR_MISSING_WORKING_FIELD,
    ERR_STRUCTURED_DATA_REQUIRED,
    MemoryType,
    PayloadType,
)
from typing import Any, Dict
from unittest.mock import AsyncMock, Mock, patch


class TestAgenticMemoryTools:
    def setup_method(self):
        """Setup specific for Agentic Memory tests (requires OpenSearch 3.3.0+)."""
        # Create a properly configured mock client
        self.mock_client = Mock()

        # Configure mock client methods to return proper data structures
        # These will be overridden in individual tests as needed
        # Use AsyncMock for async methods
        self.mock_client.cat.indices = AsyncMock(return_value=[])
        self.mock_client.indices.get_mapping = AsyncMock(return_value={})
        self.mock_client.indices.get = AsyncMock(return_value={})
        self.mock_client.search = AsyncMock(return_value={})
        self.mock_client.cat.shards = AsyncMock(return_value=[])
        self.mock_client.cat.segments = AsyncMock(return_value=[])
        self.mock_client.cat.nodes = AsyncMock(return_value=[])
        self.mock_client.cat.allocation = AsyncMock(return_value=[])
        self.mock_client.cluster.state = AsyncMock(return_value={})
        self.mock_client.indices.stats = AsyncMock(return_value={})
        self.mock_client.transport.perform_request = AsyncMock(return_value={})
        self.mock_client.info = AsyncMock(return_value={'version': {'number': '3.3.0'}})

        # Patch initialize_client to always return our mock client
        self.init_client_patcher = patch(
            'opensearch.client.initialize_client', return_value=self.mock_client
        )
        self.init_client_patcher.start()

        # Clear any existing imports to ensure fresh imports
        import sys

        modules_to_clear = [
            'tools.tools',
        ]
        for module in modules_to_clear:
            if module in sys.modules:
                del sys.modules[module]

        # Set environment variable for agentic memory tools registration
        import os
        os.environ['OPENSEARCH_MEMORY_CONTAINER_ID'] = 'test-container-id'

        # Import after patching to ensure fresh imports
        from tools.agentic_memory.actions import (
            add_agentic_memories_tool,
            create_agentic_memory_session_tool,
            delete_agentic_memory_by_query_tool,
            delete_agentic_memory_by_id_tool,
            get_agentic_memory_tool,
            search_agentic_memory_tool,
            update_agentic_memory_tool,
        )
        from tools.agentic_memory.params import (
            AddAgenticMemoriesArgs,
            CreateAgenticMemorySessionArgs,
            DeleteAgenticMemoryByIDArgs,
            DeleteAgenticMemoryByQueryArgs,
            GetAgenticMemoryArgs,
            SearchAgenticMemoryArgs,
            UpdateAgenticMemoryArgs,
        )
        from tools.tools import TOOL_REGISTRY

        self.CreateAgenticMemorySessionArgs = CreateAgenticMemorySessionArgs
        self.AddAgenticMemoriesArgs = AddAgenticMemoriesArgs
        self.GetAgenticMemoryArgs = GetAgenticMemoryArgs
        self.UpdateAgenticMemoryArgs = UpdateAgenticMemoryArgs
        self.DeleteAgenticMemoryByIDArgs = DeleteAgenticMemoryByIDArgs
        self.DeleteAgenticMemoryByQueryArgs = DeleteAgenticMemoryByQueryArgs
        self.SearchAgenticMemoryArgs = SearchAgenticMemoryArgs
        self.TOOL_REGISTRY = TOOL_REGISTRY
        self._create_agentic_memory_session_tool = create_agentic_memory_session_tool
        self._add_agentic_memories_tool = add_agentic_memories_tool
        self._get_agentic_memory_tool = get_agentic_memory_tool
        self._update_agentic_memory_tool = update_agentic_memory_tool
        self._delete_agentic_memory_by_id_tool = delete_agentic_memory_by_id_tool
        self._delete_agentic_memory_by_query_tool = delete_agentic_memory_by_query_tool
        self._search_agentic_memory_tool = search_agentic_memory_tool

    def teardown_method(self):
        """Cleanup after each test method."""
        self.init_client_patcher.stop()

        # Clean up environment variable
        import os
        if 'OPENSEARCH_MEMORY_CONTAINER_ID' in os.environ:
            del os.environ['OPENSEARCH_MEMORY_CONTAINER_ID']

    @pytest.fixture
    def memory_container_id(self):
        """Fixture for a common memory container ID."""
        return 'HudqiJkB1SltqOcZusVU'

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        'payload, mock_response', agentic_memory_data.CREATE_SESSION_HAPPY_PATH_CASES
    )
    async def test_create_agentic_memory_session_happy_paths(
        self, memory_container_id, payload, mock_response
    ):
        """Test successful create_agentic_memory_session for various payloads."""
        # Setup
        self.mock_client.transport.perform_request.return_value = mock_response

        # Execute
        args = self.CreateAgenticMemorySessionArgs(
            opensearch_cluster_name='',
            memory_container_id=memory_container_id,
            **payload,
        )
        result = await self._create_agentic_memory_session_tool(args)

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Session created:' in result[0]['text']
        # Verify that the ID from the response is in the output
        assert mock_response['session_id'] in result[0]['text']

        # Request body verification
        self.mock_client.transport.perform_request.assert_called_once_with(
            method='POST',
            url=f'/_plugins/_ml/memory_containers/{memory_container_id}/memories/sessions',
            body=payload,
        )

    @pytest.mark.asyncio
    async def test_create_agentic_memory_session_error(self):
        """Test create_agentic_memory_session exception handling."""
        # Setup
        self.mock_client.transport.perform_request.side_effect = Exception(
            'Memory container not found'
        )
        payload: Dict[str, Any] = {'session_id': 'abc123'}
        container_id = 'non_existent_container'

        # Execute
        args = self.CreateAgenticMemorySessionArgs(
            opensearch_cluster_name='', memory_container_id=container_id, **payload
        )
        result = await self._create_agentic_memory_session_tool(args)

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert result[0].get('is_error') is True
        assert 'Error creating session: Memory container not found' in result[0]['text']
        self.mock_client.transport.perform_request.assert_called_once_with(
            method='POST',
            url=f'/_plugins/_ml/memory_containers/{container_id}/memories/sessions',
            body=payload,
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        'memory_type, memory_id, mock_response',
        agentic_memory_data.GET_MEMORY_HAPPY_PATH_CASES,
    )
    async def test_get_agentic_memory_happy_paths(
        self, memory_container_id, memory_type, memory_id, mock_response
    ):
        """Test successful get_agentic_memory for all memory types."""
        # Setup
        self.mock_client.transport.perform_request.return_value = mock_response

        # Execute
        args = self.GetAgenticMemoryArgs(
            opensearch_cluster_name='',
            memory_container_id=memory_container_id,
            type=memory_type,
            id=memory_id,
        )
        result = await self._get_agentic_memory_tool(args)

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        # Check that the response is in the body (as a JSON string)
        assert mock_response['_id'] in result[0]['text']

        expected_url = (
            f'/_plugins/_ml/memory_containers/{memory_container_id}/'
            f'memories/{memory_type.value}/{memory_id}'
        )
        self.mock_client.transport.perform_request.assert_called_once_with(
            method='GET', url=expected_url
        )

    @pytest.mark.asyncio
    async def test_get_agentic_memory_api_error(self, memory_container_id):
        """Test get_agentic_memory exception handling for API errors."""
        # Setup
        self.mock_client.transport.perform_request.side_effect = Exception('Memory not found')

        # Execute
        args = self.GetAgenticMemoryArgs(
            opensearch_cluster_name='',
            memory_container_id=memory_container_id,
            type=MemoryType.working,
            id='non_existent_id',
        )
        result = await self._get_agentic_memory_tool(args)

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert result[0].get('is_error') is True
        assert 'Error retrieving memory: Memory not found' in result[0]['text']

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        'payload, mock_response',
        agentic_memory_data.ADD_MEMORIES_HAPPY_PATH_CASES,
    )
    async def test_add_agentic_memories_happy_paths(
        self, memory_container_id, payload, mock_response
    ):
        """Test successful add_agentic_memories for various payloads."""
        # Setup
        self.mock_client.transport.perform_request.return_value = mock_response

        # Execute
        args = self.AddAgenticMemoriesArgs(
            opensearch_cluster_name='',
            memory_container_id=memory_container_id,
            **payload,
        )
        result = await self._add_agentic_memories_tool(args)

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Memories added:' in result[0]['text']

        # Verify that the ID from the response is in the output
        if 'working_memory_id' in mock_response:
            assert mock_response['working_memory_id'] in result[0]['text']
        if 'session_id' in mock_response:
            assert mock_response['session_id'] in result[0]['text']

        # Request body validation
        # Pydantic adds default values (e.g., infer=False) that we need to take into account.
        expected_body = payload.copy()
        if 'infer' not in expected_body:
            expected_body['infer'] = False  # Pydantic adds default=False

        self.mock_client.transport.perform_request.assert_called_once_with(
            method='POST',
            url=f'/_plugins/_ml/memory_containers/{memory_container_id}/memories',
            body=expected_body,
        )

    @pytest.mark.asyncio
    async def test_add_agentic_memories_api_error(self, memory_container_id):
        """Test add_agentic_memories exception handling from the API."""
        # Setup
        self.mock_client.transport.perform_request.side_effect = Exception('Container not found')

        payload = {
            'messages': [{'content': [{'text': 'Hello!', 'type': 'text'}]}],
            'payload_type': PayloadType.conversational,
        }

        # Execute
        args = self.AddAgenticMemoriesArgs(
            opensearch_cluster_name='',
            memory_container_id=memory_container_id,
            **payload,
        )
        result = await self._add_agentic_memories_tool(args)

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert result[0].get('is_error') is True
        assert 'Error adding memories: Container not found' in result[0]['text']

    @pytest.mark.asyncio
    async def test_add_agentic_memories_validation_error_missing_messages(self):
        """Test validation error when messages are missing for conversational payload."""
        with pytest.raises(ValidationError) as exc_info:
            self.AddAgenticMemoriesArgs(
                opensearch_cluster_name='',
                memory_container_id='id_123',
                payload_type=PayloadType.conversational,
            )

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert errors[0]['type'] == ERR_MESSAGES_REQUIRED

    @pytest.mark.asyncio
    async def test_add_agentic_memories_validation_error_missing_structured_data(self):
        """Test validation error when structured_data is missing for data payload."""
        with pytest.raises(ValidationError) as exc_info:
            self.AddAgenticMemoriesArgs(
                opensearch_cluster_name='',
                memory_container_id='id_123',
                payload_type=PayloadType.data,
            )

        errors = exc_info.value.errors()
        assert len(errors) > 0  # There may be more errors
        assert any(e['type'] == ERR_STRUCTURED_DATA_REQUIRED for e in errors)

    @pytest.mark.asyncio
    async def test_add_agentic_memories_validation_error_conflicting_fields(self):
        """Test validation error when both messages and structured_data are provided."""
        with pytest.raises(ValidationError) as exc_info:
            self.AddAgenticMemoriesArgs(
                opensearch_cluster_name='',
                memory_container_id='id_123',
                messages=[{'content': [{'text': 'Hello!', 'type': 'text'}]}],  # type: ignore
                structured_data={'key': 'value'},
                payload_type=PayloadType.conversational,
            )

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert errors[0]['type'] == ERR_FIELD_PROHIBITED
        ctx = errors[0].get('ctx')
        assert ctx is not None
        assert ctx['field_name'] == 'structured_data'

    @pytest.mark.asyncio
    async def test_add_agentic_memories_validation_error_invalid_messages_structure(
        self,
    ):
        """Test validation error (from sub-model) when messages have invalid structure."""
        with pytest.raises(ValidationError) as exc_info:
            self.AddAgenticMemoriesArgs(
                opensearch_cluster_name='',
                memory_container_id='id_123',
                messages=[
                    {
                        'role': 'user'
                        # Missing 'content'
                    }
                ],  # type: ignore
                payload_type=PayloadType.conversational,
            )

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert errors[0]['type'] == 'missing'
        assert errors[0]['loc'] == ('messages', 0, 'content')

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        'memory_type, search_body, mock_response',
        agentic_memory_data.SEARCH_MEMORY_HAPPY_PATH_CASES,
    )
    async def test_search_agentic_memory_happy_paths(
        self, memory_container_id, memory_type, search_body, mock_response
    ):
        """Test successful search_agentic_memory for various types and queries."""
        # Setup
        self.mock_client.transport.perform_request.return_value = mock_response

        # Execute
        args = self.SearchAgenticMemoryArgs(
            opensearch_cluster_name='',
            memory_container_id=memory_container_id,
            type=memory_type,
            **search_body,
        )
        result = await self._search_agentic_memory_tool(args)

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert f'Search results ({memory_type.value}):' in result[0]['text']

        # Verify that the response is in the body (as a JSON string)
        assert json.dumps(mock_response, separators=(',', ':')) in result[0]['text']

        expected_url = (
            f'/_plugins/_ml/memory_containers/{memory_container_id}/'
            f'memories/{memory_type.value}/_search'
        )
        self.mock_client.transport.perform_request.assert_called_once_with(
            method='GET', url=expected_url, body=search_body
        )

    @pytest.mark.asyncio
    async def test_search_agentic_memory_api_error(self):
        """Test search_agentic_memory exception handling for API errors."""
        # Setup
        self.mock_client.transport.perform_request.side_effect = Exception('Container not found')
        container_id = 'non_existent_container'
        search_body: Dict[str, Any] = {'query': {'match_all': {}}}

        # Execute
        args = self.SearchAgenticMemoryArgs(
            opensearch_cluster_name='',
            memory_container_id=container_id,
            type=MemoryType.sessions,
            **search_body,
        )
        result = await self._search_agentic_memory_tool(args)

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert result[0].get('is_error') is True
        assert 'Error searching memory: Container not found' in result[0]['text']
        self.mock_client.transport.perform_request.assert_called_once_with(
            method='GET',
            url=f'/_plugins/_ml/memory_containers/{container_id}/memories/sessions/_search',
            body=search_body,
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        'memory_type, memory_id, mock_response',
        agentic_memory_data.DELETE_MEMORY_ID_HAPPY_PATH_CASES,
    )
    async def test_delete_agentic_memory_by_id_happy_paths(
        self, memory_container_id, memory_type, memory_id, mock_response
    ):
        """Test successful delete_agentic_memory_by_id for all memory types."""
        # Setup
        self.mock_client.transport.perform_request.return_value = mock_response

        # Execute
        args = self.DeleteAgenticMemoryByIDArgs(
            opensearch_cluster_name='',
            memory_container_id=memory_container_id,
            type=memory_type,
            id=memory_id,
        )
        result = await self._delete_agentic_memory_by_id_tool(args)

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Memory deleted:' in result[0]['text']

        expected_url = (
            f'/_plugins/_ml/memory_containers/{memory_container_id}/'
            f'memories/{memory_type.value}/{memory_id}'
        )
        self.mock_client.transport.perform_request.assert_called_once_with(
            method='DELETE', url=expected_url
        )

    @pytest.mark.asyncio
    async def test_delete_agentic_memory_by_id_error(self, memory_container_id):
        """Test delete_agentic_memory_by_id exception handling."""
        # Setup
        self.mock_client.transport.perform_request.side_effect = Exception('Memory not found')
        memory_type = MemoryType.working
        memory_id = 'non_existent_id'

        # Execute
        args = self.DeleteAgenticMemoryByIDArgs(
            opensearch_cluster_name='',
            memory_container_id=memory_container_id,
            type=memory_type,
            id=memory_id,
        )
        result = await self._delete_agentic_memory_by_id_tool(args)

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert result[0].get('is_error') is True
        assert 'Error deleting memory: Memory not found' in result[0]['text']

        expected_url = (
            f'/_plugins/_ml/memory_containers/{memory_container_id}/'
            f'memories/{memory_type.value}/{memory_id}'
        )
        self.mock_client.transport.perform_request.assert_called_once_with(
            method='DELETE', url=expected_url
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        'memory_type, query_body, mock_response',
        agentic_memory_data.DELETE_MEMORY_QUERY_HAPPY_PATH_CASES,
    )
    async def test_delete_agentic_memory_by_query_happy_paths(
        self, memory_container_id, memory_type, query_body, mock_response
    ):
        """Test successful delete_agentic_memory_by_query for various types and queries."""
        # Setup
        self.mock_client.transport.perform_request.return_value = mock_response

        # Execute
        args = self.DeleteAgenticMemoryByQueryArgs(
            opensearch_cluster_name='',
            memory_container_id=memory_container_id,
            type=memory_type,
            **query_body,
        )
        result = await self._delete_agentic_memory_by_query_tool(args)

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Memories deleted by query:' in result[0]['text']

        expected_url = (
            f'/_plugins/_ml/memory_containers/{memory_container_id}/'
            f'memories/{memory_type.value}/_delete_by_query'
        )
        self.mock_client.transport.perform_request.assert_called_once_with(
            method='POST', url=expected_url, body=query_body
        )

    @pytest.mark.asyncio
    async def test_delete_agentic_memory_by_query_error(self, memory_container_id):
        """Test delete_agentic_memory_by_query exception handling."""
        # Setup
        self.mock_client.transport.perform_request.side_effect = Exception(
            'Query validation failed'
        )
        memory_type = MemoryType.working

        query_body: Dict[str, Any] = {'query': {'invalid_query': {'field': 'value'}}}

        # Execute
        args = self.DeleteAgenticMemoryByQueryArgs(
            opensearch_cluster_name='',
            memory_container_id=memory_container_id,
            type=memory_type,
            **query_body,
        )
        result = await self._delete_agentic_memory_by_query_tool(args)

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert result[0].get('is_error') is True
        assert 'Error deleting memories by query: Query validation failed' in result[0]['text']

        expected_url = (
            f'/_plugins/_ml/memory_containers/{memory_container_id}/'
            f'memories/{memory_type.value}/_delete_by_query'
        )
        self.mock_client.transport.perform_request.assert_called_once_with(
            method='POST', url=expected_url, body=query_body
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        'memory_type, memory_id, update_body, mock_response',
        agentic_memory_data.UPDATE_HAPPY_PATH_CASES,
    )
    async def test_update_agentic_memory_happy_paths(
        self, memory_container_id, memory_type, memory_id, update_body, mock_response
    ):
        """Test successful update_agentic_memory for various types and fields."""
        # Setup
        self.mock_client.transport.perform_request.return_value = mock_response

        # Execute
        args = self.UpdateAgenticMemoryArgs(
            opensearch_cluster_name='',
            memory_container_id=memory_container_id,
            type=memory_type,
            id=memory_id,
            **update_body,
        )
        result = await self._update_agentic_memory_tool(args)

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Memory updated:' in result[0]['text']

        expected_url = (
            f'/_plugins/_ml/memory_containers/{memory_container_id}/'
            f'memories/{memory_type.value}/{memory_id}'
        )
        self.mock_client.transport.perform_request.assert_called_once_with(
            method='PUT', url=expected_url, body=update_body
        )

    @pytest.mark.asyncio
    async def test_update_agentic_memory_api_error(self, memory_container_id):
        """Test update_agentic_memory exception handling from the API."""
        # Setup
        self.mock_client.transport.perform_request.side_effect = Exception('Memory not found')

        # Execute
        args = self.UpdateAgenticMemoryArgs(
            opensearch_cluster_name='',
            memory_container_id=memory_container_id,
            type=MemoryType.working,
            id='non_existent_id',
            tags={'topic': 'test'},
        )
        result = await self._update_agentic_memory_tool(args)

        # Assert
        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert result[0].get('is_error') is True
        assert 'Error updating memory: Memory not found' in result[0]['text']
        self.mock_client.transport.perform_request.assert_called_once_with(
            method='PUT',
            url=f'/_plugins/_ml/memory_containers/{memory_container_id}/memories/working/non_existent_id',
            body={'tags': {'topic': 'test'}},
        )

    @pytest.mark.asyncio
    async def test_update_agentic_memory_validation_error_session_with_working_fields(
        self,
    ):
        """Test validation error when session has working memory fields."""
        with pytest.raises(ValidationError) as exc_info:
            self.UpdateAgenticMemoryArgs(
                opensearch_cluster_name='',
                memory_container_id='id_123',
                type=MemoryType.sessions,
                id='session_id',
                messages=[{'role': 'user', 'content': [{'text': 'test', 'type': 'text'}]}],  # type: ignore
            )

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert errors[0]['type'] == ERR_FIELD_NOT_ALLOWED

        ctx = errors[0].get('ctx')
        assert ctx is not None
        assert ctx['field_name'] == 'messages'
        assert ctx['memory_type'] == MemoryType.sessions.value

    @pytest.mark.asyncio
    async def test_update_agentic_memory_validation_error_working_with_session_fields(
        self,
    ):
        """Test validation error when working memory has session fields."""
        with pytest.raises(ValidationError) as exc_info:
            self.UpdateAgenticMemoryArgs(
                opensearch_cluster_name='',
                memory_container_id='id_123',
                type=MemoryType.working,
                id='working_id',
                summary='This should not be here',  # Session field
            )

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert errors[0]['type'] == ERR_FIELD_NOT_ALLOWED

        ctx = errors[0].get('ctx')
        assert ctx is not None
        assert ctx['field_name'] == 'summary'
        assert ctx['memory_type'] == MemoryType.working.value

    @pytest.mark.asyncio
    async def test_update_agentic_memory_validation_error_long_term_with_working_fields(
        self,
    ):
        """Test validation error when long-term memory has working fields."""
        with pytest.raises(ValidationError) as exc_info:
            self.UpdateAgenticMemoryArgs(
                opensearch_cluster_name='',
                memory_container_id='id_123',
                type=MemoryType.long_term,
                id='long_term_id',
                structured_data={'key': 'value'},  # Working field
            )

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert errors[0]['type'] == ERR_FIELD_NOT_ALLOWED

        ctx = errors[0].get('ctx')
        assert ctx is not None
        assert ctx['field_name'] == 'structured_data'
        assert ctx['memory_type'] == MemoryType.long_term.value

    @pytest.mark.asyncio
    async def test_update_agentic_memory_validation_error_working_no_fields(self):
        """Test validation error when working memory has no updatable fields."""
        with pytest.raises(ValidationError) as exc_info:
            self.UpdateAgenticMemoryArgs(
                opensearch_cluster_name='',
                memory_container_id='id_123',
                type=MemoryType.working,
                id='working_id',
            )

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert errors[0]['type'] == ERR_MISSING_WORKING_FIELD

    @pytest.mark.asyncio
    async def test_update_agentic_memory_validation_error_long_term_no_fields(self):
        """Test validation error when long-term memory has no updatable fields."""
        with pytest.raises(ValidationError) as exc_info:
            self.UpdateAgenticMemoryArgs(
                opensearch_cluster_name='',
                memory_container_id='id_123',
                type=MemoryType.long_term,
                id='long_term_id',
            )

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert errors[0]['type'] == ERR_MISSING_LONG_TERM_FIELD

    @pytest.mark.asyncio
    async def test_update_agentic_memory_validation_error_working_invalid_messages(
        self,
    ):
        """Test validation error (from sub-model) when working memory messages have invalid structure."""
        with pytest.raises(ValidationError) as exc_info:
            self.UpdateAgenticMemoryArgs(
                opensearch_cluster_name='',
                memory_container_id='id_123',
                type=MemoryType.working,
                id='working_id',
                messages=[
                    {
                        'role': 'user'
                        # Missing 'content' field
                    }
                ],  # type: ignore
            )

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert errors[0]['type'] == 'missing'
        assert errors[0]['loc'] == ('messages', 0, 'content')

    def test_tool_registry(self):
        """Test TOOL_REGISTRY structure."""
        expected_tools = [
            'CreateAgenticMemorySessionTool',
            'AddAgenticMemoriesTool',
            'GetAgenticMemoryTool',
            'UpdateAgenticMemoryTool',
            'DeleteAgenticMemoryByIDTool',
            'DeleteAgenticMemoryByQueryTool',
            'SearchAgenticMemoryTool',
        ]

        for tool in expected_tools:
            assert tool in self.TOOL_REGISTRY
            assert 'description' in self.TOOL_REGISTRY[tool]
            assert 'input_schema' in self.TOOL_REGISTRY[tool]
            assert 'function' in self.TOOL_REGISTRY[tool]
            assert 'args_model' in self.TOOL_REGISTRY[tool]
