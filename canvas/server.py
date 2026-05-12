"""CanvasChannel - SSE server for real-time workspace updates."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from canvas.manager import CanvasManager
from channels.base import Channel

logger = logging.getLogger(__name__)


class CanvasChannel(Channel):
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
        """Start the channel (no async initialization needed for SSE)."""
        logger.info("[Canvas] Channel started")

    async def stop(self) -> None:
        """Stop the channel and clean up all queues."""
        for session_id in self._manager.list_active_sessions():
            self._manager.remove_queue(session_id)
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
                return HTMLResponse(content=html_path.read_text())
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
            queue = self._manager.get_or_create_queue(session_id)

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
                            update = await asyncio.wait_for(queue.get(), timeout=30.0)
                            event_type = update.get("type", "update")
                            yield f"event: {event_type}\ndata: {json.dumps(update)}\n\n"
                        except asyncio.TimeoutError:
                            # Send heartbeat to keep connection alive
                            yield "event: heartbeat\ndata: \n\n"

                except asyncio.CancelledError:
                    logger.info(f"[Canvas SSE] Stream cancelled: {session_id}")
                finally:
                    # Cleanup queue on disconnect
                    self._manager.remove_queue(session_id)

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

            # For now, just acknowledge the event
            # In future, this could trigger agent response via session message
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
            }


__all__ = ["CanvasChannel"]