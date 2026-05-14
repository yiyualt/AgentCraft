"""Plugin base class and loader for extensibility."""

from __future__ import annotations

import importlib
import logging
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PluginMetadata:
    """Plugin metadata."""
    name: str
    version: str
    author: str = ""
    description: str = ""
    homepage: str = ""
    requires: list[str] = field(default_factory=list)  # Required AgentCraft version


class Plugin(ABC):
    """Base class for all plugins.

    Plugins can:
    - Register custom tools
    - Register custom channels
    - Add middleware
    - Extend behavior

    Lifecycle:
    1. PluginLoader discovers plugin
    2. PluginContext created
    3. plugin.on_load(context)
    4. Plugin active during runtime
    5. plugin.on_unload() on shutdown
    """

    @property
    @abstractmethod
    def metadata(self) -> PluginMetadata:
        """Return plugin metadata."""
        ...

    @abstractmethod
    async def on_load(self, context: PluginContext) -> None:
        """Called when plugin is loaded.

        Use context to register tools, channels, etc.
        """
        ...

    @abstractmethod
    async def on_unload(self) -> None:
        """Called when plugin is unloaded.

        Clean up resources, unregister handlers.
        """
        ...

    def check_compatibility(self, agentcraft_version: str) -> bool:
        """Check if plugin is compatible with AgentCraft version."""
        if not self.metadata.requires:
            return True  # No version requirement

        from gateway.version import VersionInfo

        ac_version = VersionInfo.parse(agentcraft_version)

        for req in self.metadata.requires:
            req_version = VersionInfo.parse(req)
            # Major must match
            if req_version.major != ac_version.major:
                return False
            # Minor can be lower or equal
            if req_version.minor > ac_version.minor:
                return False

        return True


@dataclass
class PluginContext:
    """Context provided to plugins on load.

    Provides access to registries and configuration.
    """

    # Tool registry
    tool_registry: Any = None

    # Channel router
    channel_router: Any = None

    # Session manager
    session_manager: Any = None

    # Plugin config (from config file)
    config: dict[str, Any] = field(default_factory=dict)

    # Plugin-specific config section
    plugin_config: dict[str, Any] = field(default_factory=dict)

    # Gateway app (for adding routes/middleware)
    app: Any = None

    def register_tool(self, tool_func: Any) -> None:
        """Register a tool function."""
        if self.tool_registry:
            self.tool_registry.register(tool_func)
            logger.info(f"[PluginContext] Tool registered: {tool_func.__name__}")

    def register_channel(self, channel: Any) -> None:
        """Register a channel."""
        if self.channel_router:
            self.channel_router.register(channel)
            logger.info(f"[PluginContext] Channel registered: {channel.name}")

    def add_route(self, path: str, endpoint: Any, methods: list[str] = None) -> None:
        """Add a route to the gateway."""
        if self.app:
            from fastapi import APIRouter
            router = APIRouter()
            for method in (methods or ["GET"]):
                if method == "GET":
                    router.get(path)(endpoint)
                elif method == "POST":
                    router.post(path)(endpoint)
            self.app.include_router(router)
            logger.info(f"[PluginContext] Route added: {path}")


class PluginLoader:
    """Load plugins from directories and packages."""

    def __init__(self, plugin_dirs: list[Path] | None = None):
        self._plugin_dirs = plugin_dirs or []
        self._plugins: dict[str, Plugin] = {}
        self._contexts: dict[str, PluginContext] = {}

    def add_plugin_dir(self, path: Path) -> None:
        """Add directory to search for plugins."""
        self._plugin_dirs.append(path)

    def load_from_dir(self, path: Path) -> list[Plugin]:
        """Load plugins from a directory.

        Directory structure:
        plugins/
          my_plugin/
            __init__.py  # Contains MyPlugin class
            plugin.py    # Alternative location
        """
        plugins = []

        if not path.exists():
            logger.warning(f"[PluginLoader] Plugin directory not found: {path}")
            return plugins

        for plugin_dir in path.iterdir():
            if not plugin_dir.is_dir():
                continue

            # Try __init__.py first
            init_file = plugin_dir / "__init__.py"
            plugin_file = plugin_dir / "plugin.py"

            if init_file.exists():
                plugin = self._load_plugin_from_file(init_file, plugin_dir.name)
                if plugin:
                    plugins.append(plugin)

            elif plugin_file.exists():
                plugin = self._load_plugin_from_file(plugin_file, plugin_dir.name)
                if plugin:
                    plugins.append(plugin)

        return plugins

    def load_from_package(self, package_name: str) -> Plugin | None:
        """Load plugin from installed Python package.

        Package must have entry point in [project.entry-points."agentcraft.plugins"]
        """
        try:
            # Try to import package
            module = importlib.import_module(package_name)

            # Look for Plugin subclass
            for name in dir(module):
                obj = getattr(module, name)
                if isinstance(obj, type) and issubclass(obj, Plugin) and obj != Plugin:
                    plugin = obj()
                    self._plugins[plugin.metadata.name] = plugin
                    logger.info(f"[PluginLoader] Loaded from package: {package_name}")
                    return plugin

            logger.warning(f"[PluginLoader] No Plugin class found in {package_name}")
            return None

        except ImportError as e:
            logger.error(f"[PluginLoader] Failed to import {package_name}: {e}")
            return None

    def load_from_entry_points(self) -> list[Plugin]:
        """Load plugins from Python entry points.

        Entry points defined in package pyproject.toml:
        [project.entry-points."agentcraft.plugins"]
        my_plugin = "my_package:MyPlugin"
        """
        plugins = []

        try:
            # Python 3.10+
            if sys.version_info >= (3, 10):
                from importlib.metadata import entry_points
                eps = entry_points(group="agentcraft.plugins")
            else:
                from importlib.metadata import entry_points
                eps = entry_points().get("agentcraft.plugins", [])

            for ep in eps:
                try:
                    plugin_class = ep.load()
                    if issubclass(plugin_class, Plugin):
                        plugin = plugin_class()
                        self._plugins[plugin.metadata.name] = plugin
                        plugins.append(plugin)
                        logger.info(
                            f"[PluginLoader] Loaded from entry point: {ep.name}"
                        )
                except Exception as e:
                    logger.error(
                        f"[PluginLoader] Failed to load entry point {ep.name}: {e}"
                    )

        except Exception as e:
            logger.warning(f"[PluginLoader] Entry points discovery failed: {e}")

        return plugins

    def _load_plugin_from_file(self, file_path: Path, plugin_name: str) -> Plugin | None:
        """Load plugin from a Python file."""
        try:
            # Create module spec
            spec = importlib.util.spec_from_file_location(
                f"plugins.{plugin_name}",
                file_path,
            )
            if not spec or not spec.loader:
                return None

            module = importlib.util.module_from_spec(spec)
            sys.modules[f"plugins.{plugin_name}"] = module
            spec.loader.exec_module(module)

            # Find Plugin subclass
            for name in dir(module):
                obj = getattr(module, name)
                if isinstance(obj, type) and issubclass(obj, Plugin) and obj != Plugin:
                    plugin = obj()
                    self._plugins[plugin.metadata.name] = plugin
                    logger.info(f"[PluginLoader] Loaded plugin: {plugin.metadata.name}")
                    return plugin

            return None

        except Exception as e:
            logger.error(f"[PluginLoader] Failed to load {file_path}: {e}")
            return None

    def get_plugin(self, name: str) -> Plugin | None:
        """Get loaded plugin by name."""
        return self._plugins.get(name)

    def list_plugins(self) -> list[Plugin]:
        """List all loaded plugins."""
        return list(self._plugins.values())

    async def initialize_plugin(
        self,
        plugin: Plugin,
        context: PluginContext,
    ) -> bool:
        """Initialize a plugin with context.

        Returns True if successful.
        """
        try:
            await plugin.on_load(context)
            self._contexts[plugin.metadata.name] = context
            logger.info(f"[PluginLoader] Plugin initialized: {plugin.metadata.name}")
            return True
        except Exception as e:
            logger.error(
                f"[PluginLoader] Plugin initialization failed {plugin.metadata.name}: {e}"
            )
            return False

    async def shutdown_all(self) -> None:
        """Shutdown all loaded plugins."""
        for plugin in self._plugins.values():
            try:
                await plugin.on_unload()
                logger.info(f"[PluginLoader] Plugin unloaded: {plugin.metadata.name}")
            except Exception as e:
                logger.error(
                    f"[PluginLoader] Plugin unload failed {plugin.metadata.name}: {e}"
                )


# Global plugin loader
_plugin_loader: PluginLoader | None = None


def get_plugin_loader() -> PluginLoader | None:
    """Get global plugin loader."""
    return _plugin_loader


def init_plugin_loader(plugin_dirs: list[Path] | None = None) -> PluginLoader:
    """Initialize global plugin loader."""
    global _plugin_loader
    _plugin_loader = PluginLoader(plugin_dirs)
    return _plugin_loader