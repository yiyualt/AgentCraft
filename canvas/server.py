"""CanvasChannel - SSE server for real-time workspace updates."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from canvas.manager import CanvasManager
from canvas.backends.memory_backend import MemoryBackend

logger = logging.getLogger(__name__)


class CanvasChannel:
    """Canvas channel with SSE streaming and event handling.

    Routes:
        GET /canvas           - Canvas HTML page
        GET /canvas/stream/{session_id} - SSE stream endpoint
        POST /canvas/event/{session_id} - User interaction events
    """

    name = "canvas"

    def __init__(self, canvas_manager: CanvasManager):
        """Initialize CanvasChannel.

        Args:
            canvas_manager: CanvasManager instance for queue management
        """
        self._manager = canvas_manager
        self._router = APIRouter(prefix="/canvas", tags=["canvas"])
        self._setup_routes()

    def get_router(self) -> APIRouter:
        """Get the FastAPI router."""
        return self._router

    async def start(self) -> None:
        """Start the channel (initialize backend)."""
        await self._manager.initialize()
        logger.info("[Canvas] Channel started")

    async def stop(self) -> None:
        """Stop the channel and cleanup."""
        for session_id in self._manager.list_active_sessions():
            await self._manager._backend.unregister_session(session_id)
        await self._manager.shutdown()
        logger.info("[Canvas] Channel stopped")

    async def send_message(self, peer_id: str, text: str) -> None:
        """Send a message (push update to canvas)."""
        await self._manager.push_update(peer_id, text)

    async def handle_message(self, message: Any) -> None:
        """Handle incoming message (events posted to /event endpoint)."""
        pass  # Events are handled via POST endpoint

    def _setup_routes(self) -> None:
        """Setup all routes."""

        @self._router.get("", response_class=HTMLResponse)
        async def canvas_page():
            """Serve the Canvas HTML page."""
            html_path = Path(__file__).parent.parent / "static" / "canvas.html"
            if html_path.exists():
                return HTMLResponse(
                    content=html_path.read_text(),
                    headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
                )
            return HTMLResponse(
                content="<h1>Canvas page not found</h1><p>Please create static/canvas.html</p>",
                status_code=404,
            )

        @self._router.get("/stream/{session_id}")
        async def stream_canvas(session_id: str, request: Request):
            """SSE stream for real-time canvas updates.

            Client connects here to receive updates pushed by canvas_update tool.
            Heartbeat every 30s to keep connection alive.
            """
            # Register session
            await self._manager._backend.register_session(session_id)

            async def event_generator():
                # Send initial connection event
                yield f"event: connected\ndata: {json.dumps({'session_id': session_id})}\n\n"

                try:
                    while True:
                        # Check if client disconnected
                        if await request.is_disconnected():
                            logger.info(f"[Canvas SSE] Client disconnected: {session_id}")
                            break

                        # Wait for updates with timeout (heartbeat)
                        try:
                            # Use backend.pop_message() instead of queue.get()
                            update = await self._manager._backend.pop_message(session_id, timeout=30.0)

                            if update:
                                event_type = update.get("type", "update")
                                yield f"event: {event_type}\ndata: {json.dumps(update)}\n\n"
                            else:
                                # Timeout - send heartbeat
                                yield "event: heartbeat\ndata: \n\n"

                        except Exception as e:
                            logger.error(f"[Canvas SSE] Error: {e}")
                            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

                except asyncio.CancelledError:
                    logger.info(f"[Canvas SSE] Stream cancelled: {session_id}")
                finally:
                    # Cleanup session
                    await self._manager._backend.unregister_session(session_id)

            return StreamingResponse(
                event_generator(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",  # Disable nginx buffering
                },
            )

        @self._router.post("/event/{session_id}")
        async def handle_event(session_id: str, request: Request):
            """Handle user interaction events from canvas.

            Events from interactive components (button clicks, form submits)
            are posted here and can trigger agent responses.
            """
            data = await request.json()
            event_type = data.get("type", "unknown")
            component_id = data.get("component_id", "")
            event_data = data.get("data", {})

            logger.info(
                f"[Canvas Event] session={session_id}, type={event_type}, "
                f"component={component_id}, data={event_data}"
            )

            # Push the event back to the session queue for agent to receive
            event_update = {
                "type": "user_interaction",
                "id": component_id,
                "event_type": event_type,
                "data": event_data,
                "timestamp": datetime.now().isoformat(),
            }
            await self._manager.push_user_event(session_id, event_update)
            logger.info(f"[Canvas] User interaction pushed to queue: {event_type}")

            return {
                "status": "received",
                "session_id": session_id,
                "event_type": event_type,
            }

        @self._router.get("/health")
        async def canvas_health():
            """Check canvas health and active sessions."""
            return {
                "status": "ok",
                "active_sessions": self._manager.list_active_sessions(),
                "backend": type(self._manager._backend).__name__,
            }


__all__ = ["CanvasChannel"]