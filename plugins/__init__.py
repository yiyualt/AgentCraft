"""Plugin module for extensibility."""

from .base import (
    Plugin,
    PluginMetadata,
    PluginContext,
    PluginLoader,
    get_plugin_loader,
    init_plugin_loader,
)

__all__ = [
    "Plugin",
    "PluginMetadata",
    "PluginContext",
    "PluginLoader",
    "get_plugin_loader",
    "init_plugin_loader",
]