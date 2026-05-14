# Extension Lifecycle

## Overview

Extensions (plugins) can be installed via pip packages. This document describes the lifecycle and configuration.

## Plugin Package Structure

### pyproject.toml Schema

```toml
[project]
name = "agentcraft-plugin-{name}"
version = "1.0.0"
description = "Plugin description"
authors = [{name = "Author", email = "author@example.com"}]
dependencies = [
    "agentcraft>=1.0.0",
    # Other dependencies
]

# Entry point registration
[project.entry-points."agentcraft.plugins"]
{name} = "{package}:PluginClass"

# Optional: multiple entry points for different plugin types
[project.entry-points."agentcraft.channels"]
{name} = "{package}:ChannelClass"

[project.entry-points."agentcraft.tools"]
{name} = "{package}:ToolModule"
```

## Entry Point Types

| Group | Description | Example |
|-------|-------------|---------|
| `agentcraft.plugins` | Full plugins | `telegram = "telegram_plugin:TelegramPlugin"` |
| `agentcraft.channels` | Channel-only extensions | `slack = "slack_channel:SlackChannel"` |
| `agentcraft.tools` | Tool-only extensions | `weather = "weather_tools"` |

## Version Compatibility Check

### Plugin Check

```python
class MyPlugin(Plugin):
    def check_compatibility(self, agentcraft_version: str) -> bool:
        # Requires AgentCraft 1.0+
        return agentcraft_version.startswith("1.")
```

### Automatic Check

```python
# PluginLoader checks compatibility before loading
if not plugin.check_compatibility(AGENTCRAFT_VERSION):
    logger.warning(f"Plugin {name} incompatible with {AGENTCRAFT_VERSION}")
    # Skip loading
```

## Auto-discovery at Startup

### Gateway Integration

```python
# In gateway.py lifespan
from plugins import init_plugin_loader

loader = init_plugin_loader([
    Path("plugins/"),          # Local plugins directory
    Path("~/.agentcraft/plugins/").expanduser(),
])

# Load from directories
for plugin_dir in loader._plugin_dirs:
    loader.load_from_dir(plugin_dir)

# Load from entry points (pip installed packages)
loader.load_from_entry_points()

# Initialize each plugin
for plugin in loader.list_plugins():
    context = PluginContext(
        tool_registry=_unified_registry,
        channel_router=_channel_router,
        session_manager=_session_manager,
        app=app,
        plugin_config=config.get("plugins", {}).get(plugin.metadata.name, {}),
    )
    await loader.initialize_plugin(plugin, context)
```

## Sample Plugin Package

### agentcraft-plugin-telegram

```
agentcraft-plugin-telegram/
  pyproject.toml
  telegram_plugin/
    __init__.py      # TelegramPlugin class
    channel.py       # TelegramChannel implementation
    handlers.py      # Message handlers
```

### pyproject.toml

```toml
[project]
name = "agentcraft-plugin-telegram"
version = "1.0.0"
dependencies = ["agentcraft>=1.0.0", "httpx"]

[project.entry-points."agentcraft.plugins"]
telegram = "telegram_plugin:TelegramPlugin"
```

## Installation Guide

### Install from PyPI

```bash
pip install agentcraft-plugin-telegram
```

### Install from Local

```bash
pip install ./agentcraft-plugin-telegram
```

### Install from Git

```bash
pip install git+https://github.com/user/agentcraft-plugin-telegram.git
```

## Configuration

### .agentcraft/config.yaml

```yaml
plugins:
  telegram:
    enabled: true
    bot_token: "your-telegram-bot-token"
    polling_interval: 1

  slack:
    enabled: false
    app_token: ""
    bot_token: ""
```

### Per-Plugin Config

```yaml
plugins:
  my-plugin:
    enabled: true
    custom_key: "value"
```

Accessed via `context.plugin_config`.

## Plugin-specific Config Support

### In PluginContext

```python
class PluginContext:
    config: dict[str, Any]       # Global config
    plugin_config: dict[str, Any] # [plugins.<name>] section
```

### Usage

```python
async def on_load(self, context: PluginContext) -> None:
    token = context.plugin_config.get("api_key")
    enabled = context.plugin_config.get("enabled", True)
```

## Lifecycle Events

| Event | Description |
|-------|-------------|
| `on_load` | Plugin loaded, context available |
| `on_unload` | Plugin unloaded, cleanup |
| `on_error` | Error during operation |

## Error Handling

```python
# PluginLoader wraps plugin operations
async def initialize_plugin(self, plugin: Plugin, context: PluginContext) -> bool:
    try:
        await plugin.on_load(context)
        return True
    except Exception as e:
        logger.error(f"Plugin {plugin.metadata.name} failed: {e}")
        return False
```

Plugin errors don't crash the system - logged and skipped.