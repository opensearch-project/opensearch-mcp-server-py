# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import logging
import pytest
from mcp.types import CallToolResult, TextContent
from mcp_server_opensearch.client_context import client_name_var
from mcp_server_opensearch.tool_executor import _build_call_tool_result, execute_tool
from unittest.mock import AsyncMock, Mock, patch


class TestBuildCallToolResult:
    def test_dict_item_becomes_text_content(self):
        result = _build_call_tool_result([{'type': 'text', 'text': 'hello'}], is_error=False)
        assert isinstance(result, CallToolResult)
        assert result.is_error is False
        assert len(result.content) == 1
        assert isinstance(result.content[0], TextContent)
        assert result.content[0].text == 'hello'

    def test_text_content_instance_passed_through(self):
        item = TextContent(type='text', text='direct')
        result = _build_call_tool_result([item], is_error=False)
        assert result.content[0] is item

    def test_is_error_true_propagates(self):
        result = _build_call_tool_result([{'type': 'text', 'text': 'boom'}], is_error=True)
        assert result.is_error is True

    def test_empty_list_produces_empty_content(self):
        result = _build_call_tool_result([], is_error=False)
        assert result.content == []

    def test_none_list_produces_empty_content(self):
        result = _build_call_tool_result(None, is_error=False)
        assert result.content == []

    def test_dict_missing_text_key_defaults_to_empty_string(self):
        result = _build_call_tool_result([{'type': 'text'}], is_error=False)
        assert result.content[0].text == ''

    def test_dict_missing_type_key_defaults_to_text(self):
        result = _build_call_tool_result([{'text': 'hi'}], is_error=False)
        assert isinstance(result.content[0], TextContent)

    def test_multiple_items_preserved_in_order(self):
        items = [
            {'type': 'text', 'text': 'first'},
            TextContent(type='text', text='second'),
        ]
        result = _build_call_tool_result(items, is_error=False)
        assert len(result.content) == 2
        assert result.content[0].text == 'first'
        assert result.content[1].text == 'second'


def make_enabled_tools(tool_key='TestTool', display_name=None, return_value=None):
    """Helper to create a mock enabled_tools dict."""
    if return_value is None:
        return_value = [{'type': 'text', 'text': 'Success'}]
    return {
        tool_key: {
            'display_name': display_name or tool_key,
            'description': 'A test tool',
            'input_schema': {'type': 'object', 'properties': {}},
            'args_model': Mock(),
            'function': AsyncMock(return_value=return_value),
        }
    }


class TestExecuteTool:
    @pytest.mark.asyncio
    @patch('tools.tool_params.validate_args_for_mode')
    async def test_successful_execution_logs_success(self, mock_validate, caplog):
        mock_validate.return_value = Mock()
        enabled_tools = make_enabled_tools()

        with caplog.at_level(logging.INFO):
            result = await execute_tool('TestTool', {}, enabled_tools)

        # Success is returned as a CallToolResult with isError=False.
        assert isinstance(result, CallToolResult)
        assert result.is_error is False
        assert result.content[0].text == 'Success'
        # Check structured log was emitted
        assert any('Tool executed: TestTool' in r.message for r in caplog.records)
        # Check extra fields
        success_records = [
            r
            for r in caplog.records
            if hasattr(r, 'event_type') and r.event_type == 'tool_execution'
        ]
        assert len(success_records) == 1
        assert success_records[0].status == 'success'
        assert hasattr(success_records[0], 'duration_ms')

    @pytest.mark.asyncio
    @patch('tools.tool_params.validate_args_for_mode')
    async def test_soft_error_detected_via_is_error_flag(self, mock_validate, caplog):
        mock_validate.return_value = Mock()
        enabled_tools = make_enabled_tools(
            return_value=[
                {
                    'type': 'text',
                    'text': 'Error searching index: connection refused',
                    'is_error': True,
                }
            ]
        )

        with caplog.at_level(logging.ERROR):
            result = await execute_tool('TestTool', {}, enabled_tools)

        assert isinstance(result, CallToolResult)
        assert result.is_error is True
        assert getattr(result.content[0], 'is_error', None) is None
        assert result.content[0].text == 'Error searching index: connection refused'
        error_records = [
            r
            for r in caplog.records
            if hasattr(r, 'event_type') and r.event_type == 'tool_execution'
        ]
        assert len(error_records) == 1
        assert error_records[0].status == 'error'

    @pytest.mark.asyncio
    @patch('tools.tool_params.validate_args_for_mode')
    async def test_text_starting_with_error_without_flag_is_success(self, mock_validate, caplog):
        """Text that happens to start with 'Error' but lacks is_error flag should be success."""
        mock_validate.return_value = Mock()
        enabled_tools = make_enabled_tools(
            return_value=[{'type': 'text', 'text': 'Error codes explained: 404 means not found'}]
        )

        with caplog.at_level(logging.INFO):
            await execute_tool('TestTool', {}, enabled_tools)

        records = [
            r
            for r in caplog.records
            if hasattr(r, 'event_type') and r.event_type == 'tool_execution'
        ]
        assert len(records) == 1
        assert records[0].status == 'success'

    @pytest.mark.asyncio
    async def test_unknown_tool_raises_value_error(self, caplog):
        with caplog.at_level(logging.ERROR):
            with pytest.raises(ValueError, match='Unknown or disabled tool'):
                await execute_tool('NonExistentTool', {}, {})

        error_records = [
            r
            for r in caplog.records
            if hasattr(r, 'event_type') and r.event_type == 'tool_execution'
        ]
        assert len(error_records) == 1
        assert error_records[0].status == 'error'
        assert error_records[0].error_type == 'UnknownToolError'

    @pytest.mark.asyncio
    @patch('tools.tool_params.validate_args_for_mode')
    async def test_exception_in_tool_propagates_and_logs(self, mock_validate, caplog):
        mock_validate.return_value = Mock()
        enabled_tools = make_enabled_tools()
        enabled_tools['TestTool']['function'] = AsyncMock(side_effect=RuntimeError('boom'))

        with caplog.at_level(logging.ERROR):
            with pytest.raises(RuntimeError, match='boom'):
                await execute_tool('TestTool', {}, enabled_tools)

        error_records = [
            r
            for r in caplog.records
            if hasattr(r, 'event_type') and r.event_type == 'tool_execution'
        ]
        assert len(error_records) == 1
        assert error_records[0].status == 'error'
        assert error_records[0].error_type == 'RuntimeError'

    @pytest.mark.asyncio
    @patch('tools.tool_params.validate_args_for_mode')
    async def test_validation_error_logs_error_status(self, mock_validate, caplog):
        """Validation failures (missing required field) should log status='error'."""
        mock_validate.side_effect = ValueError("Missing required field: 'query_dsl'")
        enabled_tools = make_enabled_tools()

        with caplog.at_level(logging.ERROR):
            with pytest.raises(ValueError, match='Missing required field'):
                await execute_tool('TestTool', {}, enabled_tools)

        error_records = [
            r
            for r in caplog.records
            if hasattr(r, 'event_type') and r.event_type == 'tool_execution'
        ]
        assert len(error_records) == 1
        assert error_records[0].status == 'error'
        assert error_records[0].error_type == 'ValidationError'

    @pytest.mark.asyncio
    @patch('tools.tool_params.validate_args_for_mode')
    async def test_duration_ms_is_populated(self, mock_validate, caplog):
        mock_validate.return_value = Mock()
        enabled_tools = make_enabled_tools()

        with caplog.at_level(logging.INFO):
            await execute_tool('TestTool', {}, enabled_tools)

        records = [r for r in caplog.records if hasattr(r, 'duration_ms')]
        assert len(records) == 1
        assert records[0].duration_ms >= 0

    @pytest.mark.asyncio
    @patch('tools.tool_params.validate_args_for_mode')
    async def test_tool_key_logged(self, mock_validate, caplog):
        mock_validate.return_value = Mock()
        enabled_tools = make_enabled_tools(
            tool_key='SearchIndexTool', display_name='SearchIndexTool'
        )

        with caplog.at_level(logging.INFO):
            await execute_tool('SearchIndexTool', {}, enabled_tools)

        records = [r for r in caplog.records if hasattr(r, 'tool_key')]
        assert len(records) == 1
        assert records[0].tool_key == 'SearchIndexTool'

    @pytest.mark.asyncio
    @patch('tools.tool_params.validate_args_for_mode')
    async def test_client_name_field_logged_from_contextvar(self, mock_validate, caplog):
        """The 'client_name' field in the log reflects the client_name_var contextvar."""
        mock_validate.return_value = Mock()
        enabled_tools = make_enabled_tools()

        # Simulate middleware having set the client name
        token = client_name_var.set('test-agent')
        try:
            with caplog.at_level(logging.INFO):
                await execute_tool('TestTool', {}, enabled_tools)
        finally:
            client_name_var.reset(token)

        records = [
            r
            for r in caplog.records
            if hasattr(r, 'event_type') and r.event_type == 'tool_execution'
        ]
        assert len(records) == 1
        assert records[0].client_name == 'test-agent'

    @pytest.mark.asyncio
    @patch('tools.tool_params.validate_args_for_mode')
    async def test_client_name_defaults_to_unknown(self, mock_validate, caplog):
        """Without middleware, client name defaults to 'unknown'."""
        mock_validate.return_value = Mock()
        enabled_tools = make_enabled_tools()

        with caplog.at_level(logging.INFO):
            await execute_tool('TestTool', {}, enabled_tools)

        records = [
            r
            for r in caplog.records
            if hasattr(r, 'event_type') and r.event_type == 'tool_execution'
        ]
        assert len(records) == 1
        assert records[0].client_name == 'unknown'
