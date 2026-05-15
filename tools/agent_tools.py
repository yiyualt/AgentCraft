"""Agent tool: sub-agent delegation."""

from __future__ import annotations

import logging

from tools import tool

logger = logging.getLogger("gateway")


@tool(
    name="Agent",
    description="Launch a new agent to handle complex, multi-step tasks. "
                "Each agent type has specific capabilities and tools available to it.\n\n"
                "Available agent types:\n"
                "- explore: Fast read-only search agent for locating code. Use for file pattern searches, "
                "grep for symbols/keywords, or answering 'where is X defined / which files reference Y.' "
                "NOT for code review or open-ended analysis.\n"
                "- general-purpose: General-purpose agent for researching complex questions, "
                "searching for code, and executing multi-step tasks. Use when not confident "
                "in finding the right match in first few tries.\n"
                "- plan: Software architect agent for designing implementation plans. "
                "Returns step-by-step plans, identifies critical files, considers trade-offs.\n\n"
                "Usage notes:\n"
                "- Always include a short description summarizing what the agent will do.\n"
                "- The agent starts fresh with no context from this conversation.\n"
                "- Clearly tell the agent whether to write code or just do research.\n"
                "- For a short response, say so ('report in under 200 words').\n\n"
                "Fork mode (fork_from_current=true):\n"
                "- Agent inherits the current conversation context.\n"
                "- Useful when agent needs background from ongoing discussion.\n"
                "- Fork children cannot spawn more agents (recursive protection).",
    parameters={
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": "A short (3-5 word) description of the task",
            },
            "prompt": {
                "type": "string",
                "description": "The task for the agent to perform. Be specific and self-contained.",
            },
            "subagent_type": {
                "type": "string",
                "enum": ["explore", "general-purpose", "plan"],
                "description": "The type of specialized agent to use (default: general-purpose)",
            },
            "fork_from_current": {
                "type": "boolean",
                "description": "If true, agent inherits current conversation context. "
                               "Useful when agent needs background from ongoing discussion. "
                               "Fork children cannot spawn more agents.",
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

    Args:
        prompt: The task for the agent to perform
        description: Short description of the task
        subagent_type: Type of agent (explore, general-purpose, plan)
        fork_from_current: If true, inherit current conversation context
    """
    from tools.agent_executor import get_agent_executor, ForkManager
    from canvas import get_current_session_id

    executor = get_agent_executor()
    if executor is None:
        return "[Error] Agent executor not initialized. Cannot delegate task."

    # Build task description
    task = prompt
    if description:
        task = f"[{description}] {prompt}"

    # Handle fork mode
    fork_context = None
    is_fork_child = False

    if fork_from_current:
        session_id = get_current_session_id()
        if session_id:
            fork_manager = executor.get_fork_manager()
            if fork_manager:
                fork_context = fork_manager.create_fork_context(
                    parent_session_id=session_id,
                    max_tokens=32000,
                )
                if fork_context:
                    is_fork_child = True
                    logger.info(f"[FORK] Created fork from session {session_id}")
                    # Push fork_start to canvas
                    canvas_mgr = fork_manager.get_canvas_manager()
                    if canvas_mgr:
                        await canvas_mgr.push_fork_event(
                            session_id, "fork_start",
                            task=task[:100],
                        )
                else:
                    return "[FORK Error] Could not create fork context. Parent session may not have messages."
            else:
                return "[FORK Error] Fork manager not initialized. Cannot fork from current context."
        else:
            return "[FORK Error] No current session. Cannot fork without session context."

    try:
        result = await executor.run(
            task=task,
            agent_type=subagent_type,
            context=None,
            timeout=180,
            fork_context=fork_context,
            is_fork_child=is_fork_child,
        )
        # Push fork_complete to canvas
        if is_fork_child:
            canvas_mgr = fork_manager.get_canvas_manager() if fork_manager else None
            if canvas_mgr:
                await canvas_mgr.push_fork_event(
                    session_id, "fork_complete",
                    task=task[:100],
                    result=str(result)[:200],
                )
        return result
    except Exception as e:
        # Push fork_error to canvas
        if is_fork_child:
            canvas_mgr = fork_manager.get_canvas_manager() if fork_manager else None
            if canvas_mgr:
                await canvas_mgr.push_fork_event(
                    session_id, "fork_error",
                    task=task[:100],
                    error=str(e)[:200],
                )
        return f"[Agent Error] {type(e).__name__}: {e}"


__all__ = ["agent_delegate"]