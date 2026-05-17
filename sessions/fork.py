"""Fork mechanism for sub-agent context inheritance.

Allows child agents to inherit parent conversation history
while using placeholder mechanism for prompt cache optimization.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from sessions.manager import SessionManager
from core.tokens import TokenCalculator
from sessions.memory import SlidingWindowStrategy

logger = logging.getLogger("gateway")


# Fixed placeholder token for cache optimization
# All fork children use the same placeholder, enabling prompt cache hit
FORK_PLACEHOLDER = "[FORK_TASK_PLACEHOLDER_8F2A]"

# Fork child system prompt boilerplate
FORK_CHILD_BOILERPLATE = """<fork>
STOP. READ THIS FIRST.

You are a forked worker process. You are NOT the main agent.

RULES:
1. Do NOT spawn sub-agents (Agent tool is disabled for you)
2. Do NOT ask questions - execute your task directly
3. Use tools directly: Bash, Read, Write, Edit, Glob, Grep
4. If you modify files, commit changes before reporting
5. Report once at the end, be factual and concise
6. Stay strictly within your assigned scope

Output format:
  Scope: <your assigned scope>
  Result: <key findings>
  Key files: <relevant paths>
  Files changed: <list with commit hash if applicable>
  Issues: <list if any>
</fork>"""


@dataclass
class ForkContext:
    """Context for forked agent execution."""

    parent_session_id: str
    inherited_messages: list[dict[str, Any]]
    placeholder_index: int  # Position of placeholder in messages
    is_fork_child: bool = True
    max_inherited_tokens: int = 32000


class ForkManager:
    """Manage fork operations for AgentExecutor.

    Provides context inheritance for sub-agents while optimizing
    for prompt cache sharing across multiple fork children.
    """

    def __init__(
        self,
        session_manager: SessionManager,
        token_calculator: TokenCalculator | None = None,
        canvas_manager: Any | None = None,
    ):
        self._session_manager = session_manager
        self._token_calculator = token_calculator or TokenCalculator()
        self._sliding_window = SlidingWindowStrategy()
        self._canvas_manager = canvas_manager

    def create_fork_context(
        self,
        parent_session_id: str,
        max_tokens: int = 32000,
        include_system_prompt: bool = True,
    ) -> ForkContext | None:
        """Create fork context from parent session.

        Args:
            parent_session_id: ID of parent session to inherit from
            max_tokens: Maximum tokens for inherited context
            include_system_prompt: Whether to include parent's system prompt

        Returns:
            ForkContext if successful, None if parent session not found
        """
        # Get parent session
        parent_session = self._session_manager.get_session(parent_session_id)
        if not parent_session:
            logger.warning(f"[FORK] Parent session {parent_session_id} not found")
            return None

        # Get parent messages
        parent_messages = self._session_manager.get_messages_openai(parent_session_id)

        if not parent_messages:
            logger.warning(f"[FORK] Parent session {parent_session_id} has no messages")
            return None

        # Clean up orphan tool messages (tool messages without preceding tool_calls)
        parent_messages = self._clean_orphan_tool_messages(parent_messages)

        # Calculate current tokens
        current_tokens = self._token_calculator.count_messages(parent_messages)

        # Apply truncation if needed
        if current_tokens > max_tokens:
            logger.info(
                f"[FORK] Parent context exceeds limit ({current_tokens} > {max_tokens}), "
                "applying truncation"
            )
            parent_messages = self._sliding_window.truncate_messages(
                parent_messages, max_tokens, self._token_calculator
            )
            current_tokens = self._token_calculator.count_messages(parent_messages)

        # Add fork child boilerplate as system message
        fork_system_msg = {
            "role": "system",
            "content": FORK_CHILD_BOILERPLATE,
        }

        # Build inherited messages: [fork_system, ...parent_messages, placeholder]
        inherited_messages = [fork_system_msg]

        # Filter parent messages based on include_system_prompt
        if parent_messages and parent_messages[0]["role"] == "system":
            if include_system_prompt:
                inherited_messages.append(parent_messages[0])
            inherited_messages.extend(parent_messages[1:])
        else:
            inherited_messages.extend(parent_messages)

        # Add placeholder at the end (will be replaced with actual task)
        placeholder_msg = {
            "role": "user",
            "content": FORK_PLACEHOLDER,
        }
        inherited_messages.append(placeholder_msg)

        placeholder_index = len(inherited_messages) - 1

        logger.info(
            f"[FORK] Created fork context from {parent_session_id}, "
            f"inherited_tokens={current_tokens}, message_count={len(inherited_messages)}"
        )

        return ForkContext(
            parent_session_id=parent_session_id,
            inherited_messages=inherited_messages,
            placeholder_index=placeholder_index,
            is_fork_child=True,
            max_inherited_tokens=max_tokens,
        )

    def _clean_orphan_tool_messages(
        self,
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Remove orphan tool messages without preceding tool_calls.

        Tool messages must have a preceding assistant message with tool_calls.
        If there's a tool message without one, it's orphaned and must be removed.

        Args:
            messages: Original message list

        Returns:
            Cleaned message list without orphan tool messages
        """
        cleaned = []
        last_assistant_tool_calls = None

        for msg in messages:
            role = msg.get("role")

            if role == "assistant":
                # Track tool_calls from this assistant message
                last_assistant_tool_calls = msg.get("tool_calls")
                cleaned.append(msg)
            elif role == "tool":
                # Check if there's a preceding assistant with tool_calls
                if last_assistant_tool_calls:
                    # Verify tool_call_id matches
                    tool_call_id = msg.get("tool_call_id")
                    if tool_call_id:
                        matching_ids = [tc["id"] for tc in last_assistant_tool_calls]
                        if tool_call_id in matching_ids:
                            cleaned.append(msg)
                        else:
                            logger.warning(
                                f"[FORK] Removing orphan tool message with unmatched tool_call_id: {tool_call_id}"
                            )
                    else:
                        logger.warning("[FORK] Removing tool message without tool_call_id")
                else:
                    logger.warning("[FORK] Removing orphan tool message without preceding tool_calls")
            elif role == "system":
                cleaned.append(msg)
            elif role == "user":
                cleaned.append(msg)
                # Reset tool_calls tracker after user message
                last_assistant_tool_calls = None

        logger.info(
            f"[FORK] Cleaned messages: {len(messages)} -> {len(cleaned)}, "
            f"removed {len(messages) - len(cleaned)} orphan messages"
        )
        return cleaned

    def build_fork_messages(
        self,
        fork_context: ForkContext,
        task: str,
    ) -> list[dict[str, Any]]:
        """Build messages for fork execution with placeholder replacement.

        Replaces the placeholder token with the actual task,
        while keeping all other messages identical.

        Args:
            fork_context: Fork context with inherited messages
            task: Actual task for the fork child

        Returns:
            Message list with placeholder replaced by task
        """
        # Copy inherited messages
        messages = list(fork_context.inherited_messages)

        # Replace placeholder with actual task
        for i, msg in enumerate(messages):
            if msg.get("content") == FORK_PLACEHOLDER:
                messages[i] = {
                    "role": "user",
                    "content": task,
                }
                logger.info(f"[FORK] Replaced placeholder with task at index {i}")
                break

        return messages

    def is_in_fork_child(self, messages: list[dict[str, Any]]) -> bool:
        """Detect if current context is a fork child.

        Used for recursive protection - prevents fork children
        from spawning more forks.

        Args:
            messages: Current message list

        Returns:
            True if in fork child context, False otherwise
        """
        for msg in messages:
            if msg["role"] == "system":
                content = msg.get("content", "")
                if isinstance(content, str) and "<fork>" in content:
                    return True
            elif msg["role"] == "user":
                content = msg.get("content", "")
                if isinstance(content, str) and content == FORK_PLACEHOLDER:
                    return True
        return False

    def get_canvas_manager(self) -> Any | None:
        """Get the canvas manager for pushing visual events."""
        return self._canvas_manager

    def get_fork_stats(self, fork_context: ForkContext) -> dict[str, Any]:
        """Get statistics about a fork context."""
        return {
            "parent_session_id": fork_context.parent_session_id,
            "message_count": len(fork_context.inherited_messages),
            "placeholder_index": fork_context.placeholder_index,
            "is_fork_child": fork_context.is_fork_child,
        }


__all__ = [
    "FORK_PLACEHOLDER",
    "FORK_CHILD_BOILERPLATE",
    "ForkContext",
    "ForkManager",
]