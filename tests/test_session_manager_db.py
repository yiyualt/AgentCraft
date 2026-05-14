"""数据库测试 — SessionManager 的 sessions 和 messages CRUD 操作。

使用真实 SQLite :memory: 数据库，不 Mock。
遵循项目惯例：显式错误处理，直接测试 SQL 行为。
"""
from __future__ import annotations

import json
import pytest
import sqlite3

from sessions.manager import SessionManager
from sessions.models import Session, Message, init_db, SCHEMA


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def manager():
    """SessionManager backed by in-memory SQLite."""
    return SessionManager(db_path=":memory:")


@pytest.fixture
def conn():
    """Raw SQLite connection for direct schema/state inspection."""
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys=ON")
    c.executescript(SCHEMA)
    return c


# ============================================================
# Database Schema & Initialization
# ============================================================


class TestDatabaseInit:
    def test_init_creates_sessions_table(self):
        """init_db should create the sessions table."""
        conn = sqlite3.connect(":memory:")
        conn.executescript(SCHEMA)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'"
        ).fetchall()
        assert len(tables) == 1

    def test_init_creates_messages_table(self):
        """init_db should create the messages table."""
        conn = sqlite3.connect(":memory:")
        conn.executescript(SCHEMA)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='messages'"
        ).fetchall()
        assert len(tables) == 1

    def test_init_creates_index(self):
        """init_db should create the messages_session index."""
        conn = sqlite3.connect(":memory:")
        conn.executescript(SCHEMA)
        indexes = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_messages_session'"
        ).fetchall()
        assert len(indexes) == 1

    def test_sessions_table_has_all_columns(self, conn):
        """Verify sessions table has expected column names and types."""
        columns = {
            row[1]: row[2]
            for row in conn.execute("PRAGMA table_info(sessions)").fetchall()
        }
        assert columns["id"] == "TEXT"
        assert columns["name"] == "TEXT"
        assert columns["model"] == "TEXT"
        assert columns["system_prompt"] == "TEXT"
        assert columns["created_at"] == "TEXT"
        assert columns["updated_at"] == "TEXT"
        assert columns["message_count"] == "INTEGER"
        assert columns["token_count"] == "INTEGER"
        assert columns["status"] == "TEXT"
        assert columns["skills"] == "TEXT"
        assert columns["context_window"] == "INTEGER"
        assert columns["memory_strategy"] == "TEXT"

    def test_messages_table_has_all_columns(self, conn):
        """Verify messages table has expected column names."""
        columns = {
            row[1]: row[2]
            for row in conn.execute("PRAGMA table_info(messages)").fetchall()
        }
        assert columns["id"] == "TEXT"
        assert columns["session_id"] == "TEXT"
        assert columns["role"] == "TEXT"
        assert columns["content"] == "TEXT"
        assert columns["tool_calls"] == "TEXT"
        assert columns["tool_call_id"] == "TEXT"
        assert columns["name"] == "TEXT"
        assert columns["created_at"] == "TEXT"
        assert columns["token_count"] == "INTEGER"

    def test_init_default_db_path(self):
        """Default DB path should point to ~/.agentcraft/sessions.db."""
        mgr = SessionManager()
        assert str(mgr.db_path).endswith("/.agentcraft/sessions.db")

    def test_init_custom_path(self):
        """Custom DB path should be respected."""
        mgr = SessionManager(db_path=":memory:")
        assert mgr.db_path == ":memory:"


# ============================================================
# Session CRUD
# ============================================================


class TestCreateSession:
    def test_create_session_returns_session(self, manager):
        session = manager.create_session(name="test-session")
        assert isinstance(session, Session)
        assert session.id is not None
        assert len(session.id) == 12  # UUID hex[:12]
        assert session.name == "test-session"
        assert session.status == "active"

    def test_create_session_default_values(self, manager):
        session = manager.create_session(name="defaults")
        assert session.model == "deepseek-chat"
        assert session.context_window == 64000
        assert session.memory_strategy == "sliding_window"
        assert session.message_count == 0
        assert session.token_count == 0
        assert session.system_prompt is None
        assert session.skills == ""

    def test_create_session_custom_values(self, manager):
        session = manager.create_session(
            name="custom",
            model="gpt-4",
            system_prompt="You are helpful.",
            skills="python,go",
            context_window=32000,
            memory_strategy="summary",
        )
        assert session.model == "gpt-4"
        assert session.system_prompt == "You are helpful."
        assert session.skills == "python,go"
        assert session.context_window == 32000
        assert session.memory_strategy == "summary"

    def test_create_session_sets_timestamps(self, manager):
        import datetime
        before = datetime.datetime.now(datetime.timezone.utc).isoformat()
        session = manager.create_session(name="timing")
        assert session.created_at >= before
        assert session.updated_at >= before
        assert session.created_at == session.updated_at

    def test_create_session_persists_to_db(self, manager):
        session = manager.create_session(name="persist-test")
        # Fetch directly from DB to verify persistence
        row = manager._conn.execute(
            "SELECT name FROM sessions WHERE id=?", (session.id,)
        ).fetchone()
        assert row is not None
        assert row[0] == "persist-test"

    def test_create_multiple_sessions(self, manager):
        s1 = manager.create_session(name="first")
        s2 = manager.create_session(name="second")
        assert s1.id != s2.id
        assert len(manager.list_sessions()) == 2


class TestGetSession:
    def test_get_existing_session(self, manager):
        created = manager.create_session(name="get-test")
        loaded = manager.get_session(created.id)
        assert loaded is not None
        assert loaded.id == created.id
        assert loaded.name == "get-test"

    def test_get_nonexistent_session(self, manager):
        assert manager.get_session("no-such-id") is None

    def test_get_session_returns_all_fields(self, manager):
        created = manager.create_session(
            name="full",
            model="claude-3",
            system_prompt="Be concise.",
            skills="rust",
            context_window=100000,
            memory_strategy="hybrid",
        )
        loaded = manager.get_session(created.id)
        assert loaded.name == "full"
        assert loaded.model == "claude-3"
        assert loaded.system_prompt == "Be concise."
        assert loaded.skills == "rust"
        assert loaded.context_window == 100000
        assert loaded.memory_strategy == "hybrid"
        assert loaded.message_count == 0
        assert loaded.token_count == 0
        assert loaded.status == "active"

    def test_get_session_with_messages_updates_counts(self, manager):
        session = manager.create_session(name="counts")
        manager.add_message(session.id, "user", "Hello")
        manager.add_message(session.id, "assistant", "Hi there")
        loaded = manager.get_session(session.id)
        assert loaded.message_count == 2
        assert loaded.token_count > 0


class TestListSessions:
    def test_list_empty(self, manager):
        assert manager.list_sessions() == []

    def test_list_all_active(self, manager):
        manager.create_session(name="s1")
        manager.create_session(name="s2")
        sessions = manager.list_sessions()
        assert len(sessions) == 2

    def test_list_ordered_by_updated_at_desc(self, manager):
        s1 = manager.create_session(name="first")
        s2 = manager.create_session(name="second")
        sessions = manager.list_sessions()
        assert sessions[0].id == s2.id  # Most recent first
        assert sessions[1].id == s1.id

    def test_list_filters_by_status(self, manager):
        s1 = manager.create_session(name="active")
        s2 = manager.create_session(name="archived")
        manager.update_session(s2.id, status="archived")

        active = manager.list_sessions(status="active")
        archived = manager.list_sessions(status="archived")

        assert len(active) == 1
        assert active[0].id == s1.id
        assert len(archived) == 1
        assert archived[0].id == s2.id

    def test_list_excludes_archived_by_default(self, manager):
        s1 = manager.create_session(name="keep")
        s2 = manager.create_session(name="hide")
        manager.update_session(s2.id, status="archived")

        sessions = manager.list_sessions()  # default: active
        assert len(sessions) == 1
        assert sessions[0].id == s1.id

    def test_list_all_statuses(self, manager):
        manager.create_session(name="s1")
        manager.create_session(name="s2")
        sessions = manager.list_sessions(status="active")
        assert len(sessions) == 2


class TestUpdateSession:
    def test_update_name(self, manager):
        session = manager.create_session(name="old-name")
        updated = manager.update_session(session.id, name="new-name")
        assert updated.name == "new-name"

        # Verify persistence
        reloaded = manager.get_session(session.id)
        assert reloaded.name == "new-name"

    def test_update_model(self, manager):
        session = manager.create_session(name="m")
        updated = manager.update_session(session.id, model="gpt-4o")
        assert updated.model == "gpt-4o"

    def test_update_system_prompt(self, manager):
        session = manager.create_session(name="m")
        updated = manager.update_session(session.id, system_prompt="New prompt")
        assert updated.system_prompt == "New prompt"

    def test_update_status(self, manager):
        session = manager.create_session(name="m")
        updated = manager.update_session(session.id, status="archived")
        assert updated.status == "archived"

    def test_update_skills(self, manager):
        session = manager.create_session(name="m")
        updated = manager.update_session(session.id, skills="python,java")
        assert updated.skills == "python,java"

    def test_update_context_window(self, manager):
        session = manager.create_session(name="m")
        updated = manager.update_session(session.id, context_window=16000)
        assert updated.context_window == 16000

    def test_update_memory_strategy(self, manager):
        session = manager.create_session(name="m")
        updated = manager.update_session(session.id, memory_strategy="hybrid")
        assert updated.memory_strategy == "hybrid"

    def test_update_updates_timestamp(self, manager):
        session = manager.create_session(name="m")
        import time
        time.sleep(0.01)
        updated = manager.update_session(session.id, name="renamed")
        assert updated.updated_at > session.updated_at

    def test_update_nonexistent_session(self, manager):
        result = manager.update_session("no-such-id", name="anything")
        assert result is None

    def test_update_with_no_fields(self, manager):
        session = manager.create_session(name="m")
        updated = manager.update_session(session.id)
        assert updated is not None
        assert updated.name == "m"

    def test_update_rejects_invalid_fields(self, manager):
        session = manager.create_session(name="m")
        # Fields not in the allowed set should be silently ignored
        updated = manager.update_session(session.id, message_count=9999, nonexistent="x")
        assert updated.message_count == 0  # Not updated


class TestDeleteSession:
    def test_delete_existing(self, manager):
        session = manager.create_session(name="to-delete")
        assert manager.delete_session(session.id) is True
        assert manager.get_session(session.id) is None

    def test_delete_nonexistent(self, manager):
        assert manager.delete_session("no-such-id") is False

    def test_delete_removes_from_list(self, manager):
        s1 = manager.create_session(name="keep")
        s2 = manager.create_session(name="remove")
        manager.delete_session(s2.id)
        assert len(manager.list_sessions()) == 1
        assert manager.list_sessions()[0].id == s1.id

    def test_delete_cascades_to_messages(self, manager):
        """Deleting a session should also delete its messages (foreign key CASCADE)."""
        session = manager.create_session(name="cascade")
        manager.add_message(session.id, "user", "msg1")
        manager.add_message(session.id, "user", "msg2")

        manager.delete_session(session.id)

        remaining = manager._conn.execute(
            "SELECT COUNT(*) FROM messages WHERE session_id=?", (session.id,)
        ).fetchone()[0]
        assert remaining == 0

    def test_delete_then_recreate(self, manager):
        """After deletion, a new session with the same name can be created."""
        s1 = manager.create_session(name="cyclical")
        manager.delete_session(s1.id)
        s2 = manager.create_session(name="cyclical")
        assert s2.id != s1.id
        assert s2.name == "cyclical"


# ============================================================
# Message CRUD
# ============================================================


class TestAddMessage:
    def test_add_user_message(self, manager):
        session = manager.create_session(name="msg-test")
        msg = manager.add_message(session.id, "user", "Hello, world!")
        assert isinstance(msg, Message)
        assert msg.role == "user"
        assert msg.content == "Hello, world!"
        assert msg.session_id == session.id
        assert msg.token_count > 0

    def test_add_assistant_message(self, manager):
        session = manager.create_session(name="msg-test")
        msg = manager.add_message(session.id, "assistant", "Hi!")
        assert msg.role == "assistant"

    def test_add_system_message(self, manager):
        session = manager.create_session(name="msg-test")
        msg = manager.add_message(session.id, "system", "You are a bot.")
        assert msg.role == "system"

    def test_add_message_with_tool_calls(self, manager):
        session = manager.create_session(name="msg-test")
        tool_calls = json.dumps([
            {"id": "call_1", "function": {"name": "search", "arguments": '{"q": "test"}'}}
        ])
        msg = manager.add_message(session.id, "assistant", "", tool_calls=tool_calls)
        assert msg.tool_calls == tool_calls
        assert msg.token_count > 0

    def test_add_message_with_tool_call_id(self, manager):
        session = manager.create_session(name="msg-test")
        msg = manager.add_message(
            session.id, "tool", "Result: 42",
            tool_call_id="call_1", name="calculator",
        )
        assert msg.tool_call_id == "call_1"
        assert msg.name == "calculator"

    def test_add_message_increments_count(self, manager):
        session = manager.create_session(name="counter")
        manager.add_message(session.id, "user", "A")
        manager.add_message(session.id, "assistant", "B")
        manager.add_message(session.id, "user", "C")
        loaded = manager.get_session(session.id)
        assert loaded.message_count == 3

    def test_add_message_updates_token_count(self, manager):
        session = manager.create_session(name="tokens")
        m1 = manager.add_message(session.id, "user", "Short")
        m2 = manager.add_message(session.id, "user", "A much longer message with more tokens in it")
        loaded = manager.get_session(session.id)
        assert loaded.token_count == m1.token_count + m2.token_count

    def test_add_message_generates_unique_ids(self, manager):
        session = manager.create_session(name="unique")
        m1 = manager.add_message(session.id, "user", "A")
        m2 = manager.add_message(session.id, "user", "B")
        assert m1.id != m2.id

    def test_add_message_sets_timestamp(self, manager):
        session = manager.create_session(name="timing")
        msg = manager.add_message(session.id, "user", "Hi")
        assert msg.created_at is not None
        assert len(msg.created_at) > 0


class TestGetMessages:
    def test_get_messages_empty(self, manager):
        session = manager.create_session(name="empty")
        messages = manager.get_messages(session.id)
        assert messages == []

    def test_get_messages_in_order(self, manager):
        session = manager.create_session(name="order")
        m1 = manager.add_message(session.id, "user", "First")
        m2 = manager.add_message(session.id, "assistant", "Second")
        messages = manager.get_messages(session.id)
        assert len(messages) == 2
        assert messages[0].id == m1.id
        assert messages[1].id == m2.id

    def test_get_messages_respects_limit(self, manager):
        session = manager.create_session(name="limit")
        for i in range(100):
            manager.add_message(session.id, "user", f"Msg {i}")
        messages = manager.get_messages(session.id, limit=10)
        assert len(messages) == 10

    def test_get_messages_from_different_sessions(self, manager):
        s1 = manager.create_session(name="s1")
        s2 = manager.create_session(name="s2")
        manager.add_message(s1.id, "user", "Session 1 msg")
        manager.add_message(s2.id, "user", "Session 2 msg")
        assert len(manager.get_messages(s1.id)) == 1
        assert len(manager.get_messages(s2.id)) == 1

    def test_get_messages_nonexistent_session(self, manager):
        messages = manager.get_messages("no-such-id")
        assert messages == []


class TestGetMessagesOpenAI:
    def test_format_user_message(self, manager):
        session = manager.create_session(name="fmt")
        manager.add_message(session.id, "user", "Hello")
        msgs = manager.get_messages_openai(session.id)
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "Hello"

    def test_format_with_tool_calls(self, manager):
        session = manager.create_session(name="fmt-tc")
        tool_calls = json.dumps([
            {"id": "c1", "function": {"name": "fn", "arguments": "{}"}}
        ])
        manager.add_message(session.id, "assistant", "", tool_calls=tool_calls)
        msgs = manager.get_messages_openai(session.id)
        assert "tool_calls" in msgs[0]
        assert msgs[0]["tool_calls"][0]["id"] == "c1"

    def test_format_with_tool_call_id(self, manager):
        session = manager.create_session(name="fmt-tcid")
        manager.add_message(session.id, "tool", "Result", tool_call_id="c1", name="fn")
        msgs = manager.get_messages_openai(session.id)
        assert msgs[0]["tool_call_id"] == "c1"
        assert msgs[0]["name"] == "fn"


class TestClearMessages:
    def test_clear_empty_session(self, manager):
        session = manager.create_session(name="clear")
        manager.clear_messages(session.id)  # Should not raise
        assert manager.get_messages(session.id) == []

    def test_clear_removes_all_messages(self, manager):
        session = manager.create_session(name="clear")
        manager.add_message(session.id, "user", "A")
        manager.add_message(session.id, "user", "B")
        manager.clear_messages(session.id)
        assert manager.get_messages(session.id) == []

    def test_clear_resets_message_count(self, manager):
        session = manager.create_session(name="clear")
        manager.add_message(session.id, "user", "A")
        manager.clear_messages(session.id)
        loaded = manager.get_session(session.id)
        assert loaded.message_count == 0

    def test_clear_does_not_affect_other_sessions(self, manager):
        s1 = manager.create_session(name="s1")
        s2 = manager.create_session(name="s2")
        manager.add_message(s1.id, "user", "S1 msg")
        manager.add_message(s2.id, "user", "S2 msg")
        manager.clear_messages(s1.id)
        assert len(manager.get_messages(s1.id)) == 0
        assert len(manager.get_messages(s2.id)) == 1


# ============================================================
# Token Counting
# ============================================================


class TestCountTokens:
    def test_count_tokens_empty_session(self, manager):
        session = manager.create_session(name="empty")
        assert manager.count_tokens(session.id) == 0

    def test_count_tokens_with_messages(self, manager):
        session = manager.create_session(name="count")
        manager.add_message(session.id, "user", "Hello, world!")
        manager.add_message(session.id, "assistant", "Hi there!")
        total = manager.count_tokens(session.id)
        assert total > 0

    def test_count_tokens_nonexistent_session(self, manager):
        assert manager.count_tokens("no-such-id") == 0

    def test_count_tokens_matches_stored_sum(self, manager):
        session = manager.create_session(name="verify")
        m1 = manager.add_message(session.id, "user", "Hello")
        m2 = manager.add_message(session.id, "assistant", "World")
        expected = m1.token_count + m2.token_count
        # count_tokens uses stored token_count from session
        assert manager.count_tokens(session.id) == expected


# ============================================================
# Memory Management (get_messages_with_limit)
# ============================================================


class TestGetMessagesWithLimit:
    def test_limit_keeps_messages_under_limit(self, manager):
        session = manager.create_session(name="limit-test")
        for i in range(50):
            manager.add_message(session.id, "user", f"Short message {i}")

        result = manager.get_messages_with_limit(session.id, max_tokens=200)
        import tiktoken
        calc = tiktoken.get_encoding("cl100k_base")
        total = sum(len(calc.encode(m.get("content", ""))) for m in result)
        assert total <= 200

    def test_limit_empty_session(self, manager):
        session = manager.create_session(name="empty")
        result = manager.get_messages_with_limit(session.id)
        assert result == []

    def test_limit_nonexistent_session(self, manager):
        result = manager.get_messages_with_limit("no-such-id")
        assert result == []

    def test_limit_within_budget(self, manager):
        """If all messages fit within limit, all should be returned."""
        session = manager.create_session(name="small")
        manager.add_message(session.id, "user", "Hi")
        manager.add_message(session.id, "assistant", "Hello")
        result = manager.get_messages_with_limit(session.id, max_tokens=100000)
        assert len(result) == 2

    def test_limit_preserves_system_message(self, manager):
        """System message should always be kept (SlidingWindowStrategy behavior)."""
        session = manager.create_session(name="sys")
        manager.add_message(session.id, "system", "You are helpful.")
        for i in range(20):
            manager.add_message(session.id, "user", "x" * 500)  # ~500 tokens each

        result = manager.get_messages_with_limit(session.id, max_tokens=500)
        if result:
            assert result[0]["role"] == "system"


# ============================================================
# Edge Cases & Error Handling
# ============================================================


class TestEdgeCases:
    def test_large_content(self, manager):
        """Should handle large message content."""
        session = manager.create_session(name="large")
        large = "A" * 500_000
        msg = manager.add_message(session.id, "user", large)
        assert len(msg.content) == 500_000

    def test_unicode_content(self, manager):
        """Should handle Unicode content properly."""
        session = manager.create_session(name="unicode")
        text = "你好世界 🎉 éñçödïñg téßt"
        msg = manager.add_message(session.id, "user", text)
        assert msg.content == text

    def test_special_chars_in_session_name(self, manager):
        """Session names with special characters should work."""
        s1 = manager.create_session(name="test-session-123")
        s2 = manager.create_session(name="test_session_456")
        assert manager.get_session(s1.id) is not None
        assert manager.get_session(s2.id) is not None

    def test_multiple_operations_on_same_session(self, manager):
        """Sequence of operations on one session should not corrupt state."""
        session = manager.create_session(name="workflow")

        # Add messages
        manager.add_message(session.id, "system", "You are a bot.")
        manager.add_message(session.id, "user", "Hello")
        manager.add_message(session.id, "assistant", "Hi!")
        assert manager.get_session(session.id).message_count == 3

        # Clear and re-add
        manager.clear_messages(session.id)
        assert manager.get_session(session.id).message_count == 0
        assert manager.get_messages(session.id) == []

        manager.add_message(session.id, "user", "New start")
        assert manager.get_session(session.id).message_count == 1

        # Update session
        manager.update_session(session.id, name="renamed", model="gpt-4")
        loaded = manager.get_session(session.id)
        assert loaded.name == "renamed"
        assert loaded.model == "gpt-4"

    def test_foreign_key_violation(self, manager):
        """Adding message to a deleted session should raise IntegrityError."""
        session = manager.create_session(name="orphan")
        manager.delete_session(session.id)
        with pytest.raises(sqlite3.IntegrityError):
            manager.add_message(session.id, "user", "orphan message")

    def test_concurrent_sessions_isolated(self, manager):
        """Operations on different sessions should be isolated."""
        s1 = manager.create_session(name="s1")
        s2 = manager.create_session(name="s2")
        manager.add_message(s1.id, "user", "Only in s1")
        assert len(manager.get_messages(s1.id)) == 1
        assert len(manager.get_messages(s2.id)) == 0

    def test_empty_content_message(self, manager):
        """Messages with empty content should be allowed."""
        session = manager.create_session(name="empty-msg")
        msg = manager.add_message(session.id, "user", "")
        assert msg.content == ""

    def test_token_count_never_negative(self, manager):
        """token_count should always be >= 0."""
        session = manager.create_session(name="non-neg")
        manager.add_message(session.id, "user", "")
        loaded = manager.get_session(session.id)
        assert loaded.token_count >= 0
