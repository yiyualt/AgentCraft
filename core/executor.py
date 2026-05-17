"""Tool Executor - handles tool execution with concurrency control.

Provides:
- Parallel execution for SAFE tools
- Sequential execution for UNSAFE tools
- SSE progress events for streaming
- Hook integration for PreToolUse/PostToolUse events
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from core.concurrency import is_safe

logger = logging.getLogger("gateway")


@dataclass
class ToolResult:
    """Result of a tool execution."""
    tool_call_id: str
    tool_name: str
    content: str = ""
    error: str | None = None
    duration_ms: int = 0

    def to_tool_message(self) -> dict[str, Any]:
        """Convert to OpenAI tool message format."""
        return {
            "role": "tool",
            "tool_call_id": self.tool_call_id,
            "content": self.error or self.content,
        }


class ToolExecutor:
    """Execute tool calls with concurrency control.

    Simple execution model:
    - SAFE tools: start immediately, run in parallel
    - UNSAFE tools: queue and run sequentially
    - Wait for all to complete before returning
    - Hooks: PreToolUse (can block), PostToolUse (audit)
    """

    def __init__(
        self,
        registry: Any,  # UnifiedToolRegistry
        session_id: str | None = None,
        canvas_manager: Any | None = None,
        hook_executor: Any | None = None,  # HookExecutor
    ):
        self._registry = registry
        self._session_id = session_id
        self._canvas_manager = canvas_manager
        self._hook_executor = hook_executor
        self._results: dict[str, ToolResult] = {}
        self._pending_tasks: list[asyncio.Task] = []
        self._unsafe_queue: asyncio.Queue = asyncio.Queue()
        self._unsafe_executor_started = False

    async def execute_tools(self, tool_calls: list[dict]) -> dict[str, ToolResult]:
        """Execute a batch of tool calls.

        Args:
            tool_calls: List of OpenAI tool_calls from LLM response

        Returns:
            Dict mapping tool_call_id to ToolResult
        """
        self._results.clear()
        self._pending_tasks.clear()

        # Start unsafe executor
        if not self._unsafe_executor_started:
            asyncio.create_task(self._run_unsafe_queue())
            self._unsafe_executor_started = True

        # Submit all tools
        for tc in tool_calls:
            tc_id = tc["id"]
            fn_name = tc["function"]["name"]
            try:
                fn_args = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                fn_args = {}

            logger.info(f"[EXECUTOR] Tool: {fn_name} safe={is_safe(fn_name)}")

            if is_safe(fn_name):
                # Safe tool: execute immediately
                task = asyncio.create_task(
                    self._execute_tool(tc_id, fn_name, fn_args)
                )
                self._pending_tasks.append(task)
            else:
                # Unsafe tool: queue for sequential execution
                await self._unsafe_queue.put((tc_id, fn_name, fn_args))

        # Wait for all safe tools
        if self._pending_tasks:
            await asyncio.gather(*self._pending_tasks, return_exceptions=True)

        # Wait for unsafe queue to drain
        await self._unsafe_queue.join()

        return self._results

    async def _execute_tool(
        self,
        tool_call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        """Execute a single tool with hook integration."""
        started_at = time.time()

        # Set canvas context
        if self._canvas_manager and self._session_id:
            try:
                from canvas import set_current_session_id
                set_current_session_id(self._session_id)
            except ImportError:
                pass

            # Push progress: tool starting
            await self._push_progress(f"⏳ 正在执行 **{tool_name}**...", "append")

        # === PRE_TOOL_USE Hook ===
        if self._hook_executor:
            try:
                from sessions import HookEvent, HookInput
                hook_input = HookInput(
                    event=HookEvent.PRE_TOOL_USE,
                    tool_name=tool_name,
                    args=arguments,
                    session_id=self._session_id,
                )
                hook_output = await self._hook_executor.execute(
                    HookEvent.PRE_TOOL_USE, hook_input
                )
                if hook_output and hook_output.status == "blocked":
                    logger.warning(f"[EXECUTOR] Tool {tool_name} blocked by hook")
                    duration_ms = int((time.time() - started_at) * 1000)
                    blocked_result = ToolResult(
                        tool_call_id=tool_call_id,
                        tool_name=tool_name,
                        error=f"Blocked by hook: {hook_output.message or 'Policy restriction'}",
                        duration_ms=duration_ms,
                    )
                    self._results[tool_call_id] = blocked_result
                    return blocked_result
            except Exception as e:
                logger.warning(f"[EXECUTOR] PreToolUse hook error: {e}")

        try:
            result = await self._registry.dispatch(tool_name, arguments)

            duration_ms = int((time.time() - started_at) * 1000)

            tool_result = ToolResult(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                content=result,
                duration_ms=duration_ms,
            )
            self._results[tool_call_id] = tool_result

            # === POST_TOOL_USE Hook ===
            if self._hook_executor:
                try:
                    from sessions import HookEvent, HookInput
                    hook_input = HookInput(
                        event=HookEvent.POST_TOOL_USE,
                        tool_name=tool_name,
                        args=arguments,
                        result=result,
                        session_id=self._session_id,
                    )
                    await self._hook_executor.execute(HookEvent.POST_TOOL_USE, hook_input)
                except Exception as e:
                    logger.warning(f"[EXECUTOR] PostToolUse hook error: {e}")

            # Push progress: tool completed
            if self._canvas_manager and self._session_id:
                await self._push_progress(
                    f"✅ 完成 **{tool_name}** (耗时 {duration_ms}ms)",
                    "append"
                )

            logger.info(f"[EXECUTOR] Complete: {tool_name} duration={duration_ms}ms")
            return tool_result

        except Exception as e:
            duration_ms = int((time.time() - started_at) * 1000)
            error_msg = str(e)

            tool_result = ToolResult(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                error=error_msg,
                duration_ms=duration_ms,
            )
            self._results[tool_call_id] = tool_result

            # === POST_TOOL_USE_FAILURE Hook ===
            if self._hook_executor:
                try:
                    from sessions import HookEvent, HookInput
                    hook_input = HookInput(
                        event=HookEvent.POST_TOOL_USE_FAILURE,
                        tool_name=tool_name,
                        args=arguments,
                        error=error_msg,
                        session_id=self._session_id,
                    )
                    await self._hook_executor.execute(HookEvent.POST_TOOL_USE_FAILURE, hook_input)
                except Exception as e:
                    logger.warning(f"[EXECUTOR] PostToolUseFailure hook error: {e}")

            # Push progress: tool failed
            if self._canvas_manager and self._session_id:
                await self._push_progress(
                    f"❌ **{tool_name}** 执行失败: {error_msg}",
                    "append"
                )

            logger.error(f"[EXECUTOR] Error: {tool_name} - {error_msg}")
            return tool_result

        finally:
            # Clear canvas context
            if self._canvas_manager:
                try:
                    from canvas import set_current_session_id
                    set_current_session_id(None)
                except ImportError:
                    pass

    async def _push_progress(self, content: str, action: str = "append") -> None:
        """Push progress update to canvas via SSE."""
        if not self._canvas_manager or not self._session_id:
            return

        try:
            await self._canvas_manager.push_update(
                session_id=self._session_id,
                content=content,
                mode="markdown",
                section="main",
                action=action,
            )
        except Exception as e:
            logger.debug(f"[EXECUTOR] Failed to push progress: {e}")

    async def _run_unsafe_queue(self) -> None:
        """Process unsafe tools sequentially."""
        while True:
            try:
                tc_id, tool_name, arguments = await self._unsafe_queue.get()
                await self._execute_tool(tc_id, tool_name, arguments)
                self._unsafe_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[EXECUTOR] Unsafe queue error: {e}")
                self._unsafe_queue.task_done()

    def get_tool_messages(self) -> list[dict[str, Any]]:
        """Get all results as OpenAI tool messages."""
        return [r.to_tool_message() for r in self._results.values()]


__all__ = ["ToolExecutor", "ToolResult"]