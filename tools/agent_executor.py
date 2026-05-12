"""Agent Executor - Sub-agent task delegation.

Provides the ability to delegate sub-tasks to specialized sub-agents.
Each sub-agent runs in its own context with focused tools and prompts.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any

from openai import OpenAI

from tools import UnifiedToolRegistry, get_default_registry
from sessions import (
    SessionManager, ForkContext, ForkManager, FORK_PLACEHOLDER,
    classify_error, get_retry_config, calculate_delay, ErrorKind,
    HookEvent, HookInput, HookMatcher, HookExecutor,
    GoalManager, check_stop_goal,
    PermissionChecker, PermissionResult, PermissionMode, DEFAULT_RULES,
)

# Use gateway logger to ensure logs go to gateway.log
logger = logging.getLogger("gateway")


# Agent type definitions
AGENT_TYPES = {
    "explore": {
        "description": "Fast read-only search agent for locating code. "
                       "Use it to find files by pattern, grep for symbols or keywords, "
                       "or answer 'where is X defined / which files reference Y.' "
                       "Do NOT use it for code review, design-doc auditing, "
                       "cross-file consistency checks, or open-ended analysis.",
        "tools": ["Glob", "Grep", "Read", "WebFetch"],
        "max_turns": 5,
    },
    "general-purpose": {
        "description": "General-purpose agent for researching complex questions, "
                       "searching for code, and executing multi-step tasks. "
                       "When you are not confident that you will find the right match "
                       "in the first few tries, use this agent to perform the search for you.",
        "tools": None,  # All tools available
        "max_turns": 10,
    },
    "plan": {
        "description": "Software architect agent for designing implementation plans. "
                       "Use this when you need to plan the implementation strategy for a task. "
                       "Returns step-by-step plans, identifies critical files, "
                       "and considers architectural trade-offs.",
        "tools": ["Glob", "Grep", "Read", "Write"],
        "max_turns": 8,
    },
}


class AgentExecutor:
    """Executes sub-agent tasks with dedicated context and tools."""

    def __init__(
        self,
        llm_client: OpenAI,
        registry: UnifiedToolRegistry,
        session_manager: SessionManager,
        model: str = "deepseek-chat",
        base_url: str = "",
        hooks: list[HookMatcher] | None = None,
    ):
        self._client = llm_client
        self._registry = registry
        self._session_manager = session_manager
        self._model = model
        self._base_url = base_url
        self._fork_manager: ForkManager | None = None
        self._hook_executor = HookExecutor(hooks or [])
        self._goal_manager = GoalManager()
        self._permission_checker = PermissionChecker(
            mode=PermissionMode.DEFAULT,
            rules=list(DEFAULT_RULES),
        )
        self._recent_tool_results: list[dict] = []

    def set_fork_manager(self, fork_manager: ForkManager) -> None:
        """Set the fork manager for context inheritance."""
        self._fork_manager = fork_manager
        logger.info("[AgentExecutor] Fork manager initialized")

    def get_fork_manager(self) -> ForkManager | None:
        """Get the current fork manager."""
        return self._fork_manager

    def set_hooks(self, hooks: list[HookMatcher]) -> None:
        self._hook_executor = HookExecutor(hooks)

    def get_hook_executor(self) -> HookExecutor:
        return self._hook_executor

    def set_goal(self, condition: str) -> str:
        return self._goal_manager.set_goal(condition)

    def clear_goal(self) -> str:
        return self._goal_manager.clear_goal()

    def get_goal(self) -> str | None:
        goal = self._goal_manager.get_goal()
        return goal.condition if goal else None

    def get_goal_manager(self) -> GoalManager:
        return self._goal_manager

    def set_permission_mode(self, mode: PermissionMode) -> None:
        self._permission_checker.mode = mode
        logger.info(f"[Permission] Mode set to {mode.value}")

    def get_permission_mode(self) -> PermissionMode:
        return self._permission_checker.mode

    def get_permission_checker(self) -> PermissionChecker:
        return self._permission_checker

    async def run(
        self,
        task: str,
        agent_type: str = "general-purpose",
        context: str | None = None,
        timeout: int = 180,  # Increased from 120 to 180
        fork_context: ForkContext | None = None,
        is_fork_child: bool = False,
    ) -> str:
        """Execute a sub-agent task.

        Args:
            task: The task description for the sub-agent
            agent_type: Type of agent (explore, general-purpose, plan)
            context: Optional context to pass to the sub-agent
            timeout: Maximum execution time in seconds (default: 180)
            fork_context: Optional fork context for inheriting parent conversation
            is_fork_child: Whether this is a fork child (disables Agent tool)

        Returns:
            Result from the sub-agent execution
        """
        # Recursive protection: fork children cannot spawn more agents
        if is_fork_child:
            logger.warning("[FORK] Fork child cannot spawn sub-agents, executing directly")

        if agent_type not in AGENT_TYPES:
            return f"[Error] Unknown agent type: {agent_type}. Available: {list(AGENT_TYPES.keys())}"

        agent_config = AGENT_TYPES[agent_type]
        start_time = time.time()

        # Build tool list (filter if specified)
        all_tools = self._registry.list_tools()
        if agent_config["tools"]:
            allowed_names = set(agent_config["tools"])
            tools = [t for t in all_tools if t["function"]["name"] in allowed_names]
        else:
            tools = all_tools

        # Fork children cannot use Agent tool (recursive protection)
        if is_fork_child:
            tools = [t for t in tools if t["function"]["name"] != "Agent"]
            logger.info(f"[FORK] Agent tool disabled for fork child, tools: {[t['function']['name'] for t in tools]}")

        # Build messages based on fork context or new context
        if fork_context:
            # Use fork context - inherited messages with placeholder replaced
            messages = fork_context.inherited_messages.copy()
            # Replace placeholder with actual task
            for i, msg in enumerate(messages):
                if msg.get("content") == FORK_PLACEHOLDER:
                    messages[i] = {"role": "user", "content": task}
                    logger.info(f"[FORK] Replaced placeholder with task at index {i}")
                    break
            logger.info(f"[FORK] Using fork context with {len(messages)} inherited messages")
        else:
            # Build new context from scratch
            system_prompt = self._build_system_prompt(agent_type, agent_config, context)
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": task},
            ]

        logger.info(f"[AgentExecutor] Starting {agent_type} agent for task: {task[:100]}...")
        logger.info(f"[AgentExecutor] Tools available: {[t['function']['name'] for t in tools]}")

        # Fire SubagentStart hook
        await self._hook_executor.execute(HookEvent.SUBAGENT_START, HookInput(
            event=HookEvent.SUBAGENT_START, agent_type=agent_type, session_id=str(id(self)),
        ))

        max_turns = agent_config["max_turns"]
        n_turns = 0

        try:
            # Execute with timeout
            result = await asyncio.wait_for(
                self._run_loop(messages, tools, max_turns),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            await self._hook_executor.execute(HookEvent.SUBAGENT_STOP, HookInput(
                event=HookEvent.SUBAGENT_STOP, agent_type=agent_type,
            ))
            return f"[AgentExecutor] Task timed out after {timeout}s. Consider splitting into smaller tasks."

        elapsed = time.time() - start_time
        logger.info(f"[AgentExecutor] Completed in {elapsed:.2f}s, {n_turns} turns")

        await self._hook_executor.execute(HookEvent.SUBAGENT_STOP, HookInput(
            event=HookEvent.SUBAGENT_STOP, agent_type=agent_type,
        ))

        return result

    def _build_system_prompt(
        self,
        agent_type: str,
        agent_config: dict,
        context: str | None,
    ) -> str:
        """Build system prompt for the sub-agent."""
        parts = [
            f"You are a specialized {agent_type} agent.",
            agent_config["description"],
            "",
            "Instructions:",
            "- Focus only on your assigned task.",
            "- Report your findings clearly and concisely.",
            "- Do not make assumptions beyond what you can verify.",
            "- If you cannot complete the task, explain why.",
        ]

        if context:
            parts.append("")
            parts.append("Context from parent agent:")
            parts.append(context)

        return "\n".join(parts)

    async def _run_loop(
        self,
        messages: list[dict],
        tools: list[dict],
        max_turns: int,
    ) -> str:
        """Run the agent loop with tool execution."""
        n_turns = 0

        while True:
            # Call LLM
            call_kwargs: dict[str, Any] = {
                "model": self._model,
                "messages": messages,
            }
            if tools:
                call_kwargs["tools"] = tools

            logger.info(f"[AgentExecutor] Calling LLM with model={self._model}, turn={n_turns}")

            result = None
            for retry in range(3):
                try:
                    response = await asyncio.to_thread(
                        self._client.chat.completions.create,
                        **call_kwargs,
                    )
                    result = response.model_dump()
                    break
                except Exception as e:
                    error_kind = classify_error(e)
                    strategy = get_retry_config(error_kind)
                    if error_kind == ErrorKind.AUTH or retry >= strategy.max_retries:
                        logger.error(f"[AgentExecutor] LLM error: {error_kind.value}: {e}")
                        raise
                    delay = calculate_delay(retry, strategy)
                    logger.warning(
                        f"[AgentExecutor] {error_kind.value}: {e}. "
                        f"Retrying in {delay:.1f}s ({retry + 1}/{strategy.max_retries})"
                    )
                    await asyncio.sleep(delay)

            if result is None:
                return "[AgentExecutor] LLM call failed after retries"
            logger.info(f"[AgentExecutor] LLM response received, finish_reason={result['choices'][0].get('finish_reason')}")

            choice = result["choices"][0]
            message = choice["message"]
            messages.append(message)

            # Check if done
            if choice.get("finish_reason") == "stop" or not message.get("tool_calls"):
                # Goal check — don't stop if goal is not met
                if self._goal_manager.has_goal():
                    should_stop, blocking_msg = await check_stop_goal(
                        self._goal_manager, messages, self._recent_tool_results
                    )
                    if not should_stop and blocking_msg:
                        logger.info(f"[Goal] Blocking stop: {blocking_msg[:100]}")
                        messages.append({
                            "role": "user",
                            "content": blocking_msg,
                        })
                        continue  # Keep working
                    elif should_stop:
                        logger.info(f"[Goal] Goal met, allowing stop")

                content = message.get("content") or ""
                return content

            n_turns += 1
            if n_turns > max_turns:
                # Force completion
                return (
                    f"[AgentExecutor] Reached max turns ({max_turns}). "
                    f"Partial findings: {message.get('content', 'No content yet')}"
                )

            # Execute tools
            for tc in message.get("tool_calls", []):
                fn_name = tc["function"]["name"]
                try:
                    fn_args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    fn_args = {}

                logger.info(f"[AgentExecutor] Tool call: {fn_name}({json.dumps(fn_args)[:100]}...)")

                # Permission check
                perm_result = self._permission_checker.check(fn_name, fn_args)
                if perm_result == PermissionResult.DENY:
                    self._permission_checker.record_denial(fn_name, fn_args)
                    tool_result = f"[Permission Denied] {fn_name} is not allowed in {self._permission_checker.mode.value} mode"
                    logger.warning(f"[Permission] Denied: {fn_name}")
                elif perm_result == PermissionResult.ASK and self._permission_checker.mode != PermissionMode.AUTO:
                    # In non-AUTO mode, ASK is effectively deny (no interactive prompt in sub-agents)
                    self._permission_checker.record_denial(fn_name, fn_args)
                    tool_result = f"[Permission Required] {fn_name} needs user approval"
                    logger.info(f"[Permission] Ask required for: {fn_name}")
                else:
                    # PreToolUse hook — can block execution
                    hook_output = await self._hook_executor.execute(HookEvent.PRE_TOOL_USE, HookInput(
                        event=HookEvent.PRE_TOOL_USE, tool_name=fn_name, args=fn_args,
                    ))
                    if hook_output and hook_output.decision == "deny":
                        tool_result = f"[Blocked by Hook] {hook_output.message or 'Execution denied'}"
                        await self._hook_executor.execute(HookEvent.POST_TOOL_USE_FAILURE, HookInput(
                            event=HookEvent.POST_TOOL_USE_FAILURE, tool_name=fn_name, args=fn_args,
                            error=tool_result,
                        ))
                    else:
                        try:
                            tool_result = await self._registry.dispatch(fn_name, fn_args)
                        except Exception as tool_err:
                            await self._hook_executor.execute(HookEvent.POST_TOOL_USE_FAILURE, HookInput(
                                event=HookEvent.POST_TOOL_USE_FAILURE, tool_name=fn_name, args=fn_args,
                                error=str(tool_err),
                            ))
                            tool_result = f"[Tool Error] {type(tool_err).__name__}: {str(tool_err)[:200]}"
                        else:
                            # PostToolUse hook (success)
                            await self._hook_executor.execute(HookEvent.POST_TOOL_USE, HookInput(
                                event=HookEvent.POST_TOOL_USE, tool_name=fn_name, args=fn_args,
                                result=str(tool_result)[:200],
                            ))

                    # Track recent results
                    self._recent_tool_results.append({"tool": fn_name, "output": str(tool_result)[:500]})
                    if len(self._recent_tool_results) > 20:
                        self._recent_tool_results = self._recent_tool_results[-20:]

                logger.info(f"[AgentExecutor] Tool result: {str(tool_result)[:100]}...")

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": tool_result,
                })

        # Should not reach here
        return "[AgentExecutor] Unexpected loop exit"


# Global executor reference (set during gateway startup)
_executor: AgentExecutor | None = None


def set_agent_executor(executor: AgentExecutor) -> None:
    """Set the global agent executor (called during gateway startup)."""
    global _executor
    _executor = executor
    logger.info("[AgentExecutor] Global executor initialized")


def get_agent_executor() -> AgentExecutor | None:
    """Get the global agent executor."""
    return _executor


__all__ = ["AgentExecutor", "set_agent_executor", "get_agent_executor", "AGENT_TYPES"]