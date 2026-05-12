"""Agent Executor - Sub-agent task delegation.

Provides the ability to delegate sub-tasks to specialized sub-agents.
Each sub-agent runs in its own context with focused tools and prompts.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from openai import OpenAI

from tools import UnifiedToolRegistry, get_default_registry
from sessions import SessionManager

logger = logging.getLogger(__name__)


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
    ):
        self._client = llm_client
        self._registry = registry
        self._session_manager = session_manager
        self._model = model
        self._base_url = base_url

    async def run(
        self,
        task: str,
        agent_type: str = "general-purpose",
        context: str | None = None,
        timeout: int = 120,
    ) -> str:
        """Execute a sub-agent task.

        Args:
            task: The task description for the sub-agent
            agent_type: Type of agent (explore, general-purpose, plan)
            context: Optional context to pass to the sub-agent
            timeout: Maximum execution time in seconds

        Returns:
            Result from the sub-agent execution
        """
        if agent_type not in AGENT_TYPES:
            return f"[Error] Unknown agent type: {agent_type}. Available: {list(AGENT_TYPES.keys())}"

        agent_config = AGENT_TYPES[agent_type]
        start_time = time.time()

        # Build system prompt
        system_prompt = self._build_system_prompt(agent_type, agent_config, context)

        # Build tool list (filter if specified)
        all_tools = self._registry.list_tools()
        if agent_config["tools"]:
            allowed_names = set(agent_config["tools"])
            tools = [t for t in all_tools if t["function"]["name"] in allowed_names]
        else:
            tools = all_tools

        # Initial message
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task},
        ]

        logger.info(f"[AgentExecutor] Starting {agent_type} agent for task: {task[:100]}...")
        logger.info(f"[AgentExecutor] Tools available: {[t['function']['name'] for t in tools]}")

        max_turns = agent_config["max_turns"]
        n_turns = 0

        try:
            # Execute with timeout
            result = await asyncio.wait_for(
                self._run_loop(messages, tools, max_turns),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            return f"[AgentExecutor] Task timed out after {timeout}s. Consider splitting into smaller tasks."

        elapsed = time.time() - start_time
        logger.info(f"[AgentExecutor] Completed in {elapsed:.2f}s, {n_turns} turns")

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

            response = await asyncio.to_thread(
                self._client.chat.completions.create,
                **call_kwargs,
            )
            result = response.model_dump()

            choice = result["choices"][0]
            message = choice["message"]
            messages.append(message)

            # Check if done
            if choice.get("finish_reason") == "stop" or not message.get("tool_calls"):
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

                tool_result = await self._registry.dispatch(fn_name, fn_args)

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