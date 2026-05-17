"""Memory Loader - Unified memory loading for CLI and Gateway.

Provides task-based memory retrieval (semantic search) instead of loading entire memory index.
"""

from __future__ import annotations

import logging
from typing import Any

from sessions.vector_memory import VectorMemoryStore, MemoryEntry
from tools.builtin.memory_tools import get_memory_store

logger = logging.getLogger(__name__)


class MemoryLoader:
    """Loads relevant memories based on task context."""

    def __init__(self, store: VectorMemoryStore | None = None):
        self._store = store or get_memory_store()

    def load_for_task(
        self,
        messages: list[dict[str, Any]] | None = None,
        task: str | None = None,
        limit: int = 5,
        top_k: int = 3,
    ) -> str | None:
        """Load relevant memories for a task.

        Args:
            messages: Current conversation messages (used to extract task)
            task: Explicit task string (overrides message extraction)
            limit: Number of memories to search
            top_k: Number of top memories to load into prompt

        Returns:
            Formatted memory section for system prompt, or None if no memories found
        """
        # Extract task from messages if not provided
        if not task and messages:
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    content = msg.get("content", "")
                    if content and not content.startswith("/"):  # Exclude slash commands
                        task = content
                        break

        if not task:
            # No task context - return index as fallback
            return self.load_index()

        # Search relevant memories
        try:
            relevant = self._store.search_hybrid(task, limit=limit)

            if not relevant:
                return self.load_index()

            # Format top_k memories
            names = [e.name for e in relevant[:top_k]]
            logger.info(f"[MEMORY] Loaded memories: {names} for task '{task[:30]}...'")

            lines = [
                "\n<relevant_memories>\n",
                "STOP. READ THESE MEMORIES FIRST BEFORE PROCEEDING.\n",
                "These are NOT suggestions - they are REQUIREMENTS based on past experience.\n\n",
            ]
            for entry in relevant[:top_k]:
                lines.append(f"## {entry.name}\n\n")
                lines.append(f"{entry.content}\n\n")
            lines.append("You MUST follow these rules. Do NOT ignore them.\n")
            lines.append("</relevant_memories>\n")

            return "".join(lines)

        except Exception as e:
            logger.debug(f"[MEMORY] Search failed: {e}")
            return self.load_index()

    def load_index(self) -> str | None:
        """Load memory index as fallback (all memories summary)."""
        try:
            index = self._store.get_index_content()
            if index:
                return f"\n<memory_index>\n{index}\n</memory_index>\n"
        except Exception as e:
            logger.debug(f"[MEMORY] Index load failed: {e}")
        return None


def load_relevant_memories(
    messages: list[dict[str, Any]] | None = None,
    task: str | None = None,
    limit: int = 5,
    top_k: int = 3,
) -> str | None:
    """Convenience function to load relevant memories."""
    loader = MemoryLoader()
    return loader.load_for_task(messages, task, limit, top_k)


__all__ = ["MemoryLoader", "load_relevant_memories"]