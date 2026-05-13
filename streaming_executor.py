"""Streaming Tool Executor - Parallel tool execution during API streaming.

This module implements Claude Code's key performance advantage: executing tools
while the API response is still streaming, rather than waiting for complete response.

Key components:
- StreamingToolExecutor: Manages parallel tool execution
- ConcurrencySafety: Classifies tools as safe or unsafe for parallel execution
- ToolResult: Result container for tool execution
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

logger = logging.getLogger("gateway")


# ---- Concurrency Safety Classification ----

CONCURRENCY_SAFE_TOOLS = frozenset({
    # Read-only tools - safe to run in parallel
    "Read", "Glob", "Grep", "WebFetch", "WebSearch",
    "CountTokens", "NotebookEdit",
    # MCP read tools (if available)
    "mcp__web-reader__webReader", "mcp__zread__get_repo_structure",
    "mcp__zread__read_file", "mcp__zread__search_doc",
})

CONCURRENCY_UNSAFE_TOOLS = frozenset({
    # File modification - need serialization to prevent conflicts
    "Write", "Edit",
    # Shell execution - need serialization to prevent race conditions
    "Bash",
    # Agent delegation - need serialization to prevent recursive spawning
    "Agent", "Skill",
})

CASCADE_ON_ERROR_TOOLS = frozenset({
    # Tools that should cancel siblings on error
    "Bash",
})


def is_concurrency_safe(tool_name: str) -> bool:
    """Check if a tool can be executed concurrently with other tools.

    Args:
        tool_name: Name of the tool

    Returns:
        True if the tool is safe for parallel execution
    """
    # Known safe tools
    if tool_name in CONCURRENCY_SAFE_TOOLS:
        return True

    # Known unsafe tools
    if tool_name in CONCURRENCY_UNSAFE_TOOLS:
        return False

    # MCP tools: check prefix
    if tool_name.startswith("mcp__"):
        # MCP read tools are typically safe
        # MCP write tools should be unsafe
        return tool_name in CONCURRENCY_SAFE_TOOLS

    # Unknown tools: default to unsafe (fail-closed)
    return False


def cascades_on_error(tool_name: str) -> bool:
    """Check if tool error should cancel sibling executions.

    Args:
        tool_name: Name of the tool

    Returns:
        True if error should cascade to cancel siblings
    """
    return tool_name in CASCADE_ON_ERROR_TOOLS


# ---- Tool Result Container ----

@dataclass
class ToolResult:
    """Result of a tool execution."""

    tool_call_id: str
    tool_name: str
    content: str = ""
    error: str | None = None
    duration_ms: int = 0
    started_at: float = field(default_factory=time.time)

    def to_tool_message(self) -> dict[str, Any]:
        """Convert to OpenAI tool message format."""
        return {
            "role": "tool",
            "tool_call_id": self.tool_call_id,
            "content": self.error or self.content,
        }


# ---- Progress Events ----

@dataclass
class ToolProgressEvent:
    """Event emitted during tool execution."""

    type: str  # "tool_start", "tool_progress", "tool_complete", "tool_error"
    tool_call_id: str
    tool_name: str
    timestamp: float = field(default_factory=time.time)
    progress: str | None = None
    result: str | None = None
    error: str | None = None


# ---- Streaming Tool Executor ----

class StreamingToolExecutor:
    """Execute tools in parallel while API response is streaming.

    Key features:
    1. Starts tool execution immediately when tool_use block is parsed
    2. Runs concurrency-safe tools in parallel (up to max_concurrency)
    3. Queues unsafe tools for sequential execution
    4. Cascades cancellation on BashTool errors
    """

    def __init__(
        self,
        registry: Any,  # UnifiedToolRegistry
        max_concurrency: int = 10,
        session_id: str | None = None,
        sandbox_executor: Any | None = None,  # SandboxExecutor
        canvas_manager: Any | None = None,  # CanvasManager
        custom_dispatcher: Callable[[str, dict[str, Any]], Awaitable[str]] | None = None,
    ):
        self._registry = registry
        self._max_concurrency = max_concurrency
        self._session_id = session_id
        self._sandbox_executor = sandbox_executor
        self._canvas_manager = canvas_manager
        self._custom_dispatcher = custom_dispatcher

        # Pending tool executions
        self._pending_tasks: dict[str, asyncio.Task] = {}
        self._results: dict[str, ToolResult] = {}
        self._progress_events: list[ToolProgressEvent] = []

        # Unsafe tool queue (for sequential execution)
        self._unsafe_queue: asyncio.Queue = asyncio.Queue()
        self._unsafe_executor_task: asyncio.Task | None = None

        # Cascade cancellation
        self._cascade_cancelled: bool = False
        self._cascade_reason: str | None = None

        # Semaphore for concurrency limit
        self._semaphore: asyncio.Semaphore = asyncio.Semaphore(max_concurrency)

        logger.info(
            f"[STREAMING_EXECUTOR] Initialized: max_concurrency={max_concurrency}, "
            f"session={session_id}, sandbox={sandbox_executor is not None}"
        )

    def get_progress_events(self) -> list[ToolProgressEvent]:
        """Get all progress events emitted so far."""
        return self._progress_events.copy()

    async def emit_progress(self, event: ToolProgressEvent) -> None:
        """Emit a progress event.

        Events are stored in _progress_events list for later retrieval.
        In streaming mode, these can be yielded to the client.
        """
        self._progress_events.append(event)
        logger.debug(
            f"[STREAMING_EXECUTOR] Progress: {event.type} "
            f"tool={event.tool_name} id={event.tool_call_id}"
        )

    async def on_tool_use_block(
        self,
        tool_call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> None:
        """Handle a parsed tool_use block.

        This is called when streaming API emits a complete tool_use block.
        Immediately starts execution for safe tools, queues unsafe ones.

        Args:
            tool_call_id: Unique ID for this tool call
            tool_name: Name of the tool to invoke
            arguments: Tool arguments (parsed from JSON)
        """
        if self._cascade_cancelled:
            logger.warning(
                f"[STREAMING_EXECUTOR] Skipping {tool_name}: cascade cancelled "
                f"reason={self._cascade_reason}"
            )
            return

        # Emit start event
        await self.emit_progress(ToolProgressEvent(
            type="tool_start",
            tool_call_id=tool_call_id,
            tool_name=tool_name,
        ))

        if is_concurrency_safe(tool_name):
            # Safe tool: start immediately in parallel
            task = asyncio.create_task(
                self._execute_tool_safe(tool_call_id, tool_name, arguments)
            )
            self._pending_tasks[tool_call_id] = task
            logger.info(
                f"[STREAMING_EXECUTOR] Started safe tool: {tool_name} "
                f"id={tool_call_id}"
            )
        else:
            # Unsafe tool: queue for sequential execution
            await self._unsafe_queue.put((tool_call_id, tool_name, arguments))
            logger.info(
                f"[STREAMING_EXECUTOR] Queued unsafe tool: {tool_name} "
                f"id={tool_call_id}"
            )

    async def _execute_tool_safe(
        self,
        tool_call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        """Execute a concurrency-safe tool with semaphore control.

        Args:
            tool_call_id: Unique ID for this tool call
            tool_name: Name of the tool
            arguments: Tool arguments

        Returns:
            ToolResult with execution outcome
        """
        async with self._semaphore:
            return await self._execute_tool(tool_call_id, tool_name, arguments)

    async def _execute_tool(
        self,
        tool_call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        """Execute a single tool and record result.

        Args:
            tool_call_id: Unique ID for this tool call
            tool_name: Name of the tool
            arguments: Tool arguments

        Returns:
            ToolResult with execution outcome
        """
        started_at = time.time()

        # Set canvas session_id context before execution
        if self._canvas_manager:
            try:
                from canvas import set_current_session_id
                set_current_session_id(self._session_id)
            except ImportError:
                pass

        try:
            # Use custom dispatcher if provided (handles sandbox logic)
            if self._custom_dispatcher:
                result = await self._custom_dispatcher(tool_name, arguments)
            elif self._sandbox_executor:
                # Sandbox execution: get tool source code first
                tool_code = self._registry.get_source_code(tool_name)
                if tool_code is None:
                    # MCP tools cannot be sandboxed, fall back to direct dispatch
                    logger.warning(
                        f"[STREAMING_EXECUTOR] {tool_name} has no source code, "
                        "falling back to direct dispatch"
                    )
                    result = await self._registry.dispatch(tool_name, arguments)
                else:
                    logger.info(
                        f"[STREAMING_EXECUTOR] Executing {tool_name} in sandbox "
                        f"(code_len={len(tool_code)})"
                    )
                    sandbox_result = await self._sandbox_executor.run_tool(
                        tool_name, arguments, tool_code
                    )
                    if sandbox_result.success:
                        result = sandbox_result.output
                    else:
                        result = f"Error: {sandbox_result.error}"
            else:
                # Direct execution via registry
                result = await self._registry.dispatch(tool_name, arguments)

            duration_ms = int((time.time() - started_at) * 1000)

            tool_result = ToolResult(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                content=result,
                duration_ms=duration_ms,
            )

            # Store result
            self._results[tool_call_id] = tool_result

            # Emit complete event
            await self.emit_progress(ToolProgressEvent(
                type="tool_complete",
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                result=result[:500] if len(result) > 500 else result,  # Truncate
            ))

            logger.info(
                f"[STREAMING_EXECUTOR] Tool complete: {tool_name} "
                f"id={tool_call_id} duration={duration_ms}ms"
            )

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

            # Store result
            self._results[tool_call_id] = tool_result

            # Emit error event
            await self.emit_progress(ToolProgressEvent(
                type="tool_error",
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                error=error_msg,
            ))

            logger.error(
                f"[STREAMING_EXECUTOR] Tool error: {tool_name} "
                f"id={tool_call_id} error={error_msg}"
            )

            # Check for cascade cancellation
            if cascades_on_error(tool_name):
                self._cascade_cancel_all(f"{tool_name} error: {error_msg}")

            return tool_result

        finally:
            # Clear canvas session_id context after execution
            if self._canvas_manager:
                try:
                    from canvas import set_current_session_id
                    set_current_session_id(None)
                except ImportError:
                    pass

    def _cascade_cancel_all(self, reason: str) -> None:
        """Cancel all pending tool executions.

        Called when a tool that cascades_on_error fails.

        Args:
            reason: Reason for cancellation
        """
        self._cascade_cancelled = True
        self._cascade_reason = reason

        # Cancel all pending tasks
        for task_id, task in self._pending_tasks.items():
            if not task.done():
                task.cancel(reason)

        logger.warning(
            f"[STREAMING_EXECUTOR] Cascade cancel triggered: "
            f"reason={reason} cancelled={len(self._pending_tasks)}"
        )

    async def start_unsafe_executor(self) -> None:
        """Start the sequential executor for unsafe tools.

        Unsafe tools are executed one at a time from the queue.
        """
        if self._unsafe_executor_task is not None:
            return

        self._unsafe_executor_task = asyncio.create_task(self._run_unsafe_queue())

    async def _run_unsafe_queue(self) -> None:
        """Process unsafe tools sequentially from queue."""
        while True:
            try:
                # Get next unsafe tool from queue
                tool_call_id, tool_name, arguments = await self._unsafe_queue.get()

                if self._cascade_cancelled:
                    logger.warning(
                        f"[STREAMING_EXECUTOR] Skipping queued unsafe tool: "
                        f"{tool_name} cascade cancelled"
                    )
                    self._unsafe_queue.task_done()
                    continue

                # Execute unsafe tool
                result = await self._execute_tool(tool_call_id, tool_name, arguments)

                # Mark queue task done
                self._unsafe_queue.task_done()

            except asyncio.CancelledError:
                logger.info("[STREAMING_EXECUTOR] Unsafe executor cancelled")
                break
            except Exception as e:
                logger.error(f"[STREAMING_EXECUTOR] Unsafe executor error: {e}")
                break

    async def get_results(self) -> dict[str, ToolResult]:
        """Wait for all tools to complete and return results.

        Returns:
            Dict mapping tool_call_id to ToolResult
        """
        # Wait for safe tools
        if self._pending_tasks:
            await asyncio.gather(*self._pending_tasks.values(), return_exceptions=True)

        # Wait for unsafe queue to empty
        if self._unsafe_executor_task:
            await self._unsafe_queue.join()
            self._unsafe_executor_task.cancel()
            try:
                await self._unsafe_executor_task
            except asyncio.CancelledError:
                pass

        return self._results

    def get_tool_messages(self) -> list[dict[str, Any]]:
        """Get all tool results as OpenAI tool messages.

        Returns:
            List of tool messages for appending to conversation
        """
        return [r.to_tool_message() for r in self._results.values()]

    def cancel_all(self, reason: str = "user_cancelled") -> None:
        """Cancel all pending tool executions.

        Args:
            reason: Reason for cancellation
        """
        self._cascade_cancel_all(reason)


__all__ = [
    "StreamingToolExecutor",
    "ToolResult",
    "ToolProgressEvent",
    "is_concurrency_safe",
    "cascades_on_error",
    "CONCURRENCY_SAFE_TOOLS",
    "CONCURRENCY_UNSAFE_TOOLS",
    "CASCADE_ON_ERROR_TOOLS",
]