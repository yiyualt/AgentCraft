"""Utility tools: current_time, calculator."""

from __future__ import annotations

import math

from tools import tool


@tool(description="Get the current date and time")
def current_time() -> str:
    import datetime
    now = datetime.datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S")


@tool(
    name="calculator",
    description="Evaluate a mathematical expression. Use Python arithmetic syntax.",
    parameters={
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "A mathematical expression, e.g. '2 + 2' or 'sqrt(144)'",
            }
        },
        "required": ["expression"],
    },
)
def calculator(expression: str) -> str:
    allowed_names = {k: v for k, v in math.__dict__.items() if not k.startswith("_")}
    allowed_names.update({"abs": abs, "round": round, "min": min, "max": max})
    try:
        result = eval(expression, {"__builtins__": {}}, allowed_names)
        return str(result)
    except Exception as e:
        return f"Error: {e}"


__all__ = ["current_time", "calculator"]