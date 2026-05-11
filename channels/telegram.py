"""Telegram Bot Channel implementation."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import httpx

from channels.base import Channel
from sessions.manager import SessionManager


class TelegramChannel(Channel):
    """Telegram Bot using polling mode (no webhook required)."""

    name = "telegram"
    API_BASE = "https://api.telegram.org/bot"

    def __init__(self, session_manager: SessionManager, gateway_url: str = "http://127.0.0.1:8000"):
        self._token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self._session_manager = session_manager
        self._gateway_url = gateway_url
        self._client = httpx.AsyncClient(timeout=30.0)
        self._offset = 0
        self._running = False
        self._poll_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start polling for messages."""
        if not self._token:
            print("[Telegram] No TELEGRAM_BOT_TOKEN set, skipping")
            return

        self._running = True
        me = await self._api_request("getMe")
        if me:
            print(f"[Telegram] Bot started: @{me.get('username', 'unknown')}")

        self._poll_task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        """Stop polling."""
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        await self._client.aclose()

    async def send_message(self, peer_id: str, text: str) -> None:
        """Send message to Telegram chat."""
        await self._api_request("sendMessage", {"chat_id": peer_id, "text": text})

    async def handle_message(self, update: dict) -> None:
        """Process incoming Telegram update."""
        message = update.get("message")
        if not message:
            return

        chat_id = str(message.get("chat", {}).get("id", ""))
        text = message.get("text", "")
        user_name = message.get("from", {}).get("first_name", "User")

        if not text:
            return

        # Handle commands
        if text.startswith("/"):
            await self._handle_command(chat_id, text, user_name)
            return

        # Regular message - send to LLM
        await self._process_chat(chat_id, text, user_name)

    async def _handle_command(self, chat_id: str, text: str, user_name: str) -> None:
        """Handle Telegram commands."""
        command = text.split()[0].lower()

        if command == "/new":
            # Create new session
            session = self._session_manager.create_session(
                name=f"telegram-{chat_id}-new",
                model="deepseek-chat"
            )
            await self.send_message(chat_id, f"已创建新对话: {session.id}")

        elif command == "/history":
            # Show recent history
            session_name = f"telegram-{chat_id}"
            sessions = self._session_manager.list_sessions()
            matched = [s for s in sessions if s.name == session_name]

            if not matched:
                await self.send_message(chat_id, "没有历史记录")
                return

            session = matched[0]
            messages = self._session_manager.get_messages(session.id, limit=10)

            if not messages:
                await self.send_message(chat_id, "没有历史消息")
                return

            history_text = "最近的对话:\n"
            for msg in messages[-5:]:
                role = msg.role
                content = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
                history_text += f"[{role}] {content}\n"

            await self.send_message(chat_id, history_text)

        elif command == "/help":
            await self.send_message(chat_id, "可用命令:\n/new - 创建新对话\n/history - 查看历史\n/help - 帮助")

        else:
            await self.send_message(chat_id, f"未知命令: {command}")

    async def _process_chat(self, chat_id: str, text: str, user_name: str) -> None:
        """Send message to Gateway and get response."""
        session_name = f"telegram-{chat_id}"

        # Find or create session
        sessions = self._session_manager.list_sessions()
        matched = [s for s in sessions if s.name == session_name]

        if matched:
            session = matched[0]
            session_id = session.id
        else:
            session = self._session_manager.create_session(
                name=session_name,
                model="deepseek-chat"
            )
            session_id = session.id

        # Call Gateway
        try:
            response = await self._client.post(
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
                data = response.json()
                assistant_msg = data.get("choices", [{}])[0].get("message", {})
                reply = assistant_msg.get("content", "无回复")
                await self.send_message(chat_id, reply)
            else:
                await self.send_message(chat_id, f"请求失败: {response.status_code}")

        except Exception as e:
            await self.send_message(chat_id, f"错误: {str(e)}")

    async def _poll_loop(self) -> None:
        """Polling loop for updates."""
        while self._running:
            try:
                updates = await self._api_request("getUpdates", {"offset": self._offset, "timeout": 30})

                if updates:
                    for update in updates:
                        await self.handle_message(update)
                        self._offset = update.get("update_id", 0) + 1

            except Exception as e:
                print(f"[Telegram] Poll error: {e}")
                await asyncio.sleep(5)

    async def _api_request(self, method: str, params: dict | None = None) -> Any:
        """Make Telegram Bot API request."""
        url = f"{self.API_BASE}{self._token}/{method}"

        try:
            response = await self._client.post(url, json=params or {})
            data = response.json()

            if data.get("ok"):
                return data.get("result")
            else:
                print(f"[Telegram] API error: {data.get('description', 'unknown')}")
                return None

        except Exception as e:
            print(f"[Telegram] Request error: {e}")
            return None