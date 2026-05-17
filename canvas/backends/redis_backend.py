"""Redis Backend - Redis-based queue implementation for multi-worker support."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import redis.asyncio as redis

from canvas.backends import CanvasBackend

logger = logging.getLogger(__name__)

# Redis key patterns
QUEUE_KEY = "canvas:queue:{session_id}"
NOTIFY_KEY = "canvas:notify:{session_id}"
SESSIONS_KEY = "canvas:active_sessions"


class RedisBackend(CanvasBackend):
    """Redis backend using BLPOP for reliable message delivery.

    Supports multi-worker scenarios by using Redis as shared message store.
    """

    def __init__(
        self,
        url: str = "redis://localhost:6379/0",
        max_connections: int = 50,
        ttl: int = 3600,
    ):
        """Initialize Redis backend.

        Args:
            url: Redis connection URL
            max_connections: Connection pool size
            ttl: Message TTL in seconds (auto-cleanup)
        """
        self._url = url
        self._max_connections = max_connections
        self._ttl = ttl
        self._pool: redis.ConnectionPool | None = None
        self._client: redis.Redis | None = None
        self._local_sessions: set[str] = set()  # Sessions active in this process
        self._initialized = False

    async def initialize(self) -> None:
        """Connect to Redis."""
        if self._initialized:
            return

        try:
            self._pool = redis.ConnectionPool.from_url(
                self._url,
                max_connections=self._max_connections,
                decode_responses=True,
            )
            self._client = redis.Redis(connection_pool=self._pool)

            # Test connection
            await self._client.ping()
            self._initialized = True
            logger.info(f"[RedisBackend] Connected to {self._url}")
        except Exception as e:
            logger.error(f"[RedisBackend] Connection failed: {e}")
            raise

    async def shutdown(self) -> None:
        """Close Redis connection."""
        if self._client:
            await self._client.close()
        if self._pool:
            await self._pool.disconnect()
        self._initialized = False
        logger.info("[RedisBackend] Shutdown complete")

    async def push_message(self, session_id: str, message: dict) -> bool:
        """Push message to Redis list with TTL and pub/sub notification."""
        if not self._initialized or not self._client:
            logger.warning("[RedisBackend] Not initialized, cannot push")
            return False

        try:
            queue_key = QUEUE_KEY.format(session_id=session_id)

            # 1. LPUSH to list (message persistence)
            await self._client.lpush(queue_key, json.dumps(message))

            # 2. Set TTL for auto-cleanup
            await self._client.expire(queue_key, self._ttl)

            # 3. PUBLISH notification for fast wake-up
            notify_key = NOTIFY_KEY.format(session_id=session_id)
            await self._client.publish(notify_key, "1")

            logger.debug(f"[RedisBackend] Pushed to {session_id}: {message.get('type')}")
            return True
        except Exception as e:
            logger.error(f"[RedisBackend] Push failed: {e}")
            return False

    async def pop_message(self, session_id: str, timeout: float = 30.0) -> dict | None:
        """Pop message using BLPOP (blocking with timeout)."""
        if not self._initialized or not self._client:
            return None

        queue_key = QUEUE_KEY.format(session_id=session_id)

        try:
            # BLPOP blocks until message or timeout
            # Returns tuple: (key, value) or None on timeout
            result = await self._client.blpop(queue_key, timeout=int(timeout))

            if result:
                # result[1] is the message JSON string
                return json.loads(result[1])
            return None
        except Exception as e:
            logger.error(f"[RedisBackend] Pop failed: {e}")
            return None

    def has_session(self, session_id: str) -> bool:
        """Check if session is active in this process."""
        return session_id in self._local_sessions

    def list_sessions(self) -> list[str]:
        """List sessions active in this process."""
        return list(self._local_sessions)

    async def register_session(self, session_id: str) -> None:
        """Register session in Redis set and local tracking."""
        if not self._initialized or not self._client:
            return

        self._local_sessions.add(session_id)

        # Add to global active sessions set
        await self._client.sadd(SESSIONS_KEY, session_id)
        logger.info(f"[RedisBackend] Registered session {session_id}")

    async def unregister_session(self, session_id: str) -> None:
        """Unregister session from Redis and local tracking."""
        if not self._initialized or not self._client:
            # Still cleanup local tracking even if Redis unavailable
            self._local_sessions.discard(session_id)
            return

        self._local_sessions.discard(session_id)

        # Remove from global set
        await self._client.srem(SESSIONS_KEY, session_id)

        # Clean up queue keys
        queue_key = QUEUE_KEY.format(session_id=session_id)
        await self._client.delete(queue_key)

        logger.info(f"[RedisBackend] Unregistered session {session_id}")

    async def get_global_sessions(self) -> list[str]:
        """Get all sessions across all workers (for monitoring)."""
        if not self._initialized or not self._client:
            return []

        sessions = await self._client.smembers(SESSIONS_KEY)
        return list(sessions)

    async def push_user_event(self, session_id: str, event: dict) -> None:
        """Push user interaction event back to queue.

        Used by POST /canvas/event endpoint.
        """
        await self.push_message(session_id, event)


__all__ = ["RedisBackend"]