"""Web Chat Channel - Simple HTML/JS frontend with SSE streaming."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from sessions.manager import SessionManager


class WebChannel:
    """Web Chat channel using FastAPI routes.

    Provides:
    - Static HTML page at /chat
    - SSE streaming endpoint at /chat/stream
    - Session management via browser
    """

    name = "web"

    def __init__(self, session_manager: SessionManager, gateway_url: str = "http://127.0.0.1:8000"):
        self._session_manager = session_manager
        self._gateway_url = gateway_url
        self._router = APIRouter(prefix="/chat", tags=["chat"])
        self._setup_routes()

    def get_router(self) -> APIRouter:
        """Return FastAPI router for web chat."""
        return self._router

    async def start(self) -> None:
        """No async startup needed for web channel."""
        print("[Web] Chat routes ready at /chat")

    async def stop(self) -> None:
        """No cleanup needed."""
        pass

    async def send_message(self, peer_id: str, text: str) -> None:
        """Not used for web - responses via SSE."""
        pass

    async def handle_message(self, message: Any) -> None:
        """Not used for web - handled by HTTP routes."""
        pass

    def _setup_routes(self) -> None:
        """Set up FastAPI routes."""

        @self._router.get("", response_class=HTMLResponse)
        async def chat_page():
            """Serve the chat HTML page."""
            html_path = Path(__file__).parent.parent / "static" / "chat.html"
            if html_path.exists():
                return HTMLResponse(content=html_path.read_text())
            return HTMLResponse(content="<h1>Chat page not found</h1>")

        @self._router.post("/message")
        async def send_message(request: Request):
            """Send message and get response (non-streaming)."""
            data = await request.json()
            session_id = data.get("session_id")
            text = data.get("text", "")

            if not session_id:
                # Create new session
                session = self._session_manager.create_session(
                    name=f"web-{data.get('user_id', 'anonymous')}",
                    model="deepseek-chat"
                )
                session_id = session.id

            # Call gateway internally (same process, no HTTP)
            import httpx
            client = httpx.AsyncClient(timeout=60.0)

            try:
                response = await client.post(
                    f"{self._gateway_url}/v1/chat/completions",
                    headers={
                        "Content-Type": "application/json",
                        "X-Session-Id": session_id,
                    },
                    json={
                        "model": "deepseek-chat",
                        "messages": [{"role": "user", "content": text}],
                    },
                )

                if response.status_code == 200:
                    result = response.json()
                    return {
                        "session_id": session_id,
                        "response": result.get("choices", [{}])[0].get("message", {}).get("content", ""),
                    }
                else:
                    return {"error": f"Gateway error: {response.status_code}"}

            finally:
                await client.aclose()

        @self._router.get("/sessions")
        async def list_sessions():
            """List all sessions."""
            sessions = self._session_manager.list_sessions()
            return {
                "sessions": [
                    {
                        "id": s.id,
                        "name": s.name,
                        "model": s.model,
                        "message_count": s.message_count,
                    }
                    for s in sessions
                ]
            }

        @self._router.post("/session/new")
        async def new_session(request: Request):
            """Create a new session."""
            data = await request.json()
            session = self._session_manager.create_session(
                name=data.get("name", f"web-{data.get('user_id', 'anonymous')}"),
                model=data.get("model", "deepseek-chat")
            )
            return {"session_id": session.id, "name": session.name}

        @self._router.get("/session/{session_id}/messages")
        async def get_messages(session_id: str):
            """Get messages for a session."""
            messages = self._session_manager.get_messages(session_id)
            return {
                "messages": [
                    {
                        "id": m.id,
                        "role": m.role,
                        "content": m.content,
                    }
                    for m in messages
                ]
            }