"""Memory management strategies for context window control."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from sessions.tokens import TokenCalculator


class MemoryStrategy(ABC):
    """Base class for memory management strategies."""

    @abstractmethod
    def truncate_messages(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int,
        calculator: "TokenCalculator",
    ) -> list[dict[str, Any]]:
        """Truncate messages to fit within max_tokens."""
        pass


class SlidingWindowStrategy(MemoryStrategy):
    """Keep the most recent messages within token limit."""

    def truncate_messages(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int,
        calculator: "TokenCalculator",
    ) -> list[dict[str, Any]]:
        """Truncate by keeping system message + recent messages."""
        if not messages:
            return []

        # Separate system message
        system_msg = None
        other_messages = messages
        if messages[0]["role"] == "system":
            system_msg = messages[0]
            other_messages = messages[1:]

        result = []
        total_tokens = 0

        # Add system message first (reserve 10% for it)
        if system_msg:
            sys_tokens = calculator.count_message(system_msg)
            if sys_tokens < max_tokens * 0.1:
                result.append(system_msg)
                total_tokens += sys_tokens

        # Add messages from newest to oldest (reverse iteration)
        # Reserve 10% buffer for response
        token_limit = max_tokens * 0.9
        for msg in reversed(other_messages):
            msg_tokens = calculator.count_message(msg)
            if total_tokens + msg_tokens <= token_limit:
                # Insert after system message, before other messages
                insert_pos = 1 if system_msg else 0
                result.insert(insert_pos, msg)
                total_tokens += msg_tokens
            else:
                break

        return result


class SummaryStrategy(MemoryStrategy):
    """Summarize old messages and keep recent ones."""

    def __init__(self, llm_client: Any, summary_threshold: int = 50):
        self._llm_client = llm_client
        self._summary_threshold = summary_threshold

    def truncate_messages(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int,
        calculator: "TokenCalculator",
    ) -> list[dict[str, Any]]:
        """Summarize old messages, keep recent ones."""
        if len(messages) < self._summary_threshold:
            # Not enough messages, use sliding window
            return SlidingWindowStrategy().truncate_messages(
                messages, max_tokens, calculator
            )

        # Separate system message
        system_msg = None
        other_messages = messages
        if messages[0]["role"] == "system":
            system_msg = messages[0]
            other_messages = messages[1:]

        # Split: old (to summarize) vs recent (to keep)
        split_point = len(other_messages) // 2
        old_messages = other_messages[:split_point]
        recent_messages = other_messages[split_point:]

        if not old_messages:
            return SlidingWindowStrategy().truncate_messages(
                messages, max_tokens, calculator
            )

        # Generate summary for old messages
        summary_content = self._generate_summary(old_messages)

        # Create summary message
        summary_msg = {
            "role": "system",
            "content": f"[Conversation Summary]\n{summary_content}",
        }

        # Combine: system + summary + recent
        result = []
        if system_msg:
            result.append(system_msg)
        result.append(summary_msg)
        result.extend(recent_messages)

        # Check if still within limit
        total_tokens = calculator.count_messages(result)
        if total_tokens > max_tokens:
            # Apply sliding window to recent messages
            return SlidingWindowStrategy().truncate_messages(
                result, max_tokens, calculator
            )

        return result

    def _generate_summary(self, messages: list[dict[str, Any]]) -> str:
        """Use LLM to generate conversation summary preserving key information."""
        prompt = """Summarize the following conversation history, preserving:

1. Key decisions made and their rationale
2. Files created, modified, or read (with brief description)
3. Important tool calls and their results
4. Errors encountered and how they were resolved
5. Current task state and next steps

Format as concise bullet points. Maximum 200 words.

Conversation to summarize:
"""
        for msg in messages:
            role = msg["role"]
            content = (msg.get("content") or "")[:200]

            # Include tool call info
            if msg.get("tool_calls"):
                tool_names = [tc["function"]["name"] for tc in msg["tool_calls"]]
                content += f"\n[Tools called: {', '.join(tool_names)}]"

            prompt += f"\n{role}: {content}"

        try:
            response = self._llm_client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
            )
            return response.choices[0].message.content or "Summary unavailable."
        except Exception:
            return "Summary unavailable due to error."


class HybridStrategy(MemoryStrategy):
    """Combine sliding window and summary strategies."""

    def __init__(self, llm_client: Any, summary_threshold: int = 100):
        self._sliding_window = SlidingWindowStrategy()
        self._summary = SummaryStrategy(llm_client, summary_threshold)

    def truncate_messages(
        self,
        messages: list[dict[str, Any]],
        max_tokens: int,
        calculator: "TokenCalculator",
    ) -> list[dict[str, Any]]:
        """Use summary for long conversations, sliding window for short."""
        # Count non-system messages
        other_messages = messages
        if messages and messages[0]["role"] == "system":
            other_messages = messages[1:]

        if len(other_messages) > self._summary._summary_threshold:
            return self._summary.truncate_messages(messages, max_tokens, calculator)

        return self._sliding_window.truncate_messages(messages, max_tokens, calculator)