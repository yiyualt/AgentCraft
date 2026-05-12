"""Hooks System - Lifecycle event handlers.

Fires shell commands at lifecycle events (PreToolUse, SessionStart, etc.).
Blocking hooks can veto tool execution. Hook failures don't crash the agent.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("gateway")


# ============================================================
# Event Types
# ============================================================

class HookEvent(Enum):
    # Tool execution
    PRE_TOOL_USE = "PreToolUse"
    POST_TOOL_USE = "PostToolUse"
    POST_TOOL_USE_FAILURE = "PostToolUseFailure"

    # Session
    SESSION_START = "SessionStart"
    SESSION_END = "SessionEnd"
    SETUP = "Setup"

    # Sub-agent
    SUBAGENT_START = "SubagentStart"
    SUBAGENT_STOP = "SubagentStop"

    # Compaction
    PRE_COMPACT = "PreCompact"
    POST_COMPACT = "PostCompact"

    # Permission
    PERMISSION_REQUEST = "PermissionRequest"
    PERMISSION_DENIED = "PermissionDenied"

    # Stop
    STOP = "Stop"
    STOP_FAILURE = "StopFailure"

    # Task
    TASK_CREATED = "TaskCreated"
    TASK_COMPLETED = "TaskCompleted"

    # File
    FILE_CHANGED = "FileChanged"
    CONFIG_CHANGED = "ConfigChange"

    # User interaction
    USER_PROMPT_SUBMIT = "UserPromptSubmit"
    INSTRUCTIONS_LOADED = "InstructionsLoaded"


# ============================================================
# Hook Data Classes
# ============================================================

@dataclass
class HookInput:
    event: HookEvent
    tool_name: str | None = None
    args: dict | None = None
    result: str | None = None
    error: str | None = None
    session_id: str | None = None
    agent_type: str | None = None
    timestamp: float = field(default_factory=time.time)


@dataclass
class HookOutput:
    status: str = "success"          # "success" / "failure" / "blocked"
    message: str | None = None
    decision: str | None = None      # "allow" / "deny" / "ask"
    exit_code: int | None = None


@dataclass
class HookMatcher:
    event: HookEvent
    command: str
    matcher: str | None = None       # Tool name or path pattern to match
    timeout: int = 30
    blocking: bool = False           # Can veto execution when True


# ============================================================
# Hook Executor
# ============================================================

class HookExecutor:
    """Executes matching hooks at lifecycle events."""

    def __init__(self, hooks: list[HookMatcher] | None = None):
        self._hooks: list[HookMatcher] = hooks or []

    def register(self, hook: HookMatcher) -> None:
        self._hooks.append(hook)
        logger.info(f"[Hook] Registered: {hook.event.value} → {hook.command}")

    def unregister(self, event: HookEvent, matcher: str | None = None) -> None:
        self._hooks = [
            h for h in self._hooks
            if not (h.event == event and (h.matcher == matcher or matcher is None))
        ]

    def clear(self) -> None:
        self._hooks.clear()

    async def execute(self, event: HookEvent, input_data: HookInput) -> HookOutput | None:
        matched = self._find_matching(event, input_data)
        if not matched:
            return None

        for hook in matched:
            output = await self._run_hook(hook, input_data)
            if hook.blocking and output.status == "blocked":
                return output

        return HookOutput(status="success")

    def _find_matching(self, event: HookEvent, input_data: HookInput) -> list[HookMatcher]:
        matched = []
        for hook in self._hooks:
            if hook.event != event:
                continue
            if hook.matcher and input_data.tool_name:
                if not self._match_pattern(hook.matcher, input_data.tool_name):
                    continue
            matched.append(hook)
        return matched

    @staticmethod
    def _match_pattern(pattern: str, value: str) -> bool:
        import fnmatch
        return fnmatch.fnmatch(value.lower(), pattern.lower())

    async def _run_hook(self, hook: HookMatcher, input_data: HookInput) -> HookOutput:
        try:
            input_json = json.dumps({
                "event": input_data.event.value,
                "tool_name": input_data.tool_name,
                "args": input_data.args,
                "result": input_data.result,
                "session_id": input_data.session_id,
                "timestamp": input_data.timestamp,
            })

            proc = await asyncio.create_subprocess_shell(
                hook.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input_json.encode()),
                timeout=hook.timeout,
            )

            if stdout:
                try:
                    data = json.loads(stdout.decode())
                    return HookOutput(
                        status=data.get("status", "success"),
                        message=data.get("message"),
                        decision=data.get("decision"),
                        exit_code=proc.returncode,
                    )
                except json.JSONDecodeError:
                    return HookOutput(
                        status="success",
                        message=stdout.decode()[:1000],
                        exit_code=proc.returncode,
                    )

            return HookOutput(status="success", exit_code=proc.returncode)

        except asyncio.TimeoutError:
            logger.warning(f"[Hook] Timeout ({hook.timeout}s): {hook.command}")
            return HookOutput(status="failure", message="Hook timed out")

        except Exception as e:
            logger.error(f"[Hook] Error: {e}")
            return HookOutput(status="failure", message=str(e))


# ============================================================
# Public API
# ============================================================

__all__ = [
    "HookEvent",
    "HookInput",
    "HookOutput",
    "HookMatcher",
    "HookExecutor",
]
