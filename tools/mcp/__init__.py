"""MCP Tool Manager - manages multiple MCP server instances.

Provides a unified interface to start/stop MCP servers and
route tool calls to the appropriate server.
"""

from __future__ import annotations

import logging
from typing import Any

from tools.mcp.config import MCPConfig
from tools.mcp.exceptions import MCPServerError, MCPToolError
from tools.mcp.server import MCPServer, MCPServerConfig
from tools.mcp.tools import MCPTool

logger = logging.getLogger(__name__)


class MCPToolManager:
    """Manages multiple MCP server instances and their tools."""

    def __init__(self):
        self._servers: dict[str, MCPServer] = {}
        self._tools: dict[str, MCPTool] = {}  # prefixed_name -> MCPTool

    async def initialize(self, config: MCPConfig) -> None:
        """Start all configured MCP servers.

        Args:
            config: MCPConfig with server configurations
        """
        if not config.enabled:
            logger.info("MCP is disabled globally")
            return

        for server_config in config.get_enabled_servers():
            try:
                server = MCPServer(server_config)
                await server.start()

                self._servers[server_config.name] = server

                # Register tools
                for tool in server.list_tools():
                    self._tools[tool.name] = tool

            except Exception as e:
                logger.error(f"Failed to start MCP server '{server_config.name}': {e}")
                # Continue with other servers

        logger.info(f"MCP initialized: {len(self._servers)} servers, {len(self._tools)} tools")

    async def shutdown(self) -> None:
        """Stop all MCP servers."""
        for name, server in self._servers.items():
            try:
                await server.stop()
            except Exception as e:
                logger.warning(f"Error stopping MCP server '{name}': {e}")

        self._servers.clear()
        self._tools.clear()
        logger.info("MCP shutdown complete")

    def list_tools(self) -> list[dict[str, Any]]:
        """Return all MCP tools in OpenAI format.

        Returns:
            List of OpenAI-compatible tool definitions
        """
        return [tool.to_openai_tool() for tool in self._tools.values()]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """Call an MCP tool by its prefixed name.

        Args:
            name: Prefixed tool name (e.g., "filesystem.read_file")
            arguments: Tool arguments

        Returns:
            Tool result as string

        Raises:
            MCPToolError: If tool execution fails
            MCPServerError: If server not found
        """
        tool = self._tools.get(name)
        if tool is None:
            raise MCPServerError(f"Unknown MCP tool: {name}")

        server = self._servers.get(tool.server_name)
        if server is None:
            raise MCPServerError(f"MCP server '{tool.server_name}' not running")

        try:
            result = await server.call_tool(tool.original_name, arguments)
            return result
        except MCPToolError:
            raise
        except Exception as e:
            raise MCPToolError(tool_name=name, message=str(e)) from e

    def get_server_names(self) -> list[str]:
        """Return names of all running servers."""
        return list(self._servers.keys())

    def get_tool_names(self) -> list[str]:
        """Return names of all available MCP tools."""
        return list(self._tools.keys())

    def is_tool_available(self, name: str) -> bool:
        """Check if a tool is available."""
        return name in self._tools

    def get_running_servers(self) -> int:
        """Return count of running servers."""
        return len([s for s in self._servers.values() if s.is_running])


# Convenience function for simple usage
async def create_mcp_manager(config_path: str | None = None) -> MCPToolManager:
    """Create and initialize MCP manager from config.

    Args:
        config_path: Optional path to config file

    Returns:
        Initialized MCPToolManager
    """
    config = MCPConfig.load(config_path)
    manager = MCPToolManager()
    await manager.initialize(config)
    return manager