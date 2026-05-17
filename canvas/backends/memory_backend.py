"""Memory Backend - In-memory queue implementation (original CanvasManager logic)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from canvas.backends import CanvasBackend

logger = logging.getLogger(__name__)


class MemoryBackend(CanvasBackend):
    """In-memory backend using asyncio.Queue.

    This is the original implementation, suitable for single-worker mode.
    Does NOT support multi-worker scenarios.
    """

    def __init__(self, max_queue_size: int = 100):
        """Initialize memory backend.

        Args:
            max_queue_size: Maximum messages per session queue
        """
        self._queues: dict[str, asyncio.Queue] = {}
        self._active_sessions: set[str] = set()
        self._lock = asyncio.Lock()
        self._max_queue_size = max_queue_size

    async def initialize(self) -> None:
        """No initialization needed for memory backend."""
        logger.info("[MemoryBackend] Initialized (single worker mode)")

    async def shutdown(self) -> None:
        """Clear all queues on shutdown."""
        self._queues.clear()
        self._active_sessions.clear()
        logger.info("[MemoryBackend] Shutdown complete")

    async def push_message(self, session_id: str, message: dict) -> bool:
        """Push message to in-memory queue."""
        queue = self._queues.get(session_id)
        if queue is None:
            logger.warning(f"[MemoryBackend] No queue for session {session_id}")
            return False

        try:
            await queue.put(message)
            logger.debug(f"[MemoryBackend] Pushed to {session_id}: {message.get('type')}")
            return True
        except asyncio.QueueFull:
            logger.warning(f"[MemoryBackend] Queue full for {session_id}")
            return False

    async def pop_message(self, session_id: str, timeout: float = 30.0) -> dict | None:
        """Pop message from in-memory queue with timeout."""
        queue = self._queues.get(session_id)
        if queue is None:
            return None

        try:
            message = await asyncio.wait_for(queue.get(), timeout=timeout)
            return message
        except asyncio.TimeoutError:
            return None

    def has_session(self, session_id: str) -> bool:
        """Check if session has an active queue."""
        return session_id in self._active_sessions

    def list_sessions(self) -> list[str]:
        """List all active sessions."""
        return list(self._active_sessions)

    async def register_session(self, session_id: str) -> None:
        """Register session and create queue."""
        async with self._lock:
            if session_id not in self._queues:
                self._queues[session_id] = asyncio.Queue(maxsize=self._max_queue_size)
                logger.info(f"[MemoryBackend] Created queue for {session_id}")
            self._active_sessions.add(session_id)

    async def unregister_session(self, session_id: str) -> None:
        """Unregister session and remove queue."""
        async with self._lock:
            if session_id in self._queues:
                del self._queues[session_id]
                logger.info(f"[MemoryBackend] Removed queue for {session_id}")
            self._active_sessions.discard(session_id)

    def get_or_create_queue(self, session_id: str) -> asyncio.Queue:
        """Legacy API: Get or create queue directly.

        Used by SSE stream in canvas/server.py for backward compatibility.
        """
        if session_id not in self._queues:
            self._queues[session_id] = asyncio.Queue(maxsize=self._max_queue_size)
            self._active_sessions.add(session_id)
            logger.info(f"[MemoryBackend] Created queue for {session_id}")
        return self._queues[session_id]

    def remove_queue(self, session_id: str) -> None:
        """Legacy API: Remove queue directly."""
        if session_id in self._queues:
            del self._queues[session_id]
            self._active_sessions.discard(session_id)
            logger.info(f"[MemoryBackend] Removed queue for {session_id}")


__all__ = ["MemoryBackend"]