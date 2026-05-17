"""Token counting utilities using tiktoken."""

from __future__ import annotations

from typing import Any

import tiktoken


class TokenCalculator:
    """Calculate token counts for messages using tiktoken."""

    # Model to encoding mapping
    MODEL_ENCODINGS = {
        "deepseek-chat": "cl100k_base",
        "deepseek-reasoner": "cl100k_base",
        "gpt-4": "cl100k_base",
        "gpt-4o": "o200k_base",
        "gpt-3.5-turbo": "cl100k_base",
    }

    DEFAULT_ENCODING = "cl100k_base"

    def __init__(self, model: str = "deepseek-chat"):
        encoding_name = self.MODEL_ENCODINGS.get(model, self.DEFAULT_ENCODING)
        self._encoding = tiktoken.get_encoding(encoding_name)

    def count_text(self, text: str) -> int:
        """Count tokens in plain text."""
        if not text:
            return 0
        return len(self._encoding.encode(text))

    def count_message(self, message: dict[str, Any]) -> int:
        """Count tokens in an OpenAI-format message.

        Includes role, content, tool_calls, name, etc.
        Approximation: tokens = 4 (role overhead) + content + tool tokens
        """
        # Every message has ~4 tokens overhead for role/formatting
        tokens = 4

        # Content tokens
        content = message.get("content") or ""
        if isinstance(content, str):
            tokens += self.count_text(content)
        elif isinstance(content, list):
            # Multi-modal content
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    tokens += self.count_text(part.get("text", ""))

        # Tool calls (assistant messages)
        if message.get("tool_calls"):
            for tc in message["tool_calls"]:
                fn = tc.get("function", {})
                tokens += self.count_text(fn.get("name", ""))
                tokens += self.count_text(fn.get("arguments", ""))
                tokens += 2  # overhead for tool call id

        # Tool call ID (tool messages)
        if message.get("tool_call_id"):
            tokens += self.count_text(message["tool_call_id"])

        # Name (for tool messages)
        if message.get("name"):
            tokens += self.count_text(message["name"])

        return tokens

    def count_messages(self, messages: list[dict[str, Any]]) -> int:
        """Count total tokens in a message list."""
        if not messages:
            return 0
        return sum(self.count_message(m) for m in messages)


__all__ = ["TokenCalculator"]