"""Async stdin/stdout transport for MCP stdio communication.

Handles subprocess lifecycle and message I/O.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator

from tools.mcp.exceptions import MCPConnectionError
from tools.mcp.protocol import (
    JSONRPCRequest,
    JSONRPCResponse,
    JSONRPCNotification,
    parse_message,
)

logger = logging.getLogger(__name__)

# Environment variables to inherit by default
DEFAULT_INHERITED_ENV_VARS = (
    ["HOME", "LOGNAME", "PATH", "SHELL", "TERM", "USER"]
    if sys.platform != "win32"
    else ["APPDATA", "HOMEDRIVE", "HOMEPATH", "LOCALAPPDATA", "PATH", "TEMP", "USERPROFILE"]
)


def get_default_environment() -> dict[str, str]:
    """Return minimal safe environment for subprocess."""
    env: dict[str, str] = {}
    for key in DEFAULT_INHERITED_ENV_VARS:
        value = os.environ.get(key)
        if value and not value.startswith("()"):  # Skip shell functions
            env[key] = value
    return env


class MCPStdioTransport:
    """Async transport for MCP stdio communication."""

    def __init__(
        self,
        command: str,
        args: list[str],
        env: dict[str, str] | None = None,
        cwd: Path | str | None = None,
    ):
        self.command = command
        self.args = args
        self.env = env or get_default_environment()
        self.cwd = cwd

        self._process: asyncio.subprocess.Process | None = None
        self._pending_requests: dict[int | str, asyncio.Future[JSONRPCResponse]] = {}
        self._next_id: int = 0
        self._read_task: asyncio.Task | None = None
        self._started: bool = False

    async def start(self) -> None:
        """Start the subprocess and begin reading stdout."""
        if self._started:
            return

        try:
            self._process = await asyncio.create_subprocess_exec(
                self.command,
                *self.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self.env,
                cwd=self.cwd,
                start_new_session=True,  # Separate process group for clean termination
            )

            # Start background reader task
            self._read_task = asyncio.create_task(self._read_loop())
            self._started = True
            logger.info(f"Started MCP server: {self.command} {self.args}")

        except Exception as e:
            raise MCPConnectionError(f"Failed to start subprocess: {e}") from e

    async def stop(self) -> None:
        """Stop the subprocess gracefully."""
        if not self._started or self._process is None:
            return

        # Cancel read task
        if self._read_task:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass

        # Close stdin to signal shutdown
        if self._process.stdin:
            self._process.stdin.close()
            try:
                await self._process.stdin.wait_closed()
            except Exception:
                pass

        # Wait for process to exit (with timeout)
        try:
            await asyncio.wait_for(self._process.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            # Force kill if not exited
            try:
                self._process.kill()
                await self._process.wait()
            except ProcessLookupError:
                pass

        self._started = False
        self._process = None
        logger.info(f"Stopped MCP server: {self.command}")

    async def send_request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> JSONRPCResponse:
        """Send a JSON-RPC request and wait for response."""
        if not self._started or self._process is None or self._process.stdin is None:
            raise MCPConnectionError("Transport not started")

        request_id = self._next_id
        self._next_id += 1

        request = JSONRPCRequest(id=request_id, method=method, params=params)
        json_line = request.to_json() + "\n"

        # Create future for response
        future: asyncio.Future[JSONRPCResponse] = asyncio.get_event_loop().create_future()
        self._pending_requests[request_id] = future

        try:
            # Send request
            self._process.stdin.write(json_line.encode("utf-8"))
            await self._process.stdin.drain()

            # Wait for response with timeout
            response = await asyncio.wait_for(future, timeout=timeout)
            return response

        except asyncio.TimeoutError:
            self._pending_requests.pop(request_id, None)
            raise MCPConnectionError(f"Request {method} timed out after {timeout}s")

        except Exception as e:
            self._pending_requests.pop(request_id, None)
            raise MCPConnectionError(f"Failed to send request: {e}") from e

    async def send_notification(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        if not self._started or self._process is None or self._process.stdin is None:
            raise MCPConnectionError("Transport not started")

        notification = JSONRPCNotification(method=method, params=params)
        json_line = notification.to_json() + "\n"

        self._process.stdin.write(json_line.encode("utf-8"))
        await self._process.stdin.drain()

    async def _read_loop(self) -> None:
        """Background task to read stdout and route responses."""
        if self._process is None or self._process.stdout is None:
            return

        try:
            while True:
                line = await self._process.stdout.readline()
                if not line:
                    break  # EOF

                line_str = line.decode("utf-8").strip()
                if not line_str:
                    continue

                try:
                    message = parse_message(line_str)

                    if isinstance(message, JSONRPCResponse):
                        # Route response to waiting request
                        future = self._pending_requests.pop(message.id, None)
                        if future and not future.done():
                            future.set_result(message)
                        else:
                            logger.warning(f"Received response for unknown request: {message.id}")

                    elif isinstance(message, JSONRPCNotification):
                        # Log notifications (logging, etc.)
                        logger.debug(f"MCP notification: {message.method}")

                except json.JSONDecodeError as e:
                    logger.warning(f"Invalid JSON from MCP server: {e}")

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Read loop error: {e}")

    @property
    def is_running(self) -> bool:
        return self._started and self._process is not None and self._process.returncode is None

    async def read_stderr(self) -> str:
        """Read any accumulated stderr output (for debugging)."""
        if self._process and self._process.stderr:
            # Non-blocking read of available stderr
            try:
                data = await asyncio.wait_for(self._process.stderr.read(), timeout=0.1)
                return data.decode("utf-8")
            except asyncio.TimeoutError:
                return ""
        return ""


@asynccontextmanager
async def mcp_stdio_client(
    command: str,
    args: list[str],
    env: dict[str, str] | None = None,
    cwd: Path | str | None = None,
) -> AsyncGenerator[MCPStdioTransport, None]:
    """Context manager for MCP stdio transport."""
    transport = MCPStdioTransport(command, args, env, cwd)
    await transport.start()
    try:
        yield transport
    finally:
        await transport.stop()