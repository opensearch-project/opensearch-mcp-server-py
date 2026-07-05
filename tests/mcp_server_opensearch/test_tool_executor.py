# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import logging
import pytest
from mcp.types import CallToolResult
from mcp_server_opensearch.tool_executor import execute_tool
from unittest.mock import AsyncMock, Mock, patch


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
        assert result.isError is False
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
        assert result.isError is True
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
