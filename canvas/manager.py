"""CanvasManager - manages queues and bridges tools <-> SSE."""

from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import uuid
from datetime import datetime
from typing import Any

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
        Agent → canvas_update tool → CanvasManager.push_update() → Queue
                                                              ↓
        Browser ← SSE stream ← CanvasChannel ← Queue.get()

    Each session has its own queue for isolated streaming.
    """

    def __init__(self):
        """Initialize CanvasManager."""
        self._queues: dict[str, asyncio.Queue] = {}
        self._lock = asyncio.Lock()

    def get_or_create_queue(self, session_id: str) -> asyncio.Queue:
        """Get or create SSE queue for a session.

        Args:
            session_id: Session identifier

        Returns:
            asyncio.Queue for this session's updates
        """
        if session_id not in self._queues:
            self._queues[session_id] = asyncio.Queue(maxsize=100)
            logger.info(f"[Canvas] Created queue for session {session_id}")
        return self._queues[session_id]

    def remove_queue(self, session_id: str) -> None:
        """Remove queue when SSE client disconnects.

        Args:
            session_id: Session to clean up
        """
        if session_id in self._queues:
            del self._queues[session_id]
            logger.info(f"[Canvas] Removed queue for session {session_id}")

    async def push_update(
        self,
        session_id: str,
        content: str,
        mode: str = "markdown",
        section: str = "main",
        action: str = "append",
    ) -> bool:
        """Push update to SSE queue (called by canvas_update tool)."""
        queue = self._queues.get(session_id)
        if queue is None:
            logger.warning(f"[Canvas] No queue for session {session_id}")
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

        try:
            await queue.put(update)
            logger.info(f"[Canvas] Pushed update to {session_id}: mode={mode}, section={section}")
            return True
        except asyncio.QueueFull:
            logger.warning(f"[Canvas] Queue full for {session_id}, dropping update")
            return False

    async def push_interactive(
        self,
        session_id: str,
        component_type: str,
        component_id: str,
        config: dict,
        prompt: str,
    ) -> bool:
        """Push interactive component to SSE queue (called by canvas_interact tool)."""
        queue = self._queues.get(session_id)
        if queue is None:
            logger.warning(f"[Canvas] No queue for session {session_id}")
            return False

        update = {
            "type": "canvas_interact",
            "id": component_id,
            "component_type": component_type,
            "config": config,
            "prompt": prompt,
            "timestamp": datetime.now().isoformat(),
        }

        try:
            await queue.put(update)
            logger.info(f"[Canvas] Pushed interactive component to {session_id}: type={component_type}")
            return True
        except asyncio.QueueFull:
            logger.warning(f"[Canvas] Queue full for {session_id}, dropping component")
            return False

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
        queue = self._queues.get(session_id)
        if queue is None:
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

        try:
            await queue.put(update)
            logger.info(f"[Canvas] Pushed fork event to {session_id}: type={event_type}")
            return True
        except asyncio.QueueFull:
            logger.warning(f"[Canvas] Queue full for {session_id}, dropping fork event")
            return False

    def has_active_session(self, session_id: str) -> bool:
        """Check if session has active SSE connection.

        Args:
            session_id: Session to check

        Returns:
            True if queue exists (SSE connected)
        """
        return session_id in self._queues

    def list_active_sessions(self) -> list[str]:
        """List all sessions with active SSE connections."""
        return list(self._queues.keys())


__all__ = [
    "CanvasManager",
    "set_current_session_id",
    "get_current_session_id",
]