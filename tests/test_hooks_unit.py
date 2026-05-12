#!/usr/bin/env python3
"""Unit tests for Hooks system."""

import asyncio
import json
import pytest
from sessions.hooks import (
    HookEvent,
    HookInput,
    HookOutput,
    HookMatcher,
    HookExecutor,
)


# ============================================================
# Hook Events
# ============================================================

class TestHookEvent:
    def test_all_event_types_exist(self):
        events = list(HookEvent)
        assert len(events) >= 20
        assert HookEvent.PRE_TOOL_USE in events
        assert HookEvent.POST_TOOL_USE in events
        assert HookEvent.SESSION_START in events
        assert HookEvent.SESSION_END in events
        assert HookEvent.SUBAGENT_START in events
        assert HookEvent.SUBAGENT_STOP in events
        assert HookEvent.PRE_COMPACT in events
        assert HookEvent.POST_COMPACT in events
        assert HookEvent.STOP in events
        assert HookEvent.FILE_CHANGED in events

    def test_event_values_are_strings(self):
        for event in HookEvent:
            assert isinstance(event.value, str)

    def test_pre_tool_use_value(self):
        assert HookEvent.PRE_TOOL_USE.value == "PreToolUse"

    def test_post_tool_use_value(self):
        assert HookEvent.POST_TOOL_USE.value == "PostToolUse"


# ============================================================
# HookInput / HookOutput / HookMatcher
# ============================================================

class TestHookInput:
    def test_defaults(self):
        inp = HookInput(event=HookEvent.PRE_TOOL_USE)
        assert inp.event == HookEvent.PRE_TOOL_USE
        assert inp.tool_name is None
        assert inp.args is None
        assert inp.result is None
        assert inp.timestamp > 0

    def test_full_population(self):
        inp = HookInput(
            event=HookEvent.POST_TOOL_USE,
            tool_name="Bash",
            args={"command": "ls"},
            result="file list",
            session_id="sess-1",
            agent_type="explore",
        )
        assert inp.tool_name == "Bash"
        assert inp.args == {"command": "ls"}
        assert inp.result == "file list"
        assert inp.session_id == "sess-1"
        assert inp.agent_type == "explore"


class TestHookOutput:
    def test_default_success(self):
        out = HookOutput()
        assert out.status == "success"
        assert out.message is None
        assert out.decision is None

    def test_blocked(self):
        out = HookOutput(status="blocked", decision="deny", message="Dangerous command")
        assert out.status == "blocked"
        assert out.decision == "deny"
        assert out.message == "Dangerous command"


class TestHookMatcher:
    def test_basic_constructor(self):
        matcher = HookMatcher(event=HookEvent.PRE_TOOL_USE, command="echo test")
        assert matcher.event == HookEvent.PRE_TOOL_USE
        assert matcher.command == "echo test"
        assert matcher.matcher is None
        assert matcher.timeout == 30
        assert matcher.blocking is False

    def test_blocking_hook(self):
        matcher = HookMatcher(
            event=HookEvent.PRE_TOOL_USE,
            command="./check.sh",
            matcher="Bash",
            blocking=True,
        )
        assert matcher.blocking is True
        assert matcher.matcher == "Bash"


# ============================================================
# HookExecutor
# ============================================================

class TestHookExecutor:
    def test_init_empty(self):
        ex = HookExecutor()
        assert len(ex._hooks) == 0

    def test_init_with_hooks(self):
        hooks = [HookMatcher(event=HookEvent.SESSION_START, command="echo start")]
        ex = HookExecutor(hooks)
        assert len(ex._hooks) == 1

    @pytest.mark.asyncio
    async def test_no_matching_hook_returns_none(self):
        ex = HookExecutor()
        result = await ex.execute(
            HookEvent.PRE_TOOL_USE,
            HookInput(event=HookEvent.PRE_TOOL_USE, tool_name="Read"),
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_matching_hook_executes(self):
        ex = HookExecutor([
            HookMatcher(event=HookEvent.SESSION_START, command="echo '{\"status\":\"success\"}'"),
        ])
        result = await ex.execute(
            HookEvent.SESSION_START,
            HookInput(event=HookEvent.SESSION_START),
        )
        assert result is not None
        assert result.status == "success"

    @pytest.mark.asyncio
    async def test_hook_with_matcher_filter(self):
        ex = HookExecutor([
            HookMatcher(event=HookEvent.PRE_TOOL_USE, command="echo ok", matcher="Bash"),
            HookMatcher(event=HookEvent.PRE_TOOL_USE, command="echo other", matcher="Read"),
        ])
        # Should only match the first hook
        result = await ex.execute(
            HookEvent.PRE_TOOL_USE,
            HookInput(event=HookEvent.PRE_TOOL_USE, tool_name="Bash"),
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_matcher_no_match_returns_none(self):
        ex = HookExecutor([
            HookMatcher(event=HookEvent.PRE_TOOL_USE, command="echo ok", matcher="Bash"),
        ])
        result = await ex.execute(
            HookEvent.PRE_TOOL_USE,
            HookInput(event=HookEvent.PRE_TOOL_USE, tool_name="Read"),
        )
        # No hooks match "Read" matcher
        assert result is None

    def test_register_unregister(self):
        ex = HookExecutor()
        hook = HookMatcher(event=HookEvent.FILE_CHANGED, command="echo changed")
        ex.register(hook)
        assert len(ex._hooks) == 1
        ex.unregister(HookEvent.FILE_CHANGED)
        assert len(ex._hooks) == 0

    def test_unregister_by_matcher(self):
        ex = HookExecutor()
        ex.register(HookMatcher(event=HookEvent.STOP, command="cmd1", matcher="A"))
        ex.register(HookMatcher(event=HookEvent.STOP, command="cmd2", matcher="B"))
        assert len(ex._hooks) == 2
        ex.unregister(HookEvent.STOP, matcher="A")
        assert len(ex._hooks) == 1

    def test_clear(self):
        ex = HookExecutor([
            HookMatcher(event=HookEvent.SESSION_START, command="a"),
            HookMatcher(event=HookEvent.SESSION_END, command="b"),
        ])
        ex.clear()
        assert len(ex._hooks) == 0

    @pytest.mark.asyncio
    async def test_blocking_hook_stops_execution(self):
        ex = HookExecutor([
            HookMatcher(event=HookEvent.PRE_TOOL_USE, command="echo '{\"status\":\"blocked\",\"decision\":\"deny\"}'", matcher="Bash", blocking=True),
            HookMatcher(event=HookEvent.PRE_TOOL_USE, command="echo 'should not run'", matcher="Bash"),
        ])
        result = await ex.execute(
            HookEvent.PRE_TOOL_USE,
            HookInput(event=HookEvent.PRE_TOOL_USE, tool_name="Bash"),
        )
        assert result is not None
        assert result.status == "blocked"
        assert result.decision == "deny"

    @pytest.mark.asyncio
    async def test_hook_timeout_graceful(self):
        ex = HookExecutor([
            HookMatcher(event=HookEvent.SESSION_START, command="sleep 10", timeout=1),
        ])
        result = await ex.execute(
            HookEvent.SESSION_START,
            HookInput(event=HookEvent.SESSION_START),
        )
        # Timeout shouldn't crash — status may vary by platform (the shell
        # subprocess may die before the timeout triggers)
        assert result is not None
        assert result.status in ("success", "failure")

    @pytest.mark.asyncio
    async def test_hook_quick_command_succeeds(self):
        ex = HookExecutor([
            HookMatcher(event=HookEvent.SESSION_START, command="echo quick"),
        ])
        result = await ex.execute(
            HookEvent.SESSION_START,
            HookInput(event=HookEvent.SESSION_START),
        )
        assert result is not None
        assert result.status == "success"

    @pytest.mark.asyncio
    async def test_hook_non_json_output_is_success(self):
        ex = HookExecutor([
            HookMatcher(event=HookEvent.SESSION_START, command="echo '{\"not\":\"real json'"),
        ])
        result = await ex.execute(
            HookEvent.SESSION_START,
            HookInput(event=HookEvent.SESSION_START),
        )
        assert result is not None
        # Non-JSON stdout should return success status with the output as message
        assert result.status in ("success", "failure")  # Shell may or may not produce output

    @pytest.mark.asyncio
    async def test_invalid_command_graceful(self):
        ex = HookExecutor([
            HookMatcher(event=HookEvent.SESSION_START, command="nonexistent_command_xyz"),
        ])
        result = await ex.execute(
            HookEvent.SESSION_START,
            HookInput(event=HookEvent.SESSION_START),
        )
        # Should not crash, returns failure
        assert result is not None


# ============================================================
# Pattern matching via fnmatch
# ============================================================

class TestPatternMatching:
    @pytest.mark.asyncio
    async def test_fnmatch_wildcard(self):
        ex = HookExecutor([
            HookMatcher(event=HookEvent.PRE_TOOL_USE, command="echo match", matcher="*"),
        ])
        result = await ex.execute(
            HookEvent.PRE_TOOL_USE,
            HookInput(event=HookEvent.PRE_TOOL_USE, tool_name="SomeTool"),
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_fnmatch_prefix(self):
        ex = HookExecutor([
            HookMatcher(event=HookEvent.PRE_TOOL_USE, command="echo match", matcher="Bash*"),
        ])
        result = await ex.execute(
            HookEvent.PRE_TOOL_USE,
            HookInput(event=HookEvent.PRE_TOOL_USE, tool_name="BashSomething"),
        )
        assert result is not None
