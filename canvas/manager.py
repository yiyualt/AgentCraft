"""CanvasManager - manages queues and bridges tools <-> SSE.

Supports both memory and Redis backends for multi-worker scenarios.
"""

from __future__ import annotations

import contextvars
import json
import logging
import uuid
from datetime import datetime
from typing import Any

from canvas.backends import CanvasBackend, create_backend

logger = logging.getLogger(__name__)

# Context variable to pass session_id to tools (async-safe)
_current_session_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "canvas_session_id", default=None
)


def set_current_session_id(session_id: str | None) -> None:
    """Set session_id in context (called from gateway before tool execution)."""
    _current_session_id.set(session_id)


def get_current_session_id() -> str | None:
    """Get session_id from context (called in canvas tools)."""
    return _current_session_id.get()


class CanvasManager:
    """Manages Canvas queues and coordinates tool execution with SSE streaming.

    Architecture:
        Agent → canvas_update tool → CanvasManager.push_update() → Backend
                                                              ↓
        Browser ← SSE stream ← CanvasChannel ← Backend.pop_message()

    Supports both single-worker (memory) and multi-worker (Redis) modes.
    """

    def __init__(self, backend: CanvasBackend | None = None):
        """Initialize CanvasManager with backend.

        Args:
            backend: CanvasBackend instance (memory or redis)
                     If None, uses create_backend("auto")
        """
        self._backend = backend or create_backend("auto")
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the backend (connect to Redis if needed)."""
        if self._initialized:
            return
        await self._backend.initialize()
        self._initialized = True
        logger.info("[Canvas] CanvasManager initialized")

    async def shutdown(self) -> None:
        """Shutdown the backend."""
        await self._backend.shutdown()
        self._initialized = False
        logger.info("[Canvas] CanvasManager shutdown")

    def get_backend(self) -> CanvasBackend:
        """Get the underlying backend."""
        return self._backend

    # ===== Queue Management (Legacy API for SSE) =====

    def get_or_create_queue(self, session_id: str) -> Any:
        """Get or create queue for session.

        For memory backend: returns asyncio.Queue
        For redis backend: returns None (use pop_message instead)

        Legacy API for backward compatibility with canvas/server.py.
        """
        if hasattr(self._backend, "get_or_create_queue"):
            return self._backend.get_or_create_queue(session_id)
        return None

    def remove_queue(self, session_id: str) -> None:
        """Remove queue when SSE client disconnects.

        Legacy API for backward compatibility.
        """
        if hasattr(self._backend, "remove_queue"):
            self._backend.remove_queue(session_id)
        else:
            # For Redis backend, use async unregister
            # This will be called from SSE finally block
            pass  # Handled in SSE stream cleanup

    # ===== Session Tracking =====

    def has_active_session(self, session_id: str) -> bool:
        """Check if session has active SSE connection."""
        return self._backend.has_session(session_id)

    def list_active_sessions(self) -> list[str]:
        """List all sessions with active SSE connections."""
        return self._backend.list_sessions()

    # ===== Push Methods (Called by Tools) =====

    async def push_update(
        self,
        session_id: str,
        content: str,
        mode: str = "markdown",
        section: str = "main",
        action: str = "append",
    ) -> bool:
        """Push update to SSE queue (called by canvas_update tool)."""
        if not self.has_active_session(session_id):
            logger.warning(f"[Canvas] No active session {session_id}")
            return False

        update = {
            "type": "canvas_update",
            "id": str(uuid.uuid4())[:8],
            "mode": mode,
            "content": content,
            "section": section,
            "action": action,
            "timestamp": datetime.now().isoformat(),
        }

        result = await self._backend.push_message(session_id, update)
        if result:
            logger.info(f"[Canvas] Pushed update to {session_id}: mode={mode}, section={section}")
        return result

    async def push_interactive(
        self,
        session_id: str,
        component_type: str,
        component_id: str,
        config: dict,
        prompt: str,
    ) -> bool:
        """Push interactive component to SSE queue (called by canvas_interact tool)."""
        if not self.has_active_session(session_id):
            logger.warning(f"[Canvas] No active session {session_id}")
            return False

        update = {
            "type": "canvas_interact",
            "id": component_id,
            "component_type": component_type,
            "config": config,
            "prompt": prompt,
            "timestamp": datetime.now().isoformat(),
        }

        result = await self._backend.push_message(session_id, update)
        if result:
            logger.info(f"[Canvas] Pushed interactive component to {session_id}: type={component_type}")
        return result

    async def push_fork_event(
        self,
        session_id: str,
        event_type: str,
        child_session_id: str | None = None,
        task: str | None = None,
        result: str | None = None,
        error: str | None = None,
    ) -> bool:
        """Push fork lifecycle event to SSE queue.

        Args:
            session_id: Parent session ID
            event_type: 'fork_start', 'fork_complete', 'fork_error'
            child_session_id: ID of the fork child
            task: Task description for the fork child
            result: Result from fork execution
            error: Error message if fork failed
        """
        if not self.has_active_session(session_id):
            return False

        update = {
            "type": "fork_event",
            "id": str(uuid.uuid4())[:8],
            "event_type": event_type,
            "child_session_id": child_session_id,
            "task": task,
            "result": result,
            "error": error,
            "timestamp": datetime.now().isoformat(),
        }

        result = await self._backend.push_message(session_id, update)
        if result:
            logger.info(f"[Canvas] Pushed fork event to {session_id}: type={event_type}")
        return result

    async def push_user_event(self, session_id: str, event: dict) -> None:
        """Push user interaction event back to queue.

        Used by POST /canvas/event endpoint.
        """
        event["timestamp"] = datetime.now().isoformat()
        await self._backend.push_message(session_id, event)
        logger.info(f"[Canvas] User event pushed to {session_id}")


__all__ = [
    "CanvasManager",
    "set_current_session_id",
    "get_current_session_id",
]