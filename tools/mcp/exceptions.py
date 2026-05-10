"""MCP-specific exception types."""

from __future__ import annotations


class MCPError(Exception):
    """Base exception for MCP-related errors."""
    pass


class MCPServerError(MCPError):
    """Error related to MCP server configuration or lifecycle."""
    pass


class MCPConnectionError(MCPError):
    """Error related to MCP server connection/communication."""
    pass


class MCPToolError(MCPError):
    """Error returned by an MCP tool execution."""
    def __init__(self, tool_name: str, message: str):
        self.tool_name = tool_name
        super().__init__(f"Tool '{tool_name}' error: {message}")


class MCPProtocolError(MCPError):
    """Error in MCP JSON-RPC protocol handling."""
    def __init__(self, code: int | None = None, message: str = ""):
        self.code = code
        super().__init__(f"Protocol error (code={code}): {message}")