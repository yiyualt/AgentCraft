## 1. Multi-Provider Support

- [ ] 1.1 Create `providers/` module directory structure
- [ ] 1.2 Implement `Provider` base class with complete() and stream() methods
- [ ] 1.3 Implement `DeepSeekProvider` class (migrate from current direct calls)
- [ ] 1.4 Implement `AnthropicProvider` class
- [ ] 1.5 Implement `OpenAIProvider` class
- [ ] 1.6 Create `ProviderRegistry` to manage provider instances
- [ ] 1.7 Refactor `gateway.py` to use ProviderRegistry instead of direct DeepSeek calls
- [ ] 1.8 Implement provider fallback logic (try next on failure)

## 2. Auth Profiles

- [ ] 2.1 Define YAML config schema for multiple API keys per provider
- [ ] 2.2 Implement `AuthProfileStore` to load and manage API keys
- [ ] 2.3 Implement key rotation logic (switch to next on failure)
- [ ] 2.4 Implement failure count tracking per key
- [ ] 2.5 Implement cooldown mechanism for exhausted keys
- [ ] 2.6 Add provider priority ordering support in config
- [ ] 2.7 Create default config file template at `.agentcraft/providers.yaml`

## 3. Vector Memory

- [ ] 3.1 Add sqlite-vec dependency to pyproject.toml
- [ ] 3.2 Create SQLite database schema (memories table + FTS5 + vector column)
- [ ] 3.3 Implement `VectorMemoryStore` class replacing `MemoryStore`
- [ ] 3.4 Implement embedding generation interface (abstract)
- [ ] 3.5 Implement `LocalEmbeddingModel` using sentence-transformers
- [ ] 3.6 Implement `RemoteEmbeddingModel` using OpenAI embedding API
- [ ] 3.7 Implement hybrid search (FTS + vector similarity)
- [ ] 3.8 Migrate existing Markdown memories to SQLite (migration script)
- [ ] 3.9 Update `memory_tools.py` to use VectorMemoryStore

## 4. Tool Sandbox

- [ ] 4.1 Add Docker SDK dependency to pyproject.toml
- [ ] 4.2 Implement `SandboxExecutor` class for Docker container execution
- [ ] 4.3 Implement ephemeral container creation and cleanup
- [ ] 4.4 Implement directory mounting (read and write dirs)
- [ ] 4.5 Implement network isolation configuration
- [ ] 4.6 Implement execution timeout handling
- [ ] 4.7 Refactor `tools/builtin.py` Bash tool to use SandboxExecutor
- [ ] 4.8 Add sandbox configuration options to gateway.py

## 5. Multi-Channel

- [ ] 5.1 Create `channels/` module directory structure
- [ ] 5.2 Implement `Channel` base class with receive() and send() methods
- [ ] 5.3 Refactor CLI to use `CLIChannel` class
- [ ] 5.4 Refactor Canvas/Web to use `CanvasChannel` class
- [ ] 5.5 Implement `TelegramChannel` class with bot token support
- [ ] 5.6 Implement `ChannelRouter` to dispatch messages to appropriate channel
- [ ] 5.7 Implement message normalization (channel_id, user_id, content, metadata)
- [ ] 5.8 Add Telegram bot token configuration to `.agentcraft/channels.yaml`

## 6. Gateway Protocol

- [ ] 6.1 Add `X-Gateway-Version` header to all API responses
- [ ] 6.2 Implement client version validation middleware
- [ ] 6.3 Define version compatibility rules (major must match, minor compatible)
- [ ] 6.4 Implement version negotiation for backward compatible changes
- [ ] 6.5 Create version changelog documentation
- [ ] 6.6 Add migration guide for breaking changes

## 7. Plugin System

- [ ] 7.1 Create `plugins/` module directory structure
- [ ] 7.2 Implement `Plugin` base class with name, version, on_load(), on_unload()
- [ ] 7.3 Implement `PluginContext` providing registries and config
- [ ] 7.4 Implement `PluginLoader` with load_from_dir() and load_from_package()
- [ ] 7.5 Implement Python entry point discovery mechanism
- [ ] 7.6 Implement plugin isolation (catch exceptions, log errors)
- [ ] 7.7 Create `plugins/` directory for local plugins
- [ ] 7.8 Document Plugin SDK API

## 8. Extension Lifecycle

- [ ] 8.1 Define plugin package pyproject.toml schema
- [ ] 8.2 Implement entry point registration `[project.entry-points."agentcraft.plugins"]`
- [ ] 8.3 Add AgentCraft version compatibility check for plugins
- [ ] 8.4 Implement plugin auto-discovery at startup
- [ ] 8.5 Create sample plugin package `agentcraft-plugin-telegram`
- [ ] 8.6 Document plugin installation guide (pip install)
- [ ] 8.7 Add plugin-specific config support `[plugins.<name>]`

## 9. ACP Control Plane

- [ ] 9.1 Create `acp/` module directory structure
- [ ] 9.2 Implement `AgentControlPlane` class with spawn_child()
- [ ] 9.3 Implement `ChildAgent` class with execution and result reporting
- [ ] 9.4 Implement `parent_stream()` for result aggregation
- [ ] 9.5 Implement parent-child communication (send_to_child, broadcast)
- [ ] 9.6 Implement context inheritance with token limit
- [ ] 9.7 Implement child agent limit (max 10) and timeout handling
- [ ] 9.8 Disable Agent tool in child agents (recursion protection)
- [ ] 9.9 Integrate ACP with gateway.py for multi-agent tasks
- [ ] 9.10 Document ACP usage and best practices

## 10. Model Catalog

- [ ] 10.1 Define YAML config schema for model definitions
- [ ] 10.2 Implement `ModelCatalog` class to manage models
- [ ] 10.3 Implement context window detection from API response
- [ ] 10.4 Implement context window caching in `~/.agentcraft/model-cache.json`
- [ ] 10.5 Implement model selection by name/alias/auto
- [ ] 10.6 Implement model capability tracking (vision, streaming, tools)
- [ ] 10.7 Implement model fallback within provider
- [ ] 10.8 Create default models config template

## 11. Integration Testing

- [ ] 11.1 Test provider fallback chain (DeepSeek → Anthropic → OpenAI)
- [ ] 11.2 Test auth profile rotation (key1 fails → key2 → key3)
- [ ] 11.3 Test vector memory search (semantic query)
- [ ] 11.4 Test sandbox isolation (Bash in Docker container)
- [ ] 11.5 Test Telegram channel message receive and send
- [ ] 11.6 Test Gateway version compatibility (client version mismatch)
- [ ] 11.7 Test plugin loading from directory and pip package
- [ ] 11.8 Test ACP spawn child and parent stream
- [ ] 11.9 Test model catalog context window detection