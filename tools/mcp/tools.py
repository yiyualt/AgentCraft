"""MCP Tool wrapper - converts MCP tool schema to OpenAI format.

Note: MCP tool names are prefixed with server name using '__' (double underscore)
to comply with OpenAI's naming pattern: ^[a-zA-Z0-9_-]+$
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class MCPTool:
    """Represents a tool from an MCP server.

    Tool names are prefixed with server name using '__' to avoid collisions
    between different MCP servers and comply with OpenAI naming pattern.
    """
    name: str  # Prefixed name: "server__tool_name" (uses __ instead of .)
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
                    "name": "server__tool_name",
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