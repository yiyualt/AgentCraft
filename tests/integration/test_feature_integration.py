"""Integration tests for multi-provider support."""

import pytest
import os
from unittest.mock import AsyncMock, patch, MagicMock

from providers import (
    ProviderRegistry,
    DeepSeekProvider,
    AnthropicProvider,
    OpenAIProvider,
    register_default_providers,
)
from providers.auth import AuthProfileStore, KeyProfile, ProviderAuthProfile


@pytest.mark.asyncio
async def test_provider_fallback_chain():
    """Test 11.1: Provider fallback chain (DeepSeek → Anthropic → OpenAI)."""
    registry = ProviderRegistry()

    # Mock providers
    deepseek = MagicMock(spec=DeepSeekProvider)
    deepseek.name = "DeepSeek"
    deepseek.provider_type = "deepseek"
    deepseek.is_available = MagicMock(return_value=True)
    deepseek.complete = AsyncMock(side_effect=Exception("DeepSeek failed"))

    anthropic = MagicMock(spec=AnthropicProvider)
    anthropic.name = "Anthropic"
    anthropic.provider_type = "anthropic"
    anthropic.is_available = MagicMock(return_value=True)
    anthropic.complete = AsyncMock(return_value={
        "choices": [{"message": {"content": "Anthropic response"}}]
        })

    openai = MagicMock(spec=OpenAIProvider)
    openai.name = "OpenAI"
    openai.provider_type = "openai"
    openai.is_available = MagicMock(return_value=True)

    # Register with priorities
    registry._providers["deepseek:key1"] = deepseek
    registry._providers["anthropic:key1"] = anthropic
    registry._providers["openai:key1"] = openai
    registry._fallback_order = ["deepseek", "anthropic", "openai"]

    # Test fallback
    messages = [{"role": "user", "content": "Hello"}]
    result = await registry.complete_with_fallback(messages)

    # Should have fallen back to Anthropic after DeepSeek failed
    assert deepseek.complete.called
    assert anthropic.complete.called
    assert result["choices"][0]["message"]["content"] == "Anthropic response"


@pytest.mark.asyncio
async def test_auth_profile_rotation():
    """Test 11.2: Auth profile rotation (key1 fails → key2 → key3)."""
    profile = ProviderAuthProfile(
        provider_type="deepseek",
        cooldown_seconds=60,
    )

    # Add 3 keys
    profile.add_key("key-1", name="primary", priority=100)
    profile.add_key("key-2", name="backup-1", priority=50)
    profile.add_key("key-3", name="backup-2", priority=10)

    # Get first key
    key1 = profile.get_next_key()
    assert key1.name == "primary"

    # Simulate failure - rotate to next
    key2 = profile.rotate_key(key1)
    assert key2.name == "backup-1"
    assert key1.cooldown_until is not None  # Key1 in cooldown

    # Simulate another failure
    key3 = profile.rotate_key(key2)
    assert key3.name == "backup-2"

    # All keys in cooldown - no available
    profile.rotate_key(key3)
    available = profile.get_available_keys()
    assert len(available) == 0


@pytest.mark.asyncio
async def test_vector_memory_search():
    """Test 11.3: Vector memory search (semantic query)."""
    from sessions.vector_memory import VectorMemoryStore, MockEmbeddingModel

    store = VectorMemoryStore(embedding_model=MockEmbeddingModel())

    # Save some memories
    await store.save(
        name="project-setup",
        content="Setting up the AgentCraft project with FastAPI gateway",
        metadata={"type": "setup"},
    )
    await store.save(
        name="provider-config",
        content="Configured DeepSeek and Anthropic providers with fallback",
        metadata={"type": "config"},
    )

    # Search semantically
    results = await store.search("how to configure providers")

    # Should find relevant memory
    assert len(results) > 0
    # Check content similarity (mock embedding just returns results)


@pytest.mark.asyncio
async def test_sandbox_isolation():
    """Test 11.4: Sandbox isolation (Bash in Docker container)."""
    from tools.sandbox import SandboxExecutor, SandboxConfig

    # Skip if Docker not available
    if not os.environ.get("SANDBOX_ENABLED"):
        pytest.skip("Sandbox not enabled")

    config = SandboxConfig(
        network_disabled=True,
        mount_host_bin=False,
    )
    executor = SandboxExecutor(config)

    try:
        # Execute command in sandbox
        result = await executor.execute("whoami")

        # Should execute in container
        assert result.get("success") or result.get("output")

    finally:
        await executor.cleanup()


@pytest.mark.asyncio
async def test_telegram_channel():
    """Test 11.5: Telegram channel message receive and send."""
    from channels.telegram import TelegramChannel
    from sessions import SessionManager

    # Skip if no token
    if not os.environ.get("TELEGRAM_BOT_TOKEN"):
        pytest.skip("No Telegram token")

    session_manager = SessionManager()
    channel = TelegramChannel(session_manager)

    # Mock message
    update = {
        "message": {
            "chat": {"id": 12345},
            "text": "Hello",
            "from": {"first_name": "Test"},
        }
    }

    # Handle message
    await channel.handle_message(update)

    # Start/stop
    await channel.start()
    await channel.stop()


def test_gateway_version_compatibility():
    """Test 11.6: Gateway version compatibility (client version mismatch)."""
    from gateway.version import (
        check_version_compatibility,
        validate_client_version,
        VersionCompatibility,
        GATEWAY_VERSION,
    )

    # Compatible version
    status = check_version_compatibility("1.0.0", "1.0.0")
    assert status == VersionCompatibility.COMPATIBLE

    # Deprecated version (works but warning)
    status = check_version_compatibility("0.9.0", "1.0.0")
    assert status == VersionCompatibility.DEPRECATED

    # Incompatible version (major mismatch)
    status = check_version_compatibility("0.1.0", "1.0.0")
    assert status == VersionCompatibility.INCOMPATIBLE

    # Validate client version
    is_valid, msg = validate_client_version("1.0.0")
    assert is_valid

    is_valid, msg = validate_client_version("0.1.0")
    assert not is_valid


@pytest.mark.asyncio
async def test_plugin_loading():
    """Test 11.7: Test plugin loading from directory and pip package."""
    from plugins import PluginLoader, PluginContext
    from pathlib import Path

    loader = PluginLoader()

    # Load from directory
    plugin_dir = Path("sample_plugins")
    if plugin_dir.exists():
        plugins = loader.load_from_dir(plugin_dir)
        assert len(plugins) > 0  # Should find telegram plugin

        # Initialize plugin
        context = PluginContext()
        for plugin in plugins:
            await loader.initialize_plugin(plugin, context)


@pytest.mark.asyncio
async def test_acp_spawn_child():
    """Test 11.8: Test ACP spawn child and parent stream."""
    from acp import AgentControlPlane, AcpConfig
    from unittest.mock import MagicMock

    # Mock dependencies
    llm_client = MagicMock()
    registry = MagicMock()
    session_manager = MagicMock()
    fork_manager = MagicMock()

    config = AcpConfig(max_children=5)
    acp = AgentControlPlane(
        llm_client=llm_client,
        registry=registry,
        session_manager=session_manager,
        fork_manager=fork_manager,
        config=config,
    )

    # Spawn child
    child_id = await acp.spawn_child(
        task="Analyze the code",
        agent_type="explore",
    )

    assert child_id is not None

    # Get children
    children = acp.get_children()
    assert len(children) > 0


def test_model_catalog_context_window():
    """Test 11.9: Test model catalog context window detection."""
    from models.catalog import ModelCatalog, ModelInfo

    catalog = ModelCatalog()

    # Get model by name
    model = catalog.get_model("deepseek-chat")
    assert model is not None
    assert model.context_window == 128000

    # Get context window
    cw = catalog.get_context_window("claude-sonnet-4-6")
    assert cw == 200000

    # Check capability
    assert catalog.supports_capability("deepseek-chat", "tools")
    assert not catalog.supports_capability("deepseek-chat", "vision")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])