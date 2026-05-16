"""Canvas-related tools for updating workspace."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime

from tools import tool

from canvas.manager import get_current_session_id

logger = logging.getLogger(__name__)

# Global canvas manager reference (set during gateway startup)
_canvas_manager = None


def set_canvas_manager(manager) -> None:
    """Set the global canvas manager (called during gateway startup)."""
    global _canvas_manager
    _canvas_manager = manager
    logger.info("[Canvas Tools] Canvas manager initialized")


@tool(
    name="canvas_update",
    description="Update the Canvas workspace with new content. "
                "Use this to display results, show progress, or create visual content. "
                "The content will be rendered in real-time on the connected browser.",
    parameters={
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "The content to display (markdown, HTML, code, or table data)",
            },
            "mode": {
                "type": "string",
                "enum": ["markdown", "html", "code", "table"],
                "description": "Rendering mode. markdown: formatted text, html: raw HTML, "
                               "code: code snippet with syntax highlighting, table: JSON array as table",
            },
            "section": {
                "type": "string",
                "description": "Target section in canvas. 'main' for primary content, "
                               "'sidebar' for supplementary info. Default: 'main'",
            },
            "action": {
                "type": "string",
                "enum": ["append", "replace", "clear"],
                "description": "How to apply the update. 'append': add to section, "
                               "'replace': replace last content, 'clear': clear section. Default: 'append'",
            },
        },
        "required": ["content"],
    },
)
def canvas_update(
    content: str,
    mode: str = "markdown",
    section: str = "main",
    action: str = "append",
) -> str:
    """Update canvas content and push to SSE stream."""
    global _canvas_manager

    if _canvas_manager is None:
        return "[Error] Canvas manager not initialized"

    session_id = get_current_session_id()
    if session_id is None:
        return "[Error] No active canvas session (SSE not connected)"

    if not _canvas_manager.has_active_session(session_id):
        return f"[Warning] Session {session_id} has no SSE connection. User needs to open /canvas page first."

    import asyncio

    try:
        loop = asyncio.get_running_loop()
        asyncio.ensure_future(
            _canvas_manager.push_update(
                session_id=session_id,
                content=content,
                mode=mode,
                section=section,
                action=action,
            )
        )
        return f"[Canvas] Update pushed: mode={mode}, section={section}, action={action}"
    except RuntimeError:
        return "[Error] Cannot execute in sync context"


@tool(
    name="canvas_interact",
    description="Create an interactive component in Canvas. "
                "Users can interact with buttons, forms, sliders, and select boxes. "
                "Interaction events will be sent back to you in the next turn. "
                "Use this to collect user input or confirm actions.",
    parameters={
        "type": "object",
        "properties": {
            "component_type": {
                "type": "string",
                "enum": ["button", "form", "slider", "select", "checkbox"],
                "description": "Type of interactive component",
            },
            "config": {
                "type": "object",
                "description": "Component configuration. "
                               "button: {label, style (primary/success/warning/danger)} "
                               "form: {fields: [{name, type, label, placeholder, required}]} "
                               "slider: {min, max, default, label} "
                               "select: {options: [{value, label}], label} "
                               "checkbox: {label, checked}",
            },
            "prompt": {
                "type": "string",
                "description": "Instruction text shown to user, explaining what to do with this component",
            },
        },
        "required": ["component_type", "config"],
    },
)
def canvas_interact(
    component_type: str,
    config: dict,
    prompt: str = "",
) -> str:
    """Create interactive component and return component ID."""
    global _canvas_manager

    if _canvas_manager is None:
        return "[Error] Canvas manager not initialized"

    session_id = get_current_session_id()
    if session_id is None:
        return "[Error] No active canvas session (SSE not connected)"

    if not _canvas_manager.has_active_session(session_id):
        return f"[Warning] Session {session_id} has no SSE connection."

    # Generate unique component ID
    component_id = f"comp_{uuid.uuid4().hex[:8]}"

    import asyncio

    try:
        loop = asyncio.get_running_loop()
        asyncio.ensure_future(
            _canvas_manager.push_interactive(
                session_id=session_id,
                component_type=component_type,
                component_id=component_id,
                config=config,
                prompt=prompt,
            )
        )
        return f"[Canvas] Interactive component created: id={component_id}, type={component_type}. User interaction will be sent back in next turn."
    except RuntimeError:
        return "[Error] Cannot execute in sync context"


__all__ = ["canvas_update", "canvas_interact", "set_canvas_manager"]