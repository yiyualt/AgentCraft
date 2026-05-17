"""Memory tools for AgentCraft - remember/forget/recall operations.

Uses VectorMemoryStore (SQLite + FTS + Vector) for semantic search.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from tools import tool
from core.vector_memory import VectorMemoryStore, MockEmbeddingModel, MemoryEntry


# Global memory store (initialized with project path)
_memory_store: VectorMemoryStore | None = None


def get_memory_store() -> VectorMemoryStore:
    """Get or create memory store for current project."""
    global _memory_store
    if _memory_store is None:
        # Use VectorMemoryStore with MockEmbeddingModel (works without PyTorch)
        # For real semantic search, use LocalEmbeddingModel or RemoteEmbeddingModel
        _memory_store = VectorMemoryStore(
            embedding_model=MockEmbeddingModel()
        )
    return _memory_store


def set_memory_store(store: VectorMemoryStore) -> None:
    """Set memory store (for gateway initialization)."""
    global _memory_store
    _memory_store = store


def _infer_memory_type(content: str) -> str:
    """Infer memory type from content heuristics."""
    content_lower = content.lower()

    # Feedback indicators
    if any(kw in content_lower for kw in ["don't", "do not", "never", "always", "stop", "avoid", "keep", "prefer", "不要", "必须", "禁止"]):
        return "feedback"

    # User indicators
    if any(kw in content_lower for kw in ["i'm", "i am", "my", "i work", "i have", "i know", "senior", "junior", "engineer", "developer", "我是", "资深"]):
        return "user"

    # Project indicators
    if any(kw in content_lower for kw in ["project", "deadline", "stakeholder", "compliance", "legal", "freeze", "release", "team", "项目", "截止", "合规"]):
        return "project"

    # Default to project for general context
    return "project"


def _build_memory_content(content: str, memory_type: str) -> str:
    """Build full memory content with structure."""
    if memory_type == "feedback":
        return f"{content}\n\n**Why:** User preference based on past experience\n**How to apply:** Apply this rule when making decisions in this area"
    elif memory_type == "project":
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
    m_type = memory_type or _infer_memory_type(content)

    # Generate or use provided name
    m_name = name or _generate_name(content)

    # Build full content
    full_content = _build_memory_content(content, m_type)

    # Save to VectorMemoryStore
    store.save(m_name, m_type, full_content)

    return f"Saved memory: {m_name} (type: {m_type})"


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
    description="Retrieve saved memories. Use when user asks to recall memories or you need to reference past context. Supports semantic search.",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Optional search query. If omitted, returns all memories index. Supports semantic matching.",
            },
            "mode": {
                "type": "string",
                "description": "Search mode: 'fts' (keyword), 'vector' (semantic), or 'hybrid' (combined). Default is 'hybrid'.",
                "enum": ["fts", "vector", "hybrid"],
            },
        },
        "required": [],
    },
)
async def recall(query: str | None = None, mode: str = "hybrid") -> str:
    """Retrieve memory entries.

    Args:
        query: Optional search query (returns index if omitted)
        mode: Search mode (fts/vector/hybrid)

    Returns:
        Memory content or search results
    """
    store = get_memory_store()

    if query:
        # Search mode
        if mode == "fts":
            results = store.search_fts(query, limit=10)
        elif mode == "vector":
            results = store.search_vector(query, limit=10)
        else:  # hybrid
            results = store.search_hybrid(query, limit=10)

        if not results:
            return f"No memories found for query: {query}"

        # Format results
        lines = [f"# Search Results for \"{query}\" (mode: {mode})\n\n"]
        for entry in results:
            score = f" (score: {entry.similarity:.2f})" if entry.similarity > 0 else ""
            lines.append(f"## {entry.name}{score}\n\n")
            lines.append(f"Type: {entry.type}\n\n")
            lines.append(f"{entry.content[:500]}...\n\n")

        return "".join(lines)
    else:
        # Return index
        index = store.get_index_content()
        if index:
            return index
        else:
            return "No memories saved yet. Use `remember` to save important information."