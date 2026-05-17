"""Canvas Backends - Abstract backend for message queuing."""

from __future__ import annotations

from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)


class CanvasBackend(ABC):
    """Abstract backend for Canvas message queuing.

    Supports both in-memory and Redis-based implementations.
    """

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the backend (connect to Redis, etc.)."""
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        """Shutdown the backend (close connections, cleanup)."""
        ...

    @abstractmethod
    async def push_message(self, session_id: str, message: dict) -> bool:
        """Push a message to the session queue.

        Args:
            session_id: Session identifier
            message: Message dict with type, content, etc.

        Returns:
            True if successful, False otherwise
        """
        ...

    @abstractmethod
    async def pop_message(self, session_id: str, timeout: float = 30.0) -> dict | None:
        """Pop a message from the session queue.

        Args:
            session_id: Session identifier
            timeout: Max wait time in seconds

        Returns:
            Message dict if available, None if timeout
        """
        ...

    @abstractmethod
    def has_session(self, session_id: str) -> bool:
        """Check if session has an active connection.

        Args:
            session_id: Session to check

        Returns:
            True if session is active
        """
        ...

    @abstractmethod
    def list_sessions(self) -> list[str]:
        """List all active sessions.

        Returns:
            List of session IDs
        """
        ...

    @abstractmethod
    async def register_session(self, session_id: str) -> None:
        """Register a session as active.

        Args:
            session_id: Session to register
        """
        ...

    @abstractmethod
    async def unregister_session(self, session_id: str) -> None:
        """Unregister a session (cleanup).

        Args:
            session_id: Session to unregister
        """
        ...


def create_backend(
    mode: str = "auto",
    url: str = "redis://localhost:6379/0",
    max_connections: int = 50,
    ttl: int = 3600,
) -> CanvasBackend:
    """Create a backend based on mode.

    Args:
        mode: "auto", "redis", or "memory"
            - auto: Try Redis, fallback to memory if unavailable
            - redis: Force Redis (raise error if unavailable)
            - memory: Force in-memory (single worker only)
        url: Redis URL (redis://host:port/db)
        max_connections: Redis connection pool size
        ttl: Message TTL in seconds

    Returns:
        CanvasBackend instance
    """
    if mode == "memory":
        logger.info("[CanvasBackend] Using memory backend (single worker mode)")
        from canvas.backends.memory_backend import MemoryBackend
        return MemoryBackend()

    if mode == "redis":
        logger.info("[CanvasBackend] Using Redis backend (forced)")
        from canvas.backends.redis_backend import RedisBackend
        return RedisBackend(url, max_connections, ttl)

    # auto mode: try Redis, fallback to memory
    try:
        import redis.asyncio as redis
        from canvas.backends.redis_backend import RedisBackend

        backend = RedisBackend(url, max_connections, ttl)
        logger.info("[CanvasBackend] Using Redis backend (auto mode)")
        return backend
    except ImportError:
        logger.warning("[CanvasBackend] Redis not installed, using memory backend")
        from canvas.backends.memory_backend import MemoryBackend
        return MemoryBackend()
    except Exception as e:
        logger.warning(f"[CanvasBackend] Redis unavailable: {e}, using memory backend")
        from canvas.backends.memory_backend import MemoryBackend
        return MemoryBackend()


__all__ = ["CanvasBackend", "create_backend"]