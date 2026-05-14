# Plugin SDK API

## Overview

AgentCraft supports plugins for extending functionality. Plugins can:
- Register custom tools
- Register custom channels (Telegram, Slack, etc.)
- Add API routes
- Add middleware
- Hook into lifecycle events

## Plugin Structure

### Directory-based Plugin

```
plugins/
  my_plugin/
    __init__.py      # Contains MyPlugin class
    tools.py         # Custom tools
    channels.py      # Custom channels
```

### Package-based Plugin

```
agentcraft-plugin-telegram/
  pyproject.toml     # Entry point registration
  telegram/
    __init__.py      # TelegramPlugin class
```

## Creating a Plugin

### 1. Define Plugin Class

```python
from plugins import Plugin, PluginMetadata, PluginContext

class MyPlugin(Plugin):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="my-plugin",
            version="1.0.0",
            author="Your Name",
            description="My custom plugin",
            requires=["1.0"],  # AgentCraft version requirement
        )

    async def on_load(self, context: PluginContext) -> None:
        # Register tools
        from my_plugin.tools import my_custom_tool
        context.register_tool(my_custom_tool)

        # Register channels
        from my_plugin.channels import MyChannel
        context.register_channel(MyChannel())

        # Add routes
        context.add_route("/my-plugin/action", my_action, methods=["POST"])

        # Access config
        my_config = context.plugin_config
        api_key = my_config.get("api_key")

    async def on_unload(self) -> None:
        # Clean up resources
        pass
```

### 2. Define Custom Tool

```python
from tools import tool

@tool(name="MyCustomTool")
async def my_custom_tool(prompt: str, description: str = None) -> str:
    """
    My custom tool description.

    Args:
        prompt: The prompt to process
        description: Optional description

    Returns:
        Result string
    """
    # Tool implementation
    return f"Processed: {prompt}"
```

### 3. Define Custom Channel

```python
from channels import Channel

class MyChannel(Channel):
    name = "my_channel"

    async def start(self) -> None:
        # Connect to service
        pass

    async def stop(self) -> None:
        # Disconnect
        pass

    async def send_message(self, peer_id: str, text: str) -> None:
        # Send message
        pass

    async def handle_message(self, message: Any) -> None:
        # Process incoming message
        pass
```

## Package-based Plugin

### pyproject.toml

```toml
[project]
name = "agentcraft-plugin-telegram"
version = "1.0.0"
dependencies = ["agentcraft>=1.0.0"]

[project.entry-points."agentcraft.plugins"]
telegram = "telegram:TelegramPlugin"
```

### Installation

```bash
pip install agentcraft-plugin-telegram
```

Plugin auto-discovered at startup via entry points.

## Configuration

### .agentcraft/plugins.yaml

```yaml
plugins:
  my-plugin:
    enabled: true
    api_key: "your-key"
    custom_setting: "value"
```

## Plugin Context

The `PluginContext` provides:

| Property | Description |
|----------|-------------|
| `tool_registry` | Registry to register tools |
| `channel_router` | Router to register channels |
| `session_manager` | Session manager instance |
| `app` | FastAPI app for routes/middleware |
| `config` | Global config |
| `plugin_config` | Plugin-specific config section |

## Methods

| Method | Description |
|--------|-------------|
| `register_tool(func)` | Register a tool function |
| `register_channel(channel)` | Register a channel |
| `add_route(path, endpoint, methods)` | Add API route |

## Version Compatibility

```python
class MyPlugin(Plugin):
    def check_compatibility(self, agentcraft_version: str) -> bool:
        # Override to check version
        return True
```

Rules:
- Major version must match
- Minor version can be lower or equal

## Lifecycle

```
1. AgentCraft starts
2. PluginLoader discovers plugins
   - From directories (plugins/)
   - From entry points
3. PluginContext created
4. plugin.on_load(context)
5. Plugin active during runtime
6. plugin.on_unload() on shutdown
```

## Error Handling

Plugins are isolated:
- Exceptions in `on_load()` logged, plugin not activated
- Exceptions in tools/channels logged, operation failed but system continues
- Exceptions in `on_unload()` logged, cleanup incomplete

## Example: Telegram Plugin

```python
class TelegramPlugin(Plugin):
    @property
    def metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="telegram",
            version="1.0.0",
            author="AgentCraft",
            description="Telegram bot channel",
        )

    async def on_load(self, context: PluginContext) -> None:
        token = context.plugin_config.get("bot_token")
        if token:
            channel = TelegramChannel(context.session_manager, token)
            context.register_channel(channel)
```

## Testing Plugins

```python
import pytest
from plugins import PluginContext

@pytest.fixture
def plugin_context():
    return PluginContext(
        tool_registry=MockRegistry(),
        channel_router=MockRouter(),
    )

async def test_plugin_load(plugin_context):
    plugin = MyPlugin()
    await plugin.on_load(plugin_context)
    assert plugin_context.tool_registry.has_tool("MyCustomTool")
```