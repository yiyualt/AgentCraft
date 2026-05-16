"""Agent tool: sub-agent delegation using core/tool_loop.

This is a refactored version that uses the unified core/tool_loop
instead of duplicating the agent loop logic.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from tools import tool

logger = logging.getLogger("gateway")


# Agent type definitions - tools available and max turns
AGENT_TYPES = {
    "explore": {
        "description": "Fast read-only search agent for locating code.",
        "tools": ["Glob", "Grep", "Read", "WebFetch"],
        "max_turns": 5,
    },
    "general-purpose": {
        "description": "General-purpose agent for complex tasks.",
        "tools": None,  # All tools
        "max_turns": 10,
    },
    "plan": {
        "description": "Architect agent for implementation planning.",
        "tools": ["Glob", "Grep", "Read", "Write"],
        "max_turns": 8,
    },
}


# Global references (set during gateway startup)
_llm_client: Any = None
_registry: Any = None
_fork_manager: Any = None
_canvas_manager: Any = None


def set_agent_context(
    llm_client: Any,
    registry: Any,
    fork_manager: Any = None,
    canvas_manager: Any = None,
) -> None:
    """Set global context for agent delegation."""
    global _llm_client, _registry, _fork_manager, _canvas_manager
    _llm_client = llm_client
    _registry = registry
    _fork_manager = fork_manager
    _canvas_manager = canvas_manager
    logger.info("[Agent] Context initialized")


def get_fork_manager() -> Any:
    """Get the fork manager."""
    return _fork_manager


class SimpleAgentRunner:
    """Simple agent runner for webhook/automation compatibility.

    Provides run() method that calls core/tool_loop.
    """

    def __init__(self, llm_client, registry):
        self._client = llm_client
        self._registry = registry

    async def run(
        self,
        task: str,
        agent_type: str = "general-purpose",
        timeout: int = 180,
    ) -> str:
        """Run a sub-agent task."""
        from core import run_tool_loop

        config = AGENT_TYPES.get(agent_type, AGENT_TYPES["general-purpose"])

        # Filter tools
        all_tools = self._registry.list_tools()
        if config["tools"]:
            allowed = set(config["tools"])
            tools = [t for t in all_tools if t["function"]["name"] in allowed]
        else:
            tools = all_tools

        # Build messages
        messages = [
            {"role": "system", "content": f"You are a {agent_type} agent. {config['description']}"},
            {"role": "user", "content": task},
        ]

        try:
            _, result = await asyncio.wait_for(
                run_tool_loop(
                    messages=messages,
                    llm_client=self._client,
                    model="deepseek-chat",
                    registry=self._registry,
                    tools=tools,
                    max_turns=config["max_turns"],
                ),
                timeout=timeout,
            )
            return result["choices"][0]["message"].get("content", "")
        except asyncio.TimeoutError:
            return f"[Agent] Timeout after {timeout}s"


def get_agent_runner() -> SimpleAgentRunner | None:
    """Get agent runner for webhook/automation."""
    if _llm_client is None or _registry is None:
        return None
    return SimpleAgentRunner(_llm_client, _registry)


def _build_system_prompt(agent_type: str, task: str) -> str:
    """Build system prompt for sub-agent."""
    config = AGENT_TYPES.get(agent_type, AGENT_TYPES["general-purpose"])
    return f"""You are a specialized {agent_type} agent.

{config['description']}

Instructions:
- Focus only on your assigned task.
- Report your findings clearly and concisely.
- Do not make assumptions beyond what you can verify.
- If you cannot complete the task, explain why.

Task: {task}
"""


def _filter_tools(all_tools: list[dict], allowed_names: list[str] | None) -> list[dict]:
    """Filter tools to allowed set."""
    if allowed_names is None:
        return all_tools
    allowed = set(allowed_names)
    return [t for t in all_tools if t["function"]["name"] in allowed]


def _get_fork_context(session_id: str, task: str) -> tuple[list[dict], bool]:
    """Create fork context if available.

    Returns:
        Tuple of (messages, is_fork_child)
    """
    if _fork_manager is None or session_id is None:
        return None, False

    fork_context = _fork_manager.create_fork_context(
        parent_session_id=session_id,
        max_tokens=32000,
    )
    if fork_context is None:
        return None, False

    # Replace placeholder with task
    messages = fork_context.inherited_messages.copy()
    for i, msg in enumerate(messages):
        if msg.get("content") == "FORK_PLACEHOLDER":
            messages[i] = {"role": "user", "content": task}
            break

    return messages, True


@tool(
    name="Agent",
    description="Launch a new agent to handle complex, multi-step tasks. "
                "Each agent type has specific capabilities.\n\n"
                "Available types:\n"
                "- explore: Fast read-only search agent\n"
                "- general-purpose: General agent for complex tasks\n"
                "- plan: Architect agent for implementation planning\n\n"
                "fork_from_current=true: Agent inherits current conversation context.\n"
                "Fork children cannot spawn more agents.",
    parameters={
        "type": "object",
        "properties": {
            "prompt": {
                "type": "string",
                "description": "The task for the agent to perform",
            },
            "description": {
                "type": "string",
                "description": "Short (3-5 word) description",
            },
            "subagent_type": {
                "type": "string",
                "enum": ["explore", "general-purpose", "plan"],
                "description": "Agent type (default: general-purpose)",
            },
            "fork_from_current": {
                "type": "boolean",
                "description": "If true, inherit current conversation context",
            },
        },
        "required": ["prompt"],
    },
)
async def agent_delegate(
    prompt: str,
    description: str | None = None,
    subagent_type: str = "general-purpose",
    fork_from_current: bool = False,
) -> str:
    """Delegate a sub-task to a specialized sub-agent.

    Uses core/tool_loop for unified agent execution.
    """
    from core import run_tool_loop
    from canvas import get_current_session_id

    # Check context
    if _llm_client is None or _registry is None:
        return "[Error] Agent context not initialized"

    # Build task
    task = f"[{description}] {prompt}" if description else prompt

    # Get session for fork
    session_id = get_current_session_id()

    # Fork handling
    fork_messages, is_fork_child = _get_fork_context(session_id, task) if fork_from_current else (None, False)

    if fork_from_current and not fork_messages:
        return "[FORK Error] Could not create fork context"

    # Fork children cannot use Agent tool
    if is_fork_child:
        logger.warning("[FORK] Fork child cannot spawn sub-agents")

    # Build messages
    if fork_messages:
        messages = fork_messages
    else:
        messages = [
            {"role": "system", "content": _build_system_prompt(subagent_type, task)},
            {"role": "user", "content": task},
        ]

    # Filter tools
    config = AGENT_TYPES.get(subagent_type, AGENT_TYPES["general-purpose"])
    all_tools = _registry.list_tools()
    tools = _filter_tools(all_tools, config["tools"])

    # Fork children: disable Agent tool
    if is_fork_child:
        tools = [t for t in tools if t["function"]["name"] != "Agent"]

    # Push fork_start to canvas
    if is_fork_child and _canvas_manager and session_id:
        await _canvas_manager.push_fork_event(
            session_id, "fork_start", task=task[:100]
        )

    start_time = time.time()

    try:
        # Run tool loop with timeout
        messages, result = await asyncio.wait_for(
            run_tool_loop(
                messages=messages,
                llm_client=_llm_client,
                model="deepseek-chat",
                registry=_registry,
                tools=tools,
                max_turns=config["max_turns"],
            ),
            timeout=180,
        )

        elapsed = time.time() - start_time
        logger.info(f"[Agent] {subagent_type} completed in {elapsed:.2f}s")

        # Push fork_complete to canvas
        if is_fork_child and _canvas_manager and session_id:
            content = result["choices"][0]["message"].get("content", "")
            await _canvas_manager.push_fork_event(
                session_id, "fork_complete",
                task=task[:100],
                result=content[:200],
            )

        return result["choices"][0]["message"].get("content", "")

    except asyncio.TimeoutError:
        logger.warning(f"[Agent] Timeout after 180s")
        if is_fork_child and _canvas_manager and session_id:
            await _canvas_manager.push_fork_event(
                session_id, "fork_error",
                task=task[:100],
                error="Timeout after 180s",
            )
        return f"[Agent] Task timed out after 180s. Consider splitting into smaller tasks."

    except Exception as e:
        logger.error(f"[Agent] Error: {e}")
        if is_fork_child and _canvas_manager and session_id:
            await _canvas_manager.push_fork_event(
                session_id, "fork_error",
                task=task[:100],
                error=str(e)[:200],
            )
        return f"[Agent Error] {type(e).__name__}: {e}"


__all__ = [
    "agent_delegate",
    "set_agent_context",
    "get_fork_manager",
    "AGENT_TYPES",
]