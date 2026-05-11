"""Lightweight tool registration and execution system."""

from __future__ import annotations

import inspect
import json
from typing import Any, Callable


class Tool:
    """A registered tool that the LLM can invoke."""

    def __init__(self, fn: Callable, name: str, description: str, parameters: dict[str, Any]):
        self.fn = fn
        self.name = name
        self.description = description
        self.parameters = parameters

    def to_openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def run(self, arguments: dict[str, Any]) -> str:
        result = self.fn(**arguments)
        if not isinstance(result, str):
            result = json.dumps(result, ensure_ascii=False)
        return result

    def get_source_code(self) -> str | None:
        """Get the source code of the tool function.

        Returns:
            Source code string, or None if unavailable
        """
        try:
            return inspect.getsource(self.fn)
        except (OSError, TypeError):
            return None


class ToolRegistry:
    """Registry of tools available to the LLM."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def get_source_code(self, name: str) -> str | None:
        """Get source code of a registered tool.

        Args:
            name: Tool name

        Returns:
            Source code string, or None if tool not found or unavailable
        """
        tool = self.get(name)
        if tool:
            return tool.get_source_code()
        return None

    def list_tools(self) -> list[dict[str, Any]]:
        return [t.to_openai_tool() for t in self._tools.values()]

    def dispatch(self, name: str, arguments: dict[str, Any]) -> str:
        tool = self.get(name)
        if tool is None:
            return json.dumps({"error": f"Unknown tool: {name}"}, ensure_ascii=False)
        return tool.run(arguments)


# ---- Convenience registry ----
_default_registry = ToolRegistry()


def tool(
    *,
    name: str | None = None,
    description: str = "",
    parameters: dict[str, Any] | None = None,
) -> Callable:
    """Decorator that registers a function as a tool.

    Usage:
        @tool(description="Add two numbers", parameters={...})
        def add(a: int, b: int) -> int:
            return a + b
    """
    def decorator(fn: Callable) -> Callable:
        tool_name = name or fn.__name__
        sig = inspect.signature(fn)
        params = parameters or _infer_parameters(sig)
        t = Tool(fn=fn, name=tool_name, description=description, parameters=params)
        _default_registry.register(t)
        return fn
    return decorator


def _infer_parameters(sig: inspect.Signature) -> dict[str, Any]:
    """Naively infer a JSON Schema from type hints (simple types only)."""
    json_type_map = {str: "string", int: "integer", float: "number", bool: "boolean"}
    properties = {}
    required = []
    for name, param in sig.parameters.items():
        if param.annotation is inspect.Parameter.empty:
            continue
        hint = param.annotation
        json_type = json_type_map.get(hint, "string")
        properties[name] = {"type": json_type, "description": f"Parameter {name}"}
        if param.default is inspect.Parameter.empty:
            required.append(name)
    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


def get_default_registry() -> ToolRegistry:
    return _default_registry


class UnifiedToolRegistry:
    """Combined registry for local tools and MCP tools.

    Provides async dispatch that routes to either local tools
    (synchronous) or MCP tools (async).
    """

    def __init__(self, local_registry: ToolRegistry, mcp_manager: Any = None):
        self._local_registry = local_registry
        self._mcp_manager = mcp_manager

    def list_tools(self) -> list[dict[str, Any]]:
        """Return combined list of local and MCP tools."""
        tools = self._local_registry.list_tools()
        if self._mcp_manager:
            tools.extend(self._mcp_manager.list_tools())
        return tools

    def get_source_code(self, name: str) -> str | None:
        """Get source code of a local tool.

        Note: MCP tools cannot have source code extracted.

        Args:
            name: Tool name

        Returns:
            Source code string, or None if not available
        """
        if self.is_mcp_tool(name):
            return None
        return self._local_registry.get_source_code(name)

    async def dispatch(self, name: str, arguments: dict[str, Any]) -> str:
        """Dispatch tool call to local or MCP handler.

        Args:
            name: Tool name (may be prefixed with server name for MCP)
            arguments: Tool arguments

        Returns:
            Tool result as string
        """
        # Try local tools first (synchronous)
        local_tool = self._local_registry.get(name)
        if local_tool:
            return local_tool.run(arguments)

        # Try MCP tools (async)
        if self._mcp_manager and self._mcp_manager.is_tool_available(name):
            return await self._mcp_manager.call_tool(name, arguments)

        # Unknown tool
        return json.dumps({"error": f"Unknown tool: {name}"}, ensure_ascii=False)

    def is_mcp_tool(self, name: str) -> bool:
        """Check if a tool is from MCP."""
        if self._mcp_manager:
            return self._mcp_manager.is_tool_available(name)
        return False

    def get_mcp_tool_names(self) -> list[str]:
        """Return names of available MCP tools."""
        if self._mcp_manager:
            return self._mcp_manager.get_tool_names()
        return []
