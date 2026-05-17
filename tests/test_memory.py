"""Unit tests for Memory Management."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from core.tokens import TokenCalculator
from sessions.memory import SlidingWindowStrategy
from sessions.manager import SessionManager


# ============================================================
# TokenCalculator
# ============================================================


class TestTokenCalculator:
    def test_count_text_basic(self):
        calc = TokenCalculator()
        # "Hello, world!" = 4 tokens in cl100k_base
        tokens = calc.count_text("Hello, world!")
        assert tokens == 4

    def test_count_text_empty(self):
        calc = TokenCalculator()
        assert calc.count_text("") == 0

    def test_count_text_chinese(self):
        calc = TokenCalculator()
        # Chinese characters use more tokens
        tokens = calc.count_text("你好世界")
        assert tokens > 0

    def test_count_message_user(self):
        calc = TokenCalculator()
        msg = {"role": "user", "content": "Hello"}
        tokens = calc.count_message(msg)
        # role overhead (4) + content (1) = 5
        assert tokens >= 5

    def test_count_message_with_tool_calls(self):
        calc = TokenCalculator()
        msg = {
            "role": "assistant",
            "content": "Result",
            "tool_calls": [
                {"id": "call_1", "function": {"name": "search", "arguments": "{}"}}
            ],
        }
        tokens = calc.count_message(msg)
        assert tokens > 5  # Should include tool call overhead

    def test_count_messages(self):
        calc = TokenCalculator()
        msgs = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hi"},
        ]
        total = calc.count_messages(msgs)
        assert total > 0
        # Total should be sum of individual counts
        assert total == calc.count_message(msgs[0]) + calc.count_message(msgs[1])


# ============================================================
# SlidingWindowStrategy
# ============================================================


class TestSlidingWindowStrategy:
    def test_truncate_empty(self):
        strategy = SlidingWindowStrategy()
        calc = TokenCalculator()
        result = strategy.truncate_messages([], 1000, calc)
        assert result == []

    def test_keeps_system_message(self):
        strategy = SlidingWindowStrategy()
        calc = TokenCalculator()
        messages = [{"role": "system", "content": "You are helpful."}]
        for i in range(10):
            messages.append({"role": "user", "content": f"Query {i}"})

        result = strategy.truncate_messages(messages, 100, calc)
        assert result[0]["role"] == "system"

    def test_keeps_recent_messages(self):
        strategy = SlidingWindowStrategy()
        calc = TokenCalculator()
        messages = [{"role": "user", "content": f"Query {i}" * 10} for i in range(20)]

        result = strategy.truncate_messages(messages, 200, calc)
        # Should keep last messages
        assert "Query 19" in result[-1]["content"]

    def test_respects_token_limit(self):
        strategy = SlidingWindowStrategy()
        calc = TokenCalculator()
        # Each message has ~50 tokens
        messages = [{"role": "user", "content": "x" * 100} for _ in range(100)]

        result = strategy.truncate_messages(messages, 500, calc)
        total_tokens = calc.count_messages(result)
        # Should be under limit (with 10% buffer)
        assert total_tokens <= 500

    def test_keeps_all_if_within_limit(self):
        strategy = SlidingWindowStrategy()
        calc = TokenCalculator()
        messages = [{"role": "user", "content": "Hi"} for _ in range(5)]

        result = strategy.truncate_messages(messages, 10000, calc)
        # Should keep all messages
        assert len(result) == 5


# ============================================================
# SessionManager Memory Methods
# ============================================================


class TestSessionManagerMemory:
    @pytest.fixture
    def manager(self):
        with tempfile.TemporaryDirectory() as d:
            db_path = Path(d) / "test.db"
            yield SessionManager(str(db_path))

    def test_add_message_stores_token_count(self, manager):
        session = manager.create_session(name="test")
        msg = manager.add_message(session.id, "user", "Hello, world!")
        assert msg.token_count > 0

    def test_session_token_count_updates(self, manager):
        session = manager.create_session(name="test")
        manager.add_message(session.id, "user", "Hello")
        manager.add_message(session.id, "user", "World")

        updated = manager.get_session(session.id)
        assert updated.token_count > 0

    def test_get_messages_with_limit(self, manager):
        session = manager.create_session(name="test")
        # Add many messages
        for i in range(100):
            manager.add_message(session.id, "user", f"Message {i}" * 50)

        # Get with small limit
        messages = manager.get_messages_with_limit(session.id, max_tokens=500)
        # Should be truncated
        assert len(messages) < 100

    def test_context_window_field(self, manager):
        session = manager.create_session(name="test")
        assert session.context_window == 64000

        # Update context window
        updated = manager.update_session(session.id, context_window=32000)
        assert updated.context_window == 32000

    def test_memory_strategy_field(self, manager):
        session = manager.create_session(name="test")
        assert session.memory_strategy == "sliding_window"

        # Update memory strategy
        updated = manager.update_session(session.id, memory_strategy="summary")
        assert updated.memory_strategy == "summary"