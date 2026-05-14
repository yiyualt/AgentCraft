"""CLI Channel implementation for terminal interface."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from channels.base import Channel
from sessions.manager import SessionManager


@dataclass
class NormalizedMessage:
    """Normalized message format across all channels."""
    channel_id: str  # Channel type (cli, telegram, web, etc.)
    user_id: str     # User identifier
    peer_id: str     # Conversation/chat ID
    content: str     # Message content (text)
    metadata: dict[str, Any]  # Channel-specific metadata


class CLIChannel(Channel):
    """CLI terminal channel implementation."""

    name = "cli"

    def __init__(self, session_manager: SessionManager):
        self._session_manager = session_manager
        self._running = False
        self._message_queue: asyncio.Queue[NormalizedMessage] = asyncio.Queue()

    async def start(self) -> None:
        """Start CLI channel."""
        self._running = True
        # CLI doesn't need async start - it's handled by the REPL loop

    async def stop(self) -> None:
        """Stop CLI channel."""
        self._running = False

    async def send_message(self, peer_id: str, text: str) -> None:
        """Send message to CLI (print to terminal).

        Args:
            peer_id: Session ID (unused for CLI, single user)
            text: Message text to display
        """
        # CLI output is handled by the REPL, this is for programmatic send
        print(text)

    async def handle_message(self, message: Any) -> None:
        """Process incoming CLI message.

        Args:
            message: NormalizedMessage or raw dict
        """
        if isinstance(message, NormalizedMessage):
            await self._message_queue.put(message)
        elif isinstance(message, dict):
            norm_msg = self.normalize_message(message)
            await self._message_queue.put(norm_msg)

    def normalize_message(self, raw_message: dict[str, Any]) -> NormalizedMessage:
        """Normalize CLI message to standard format.

        CLI messages have:
        - user: current user (default "cli-user")
        - session: session ID
        - content: text input
        """
        return NormalizedMessage(
            channel_id=self.name,
            user_id=raw_message.get("user", "cli-user"),
            peer_id=raw_message.get("session", "cli-default"),
            content=raw_message.get("content", ""),
            metadata={
                "timestamp": raw_message.get("timestamp"),
                "source": "terminal",
            },
        )

    async def receive_message(self) -> NormalizedMessage | None:
        """Receive next message from queue.

        Used by CLI REPL to get messages.
        """
        try:
            return await asyncio.wait_for(
                self._message_queue.get(),
                timeout=0.1,
            )
        except asyncio.TimeoutError:
            return None

    def create_session_name(self, peer_id: str) -> str:
        """Generate session name from peer ID."""
        return f"cli-{peer_id}"


class WebChannelWrapper(Channel):
    """Wrapper for WebChannel to ensure normalized messages."""

    name = "web"

    def __init__(self, base_channel: Channel):
        self._base = base_channel

    async def start(self) -> None:
        await self._base.start()

    async def stop(self) -> None:
        await self._base.stop()

    async def send_message(self, peer_id: str, text: str) -> None:
        await self._base.send_message(peer_id, text)

    async def handle_message(self, message: Any) -> None:
        """Normalize message before handling."""
        if isinstance(message, dict) and "content" in message:
            norm_msg = NormalizedMessage(
                channel_id=self.name,
                user_id=message.get("user_id", "web-user"),
                peer_id=message.get("peer_id", "web-default"),
                content=message.get("content", ""),
                metadata=message.get("metadata", {}),
            )
            await self._base.handle_message({
                "normalized": norm_msg,
                "original": message,
            })
        else:
            await self._base.handle_message(message)

    def normalize_message(self, raw_message: dict[str, Any]) -> NormalizedMessage:
        """Normalize web message."""
        return NormalizedMessage(
            channel_id=self.name,
            user_id=raw_message.get("user_id", "web-user"),
            peer_id=raw_message.get("peer_id", raw_message.get("session_id", "web-default")),
            content=raw_message.get("content", ""),
            metadata={
                "request_id": raw_message.get("request_id"),
                "source": "web",
            },
        )


class TelegramChannelWrapper(Channel):
    """Wrapper for TelegramChannel to ensure normalized messages."""

    name = "telegram"

    def __init__(self, base_channel: Channel):
        self._base = base_channel

    async def start(self) -> None:
        await self._base.start()

    async def stop(self) -> None:
        await self._base.stop()

    async def send_message(self, peer_id: str, text: str) -> None:
        await self._base.send_message(peer_id, text)

    async def handle_message(self, message: Any) -> None:
        """Normalize Telegram message before handling."""
        if isinstance(message, dict) and "message" in message:
            # Telegram update format
            msg = message.get("message", {})
            norm_msg = NormalizedMessage(
                channel_id=self.name,
                user_id=str(msg.get("from", {}).get("id", "telegram-user")),
                peer_id=str(msg.get("chat", {}).get("id", "telegram-default")),
                content=msg.get("text", ""),
                metadata={
                    "username": msg.get("from", {}).get("username"),
                    "first_name": msg.get("from", {}).get("first_name"),
                    "message_id": msg.get("message_id"),
                    "source": "telegram",
                },
            )
            await self._base.handle_message({
                "normalized": norm_msg,
                "original": message,
            })
        else:
            await self._base.handle_message(message)

    def normalize_message(self, raw_message: dict[str, Any]) -> NormalizedMessage:
        """Normalize Telegram message."""
        msg = raw_message.get("message", {})
        return NormalizedMessage(
            channel_id=self.name,
            user_id=str(msg.get("from", {}).get("id", "telegram-user")),
            peer_id=str(msg.get("chat", {}).get("id", "telegram-default")),
            content=msg.get("text", ""),
            metadata={
                "username": msg.get("from", {}).get("username"),
                "source": "telegram",
            },
        )