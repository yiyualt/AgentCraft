"""Prompt Builder - Unified system prompt building for CLI and Gateway.

Builds system prompts with:
- Skill listing
- Goal condition
- Relevant memories (task-based retrieval)
- Session context
"""

from __future__ import annotations

import logging
from typing import Any

from skills import SkillLoader
from core.memory_loader import MemoryLoader, load_relevant_memories

logger = logging.getLogger(__name__)


class PromptBuilder:
    """Builds system prompts with consistent formatting."""

    def __init__(
        self,
        skill_loader: SkillLoader | None = None,
        memory_loader: MemoryLoader | None = None,
    ):
        self._skill_loader = skill_loader
        self._memory_loader = memory_loader or MemoryLoader()

    def build(
        self,
        messages: list[dict[str, Any]] | None = None,
        goal: str | None = None,
        skill_name: str | None = None,
        session_system_prompt: str | None = None,
    ) -> str:
        """Build system prompt.

        Args:
            messages: Current conversation messages (for memory retrieval)
            goal: Optional goal condition
            skill_name: Optional specific skill
            session_system_prompt: Optional custom system prompt from session

        Returns:
            Complete system prompt string
        """
        parts = []

        # Custom system prompt first
        if session_system_prompt:
            parts.append(session_system_prompt)

        # Skill listing
        if self._skill_loader:
            skill_listing = self._skill_loader.build_skill_listing()
            if skill_listing:
                parts.append(skill_listing)

        # Goal condition
        if goal:
            parts.append(f"\n<goal>\nGoal: {goal}\nComplete this goal before ending the session.\n</goal>")

        # Memory context (task-based retrieval)
        memory_section = self._memory_loader.load_for_task(messages=messages)
        if memory_section:
            parts.append(memory_section)

        return "\n\n".join(parts) if parts else ""

    def insert_into_messages(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str | None = None,
    ) -> list[dict[str, Any]]:
        """Insert system prompt into messages list.

        Args:
            messages: Current messages list
            system_prompt: System prompt to insert (will build if None)

        Returns:
            Messages list with system prompt inserted
        """
        if system_prompt is None:
            system_prompt = self.build(messages=messages)

        if not system_prompt:
            return messages

        # Check if system message already exists
        for msg in messages:
            if msg.get("role") == "system":
                # Update existing system message
                msg["content"] = system_prompt
                return messages

        # Insert at beginning
        messages.insert(0, {"role": "system", "content": system_prompt})
        return messages


def build_system_prompt(
    messages: list[dict[str, Any]] | None = None,
    goal: str | None = None,
    skill_loader: SkillLoader | None = None,
) -> str:
    """Convenience function to build system prompt."""
    builder = PromptBuilder(skill_loader=skill_loader)
    return builder.build(messages=messages, goal=goal)