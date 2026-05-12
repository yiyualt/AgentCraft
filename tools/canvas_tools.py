"""Canvas-related tools for updating workspace."""

from __future__ import annotations

import json
import logging

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
    """Update canvas content and push to SSE stream.

    This is a sync wrapper that calls the async implementation.
    The async execution happens through ToolRegistry.dispatch().
    """
    global _canvas_manager

    if _canvas_manager is None:
        return "[Error] Canvas manager not initialized"

    session_id = get_current_session_id()
    if session_id is None:
        return "[Error] No active canvas session (SSE not connected)"

    if not _canvas_manager.has_active_session(session_id):
        return f"[Warning] Session {session_id} has no SSE connection. User needs to open /canvas page first."

    # For sync tools, we need to push synchronously
    # This requires running async code in sync context
    import asyncio

    try:
        loop = asyncio.get_running_loop()
        # We're in async context, create task
        future = asyncio.ensure_future(
            _canvas_manager.push_update(
                session_id=session_id,
                content=content,
                mode=mode,
                section=section,
                action=action,
            )
        )
        # Fire and forget - don't wait for completion
        # The result will be logged
        return f"[Canvas] Update pushed: mode={mode}, section={section}, action={action}"
    except RuntimeError:
        # No running loop, need to create one (shouldn't happen in gateway)
        return "[Error] Cannot execute in sync context"


__all__ = ["canvas_update", "set_canvas_manager"]