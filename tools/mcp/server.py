"""MCP Server wrapper - manages lifecycle and tool calls."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.mcp.exceptions import MCPServerError, MCPToolError
from tools.mcp.protocol import (
    MCPInitializeParams,
    MCPInitializeResult,
    JSONRPCResponse,
)
from tools.mcp.transport import MCPStdioTransport
from tools.mcp.tools import MCPTool

logger = logging.getLogger(__name__)


@dataclass
class MCPServerConfig:
    """Configuration for a single MCP server."""
    name: str
    command: str
    args: list[str]
    env: dict[str, str] | None = None
    cwd: Path | str | None = None
    enabled: bool = True


class MCPServer:
    """Manages a single MCP server instance."""

    def __init__(self, config: MCPServerConfig):
        self.config = config
        self._transport: MCPStdioTransport | None = None
        self._initialized: bool = False
        self._tools: list[MCPTool] = []
        self._server_info: dict[str, str] = {}

    async def start(self) -> None:
        """Start the MCP server and perform initialization handshake."""
        if not self.config.enabled:
            logger.info(f"MCP server '{self.config.name}' is disabled, skipping")
            return

        self._transport = MCPStdioTransport(
            command=self.config.command,
            args=self.config.args,
            env=self.config.env,
            cwd=self.config.cwd,
        )

        await self._transport.start()

        # Perform MCP initialization handshake
        await self._initialize()

        # Fetch available tools
        await self._fetch_tools()

        self._initialized = True
        logger.info(
            f"MCP server '{self.config.name}' initialized with {len(self._tools)} tools"
        )

    async def stop(self) -> None:
        """Stop the MCP server."""
        if self._transport:
            await self._transport.stop()
        self._initialized = False
        self._tools = []

    async def _initialize(self) -> MCPInitializeResult:
        """Perform MCP initialization handshake."""
        if self._transport is None:
            raise MCPServerError("Transport not started")

        # Send initialize request
        params = MCPInitializeParams()
        response = await self._transport.send_request(
            "initialize",
            {
                "protocolVersion": params.protocol_version,
                "clientInfo": params.client_info,
                "capabilities": params.capabilities,
            },
        )
        response.raise_if_error()

        result = MCPInitializeResult.from_dict(response.result or {})
        self._server_info = result.server_info

        # Send initialized notification
        await self._transport.send_notification("notifications/initialized")

        return result

    async def _fetch_tools(self) -> None:
        """Fetch list of available tools from the server."""
        if self._transport is None:
            raise MCPServerError("Transport not started")

        response = await self._transport.send_request("tools/list", {})
        response.raise_if_error()

        tools_data = (response.result or {}).get("tools", [])
        self._tools = []

        for tool_data in tools_data:
            # Prefix tool name with server name to avoid collisions
            prefixed_name = f"{self.config.name}.{tool_data.get('name', '')}"
            tool = MCPTool(
                name=prefixed_name,
                original_name=tool_data.get("name", ""),
                description=tool_data.get("description", ""),
                input_schema=tool_data.get("inputSchema", {}),
                server_name=self.config.name,
            )
            self._tools.append(tool)

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """Call a tool on this MCP server.

        Args:
            name: Original tool name (without prefix)
            arguments: Tool arguments

        Returns:
            Tool result as string
        """
        if not self._initialized or self._transport is None:
            raise MCPServerError(f"Server '{self.config.name}' not initialized")

        response = await self._transport.send_request(
            "tools/call",
            {"name": name, "arguments": arguments},
        )

        if response.is_error():
            error_msg = response.error.get("message", "Unknown error") if response.error else "Unknown error"
            raise MCPToolError(tool_name=name, message=error_msg)

        # Extract content from result
        result = response.result or {}
        content = result.get("content", [])

        # Format content as string
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        parts.append(item.get("text", ""))
                    else:
                        parts.append(str(item))
                else:
                    parts.append(str(item))
            return "\n".join(parts)

        return str(content)

    def list_tools(self) -> list[MCPTool]:
        """Return list of available tools."""
        return self._tools.copy()

    @property
    def is_running(self) -> bool:
        return self._initialized and self._transport is not None and self._transport.is_running

    @property
    def server_info(self) -> dict[str, str]:
        return self._server_info.copy()