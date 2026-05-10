"""MCP Tool wrapper - converts MCP tool schema to OpenAI format."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class MCPTool:
    """Represents a tool from an MCP server.

    Tool names are prefixed with server name to avoid collisions
    between different MCP servers.
    """
    name: str  # Prefixed name: "server.tool_name"
    original_name: str  # Original name without prefix
    description: str
    input_schema: dict[str, Any]  # JSON Schema for input
    server_name: str  # Name of the MCP server providing this tool

    def to_openai_tool(self) -> dict[str, Any]:
        """Convert to OpenAI-compatible tool definition.

        Returns:
            OpenAI tool format:
            {
                "type": "function",
                "function": {
                    "name": "server.tool_name",
                    "description": "...",
                    "parameters": {...}  # inputSchema
                }
            }
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }

    def get_original_name(self) -> str:
        """Get the tool name without server prefix."""
        return self.original_name

    def __repr__(self) -> str:
        return f"MCPTool(name={self.name}, server={self.server_name})"