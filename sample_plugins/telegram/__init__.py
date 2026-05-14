"""Sample Telegram plugin for AgentCraft."""

from __future__ import annotations

from plugins import Plugin, PluginMetadata, PluginContext


class TelegramPlugin(Plugin):
    """Telegram bot channel as a plugin."""

    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="telegram",
            version="1.0.0",
            author="AgentCraft Team",
            description="Telegram bot channel for AgentCraft",
            homepage="https://github.com/pyleaf/agentcraft",
            requires=["1.0"],
        )

    async def on_load(self, context: PluginContext) -> None:
        """Initialize Telegram channel."""
        import os

        # Get bot token from config or environment
        token = context.plugin_config.get(
            "bot_token",
            os.environ.get("TELEGRAM_BOT_TOKEN", "")
        )

        if not token:
            import logging
            logging.warning("[TelegramPlugin] No bot token configured")
            return

        # Create and register channel
        from channels.telegram import TelegramChannel
        channel = TelegramChannel(context.session_manager)
        context.register_channel(channel)

        # Add plugin-specific routes
        context.add_route(
            "/telegram/status",
            self._status_endpoint,
            methods=["GET"]
        )

    async def on_unload(self) -> None:
        """Cleanup Telegram resources."""
        # Channel cleanup handled by ChannelRouter
        pass

    async def _status_endpoint(self) -> dict:
        """Status endpoint for plugin."""
        return {
            "plugin": "telegram",
            "version": "1.0.0",
            "status": "active",
        }