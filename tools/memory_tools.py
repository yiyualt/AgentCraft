"""Memory tools for AgentCraft - remember/forget/recall operations."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from tools import tool
from sessions.memory_persistence import MemoryStore, MemoryEntry, MemoryType


# Global memory store (initialized with project path)
_memory_store: MemoryStore | None = None


def get_memory_store() -> MemoryStore:
    """Get or create memory store for current project."""
    global _memory_store
    if _memory_store is None:
        # Use current working directory as project path
        project_path = os.getcwd()
        _memory_store = MemoryStore(project_path)
    return _memory_store


def set_memory_store(store: MemoryStore) -> None:
    """Set memory store (for gateway initialization)."""
    global _memory_store
    _memory_store = store


def _infer_memory_type(content: str) -> MemoryType:
    """Infer memory type from content heuristics."""
    content_lower = content.lower()

    # Feedback indicators
    if any(kw in content_lower for kw in ["don't", "do not", "never", "always", "stop", "avoid", "keep", "prefer"]):
        return MemoryType.FEEDBACK

    # User indicators
    if any(kw in content_lower for kw in ["i'm", "i am", "my", "i work", "i have", "i know", "senior", "junior", "engineer", "developer"]):
        return MemoryType.USER

    # Project indicators
    if any(kw in content_lower for kw in ["project", "deadline", "stakeholder", "compliance", "legal", "freeze", "release", "team"]):
        return MemoryType.PROJECT

    # Default to project for general context
    return MemoryType.PROJECT


def _build_memory_content(content: str, memory_type: MemoryType) -> str:
    """Build full memory content with structure."""
    if memory_type == MemoryType.FEEDBACK:
        return f"{content}\n\n**Why:** User preference based on past experience\n**How to apply:** Apply this rule when making decisions in this area"
    elif memory_type == MemoryType.PROJECT:
        return f"{content}\n\n**Why:** Project constraint or context\n**How to apply:** Consider this when planning or implementing features"
    else:
        return content


def _generate_name(content: str) -> str:
    """Generate kebab-case name from content."""
    # Take first few words and convert to kebab-case
    words = content.lower().split()[:5]
    # Remove special chars
    cleaned = [w.replace("'", "").replace('"', '') for w in words if w.isalnum() or w.replace("'", "").isalnum()]
    return "-".join(cleaned[:3]) if cleaned else "memory"


@tool(
    name="remember",
    description="Save important information to memory for future sessions. Use when user explicitly asks to remember something or you detect important context worth persisting.",
    parameters={
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "The content to remember. For feedback/project types, will add Why/How to apply sections.",
            },
            "name": {
                "type": "string",
                "description": "Optional kebab-case name for the memory. If omitted, will generate from content.",
            },
            "memory_type": {
                "type": "string",
                "description": "Optional memory type: 'user', 'feedback', 'project', or 'reference'. If omitted, will infer from content.",
                "enum": ["user", "feedback", "project", "reference"],
            },
        },
        "required": ["content"],
    },
)
async def remember(
    content: str,
    name: str | None = None,
    memory_type: str | None = None,
) -> str:
    """Save a memory entry.

    Args:
        content: The content to remember
        name: Optional kebab-case identifier (auto-generated if omitted)
        memory_type: Optional type (auto-inferred if omitted)

    Returns:
        Confirmation message with memory name
    """
    store = get_memory_store()

    # Infer or parse type
    if memory_type:
        m_type = MemoryType(memory_type.lower())
    else:
        m_type = _infer_memory_type(content)

    # Generate or use provided name
    m_name = name or _generate_name(content)

    # Build full content
    full_content = _build_memory_content(content, m_type)

    # Create entry
    entry = MemoryEntry(
        name=m_name,
        description=content[:100] if len(content) > 100 else content,
        type=m_type,
        content=full_content,
    )

    # Save
    store.save(entry)

    return f"Saved memory: {m_name} (type: {m_type.value})"


@tool(
    name="forget",
    description="Delete a previously saved memory. Use when user asks to forget something or remove outdated information.",
    parameters={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "The kebab-case name of the memory to delete.",
            },
        },
        "required": ["name"],
    },
)
async def forget(name: str) -> str:
    """Delete a memory entry.

    Args:
        name: The kebab-case identifier of the memory

    Returns:
        Confirmation message or error
    """
    store = get_memory_store()

    if store.delete(name):
        return f"Forgot memory: {name}"
    else:
        return f"Memory not found: {name}"


@tool(
    name="recall",
    description="Retrieve saved memories. Use when user asks to recall memories or you need to reference past context.",
    parameters={
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Optional specific memory name to retrieve. If omitted, returns all memories index.",
            },
        },
        "required": [],
    },
)
async def recall(name: str | None = None) -> str:
    """Retrieve memory entries.

    Args:
        name: Optional specific memory name (returns index if omitted)

    Returns:
        Memory content or index listing
    """
    store = get_memory_store()

    if name:
        entry = store.load(name)
        if entry:
            return f"## {entry.name}\n\n{entry.content}"
        else:
            return f"Memory not found: {name}"
    else:
        # Return index
        index = store.get_index_content()
        if index:
            return index
        else:
            return "No memories saved yet. Use `remember` to save important information."