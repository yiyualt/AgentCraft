"""LLM Request Queue - manages concurrent LLM requests with queuing.

Solves the blocking problem when multiple concurrent requests arrive:
- Requests queue if semaphore is exhausted (no direct 429 rejection)
- Each request acquires semaphore only during stream generation
- Timeout returns graceful error
- Metrics for monitoring
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Callable

logger = logging.getLogger(__name__)


class RequestStatus(Enum):
    """Request lifecycle status."""
    QUEUED = "queued"
    ACTIVE = "active"
    COMPLETED = "completed"
    TIMEOUT = "timeout"
    ERROR = "error"


@dataclass
class QueuedRequest:
    """A queued LLM request."""
    request_id: str
    session_id: str | None
    model: str
    messages: list[dict[str, Any]]
    kwargs: dict[str, Any] = field(default_factory=dict)
    status: RequestStatus = RequestStatus.QUEUED
    queued_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    wait_time_ms: float | None = None
    execute_time_ms: float | None = None
    error: str | None = None
    # For streaming
    _stream_ready: asyncio.Event = field(default_factory=asyncio.Event)
    _stream_iterator: AsyncIterator[str] | None = None
    _stream_result: dict[str, Any] = field(default_factory=dict)
    _stream_error: str | None = None


@dataclass
class QueueMetrics:
    """Queue performance metrics."""
    total_requests: int = 0
    queued_requests: int = 0
    active_requests: int = 0
    completed_requests: int = 0
    timeout_requests: int = 0
    error_requests: int = 0
    avg_wait_time_ms: float = 0.0
    avg_execute_time_ms: float = 0.0


class LLMRequestQueue:
    """Manages LLM request concurrency with queue-based handling.

    Architecture:
        Request → Queue → Semaphore → Provider.stream() → SSE

    Config:
        - max_concurrent: Semaphore limit (default 10)
        - max_queue_size: Max queued requests (default 100)
        - queue_timeout: Max wait time in queue (default 60s)
        - request_timeout: Max request duration (default 300s)
    """

    def __init__(
        self,
        max_concurrent: int = 10,
        max_queue_size: int = 100,
        queue_timeout: float = 60.0,
        request_timeout: float = 300.0,
    ):
        self._max_concurrent = max_concurrent
        self._max_queue_size = max_queue_size
        self._queue_timeout = queue_timeout
        self._request_timeout = request_timeout

        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._queue: asyncio.Queue[QueuedRequest] = asyncio.Queue(maxsize=max_queue_size)
        self._pending: dict[str, QueuedRequest] = {}
        self._metrics = QueueMetrics()
        self._running = False
        self._processor_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start queue processor."""
        if self._running:
            return
        self._running = True
        self._processor_task = asyncio.create_task(self._process_queue())
        logger.info(
            f"[LLMQueue] Started: max_concurrent={self._max_concurrent}, "
            f"max_queue={self._max_queue_size}, queue_timeout={self._queue_timeout}s"
        )

    async def stop(self) -> None:
        """Stop queue processor."""
        self._running = False
        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass
        logger.info("[LLMQueue] Stopped")

    async def submit_streaming(
        self,
        messages: list[dict[str, Any]],
        model: str,
        session_id: str | None = None,
        stream_executor: Callable[[QueuedRequest], AsyncIterator[str]] | None = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        """Submit streaming request to queue.

        Yields SSE events. Raises TimeoutError if queue wait exceeds limit.
        """
        request_id = f"req-{uuid.uuid4().hex[:8]}"

        request = QueuedRequest(
            request_id=request_id,
            session_id=session_id,
            model=model,
            messages=messages,
            kwargs=kwargs,
        )

        # Check queue capacity
        if self._queue.full():
            yield f"event: error\ndata: {{\"error\": \"Queue full (max {self._max_queue_size} requests)\"}}\n\n"
            return

        # Store executor for later
        request._stream_executor = stream_executor

        # Enqueue
        await self._queue.put(request)
        self._pending[request_id] = request

        # Update metrics
        self._metrics.total_requests += 1
        self._metrics.queued_requests += 1

        queue_pos = self._queue.qsize()
        logger.info(f"[LLMQueue] Request {request_id} queued (pos={queue_pos})")

        # Yield queue status
        yield f"event: queue_status\ndata: {{\"request_id\": \"{request_id}\", \"status\": \"queued\", \"position\": {queue_pos}}}\n\n"

        # Wait for stream to be ready (with timeout)
        try:
            await asyncio.wait_for(
                request._stream_ready.wait(),
                timeout=self._queue_timeout + self._request_timeout,
            )
        except asyncio.TimeoutError:
            request.status = RequestStatus.TIMEOUT
            request.error = f"Queue wait timeout ({self._queue_timeout}s)"
            self._metrics.timeout_requests += 1
            self._metrics.queued_requests -= 1
            yield f"event: error\ndata: {{\"error\": \"{request.error}\"}}\n\n"
            if request_id in self._pending:
                del self._pending[request_id]
            return

        # Check if request was processed
        if request.status == RequestStatus.ERROR:
            yield f"event: error\ndata: {{\"error\": \"{request.error}\"}}\n\n"
            return

        # Stream results
        if request._stream_iterator:
            try:
                for chunk in request._stream_iterator:
                    yield chunk
            except Exception as e:
                logger.error(f"[LLMQueue] Stream error: {e}")
                yield f"event: error\ndata: {{\"error\": \"{str(e)}\"}}\n\n"

        # Final status
        if request.status == RequestStatus.COMPLETED:
            yield f"event: stream_end\ndata: {{\"request_id\": \"{request_id}\"}}\n\n"
        elif request.status == RequestStatus.TIMEOUT:
            yield f"event: error\ndata: {{\"error\": \"Request timeout\"}}\n\n"

        # Cleanup
        if request_id in self._pending:
            del self._pending[request_id]

    async def _process_queue(self) -> None:
        """Background task: process queued requests."""
        while self._running:
            try:
                # Wait for next request
                request = await asyncio.wait_for(self._queue.get(), timeout=1.0)

                # Update status
                request.status = RequestStatus.ACTIVE
                request.started_at = time.time()
                request.wait_time_ms = (request.started_at - request.queued_at) * 1000

                self._metrics.queued_requests -= 1
                self._metrics.active_requests += 1

                logger.info(
                    f"[LLMQueue] Request {request.request_id} started "
                    f"(wait={request.wait_time_ms:.0f}ms)"
                )

                # Acquire semaphore and execute
                async with self._semaphore:
                    # Signal ready
                    request._stream_ready.set()

                    # Execute streaming if executor provided
                    if hasattr(request, "_stream_executor") and request._stream_executor:
                        try:
                            async with asyncio.timeout(self._request_timeout):
                                # Collect stream results
                                stream_result = []
                                for chunk in request._stream_executor(request):
                                    stream_result.append(chunk)
                                    request._stream_iterator = iter(stream_result)

                        except asyncio.TimeoutError:
                            request.status = RequestStatus.TIMEOUT
                            request.error = f"Request timeout ({self._request_timeout}s)"
                            self._metrics.timeout_requests += 1
                        except Exception as e:
                            request.status = RequestStatus.ERROR
                            request.error = str(e)
                            self._metrics.error_requests += 1
                            logger.error(f"[LLMQueue] Execute error: {e}")

                # Mark completed
                request.completed_at = time.time()
                request.execute_time_ms = (request.completed_at - request.started_at) * 1000

                if request.status == RequestStatus.ACTIVE:
                    request.status = RequestStatus.COMPLETED

                self._metrics.active_requests -= 1
                self._metrics.completed_requests += 1

                # Update avg metrics
                n = self._metrics.completed_requests
                self._metrics.avg_wait_time_ms = (
                    (self._metrics.avg_wait_time_ms * (n - 1) + request.wait_time_ms) / n
                )
                self._metrics.avg_execute_time_ms = (
                    (self._metrics.avg_execute_time_ms * (n - 1) + request.execute_time_ms) / n
                )

                logger.info(
                    f"[LLMQueue] Request {request.request_id} completed "
                    f"(execute={request.execute_time_ms:.0f}ms)"
                )

                self._queue.task_done()

            except asyncio.TimeoutError:
                # No requests, continue polling
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[LLMQueue] Processor error: {e}")
                await asyncio.sleep(1.0)

    def get_status(self) -> dict[str, Any]:
        """Get queue status snapshot."""
        return {
            "running": self._running,
            "max_concurrent": self._max_concurrent,
            "max_queue_size": self._max_queue_size,
            "queue_timeout": self._queue_timeout,
            "request_timeout": self._request_timeout,
            "current_queue_size": self._queue.qsize(),
            "semaphore_value": self._semaphore._value,
            "metrics": {
                "total_requests": self._metrics.total_requests,
                "queued_requests": self._metrics.queued_requests,
                "active_requests": self._metrics.active_requests,
                "completed_requests": self._metrics.completed_requests,
                "timeout_requests": self._metrics.timeout_requests,
                "error_requests": self._metrics.error_requests,
                "avg_wait_time_ms": round(self._metrics.avg_wait_time_ms, 1),
                "avg_execute_time_ms": round(self._metrics.avg_execute_time_ms, 1),
            },
        }


__all__ = ["LLMRequestQueue", "QueuedRequest", "QueueMetrics", "RequestStatus"]