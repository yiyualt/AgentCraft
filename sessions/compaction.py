"""Auto-compaction system for context window management.

Provides multi-layer compression to prevent context overflow:
- Level 1 (Microcompact): Simple truncation, no LLM call
- Level 2 (Autocompact): LLM summarization preserving key info
- Level 3 (Reactive): Aggressive compression for error recovery
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

from sessions.manager import SessionManager
from sessions.memory import SlidingWindowStrategy
from core.tokens import TokenCalculator

logger = logging.getLogger("gateway")


@dataclass
class CompactionConfig:
    """Configuration for auto-compaction thresholds."""

    micro_threshold: float = 0.6      # 60% of context window
    auto_threshold: float = 0.8       # 80% of context window
    reactive_threshold: float = 0.9   # 90% of context window

    max_failures: int = 3             # Circuit breaker threshold
    cooldown_seconds: int = 60        # Wait after failure before retry

    summary_model: str = "deepseek-chat"
    summary_max_tokens: int = 500
    keep_recent_messages: int = 10    # Messages to preserve in reactive mode


@dataclass
class CompactionState:
    """Track compaction state for circuit breaker."""

    consecutive_failures: int = 0
    last_failure_time: float | None = None
    last_compaction_level: int = 0
    total_tokens_compacted: int = 0
    compaction_count: int = 0


class CompactionManager:
    """Manage auto-compaction of conversations.

    Automatically compresses conversation context when approaching
    token limits, using intelligent summarization to preserve key information.
    """

    def __init__(
        self,
        session_manager: SessionManager,
        llm_client: OpenAI,
        config: CompactionConfig | None = None,
    ):
        self._session_manager = session_manager
        self._llm_client = llm_client
        self._config = config or CompactionConfig()
        self._states: dict[str, CompactionState] = {}  # session_id -> state
        self._sliding_window = SlidingWindowStrategy()

    def get_state(self, session_id: str) -> CompactionState:
        """Get or create compaction state for session."""
        if session_id not in self._states:
            self._states[session_id] = CompactionState()
        return self._states[session_id]

    def check_compaction_needed(
        self,
        session_id: str,
        current_tokens: int,
        context_window: int,
    ) -> int | None:
        """Check if compaction needed, return level (1-3) or None.

        Args:
            session_id: Session identifier
            current_tokens: Current token count of messages
            context_window: Maximum context window for the model

        Returns:
            Compaction level (1=Micro, 2=Auto, 3=Reactive) or None if not needed
        """
        ratio = current_tokens / context_window

        # Check circuit breaker
        state = self.get_state(session_id)
        if state.consecutive_failures >= self._config.max_failures:
            # Check cooldown
            if state.last_failure_time:
                elapsed = time.time() - state.last_failure_time
                if elapsed < self._config.cooldown_seconds:
                    logger.warning(
                        f"[COMPACTION] Circuit breaker active for session {session_id}, "
                        f"cooldown remaining: {self._config.cooldown_seconds - elapsed:.0f}s"
                    )
                    return None
            # Reset failures after cooldown
            state.consecutive_failures = 0
            logger.info(f"[COMPACTION] Circuit breaker reset for session {session_id}")

        # Determine compaction level
        if ratio >= self._config.reactive_threshold:
            return 3  # Reactive - most aggressive
        elif ratio >= self._config.auto_threshold:
            return 2  # Autocompact - LLM summary
        elif ratio >= self._config.micro_threshold:
            return 1  # Microcompact - simple truncation

        return None

    async def compact(
        self,
        session_id: str,
        messages: list[dict],
        level: int,
        calculator: TokenCalculator,
        target_tokens: int | None = None,
    ) -> list[dict]:
        """Perform compaction at specified level.

        Args:
            session_id: Session identifier
            messages: Current message list
            level: Compaction level (1-3)
            calculator: Token calculator for the model
            target_tokens: Target token count (default: 50% of threshold)

        Returns:
            Compacted message list
        """
        state = self.get_state(session_id)
        original_tokens = calculator.count_messages(messages)

        logger.info(
            f"[COMPACTION] Level {level} triggered for session {session_id}, "
            f"current_tokens={original_tokens}"
        )

        try:
            if level == 1:
                result = self._microcompact(messages, calculator, target_tokens)
            elif level == 2:
                result = await self._autocompact(messages, calculator, target_tokens)
            elif level == 3:
                result = await self._reactive_compact(messages, calculator, target_tokens)
            else:
                result = messages

            # Calculate savings
            new_tokens = calculator.count_messages(result)
            tokens_saved = original_tokens - new_tokens

            # Record success
            state.consecutive_failures = 0
            state.last_compaction_level = level
            state.total_tokens_compacted += tokens_saved
            state.compaction_count += 1

            logger.info(
                f"[COMPACTION] Level {level} complete, "
                f"tokens_saved={tokens_saved}, new_count={new_tokens}"
            )

            return result

        except Exception as e:
            # Record failure
            state.consecutive_failures += 1
            state.last_failure_time = time.time()
            logger.error(
                f"[COMPACTION] Level {level} failed: {e}, "
                f"consecutive_failures={state.consecutive_failures}"
            )
            return messages  # Return original on failure

    def _microcompact(
        self,
        messages: list[dict],
        calculator: TokenCalculator,
        target_tokens: int | None = None,
    ) -> list[dict]:
        """Level 1: Simple truncation using sliding window.

        Fast, no LLM call. Preserves system message + recent messages.
        """
        if not target_tokens:
            # Default: reduce to 40% of context (below micro threshold)
            target_tokens = int(calculator.count_messages(messages) * 0.4)

        return self._sliding_window.truncate_messages(messages, target_tokens, calculator)

    async def _autocompact(
        self,
        messages: list[dict],
        calculator: TokenCalculator,
        target_tokens: int | None = None,
    ) -> list[dict]:
        """Level 2: LLM summarization preserving key information.

        Summarizes older messages while preserving:
        - Key decisions and rationale
        - Important tool calls and results
        - Files created/modified
        - Current task state
        """
        # Separate system message
        system_msg = None
        other_messages = messages
        if messages and messages[0]["role"] == "system":
            system_msg = messages[0]
            other_messages = messages[1:]

        # Determine split point: keep last 30% of messages
        split_point = int(len(other_messages) * 0.7)
        old_messages = other_messages[:split_point]
        recent_messages = other_messages[split_point:]

        if not old_messages:
            # Nothing to summarize, use microcompact
            return self._microcompact(messages, calculator, target_tokens)

        # Generate enhanced summary
        summary_content = await self._generate_enhanced_summary(old_messages)

        # Create summary message
        summary_msg = {
            "role": "user",
            "content": f"<context_summary>\n{summary_content}\n</context_summary>",
        }

        # Combine: system + summary + recent
        result = []
        if system_msg:
            result.append(system_msg)
        result.append(summary_msg)
        result.extend(recent_messages)

        # Check if still within limit
        current_tokens = calculator.count_messages(result)
        if target_tokens and current_tokens > target_tokens:
            # Apply sliding window to further reduce
            result = self._sliding_window.truncate_messages(result, target_tokens, calculator)

        return result

    async def _reactive_compact(
        self,
        messages: list[dict],
        calculator: TokenCalculator,
        target_tokens: int | None = None,
    ) -> list[dict]:
        """Level 3: Aggressive compression for error recovery.

        Keeps only: system + summary + last N messages.
        Used when prompt_too_long error occurs.
        """
        keep_count = self._config.keep_recent_messages

        # Separate system message
        system_msg = None
        other_messages = messages
        if messages and messages[0]["role"] == "system":
            system_msg = messages[0]
            other_messages = messages[1:]

        # Keep only the most recent messages
        recent_messages = other_messages[-keep_count:] if len(other_messages) > keep_count else other_messages

        # Summarize everything before
        old_messages = other_messages[:-keep_count] if len(other_messages) > keep_count else []

        if old_messages:
            summary_content = await self._generate_enhanced_summary(old_messages)
            summary_msg = {
                "role": "user",
                "content": f"<context_summary>\n{summary_content}\n</context_summary>",
            }
        else:
            summary_msg = None

        # Combine: system + summary + recent
        result = []
        if system_msg:
            result.append(system_msg)
        if summary_msg:
            result.append(summary_msg)
        result.extend(recent_messages)

        # Final check - if still too long, apply sliding window
        current_tokens = calculator.count_messages(result)
        if target_tokens and current_tokens > target_tokens:
            result = self._sliding_window.truncate_messages(result, target_tokens, calculator)

        return result

    async def _generate_enhanced_summary(self, messages: list[dict]) -> str:
        """Use LLM to generate enhanced summary preserving key information."""
        # Build summary prompt
        prompt = """Summarize the following conversation history, preserving:

1. Key decisions made and their rationale
2. Files created, modified, or read (with brief description)
3. Important tool calls and their results
4. Errors encountered and how they were resolved
5. Current task state and next steps

Format as concise bullet points. Maximum 300 words.

Conversation to summarize:
"""

        # Add message content (truncate long messages)
        for msg in messages:
            role = msg["role"]
            content = (msg.get("content") or "")[:300]

            # Include tool call info
            if msg.get("tool_calls"):
                tool_names = [tc["function"]["name"] for tc in msg["tool_calls"]]
                content += f"\n[Tools called: {', '.join(tool_names)}]"

            prompt += f"\n{role}: {content}"

        try:
            # Call LLM for summary
            response = await asyncio.to_thread(
                self._llm_client.chat.completions.create,
                model=self._config.summary_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=self._config.summary_max_tokens,
            )
            summary = response.choices[0].message.content or "Summary unavailable."
            return summary
        except Exception as e:
            logger.error(f"[COMPACTION] Summary generation failed: {e}")
            return "Summary unavailable due to error."

    def get_compaction_stats(self, session_id: str) -> dict:
        """Get compaction statistics for a session."""
        state = self.get_state(session_id)
        return {
            "compaction_count": state.compaction_count,
            "total_tokens_compacted": state.total_tokens_compacted,
            "consecutive_failures": state.consecutive_failures,
            "last_compaction_level": state.last_compaction_level,
        }


__all__ = ["CompactionConfig", "CompactionState", "CompactionManager"]