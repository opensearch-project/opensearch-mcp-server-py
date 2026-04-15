# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import json
import os
import pytest
import sys
from unittest.mock import AsyncMock, Mock, patch


class TestMemoryToolsRegistry:
    """Tests for the MEMORY_TOOLS_REGISTRY and _is_memory_enabled."""

    def test_registry_empty_when_disabled(self):
        """Registry should be empty when MEMORY_TOOLS_ENABLED is not set."""
        with patch.dict(os.environ, {}, clear=True):
            # Force reimport
            if 'tools.memory_tools' in sys.modules:
                del sys.modules['tools.memory_tools']
            from tools.memory_tools import MEMORY_TOOLS_REGISTRY

            assert MEMORY_TOOLS_REGISTRY == {}

    def test_registry_empty_when_explicitly_disabled(self):
        """Registry should be empty when MEMORY_TOOLS_ENABLED=false."""
        env = {'MEMORY_TOOLS_ENABLED': 'false'}
        with patch.dict(os.environ, env, clear=True):
            if 'tools.memory_tools' in sys.modules:
                del sys.modules['tools.memory_tools']
            from tools.memory_tools import MEMORY_TOOLS_REGISTRY

            assert MEMORY_TOOLS_REGISTRY == {}

    def test_registry_populated_when_enabled(self):
        """Registry should contain all 3 tools when MEMORY_TOOLS_ENABLED=true."""
        env = {'MEMORY_TOOLS_ENABLED': 'true'}
        with patch.dict(os.environ, env, clear=True):
            if 'tools.memory_tools' in sys.modules:
                del sys.modules['tools.memory_tools']
            from tools.memory_tools import MEMORY_TOOLS_REGISTRY

            assert 'SaveMemoryTool' in MEMORY_TOOLS_REGISTRY
            assert 'SearchMemoryTool' in MEMORY_TOOLS_REGISTRY
            assert 'DeleteMemoryTool' in MEMORY_TOOLS_REGISTRY

    def test_registry_tool_structure(self):
        """Each tool in the registry should have required fields."""
        env = {'MEMORY_TOOLS_ENABLED': 'true'}
        with patch.dict(os.environ, env, clear=True):
            if 'tools.memory_tools' in sys.modules:
                del sys.modules['tools.memory_tools']
            from tools.memory_tools import MEMORY_TOOLS_REGISTRY

            required_keys = [
                'display_name',
                'description',
                'input_schema',
                'function',
                'args_model',
                'min_version',
                'http_methods',
            ]
            for tool_name, tool_def in MEMORY_TOOLS_REGISTRY.items():
                for key in required_keys:
                    assert key in tool_def, f'{tool_name} missing key: {key}'

    def test_save_and_delete_bypass_write_filter(self):
        """SaveMemoryTool and DeleteMemoryTool should bypass write filter."""
        env = {'MEMORY_TOOLS_ENABLED': 'true'}
        with patch.dict(os.environ, env, clear=True):
            if 'tools.memory_tools' in sys.modules:
                del sys.modules['tools.memory_tools']
            from tools.memory_tools import MEMORY_TOOLS_REGISTRY

            assert MEMORY_TOOLS_REGISTRY['SaveMemoryTool'].get('bypass_write_filter') is True
            assert MEMORY_TOOLS_REGISTRY['DeleteMemoryTool'].get('bypass_write_filter') is True

    def test_search_does_not_bypass_write_filter(self):
        """SearchMemoryTool should not have bypass_write_filter."""
        env = {'MEMORY_TOOLS_ENABLED': 'true'}
        with patch.dict(os.environ, env, clear=True):
            if 'tools.memory_tools' in sys.modules:
                del sys.modules['tools.memory_tools']
            from tools.memory_tools import MEMORY_TOOLS_REGISTRY

            assert MEMORY_TOOLS_REGISTRY['SearchMemoryTool'].get('bypass_write_filter') is None


class TestMemoryToolArgs:
    """Tests for argument model validation."""

    def setup_method(self):
        """Set up argument models for testing."""
        from tools.memory_tools import (
            DeleteMemoryArgs,
            SaveMemoryArgs,
            SearchMemoryArgs,
        )

        self.SaveMemoryArgs = SaveMemoryArgs
        self.SearchMemoryArgs = SearchMemoryArgs
        self.DeleteMemoryArgs = DeleteMemoryArgs

    def test_save_memory_args_required_fields(self):
        """SaveMemoryArgs requires memory field."""
        args = self.SaveMemoryArgs(
            memory='Test memory',
            opensearch_cluster_name='',
        )
        assert args.memory == 'Test memory'
        assert args.user_id is None
        assert args.agent_id is None
        assert args.session_id is None
        assert args.tags is None

    def test_save_memory_args_all_fields(self):
        """SaveMemoryArgs accepts all optional fields."""
        args = self.SaveMemoryArgs(
            memory='Test memory',
            user_id='user-1',
            agent_id='agent-1',
            session_id='session-1',
            tags='tag1,tag2',
            opensearch_cluster_name='',
        )
        assert args.user_id == 'user-1'
        assert args.agent_id == 'agent-1'
        assert args.session_id == 'session-1'
        assert args.tags == 'tag1,tag2'

    def test_save_memory_args_missing_memory_raises(self):
        """SaveMemoryArgs should fail without memory field."""
        with pytest.raises(ValueError):
            self.SaveMemoryArgs(opensearch_cluster_name='')

    def test_search_memory_args_defaults(self):
        """SearchMemoryArgs has correct defaults."""
        args = self.SearchMemoryArgs(
            query='test query',
            opensearch_cluster_name='',
        )
        assert args.query == 'test query'
        assert args.size == 10
        assert args.user_id is None
        assert args.tags is None

    def test_search_memory_args_custom_size(self):
        """SearchMemoryArgs accepts custom size."""
        args = self.SearchMemoryArgs(
            query='test',
            size=50,
            opensearch_cluster_name='',
        )
        assert args.size == 50

    def test_search_memory_args_missing_query_raises(self):
        """SearchMemoryArgs should fail without query field."""
        with pytest.raises(ValueError):
            self.SearchMemoryArgs(opensearch_cluster_name='')

    def test_delete_memory_args_required_fields(self):
        """DeleteMemoryArgs requires memory_id."""
        args = self.DeleteMemoryArgs(
            memory_id='abc123',
            opensearch_cluster_name='',
        )
        assert args.memory_id == 'abc123'

    def test_delete_memory_args_missing_id_raises(self):
        """DeleteMemoryArgs should fail without memory_id."""
        with pytest.raises(ValueError):
            self.DeleteMemoryArgs(opensearch_cluster_name='')


class TestSaveMemoryTool:
    """Tests for save_memory_tool function."""

    def setup_method(self):
        """Set up save_memory_tool for testing."""
        from tools.memory_tools import SaveMemoryArgs, save_memory_tool

        self._save_memory_tool = save_memory_tool
        self.SaveMemoryArgs = SaveMemoryArgs

    @pytest.mark.asyncio
    async def test_save_memory_success(self):
        """Test successful memory save."""
        mock_client = AsyncMock()
        mock_client.index.return_value = {'_id': 'test-id-123'}
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        args = self.SaveMemoryArgs(
            memory='User prefers dark mode',
            user_id='alice',
            tags='preference,ui',
            opensearch_cluster_name='',
        )

        with (
            patch('tools.memory_tools._ensure_memory_index', new_callable=AsyncMock),
            patch('opensearch.client.get_opensearch_client', return_value=mock_client),
        ):
            result = await self._save_memory_tool(args)

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'test-id-123' in result[0]['text']
        assert 'User prefers dark mode' in result[0]['text']

        # Verify the document structure
        call_kwargs = mock_client.index.call_args
        doc = call_kwargs.kwargs.get('body') or call_kwargs[1].get('body')
        assert doc['memory_text'] == 'User prefers dark mode'
        assert doc['user_id'] == 'alice'
        assert doc['tags'] == ['preference', 'ui']
        assert 'created_at' in doc
        assert 'updated_at' in doc

    @pytest.mark.asyncio
    async def test_save_memory_minimal_fields(self):
        """Test save with only required fields — optional fields omitted from doc."""
        mock_client = AsyncMock()
        mock_client.index.return_value = {'_id': 'min-id'}
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        args = self.SaveMemoryArgs(
            memory='Simple fact',
            opensearch_cluster_name='',
        )

        with (
            patch('tools.memory_tools._ensure_memory_index', new_callable=AsyncMock),
            patch('opensearch.client.get_opensearch_client', return_value=mock_client),
        ):
            await self._save_memory_tool(args)

        call_kwargs = mock_client.index.call_args
        doc = call_kwargs.kwargs.get('body') or call_kwargs[1].get('body')
        assert 'user_id' not in doc
        assert 'agent_id' not in doc
        assert 'session_id' not in doc
        assert 'tags' not in doc

    @pytest.mark.asyncio
    async def test_save_memory_error_handling(self):
        """Test error handling when save fails."""
        args = self.SaveMemoryArgs(
            memory='Will fail',
            opensearch_cluster_name='',
        )

        with patch(
            'tools.memory_tools._ensure_memory_index',
            new_callable=AsyncMock,
            side_effect=Exception('Connection refused'),
        ):
            result = await self._save_memory_tool(args)

        assert len(result) == 1
        assert result[0]['type'] == 'text'
        assert 'Error' in result[0]['text']


class TestSearchMemoryTool:
    """Tests for search_memory_tool function."""

    def setup_method(self):
        """Set up search_memory_tool for testing."""
        from tools.memory_tools import SearchMemoryArgs, search_memory_tool

        self._search_memory_tool = search_memory_tool
        self.SearchMemoryArgs = SearchMemoryArgs

    def _make_mock_client(self, search_response=None, index_exists=True):
        """Create a mock OpenSearch client for search tests."""
        mock_client = AsyncMock()
        mock_client.indices.exists.return_value = index_exists
        mock_client.search.return_value = search_response or {
            'hits': {'hits': []}
        }
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        return mock_client

    @pytest.mark.asyncio
    async def test_search_semantic_query(self):
        """Test semantic search wraps query in script_score."""
        mock_client = self._make_mock_client({
            'hits': {
                'hits': [
                    {
                        '_id': 'hit-1',
                        '_score': 5.0,
                        '_source': {
                            'memory_text': 'User likes dark mode',
                            'created_at': '2026-04-15T10:00:00+00:00',
                            'user_id': 'alice',
                        },
                    }
                ]
            }
        })

        args = self.SearchMemoryArgs(
            query='dark mode preference',
            opensearch_cluster_name='',
        )

        with patch('opensearch.client.get_opensearch_client', return_value=mock_client):
            result = await self._search_memory_tool(args)

        assert len(result) == 1
        assert 'Found 1 matching memories' in result[0]['text']
        assert 'dark mode' in result[0]['text']

        # Verify script_score wrapping
        call_kwargs = mock_client.search.call_args
        body = call_kwargs.kwargs.get('body') or call_kwargs[1].get('body')
        query = body['query']
        assert 'script_score' in query
        assert 'painless' in query['script_score']['script']['lang']
        assert 'decay' in query['script_score']['script']['source']

    @pytest.mark.asyncio
    async def test_search_list_all_no_script_score(self):
        """Test that * query uses match_all without script_score."""
        mock_client = self._make_mock_client({
            'hits': {
                'hits': [
                    {
                        '_id': 'hit-1',
                        '_score': 1.0,
                        '_source': {
                            'memory_text': 'Some memory',
                            'created_at': '2026-04-15T10:00:00+00:00',
                        },
                    }
                ]
            }
        })

        args = self.SearchMemoryArgs(
            query='*',
            opensearch_cluster_name='',
        )

        with patch('opensearch.client.get_opensearch_client', return_value=mock_client):
            await self._search_memory_tool(args)

        call_kwargs = mock_client.search.call_args
        body = call_kwargs.kwargs.get('body') or call_kwargs[1].get('body')
        query = body['query']
        assert 'script_score' not in query
        assert 'match_all' in query
        # Should sort by created_at desc for list-all
        assert body['sort'] == [{'created_at': {'order': 'desc'}}]

    @pytest.mark.asyncio
    async def test_search_empty_query_treated_as_list_all(self):
        """Test that empty string query is treated as list-all."""
        mock_client = self._make_mock_client({
            'hits': {'hits': []}
        })

        args = self.SearchMemoryArgs(
            query='  ',
            opensearch_cluster_name='',
        )

        with patch('opensearch.client.get_opensearch_client', return_value=mock_client):
            await self._search_memory_tool(args)

        call_kwargs = mock_client.search.call_args
        body = call_kwargs.kwargs.get('body') or call_kwargs[1].get('body')
        assert 'script_score' not in body['query']

    @pytest.mark.asyncio
    async def test_search_with_filters(self):
        """Test search with user_id, agent_id, and tags filters."""
        mock_client = self._make_mock_client({'hits': {'hits': []}})

        args = self.SearchMemoryArgs(
            query='project setup',
            user_id='alice',
            agent_id='kiro',
            tags='project,config',
            opensearch_cluster_name='',
        )

        with patch('opensearch.client.get_opensearch_client', return_value=mock_client):
            await self._search_memory_tool(args)

        call_kwargs = mock_client.search.call_args
        body = call_kwargs.kwargs.get('body') or call_kwargs[1].get('body')
        # script_score wraps the bool query
        inner_query = body['query']['script_score']['query']
        assert 'bool' in inner_query
        filters = inner_query['bool']['filter']
        filter_fields = [list(f['term'].keys())[0] for f in filters]
        assert 'user_id' in filter_fields
        assert 'agent_id' in filter_fields
        assert 'tags' in filter_fields

    @pytest.mark.asyncio
    async def test_search_list_all_with_filters(self):
        """Test * query with filters uses bool + match_all without script_score."""
        mock_client = self._make_mock_client({'hits': {'hits': []}})

        args = self.SearchMemoryArgs(
            query='*',
            user_id='alice',
            opensearch_cluster_name='',
        )

        with patch('opensearch.client.get_opensearch_client', return_value=mock_client):
            await self._search_memory_tool(args)

        call_kwargs = mock_client.search.call_args
        body = call_kwargs.kwargs.get('body') or call_kwargs[1].get('body')
        query = body['query']
        assert 'script_score' not in query
        assert 'bool' in query
        assert 'match_all' in query['bool']['must']

    @pytest.mark.asyncio
    async def test_search_size_capped_at_100(self):
        """Test that size is capped at 100."""
        mock_client = self._make_mock_client({'hits': {'hits': []}})

        args = self.SearchMemoryArgs(
            query='test',
            size=500,
            opensearch_cluster_name='',
        )

        with patch('opensearch.client.get_opensearch_client', return_value=mock_client):
            await self._search_memory_tool(args)

        call_kwargs = mock_client.search.call_args
        body = call_kwargs.kwargs.get('body') or call_kwargs[1].get('body')
        assert body['size'] == 100

    @pytest.mark.asyncio
    async def test_search_index_not_exists(self):
        """Test graceful handling when memory index doesn't exist."""
        mock_client = self._make_mock_client(index_exists=False)

        args = self.SearchMemoryArgs(
            query='anything',
            opensearch_cluster_name='',
        )

        with patch('opensearch.client.get_opensearch_client', return_value=mock_client):
            result = await self._search_memory_tool(args)

        assert len(result) == 1
        assert 'not been created yet' in result[0]['text']
        mock_client.search.assert_not_called()

    @pytest.mark.asyncio
    async def test_search_no_hits(self):
        """Test response when no memories match."""
        mock_client = self._make_mock_client({'hits': {'hits': []}})

        args = self.SearchMemoryArgs(
            query='nonexistent topic',
            opensearch_cluster_name='',
        )

        with patch('opensearch.client.get_opensearch_client', return_value=mock_client):
            result = await self._search_memory_tool(args)

        assert result[0]['text'] == 'No matching memories found.'

    @pytest.mark.asyncio
    async def test_search_result_formatting(self):
        """Test that search results include all expected fields."""
        mock_client = self._make_mock_client({
            'hits': {
                'hits': [
                    {
                        '_id': 'mem-1',
                        '_score': 8.5,
                        '_source': {
                            'memory_text': 'Project uses pytest',
                            'created_at': '2026-04-15T10:00:00+00:00',
                            'user_id': 'alice',
                            'agent_id': 'kiro',
                            'session_id': 'sess-1',
                            'tags': ['project', 'testing'],
                        },
                    }
                ]
            }
        })

        args = self.SearchMemoryArgs(
            query='pytest',
            opensearch_cluster_name='',
        )

        with patch('opensearch.client.get_opensearch_client', return_value=mock_client):
            result = await self._search_memory_tool(args)

        parsed = json.loads(result[0]['text'].split('\n', 1)[1])
        entry = parsed[0]
        assert entry['id'] == 'mem-1'
        assert entry['memory'] == 'Project uses pytest'
        assert entry['score'] == 8.5
        assert entry['user_id'] == 'alice'
        assert entry['agent_id'] == 'kiro'
        assert entry['session_id'] == 'sess-1'
        assert entry['tags'] == ['project', 'testing']

    @pytest.mark.asyncio
    async def test_search_error_handling(self):
        """Test error handling when search fails."""
        mock_client = AsyncMock()
        mock_client.indices.exists.side_effect = Exception('Cluster unavailable')
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        args = self.SearchMemoryArgs(
            query='test',
            opensearch_cluster_name='',
        )

        with patch('opensearch.client.get_opensearch_client', return_value=mock_client):
            result = await self._search_memory_tool(args)

        assert 'Error' in result[0]['text']

    @pytest.mark.asyncio
    async def test_search_semantic_query_sort_by_score(self):
        """Test that semantic queries sort by _score desc."""
        mock_client = self._make_mock_client({'hits': {'hits': []}})

        args = self.SearchMemoryArgs(
            query='some topic',
            opensearch_cluster_name='',
        )

        with patch('opensearch.client.get_opensearch_client', return_value=mock_client):
            await self._search_memory_tool(args)

        call_kwargs = mock_client.search.call_args
        body = call_kwargs.kwargs.get('body') or call_kwargs[1].get('body')
        assert body['sort'] == [{'_score': {'order': 'desc'}}]


class TestDeleteMemoryTool:
    """Tests for delete_memory_tool function."""

    def setup_method(self):
        """Set up delete_memory_tool for testing."""
        from tools.memory_tools import DeleteMemoryArgs, delete_memory_tool

        self._delete_memory_tool = delete_memory_tool
        self.DeleteMemoryArgs = DeleteMemoryArgs

    @pytest.mark.asyncio
    async def test_delete_memory_success(self):
        """Test successful memory deletion."""
        mock_client = AsyncMock()
        mock_client.delete.return_value = {'result': 'deleted'}
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        args = self.DeleteMemoryArgs(
            memory_id='mem-to-delete',
            opensearch_cluster_name='',
        )

        with patch('opensearch.client.get_opensearch_client', return_value=mock_client):
            result = await self._delete_memory_tool(args)

        assert len(result) == 1
        assert 'mem-to-delete' in result[0]['text']
        assert 'deleted' in result[0]['text']

    @pytest.mark.asyncio
    async def test_delete_memory_error_handling(self):
        """Test error handling when delete fails."""
        mock_client = AsyncMock()
        mock_client.delete.side_effect = Exception('Document not found')
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        args = self.DeleteMemoryArgs(
            memory_id='nonexistent',
            opensearch_cluster_name='',
        )

        with patch('opensearch.client.get_opensearch_client', return_value=mock_client):
            result = await self._delete_memory_tool(args)

        assert 'Error' in result[0]['text']


class TestHelperFunctions:
    """Tests for helper/utility functions."""

    def test_get_memory_index_name_default(self):
        """Test default index name."""
        with patch.dict(os.environ, {}, clear=True):
            from tools.memory_tools import _get_memory_index_name

            assert _get_memory_index_name() == 'agent-memory'

    def test_get_memory_index_name_custom(self):
        """Test custom index name from env."""
        with patch.dict(os.environ, {'MEMORY_INDEX_NAME': 'my-memories'}):
            from tools.memory_tools import _get_memory_index_name

            assert _get_memory_index_name() == 'my-memories'

    def test_is_serverless_aoss_url(self):
        """Test AOSS URL detection."""
        from tools.memory_tools import _is_serverless

        assert _is_serverless('https://abc123.us-east-1.aoss.amazonaws.com') is True
        assert _is_serverless('https://search-domain.us-east-1.es.amazonaws.com') is False
        assert _is_serverless('http://localhost:9200') is False
        assert _is_serverless(None) is False
        assert _is_serverless('') is False

    def test_is_memory_enabled(self):
        """Test memory enabled check."""
        from tools.memory_tools import _is_memory_enabled

        with patch.dict(os.environ, {'MEMORY_TOOLS_ENABLED': 'true'}):
            assert _is_memory_enabled() is True

        with patch.dict(os.environ, {'MEMORY_TOOLS_ENABLED': 'TRUE'}):
            assert _is_memory_enabled() is True

        with patch.dict(os.environ, {'MEMORY_TOOLS_ENABLED': 'false'}):
            assert _is_memory_enabled() is False

        with patch.dict(os.environ, {}, clear=True):
            assert _is_memory_enabled() is False

    def test_get_collection_id_from_url(self):
        """Test AOSS collection ID extraction."""
        from tools.memory_tools import _get_collection_id_from_url

        assert (
            _get_collection_id_from_url('https://abc123def.us-east-1.aoss.amazonaws.com')
            == 'abc123def'
        )
        assert _get_collection_id_from_url('http://localhost:9200') is None

    def test_get_collection_id_from_env_override(self):
        """Test collection ID from env override."""
        from tools.memory_tools import _get_collection_id_from_url

        with patch.dict(os.environ, {'AWS_OPENSEARCH_COLLECTION_ID': 'override-id'}):
            assert _get_collection_id_from_url('https://abc.us-east-1.aoss.amazonaws.com') == 'override-id'

    def test_get_domain_name_from_url(self):
        """Test domain name extraction from managed domain URL."""
        from tools.memory_tools import _get_domain_name_from_url

        url = 'https://search-my-domain-abc123def456.us-east-1.es.amazonaws.com'
        assert _get_domain_name_from_url(url) == 'my-domain'

    def test_get_domain_name_from_env_override(self):
        """Test domain name from env override."""
        from tools.memory_tools import _get_domain_name_from_url

        with patch.dict(os.environ, {'AWS_OPENSEARCH_DOMAIN_NAME': 'custom-domain'}):
            assert _get_domain_name_from_url('http://localhost:9200') == 'custom-domain'

    def test_get_caller_principal_arn_assumed_role(self):
        """Test STS assumed-role ARN conversion to IAM role ARN."""
        from tools.memory_tools import _get_caller_principal_arn

        mock_session = Mock()
        mock_sts = Mock()
        mock_session.client.return_value = mock_sts
        mock_sts.get_caller_identity.return_value = {
            'Arn': 'arn:aws:sts::123456789012:assumed-role/MyRole/session-name'
        }

        result = _get_caller_principal_arn(mock_session)
        assert result == 'arn:aws:iam::123456789012:role/MyRole'

    def test_get_caller_principal_arn_iam_user(self):
        """Test IAM user ARN is returned as-is."""
        from tools.memory_tools import _get_caller_principal_arn

        mock_session = Mock()
        mock_sts = Mock()
        mock_session.client.return_value = mock_sts
        mock_sts.get_caller_identity.return_value = {
            'Arn': 'arn:aws:iam::123456789012:user/my-user'
        }

        result = _get_caller_principal_arn(mock_session)
        assert result == 'arn:aws:iam::123456789012:user/my-user'


class TestWriteFilterBypass:
    """Tests for memory tools bypassing write filter."""

    def test_apply_write_filter_preserves_memory_tools(self):
        """Memory tools with bypass_write_filter should survive write filtering."""
        from tools.tool_filter import apply_write_filter

        registry = {
            'SaveMemoryTool': {
                'http_methods': 'GET, POST, PUT',
                'bypass_write_filter': True,
            },
            'DeleteMemoryTool': {
                'http_methods': 'GET, DELETE',
                'bypass_write_filter': True,
            },
            'SearchMemoryTool': {
                'http_methods': 'GET',
            },
            'SomeWriteTool': {
                'http_methods': 'POST',
            },
        }

        apply_write_filter(registry)

        assert 'SaveMemoryTool' in registry
        assert 'DeleteMemoryTool' in registry
        assert 'SearchMemoryTool' in registry
        assert 'SomeWriteTool' not in registry  # No GET, no bypass → removed
