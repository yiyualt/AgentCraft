"""Channel Adapters - External communication channels for AgentCraft."""

from channels.base import Channel, ChannelRouter
from channels.cli import CLIChannel, NormalizedMessage, WebChannelWrapper, TelegramChannelWrapper

__all__ = [
    "Channel",
    "ChannelRouter",
    "CLIChannel",
    "NormalizedMessage",
    "WebChannelWrapper",
    "TelegramChannelWrapper",
]