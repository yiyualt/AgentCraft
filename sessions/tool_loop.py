"""Tool Loop - the core agent execution loop.

The fundamental pattern:
    while True:
        response = call_llm(messages, tools)
        if no tool_calls:
            return response
        results = execute_tools(response.tool_calls)
        messages.append(results)
        # next iteration
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from core.executor import ToolExecutor, ToolResult

logger = logging.getLogger("gateway")


def clean_orphan_tool_messages(messages: list[dict]) -> list[dict]:
    """Remove orphan tool messages without preceding tool_calls.

    Tool messages must have a preceding assistant message with tool_calls.
    """
    cleaned = []
    last_assistant_tool_calls = None
    removed_count = 0

    for msg in messages:
        role = msg.get("role")

        if role == "assistant":
            last_assistant_tool_calls = msg.get("tool_calls")
            cleaned.append(msg)
        elif role == "tool":
            if last_assistant_tool_calls:
                tool_call_id = msg.get("tool_call_id")
                if tool_call_id:
                    matching_ids = [tc["id"] for tc in last_assistant_tool_calls]
                    if tool_call_id in matching_ids:
                        cleaned.append(msg)
                    else:
                        removed_count += 1
                else:
                    removed_count += 1
            else:
                removed_count += 1
        else:
            cleaned.append(msg)
            if role == "user":
                last_assistant_tool_calls = None

    if removed_count > 0:
        logger.info(f"[MESSAGES] Cleaned orphan tool messages: removed {removed_count}")

    return cleaned


async def run_tool_loop(
    messages: list[dict],
    llm_client: Any,
    model: str,
    registry: Any,
    tools: list[dict] | None = None,
    session_id: str | None = None,
    canvas_manager: Any | None = None,
    compaction_manager: Any | None = None,
    budget_manager: Any | None = None,
    session: Any | None = None,
    provider_registry: Any | None = None,
    semaphore: asyncio.Semaphore | None = None,
    max_turns: int = 50,
    **kwargs,
) -> tuple[list[dict], dict]:
    """Run the tool execution loop.

    Args:
        messages: Conversation messages
        llm_client: OpenAI client
        model: Model name
        registry: UnifiedToolRegistry
        tools: Available tools list
        session_id: Session ID (optional)
        canvas_manager: CanvasManager (optional)
        compaction_manager: CompactionManager (optional)
        budget_manager: BudgetManager (optional)
        session: Session object (optional)
        provider_registry: ProviderRegistry for fallback (optional)
        semaphore: Concurrency semaphore (optional)
        max_turns: Maximum tool turns
        **kwargs: Additional LLM parameters

    Returns:
        Tuple of (final_messages, final_response)
    """
    messages = clean_orphan_tool_messages(messages)
    n_turns = 0

    executor = ToolExecutor(
        registry=registry,
        session_id=session_id,
        canvas_manager=canvas_manager,
    )

    while True:
        # Auto-compaction check (if enabled)
        if session_id and compaction_manager and session:
            context_window = session.context_window or 64000
            current_tokens = len(json.dumps(messages, ensure_ascii=False)) // 4

            level = compaction_manager.check_compaction_needed(
                session_id=session_id,
                current_tokens=current_tokens,
                context_window=context_window,
            )

            if level:
                logger.info(f"[COMPACTION] Level {level} for session {session_id}")
                # Simple compaction: keep last N messages
                keep_count = int(len(messages) * 0.5)
                messages = messages[:2] + messages[-keep_count:]  # Keep system + recent

        # Budget check (if enabled)
        if session_id and budget_manager and session:
            budget = getattr(session, 'token_budget', None) or 50000
            current_tokens = len(json.dumps(messages, ensure_ascii=False)) // 4

            if current_tokens > budget:
                logger.info(f"[BUDGET] Limit reached: {current_tokens}/{budget}")
                messages.append({
                    "role": "assistant",
                    "content": f"[Budget Limit] Used {current_tokens}/{budget} tokens.",
                })
                break

        # Build LLM call kwargs
        call_kwargs = {"model": model, "messages": messages, **kwargs}
        if tools:
            call_kwargs["tools"] = tools

        # LLM call
        logger.info(f"[LLM] Turn {n_turns}: model={model}, messages={len(messages)}")

        try:
            if semaphore:
                async with semaphore:
                    result = await _call_llm(
                        llm_client, provider_registry, call_kwargs
                    )
            else:
                result = await _call_llm(
                    llm_client, provider_registry, call_kwargs
                )
        except Exception as e:
            logger.error(f"[LLM ERROR] {e}")
            raise

        # Process response
        choice = result["choices"][0]
        message = choice["message"]
        messages.append(message)

        # Check for tool calls
        tool_calls = message.get("tool_calls")
        if not tool_calls:
            logger.info("[LLM] No tool_calls, done")
            break

        n_turns += 1
        logger.info(f"[TOOL] Turn {n_turns}: {[tc['function']['name'] for tc in tool_calls]}")

        # Safety limit
        if n_turns > max_turns:
            logger.warning(f"[TOOL LIMIT] Exceeded {max_turns} turns")
            for tc in tool_calls:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": f"Tool limit ({max_turns}) reached.",
                })
            break

        # Execute tools
        results = await executor.execute_tools(tool_calls)

        # Append tool results
        for tc in tool_calls:
            tc_id = tc["id"]
            result = results.get(tc_id)
            if result:
                messages.append(result.to_tool_message())
            else:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": "Tool not executed",
                })

    return messages, result


async def _call_llm(
    llm_client: Any,
    provider_registry: Any | None,
    call_kwargs: dict,
) -> dict:
    """Call LLM with optional provider fallback."""
    if provider_registry and provider_registry.get_fallback_chain():
        return await provider_registry.complete_with_fallback(
            messages=call_kwargs["messages"],
            model=call_kwargs["model"],
            tools=call_kwargs.get("tools"),
            **{k: v for k, v in call_kwargs.items() if k not in ("messages", "model", "tools")},
        )
    else:
        response = await asyncio.to_thread(
            llm_client.chat.completions.create, **call_kwargs
        )
        return response.model_dump()


__all__ = ["run_tool_loop", "clean_orphan_tool_messages"]