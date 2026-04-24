# Copyright OpenSearch Contributors
# SPDX-License-Identifier: Apache-2.0

import asyncio
import logging
import os
import signal
import socket
import subprocess
import sys


logger = logging.getLogger(__name__)


def _find_free_port() -> int:
    """Find a free port by binding to port 0 and reading back the assigned port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class MCPServerProcess:
    """Manages an MCP server subprocess for integration testing."""

    def __init__(
        self,
        env: dict,
        transport: str = 'stream',
        port: int | None = None,
        extra_args: list[str] | None = None,
        mode: str = 'single',
        config_file: str | None = None,
        profile: str | None = None,
    ):
        self.env = env
        self.transport = transport
        self.port = port or _find_free_port()
        self.extra_args = extra_args or []
        self.mode = mode
        self.config_file = config_file
        self.profile = profile
        self._process: subprocess.Popen | None = None

    @property
    def url(self) -> str:
        return f'http://127.0.0.1:{self.port}/mcp'

    @property
    def health_url(self) -> str:
        return f'http://127.0.0.1:{self.port}/health'

    async def start(self, timeout: float = 30.0) -> None:
        """Start the MCP server subprocess and wait until it is ready."""
        cmd = [
            sys.executable,
            '-m',
            'mcp_server_opensearch',
            '--transport',
            self.transport,
            '--port',
            str(self.port),
            '--host',
            '127.0.0.1',
            '--mode',
            self.mode,
        ]

        if self.config_file:
            cmd.extend(['--config', self.config_file])

        if self.profile:
            cmd.extend(['--profile', self.profile])

        cmd.extend(self.extra_args)

        # Build process environment: inherit current env, overlay test-specific vars
        proc_env = os.environ.copy()
        # Clear potentially conflicting vars so each server is isolated
        for key in list(proc_env.keys()):
            if key.startswith(('OPENSEARCH_', 'AWS_')):
                del proc_env[key]
        proc_env.update(self.env)

        logger.info(f'Starting MCP server on port {self.port}: {" ".join(cmd)}')
        self._process = subprocess.Popen(
            cmd,
            env=proc_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Wait for the server to become ready
        await self._wait_for_ready(timeout)
        logger.info(f'MCP server ready on port {self.port} (pid={self._process.pid})')

    async def _wait_for_ready(self, timeout: float) -> None:
        """Poll the health endpoint until the server responds or timeout."""
        import aiohttp

        deadline = asyncio.get_event_loop().time() + timeout
        last_error = None

        while asyncio.get_event_loop().time() < deadline:
            # Check if process died
            if self._process and self._process.poll() is not None:
                raise RuntimeError(
                    f'MCP server exited with code {self._process.returncode}'
                )

            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        self.health_url, timeout=aiohttp.ClientTimeout(total=2)
                    ) as resp:
                        if resp.status == 200:
                            return
            except Exception as e:
                last_error = e

            await asyncio.sleep(0.5)

        raise TimeoutError(
            f'MCP server on port {self.port} did not become ready within {timeout}s. '
            f'Last error: {last_error}'
        )

    async def stop(self) -> None:
        """Stop the server subprocess gracefully, then force kill if needed."""
        if self._process is None:
            return

        logger.info(f'Stopping MCP server on port {self.port} (pid={self._process.pid})')

        try:
            if sys.platform == 'win32':
                self._process.terminate()
            else:
                self._process.send_signal(signal.SIGTERM)
            # Wait up to 5 seconds for graceful shutdown
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning(f'Server on port {self.port} did not stop gracefully, killing')
                self._process.kill()
                self._process.wait(timeout=5)
        except ProcessLookupError:
            pass  # Already dead
        finally:
            self._process = None
