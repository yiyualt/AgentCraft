"""Concurrency safety classification for tool execution.

Simple rules:
- SAFE tools (read-only): can run in parallel
- UNSAFE tools (write/side-effect): must run sequentially
"""

from __future__ import annotations


# Read-only tools - safe to run in parallel
SAFE_TOOLS = frozenset({
    "Read", "Glob", "Grep", "WebFetch", "WebSearch",
    "CountTokens", "NotebookEdit",
    # MCP sentiment tools (read-only)
    "sentiment__sentiment_classify", "sentiment__sentiment_batch", "sentiment__sentiment_keywords",
})

# Write/side-effect tools - must run sequentially
UNSAFE_TOOLS = frozenset({
    "Write", "Edit", "Bash",
    "Agent", "Skill",
})


def is_safe(tool_name: str) -> bool:
    """Check if a tool can run in parallel with others.

    Args:
        tool_name: Name of the tool

    Returns:
        True if safe for parallel execution
    """
    if tool_name in SAFE_TOOLS:
        return True
    if tool_name in UNSAFE_TOOLS:
        return False
    # Unknown tools: default to unsafe (fail-closed)
    return False


__all__ = ["is_safe", "SAFE_TOOLS", "UNSAFE_TOOLS"]