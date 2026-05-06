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


class ToolRegistry:
    """Registry of tools available to the LLM."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

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
