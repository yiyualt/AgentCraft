"""Unit tests for sessions/fork.py — ForkManager, ForkContext, constants."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from sessions.fork import (
    FORK_PLACEHOLDER,
    FORK_CHILD_BOILERPLATE,
    ForkContext,
    ForkManager,
)
from sessions.manager import SessionManager
from sessions.tokens import TokenCalculator
from sessions.memory import SlidingWindowStrategy


# ── Helpers ──────────────────────────────────────────────────────────────

def make_msg(role: str, content: str, **kwargs):
    """Create an OpenAI-format message dict."""
    msg: dict = {"role": role, "content": content}
    msg.update(kwargs)
    return msg


def make_assistant(content: str):
    """Create an assistant message without tool calls."""
    return make_msg("assistant", content)


def make_assistant_with_tool_calls(content: str, tool_calls: list):
    """Create an assistant message with tool_calls."""
    return {
        "role": "assistant",
        "content": content,
        "tool_calls": tool_calls,
    }


def make_tool_result(tool_call_id: str, content: str = "result"):
    """Create a tool result message."""
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": content,
    }


# ── Constants ────────────────────────────────────────────────────────────

class TestForkConstants:
    def test_placeholder_is_string(self):
        assert isinstance(FORK_PLACEHOLDER, str)
        assert len(FORK_PLACEHOLDER) > 0

    def test_placeholder_is_fixed(self):
        assert FORK_PLACEHOLDER == "[FORK_TASK_PLACEHOLDER_8F2A]"

    def test_boilerplate_contains_fork_tag(self):
        assert "<fork>" in FORK_CHILD_BOILERPLATE
        assert "</fork>" in FORK_CHILD_BOILERPLATE

    def test_boilerplate_contains_rules(self):
        assert "STOP. READ THIS FIRST." in FORK_CHILD_BOILERPLATE
        assert "forked worker process" in FORK_CHILD_BOILERPLATE
        assert "Do NOT spawn sub-agents" in FORK_CHILD_BOILERPLATE
        assert "Do NOT ask questions" in FORK_CHILD_BOILERPLATE
        assert "Output format" in FORK_CHILD_BOILERPLATE


# ── ForkContext ──────────────────────────────────────────────────────────

class TestForkContext:
    def test_create_minimal(self):
        ctx = ForkContext(
            parent_session_id="abc123",
            inherited_messages=[],
            placeholder_index=0,
        )
        assert ctx.parent_session_id == "abc123"
        assert ctx.inherited_messages == []
        assert ctx.placeholder_index == 0
        assert ctx.is_fork_child is True
        assert ctx.max_inherited_tokens == 32000

    def test_create_full(self):
        msgs = [make_msg("user", "hello")]
        ctx = ForkContext(
            parent_session_id="xyz",
            inherited_messages=msgs,
            placeholder_index=5,
            is_fork_child=True,
            max_inherited_tokens=16000,
        )
        assert ctx.parent_session_id == "xyz"
        assert ctx.inherited_messages == msgs
        assert ctx.placeholder_index == 5
        assert ctx.is_fork_child is True
        assert ctx.max_inherited_tokens == 16000

    def test_default_is_fork_child(self):
        ctx = ForkContext(
            parent_session_id="s",
            inherited_messages=[],
            placeholder_index=0,
        )
        assert ctx.is_fork_child is True


# ── ForkManager._clean_orphan_tool_messages ──────────────────────────────

class TestCleanOrphanToolMessages:
    @pytest.fixture
    def fm(self):
        """ForkManager with mocked dependencies (no DB needed for _clean)."""
        sm = MagicMock(spec=SessionManager)
        tc = MagicMock(spec=TokenCalculator)
        return ForkManager(session_manager=sm, token_calculator=tc)

    def test_passes_through_normal_messages(self, fm):
        msgs = [
            make_msg("system", "You are helpful"),
            make_msg("user", "Hello"),
            make_msg("assistant", "Hi there!"),
        ]
        result = fm._clean_orphan_tool_messages(msgs)
        assert len(result) == 3
        assert result == msgs

    def test_keeps_valid_tool_chain(self, fm):
        """Tool message with matching preceding assistant tool_call is kept."""
        msgs = [
            make_assistant_with_tool_calls("Let me read", [
                {"id": "call_1", "type": "function", "function": {"name": "Read", "arguments": "{}"}}
            ]),
            make_tool_result("call_1", "file contents"),
            make_assistant("Got it"),
        ]
        result = fm._clean_orphan_tool_messages(msgs)
        assert len(result) == 3

    def test_removes_orphan_tool_without_preceding_tool_calls(self, fm):
        """Tool message without any preceding assistant tool_calls is removed."""
        msgs = [
            make_msg("system", "system"),
            make_tool_result("call_orphan", "result"),
            make_msg("user", "next"),
        ]
        result = fm._clean_orphan_tool_messages(msgs)
        assert len(result) == 2
        roles = [m["role"] for m in result]
        assert "tool" not in roles

    def test_removes_tool_with_unmatched_tool_call_id(self, fm):
        """Tool message whose tool_call_id doesn't match preceding assistant's tool_calls."""
        msgs = [
            make_assistant_with_tool_calls("calling", [
                {"id": "call_A", "type": "function", "function": {"name": "Read", "arguments": "{}"}}
            ]),
            make_tool_result("call_B", "wrong id"),  # doesn't match call_A
            make_msg("user", "next"),
        ]
        result = fm._clean_orphan_tool_messages(msgs)
        # call_B is removed
        assert len(result) == 2
        roles = [m["role"] for m in result]
        assert roles == ["assistant", "user"]

    def test_removes_tool_without_tool_call_id(self, fm):
        """Tool message without tool_call_id field is removed."""
        msgs = [
            make_assistant_with_tool_calls("calling", [
                {"id": "call_1", "type": "function", "function": {"name": "Read", "arguments": "{}"}}
            ]),
            {"role": "tool", "content": "no id"},  # missing tool_call_id
            make_msg("user", "next"),
        ]
        result = fm._clean_orphan_tool_messages(msgs)
        assert len(result) == 2

    def test_multiple_tool_calls_kept(self, fm):
        """Multiple valid tool results following one assistant with multiple tool_calls."""
        msgs = [
            make_assistant_with_tool_calls("multi call", [
                {"id": "call_1", "type": "function", "function": {"name": "Read", "arguments": "{}"}},
                {"id": "call_2", "type": "function", "function": {"name": "Grep", "arguments": "{}"}},
            ]),
            make_tool_result("call_1", "result 1"),
            make_tool_result("call_2", "result 2"),
        ]
        result = fm._clean_orphan_tool_messages(msgs)
        assert len(result) == 3  # assistant + 2 tool results

    def test_resets_tool_calls_after_user_message(self, fm):
        """After a user message, tool_calls tracking resets."""
        msgs = [
            make_assistant_with_tool_calls("calling", [
                {"id": "call_1", "type": "function", "function": {"name": "Read", "arguments": "{}"}}
            ]),
            make_tool_result("call_1", "result"),
            make_msg("user", "new message"),
            make_tool_result("call_2", "orphan after user"),  # orphan — no preceding assistant with tool_calls
        ]
        result = fm._clean_orphan_tool_messages(msgs)
        assert len(result) == 3  # assistant, tool_result, user (orphan removed)

    def test_returns_empty_for_empty_input(self, fm):
        assert fm._clean_orphan_tool_messages([]) == []

    def test_preserves_message_order(self, fm):
        msgs = [
            make_msg("system", "sys"),
            make_msg("user", "q1"),
            make_assistant("a1"),
            make_msg("user", "q2"),
            make_assistant_with_tool_calls("calling", [
                {"id": "c1", "type": "function", "function": {"name": "Read", "arguments": "{}"}}
            ]),
            make_tool_result("c1", "result"),
            make_assistant("summary"),
        ]
        result = fm._clean_orphan_tool_messages(msgs)
        assert result == msgs  # all valid, order preserved


# ── ForkManager.build_fork_messages ──────────────────────────────────────

class TestBuildForkMessages:
    @pytest.fixture
    def fm(self):
        sm = MagicMock(spec=SessionManager)
        tc = MagicMock(spec=TokenCalculator)
        return ForkManager(session_manager=sm, token_calculator=tc)

    def test_replaces_placeholder_with_task(self, fm):
        msgs = [
            make_msg("system", "sys"),
            make_msg("user", FORK_PLACEHOLDER),
        ]
        ctx = ForkContext(
            parent_session_id="p",
            inherited_messages=msgs,
            placeholder_index=1,
        )
        result = fm.build_fork_messages(ctx, "actual task here")
        assert result[1]["role"] == "user"
        assert result[1]["content"] == "actual task here"

    def test_replaces_only_placeholder(self, fm):
        msgs = [
            make_msg("user", "not a placeholder"),
            make_msg("user", FORK_PLACEHOLDER),
            make_msg("user", "also not"),
        ]
        ctx = ForkContext(
            parent_session_id="p",
            inherited_messages=msgs,
            placeholder_index=1,
        )
        result = fm.build_fork_messages(ctx, "task")
        assert result[0]["content"] == "not a placeholder"
        assert result[1]["content"] == "task"
        assert result[2]["content"] == "also not"

    def test_does_not_modify_without_placeholder(self, fm):
        msgs = [
            make_msg("system", "sys"),
            make_msg("user", "some task"),
        ]
        ctx = ForkContext(
            parent_session_id="p",
            inherited_messages=msgs,
            placeholder_index=-1,
        )
        result = fm.build_fork_messages(ctx, "ignored task")
        assert result == msgs  # unchanged

    def test_returns_new_list_not_mutation(self, fm):
        msgs = [make_msg("user", FORK_PLACEHOLDER)]
        ctx = ForkContext(
            parent_session_id="p",
            inherited_messages=msgs,
            placeholder_index=0,
        )
        result = fm.build_fork_messages(ctx, "task")
        assert result is not msgs  # new list
        assert msgs[0]["content"] == FORK_PLACEHOLDER  # original unchanged


# ── ForkManager.is_in_fork_child ─────────────────────────────────────────

class TestIsInForkChild:
    @pytest.fixture
    def fm(self):
        sm = MagicMock(spec=SessionManager)
        tc = MagicMock(spec=TokenCalculator)
        return ForkManager(session_manager=sm, token_calculator=tc)

    def test_detects_fork_by_system_message(self, fm):
        msgs = [
            make_msg("system", FORK_CHILD_BOILERPLATE),
            make_msg("user", "do something"),
        ]
        assert fm.is_in_fork_child(msgs) is True

    def test_detects_fork_by_placeholder(self, fm):
        msgs = [
            make_msg("system", "normal system"),
            make_msg("user", FORK_PLACEHOLDER),
        ]
        assert fm.is_in_fork_child(msgs) is True

    def test_returns_false_for_normal_messages(self, fm):
        msgs = [
            make_msg("system", "You are helpful"),
            make_msg("user", "hello"),
            make_msg("assistant", "hi"),
        ]
        assert fm.is_in_fork_child(msgs) is False

    def test_returns_false_for_empty(self, fm):
        assert fm.is_in_fork_child([]) is False

    def test_returns_false_for_non_string_content(self, fm):
        """Content that isn't a string should not crash."""
        msgs = [{"role": "system", "content": None}]
        assert fm.is_in_fork_child(msgs) is False

    def test_partial_fork_tag_not_detected(self, fm):
        msgs = [
            make_msg("system", "This mentions fork but without tag"),
            make_msg("user", "fork mode"),
        ]
        # "<fork>" is the tag, not "fork"
        assert fm.is_in_fork_child(msgs) is False


# ── ForkManager.get_fork_stats ───────────────────────────────────────────

class TestGetForkStats:
    @pytest.fixture
    def fm(self):
        sm = MagicMock(spec=SessionManager)
        tc = MagicMock(spec=TokenCalculator)
        return ForkManager(session_manager=sm, token_calculator=tc)

    def test_returns_correct_stats(self, fm):
        msgs = [make_msg("user", "hello")]
        ctx = ForkContext(
            parent_session_id="parent-1",
            inherited_messages=msgs,
            placeholder_index=1,
        )
        stats = fm.get_fork_stats(ctx)
        assert stats["parent_session_id"] == "parent-1"
        assert stats["message_count"] == 1
        assert stats["placeholder_index"] == 1
        assert stats["is_fork_child"] is True


# ── ForkManager.create_fork_context (integration with mocks) ─────────────

class TestCreateForkContext:
    """Test create_fork_context with mocked SessionManager and TokenCalculator."""

    @pytest.fixture
    def mock_session(self):
        """Mock a Session object."""
        from sessions.models import Session
        return Session(
            id="session-1",
            name="test",
            model="deepseek-chat",
            system_prompt="You are helpful",
        )

    @pytest.fixture
    def sample_messages(self):
        return [
            make_msg("system", "You are helpful"),
            make_msg("user", "Hello"),
            make_msg("assistant", "Hi! How can I help?"),
        ]

    @pytest.fixture
    def fm_with_session(self, mock_session, sample_messages):
        sm = MagicMock(spec=SessionManager)
        sm.get_session.return_value = mock_session
        sm.get_messages_openai.return_value = list(sample_messages)

        tc = MagicMock(spec=TokenCalculator)
        tc.count_messages.return_value = 500  # well under 32000

        return ForkManager(session_manager=sm, token_calculator=tc), sm

    def test_returns_none_when_session_not_found(self):
        sm = MagicMock(spec=SessionManager)
        sm.get_session.return_value = None
        tc = MagicMock(spec=TokenCalculator)
        fm = ForkManager(session_manager=sm, token_calculator=tc)

        result = fm.create_fork_context("nonexistent")
        assert result is None

    def test_returns_none_when_no_messages(self):
        sm = MagicMock(spec=SessionManager)
        sm.get_session.return_value = MagicMock()
        sm.get_messages_openai.return_value = []
        tc = MagicMock(spec=TokenCalculator)
        fm = ForkManager(session_manager=sm, token_calculator=tc)

        result = fm.create_fork_context("empty-session")
        assert result is None

    def test_creates_fork_context_success(self, fm_with_session):
        fm, sm = fm_with_session
        result = fm.create_fork_context("session-1")

        assert result is not None
        assert isinstance(result, ForkContext)
        assert result.parent_session_id == "session-1"
        assert result.is_fork_child is True
        assert result.placeholder_index == len(result.inherited_messages) - 1

    def test_inherited_messages_contain_boilerplate(self, fm_with_session):
        fm, sm = fm_with_session
        result = fm.create_fork_context("session-1")

        assert result is not None
        # First message should be FORK_CHILD_BOILERPLATE system message
        assert result.inherited_messages[0]["role"] == "system"
        assert result.inherited_messages[0]["content"] == FORK_CHILD_BOILERPLATE

    def test_inherited_messages_contain_parent_system_prompt(self, fm_with_session):
        fm, sm = fm_with_session
        result = fm.create_fork_context("session-1")

        assert result is not None
        # Second message should be parent's system prompt
        assert result.inherited_messages[1]["role"] == "system"
        assert result.inherited_messages[1]["content"] == "You are helpful"

    def test_last_message_is_placeholder(self, fm_with_session):
        fm, sm = fm_with_session
        result = fm.create_fork_context("session-1")

        assert result is not None
        last_msg = result.inherited_messages[-1]
        assert last_msg["role"] == "user"
        assert last_msg["content"] == FORK_PLACEHOLDER

    def test_include_system_prompt_false(self, mock_session, sample_messages):
        sm = MagicMock(spec=SessionManager)
        sm.get_session.return_value = mock_session
        sm.get_messages_openai.return_value = list(sample_messages)
        tc = MagicMock(spec=TokenCalculator)
        tc.count_messages.return_value = 500
        fm = ForkManager(session_manager=sm, token_calculator=tc)

        result = fm.create_fork_context("session-1", include_system_prompt=False)
        assert result is not None
        # Without parent system prompt, messages should start with boilerplate then user msg
        # The boilerplate is always first
        assert result.inherited_messages[0]["content"] == FORK_CHILD_BOILERPLATE
        # But parent system prompt should NOT be second — it should be user msg directly
        roles = [m["role"] for m in result.inherited_messages[1:] if m["content"] != FORK_PLACEHOLDER]
        # No extra system message (parent system prompt excluded)
        system_count = sum(1 for m in result.inherited_messages if m["role"] == "system")
        assert system_count == 1  # only boilerplate

    def test_truncation_applied_when_over_limit(self, mock_session):
        """When message tokens exceed max_tokens, SlidingWindowStrategy is applied."""
        sm = MagicMock(spec=SessionManager)
        sm.get_session.return_value = mock_session
        # Return many messages
        msgs = [make_msg("user", f"msg {i}") for i in range(100)]
        sm.get_messages_openai.return_value = msgs

        tc = MagicMock(spec=TokenCalculator)
        tc.count_messages.return_value = 50000  # over 32000

        fm = ForkManager(session_manager=sm, token_calculator=tc)

        with patch.object(fm._sliding_window, 'truncate_messages') as mock_truncate:
            mock_truncate.return_value = msgs[:10]  # truncated
            result = fm.create_fork_context("session-1", max_tokens=32000)
            mock_truncate.assert_called_once()

        assert result is not None

    def test_no_truncation_when_under_limit(self, fm_with_session):
        fm, sm = fm_with_session
        with patch.object(fm._sliding_window, 'truncate_messages') as mock_truncate:
            result = fm.create_fork_context("session-1", max_tokens=32000)
            mock_truncate.assert_not_called()

        assert result is not None

    def test_cleans_orphan_messages_before_truncation(self, mock_session):
        """_clean_orphan_tool_messages is called before token counting."""
        sm = MagicMock(spec=SessionManager)
        sm.get_session.return_value = mock_session
        sm.get_messages_openai.return_value = [make_msg("user", "hi")]

        tc = MagicMock(spec=TokenCalculator)
        tc.count_messages.return_value = 100

        fm = ForkManager(session_manager=sm, token_calculator=tc)

        with patch.object(fm, '_clean_orphan_tool_messages', wraps=fm._clean_orphan_tool_messages) as spy:
            fm.create_fork_context("session-1")
            spy.assert_called_once()

    def test_custom_max_tokens(self, mock_session):
        sm = MagicMock(spec=SessionManager)
        sm.get_session.return_value = mock_session
        sm.get_messages_openai.return_value = [make_msg("user", "hi")]
        tc = MagicMock(spec=TokenCalculator)
        tc.count_messages.return_value = 500
        fm = ForkManager(session_manager=sm, token_calculator=tc)

        result = fm.create_fork_context("session-1", max_tokens=8000)
        assert result is not None
        assert result.max_inherited_tokens == 8000
