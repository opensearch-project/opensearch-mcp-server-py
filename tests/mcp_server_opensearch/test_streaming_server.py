# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import pytest
import pytest_asyncio
from mcp.types import TextContent
from unittest.mock import ANY, AsyncMock, Mock, patch


@pytest.fixture(autouse=True)
def patch_opensearch_version():
    """Mock OpenSearch client and version check."""
    from semver import Version
    from unittest.mock import AsyncMock

    mock_client = Mock()
    mock_client.info = AsyncMock(return_value={'version': {'number': '3.0.0'}})

    async def mock_get_version(*args, **kwargs):
        return Version.parse('2.9.0')

    with (
        patch('opensearch.helper.get_opensearch_version', side_effect=mock_get_version),
        patch('opensearch.client.initialize_client', return_value=mock_client),
        patch('mcp_server_opensearch.global_state.get_mode', return_value='single'),
    ):
        yield


class TestMCPServer:
    @pytest.fixture
    def mock_tool_registry(self):
        """Provides a mock tool registry for testing."""
        return {
            'test-tool': {
                'description': 'Test tool',
                'input_schema': {'type': 'object'},
                'args_model': Mock(),
                'function': AsyncMock(return_value=[TextContent(type='text', text='test result')]),
            }
        }

    @pytest.mark.asyncio
    @patch('mcp_server_opensearch.streaming_server.apply_custom_tool_config')
    @patch('mcp_server_opensearch.streaming_server.get_tools')
    @patch('mcp_server_opensearch.streaming_server.generate_tools_from_openapi')
    @patch('mcp_server_opensearch.streaming_server.load_clusters_from_yaml')
    async def test_create_mcp_server(
        self,
        mock_load_clusters,
        mock_generate_tools,
        mock_get_tools,
        mock_apply_config,
        mock_tool_registry,
    ):
        """Test MCP server creation."""
        # Setup mocks
        mock_get_tools.return_value = mock_tool_registry
        mock_apply_config.return_value = mock_tool_registry  # Assume no changes for this test
        mock_generate_tools.return_value = None
        mock_load_clusters.return_value = None

        # Create server
        from mcp_server_opensearch.streaming_server import create_mcp_server

        server = await create_mcp_server(
            mode='single', config_file_path='some/path', cli_tool_overrides={'key': 'val'}
        )

        assert server.name == 'opensearch-mcp-server'
        mock_generate_tools.assert_called_once()
        mock_apply_config.assert_called_once_with(ANY, 'some/path', {'key': 'val'})
        mock_get_tools.assert_called_once_with(
            tool_registry=mock_tool_registry,
            config_file_path='some/path',
        )

    @pytest.mark.asyncio
    @patch('mcp_server_opensearch.streaming_server.get_tools')
    @patch('mcp_server_opensearch.streaming_server.generate_tools_from_openapi')
    @patch('mcp_server_opensearch.streaming_server.load_clusters_from_yaml')
    async def test_list_tools(
        self, mock_load_clusters, mock_generate_tools, mock_get_tools, mock_tool_registry
    ):
        """Test listing available tools."""
        # Setup mocks
        mock_get_tools.return_value = mock_tool_registry
        mock_generate_tools.return_value = None
        mock_load_clusters.return_value = None

        # Create server
        from mcp.types import Tool
        from mcp_server_opensearch.streaming_server import create_mcp_server

        await create_mcp_server()

        # Get the tools by calling the decorated function
        tools = []
        for tool_name, tool_info in mock_get_tools.return_value.items():
            tools.append(
                Tool(
                    name=tool_name,
                    description=tool_info['description'],
                    inputSchema=tool_info['input_schema'],
                )
            )

        assert len(tools) == 1
        assert tools[0].name == 'test-tool'
        assert tools[0].description == 'Test tool'
        assert tools[0].inputSchema == {'type': 'object'}

    @pytest.mark.asyncio
    @patch('mcp_server_opensearch.streaming_server.get_tools')
    @patch('mcp_server_opensearch.streaming_server.generate_tools_from_openapi')
    @patch('mcp_server_opensearch.streaming_server.load_clusters_from_yaml')
    async def test_call_tool(
        self, mock_load_clusters, mock_generate_tools, mock_get_tools, mock_tool_registry
    ):
        """Test calling the tool."""
        # Setup mocks
        mock_get_tools.return_value = mock_tool_registry
        mock_generate_tools.return_value = None
        mock_load_clusters.return_value = None
        mock_tool_registry['test-tool']['function'].return_value = [
            TextContent(type='text', text='result')
        ]

        # Create server and mock the call_tool decorator
        mock_call_tool = AsyncMock()
        mock_call_tool.return_value = [TextContent(type='text', text='result')]

        # Test the decorated function
        result = await mock_call_tool('test-tool', {'param': 'value'})

        assert len(result) == 1
        assert isinstance(result[0], TextContent)
        assert result[0].text == 'result'


class TestMCPStarletteApp:
    @pytest_asyncio.fixture
    async def app_handler(self):
        """Provides an MCPStarletteApp instance for testing."""
        from mcp_server_opensearch.streaming_server import MCPStarletteApp, create_mcp_server

        # Mock dependencies
        with (
            patch(
                'mcp_server_opensearch.streaming_server.get_tools',
                new_callable=AsyncMock,
                return_value={},
            ),
            patch(
                'mcp_server_opensearch.streaming_server.generate_tools_from_openapi',
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                'mcp_server_opensearch.streaming_server.load_clusters_from_yaml',
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            server = await create_mcp_server()
            return MCPStarletteApp(server)

    def test_create_app(self, app_handler):
        """Test Starlette application creation and configuration."""
        from starlette.routing import Mount, Route

        app = app_handler.create_app()
        assert len(app.routes) == 5

        # Check routes
        assert app.routes[0].path == '/sse'
        assert app.routes[1].path == '/health'
        assert app.routes[2].path == '/messages'
        # Bare '/mcp' is a Route (served directly, no 307); sub-paths go through the Mount.
        assert app.routes[3].path == '/mcp' and isinstance(app.routes[3], Route)
        assert app.routes[4].path == '/mcp' and isinstance(app.routes[4], Mount)

    @pytest.mark.asyncio
    async def test_mcp_endpoint_no_redirect(self, app_handler):
        """Bare '/mcp' is served directly without a 307 redirect to '/mcp/' (issue #271)."""
        from starlette.responses import PlainTextResponse
        from starlette.testclient import TestClient

        async def fake_handle_request(scope, receive, send):
            await PlainTextResponse('ok')(scope, receive, send)

        app_handler.session_manager.handle_request = fake_handle_request
        app = app_handler.create_app()
        app.router.lifespan_context = None  # skip the real session manager startup
        client = TestClient(app)

        for method in ('GET', 'POST', 'DELETE'):
            response = client.request(method, '/mcp', follow_redirects=False)
            assert response.status_code == 200
            assert response.headers.get('location') is None

    @pytest.mark.asyncio
    async def test_handle_sse(self, app_handler):
        """Test SSE connection handling."""
        mock_request = Mock()

        # Mock SSE connection context
        mock_read_stream = AsyncMock()
        mock_write_stream = AsyncMock()

        # Create a proper async context manager mock
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = (mock_read_stream, mock_write_stream)
        mock_context.__aexit__.return_value = None

        # Set up the connect_sse mock to return our context manager
        app_handler.sse.connect_sse = Mock(return_value=mock_context)

        # Mock the server run method to return immediately
        app_handler.mcp_server.run = AsyncMock()
        app_handler.mcp_server.create_initialization_options = Mock(return_value={})

        # Add a side effect to make run return immediately
        app_handler.mcp_server.run.return_value = None

        await app_handler.handle_sse(mock_request)

        # Verify SSE connection was established
        app_handler.sse.connect_sse.assert_called_once_with(
            mock_request.scope, mock_request.receive, mock_request._send
        )

        # Verify context manager was used
        mock_context.__aenter__.assert_called_once()
        mock_context.__aexit__.assert_called_once()

        # Verify server.run was called with correct arguments
        app_handler.mcp_server.run.assert_called_once_with(mock_read_stream, mock_write_stream, {})


@pytest.mark.asyncio
async def test_serve():
    """Test server startup and configuration."""
    from mcp_server_opensearch.streaming_server import serve

    # Mock uvicorn server
    mock_server = AsyncMock()
    mock_config = Mock()

    with (
        patch('uvicorn.Server', return_value=mock_server) as mock_server_class,
        patch('uvicorn.Config', return_value=mock_config) as mock_config_class,
        patch('mcp_server_opensearch.streaming_server.get_tools', return_value={}),
        patch(
            'mcp_server_opensearch.streaming_server.generate_tools_from_openapi', return_value=None
        ),
        patch('mcp_server_opensearch.streaming_server.load_clusters_from_yaml', return_value=None),
    ):
        await serve(host='localhost', port=8000)

        # Verify config
        mock_config_class.assert_called_once()
        config_args = mock_config_class.call_args[1]
        assert config_args['host'] == 'localhost'
        assert config_args['port'] == 8000

        # Verify server started
        mock_server_class.assert_called_once_with(mock_config)
        mock_server.serve.assert_called_once()
