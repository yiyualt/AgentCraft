"""Base Channel abstraction and Channel Router."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Channel(ABC):
    """Base class for all communication channels.

    Each channel (Telegram, Slack, Web) implements this interface
    to handle incoming messages and send responses.
    """

    name: str = "base"

    @abstractmethod
    async def start(self) -> None:
        """Start the channel (connect to service, begin polling, etc.)."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop the channel (disconnect, cleanup)."""
        ...

    @abstractmethod
    async def send_message(self, peer_id: str, text: str) -> None:
        """Send a message to a specific peer/user."""
        ...

    @abstractmethod
    async def handle_message(self, message: Any) -> None:
        """Process an incoming message from this channel."""
        ...


class ChannelRouter:
    """Routes incoming messages to appropriate sessions.

    Maps channel-specific identifiers to internal session IDs.
    """

    def __init__(self):
        self._channels: dict[str, Channel] = {}

    def register(self, channel: Channel) -> None:
        """Register a channel."""
        self._channels[channel.name] = channel

    def unregister(self, name: str) -> None:
        """Unregister a channel."""
        self._channels.pop(name, None)

    def get_channel(self, name: str) -> Channel | None:
        """Get a registered channel by name."""
        return self._channels.get(name)

    def get_session_name(self, channel_name: str, peer_id: str) -> str:
        """Generate session name from channel and peer identifiers."""
        return f"{channel_name}-{peer_id}"

    async def start_all(self) -> None:
        """Start all registered channels."""
        for channel in self._channels.values():
            await channel.start()

    async def stop_all(self) -> None:
        """Stop all registered channels."""
        for channel in self._channels.values():
            await channel.stop()