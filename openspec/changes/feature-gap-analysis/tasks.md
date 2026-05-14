## 1. Multi-Provider Support

- [x] 1.1 Create `providers/` module directory structure
- [x] 1.2 Implement `Provider` base class with complete() and stream() methods
- [x] 1.3 Implement `DeepSeekProvider` class (migrate from current direct calls)
- [x] 1.4 Implement `AnthropicProvider` class
- [x] 1.5 Implement `OpenAIProvider` class
- [x] 1.6 Create `ProviderRegistry` to manage provider instances
- [x] 1.7 Refactor `gateway.py` to use ProviderRegistry instead of direct DeepSeek calls
- [x] 1.8 Implement provider fallback logic (try next on failure)

## 2. Auth Profiles

- [x] 2.1 Define YAML config schema for multiple API keys per provider
- [x] 2.2 Implement `AuthProfileStore` to load and manage API keys
- [x] 2.3 Implement key rotation logic (switch to next on failure)
- [x] 2.4 Implement failure count tracking per key
- [x] 2.5 Implement cooldown mechanism for exhausted keys
- [x] 2.6 Add provider priority ordering support in config
- [x] 2.7 Create default config file template at `.agentcraft/providers.yaml`

## 3. Vector Memory

- [x] 3.1 Add sqlite-vec dependency to pyproject.toml (no extra dependency needed - uses numpy + FTS5 built-in)
- [x] 3.2 Create SQLite database schema (memories table + FTS5 + vector column)
- [x] 3.3 Implement `VectorMemoryStore` class replacing `MemoryStore`
- [x] 3.4 Implement embedding generation interface (abstract)
- [x] 3.5 Implement `LocalEmbeddingModel` using sentence-transformers (with MockEmbeddingModel fallback)
- [x] 3.6 Implement `RemoteEmbeddingModel` using OpenAI embedding API
- [x] 3.7 Implement hybrid search (FTS + vector similarity)
- [x] 3.8 Migrate existing Markdown memories to SQLite (migration script included in VectorMemoryStore)
- [x] 3.9 Update `memory_tools.py` to use VectorMemoryStore

## 4. Tool Sandbox

- [x] 4.1 Add Docker SDK dependency to pyproject.toml
- [x] 4.2 Implement `SandboxExecutor` class for Docker container execution
- [x] 4.3 Implement ephemeral container creation and cleanup
- [x] 4.4 Implement directory mounting (read and write dirs)
- [x] 4.5 Implement network isolation configuration
- [x] 4.6 Implement execution timeout handling
- [x] 4.7 Gateway integration with SANDBOX_ENABLED environment variable
- [x] 4.8 CLI integration with --sandbox and --sandbox-network flags

## 5. Multi-Channel

- [x] 5.1 Create `channels/` module directory structure
- [x] 5.2 Implement `Channel` base class with receive() and send() methods
- [x] 5.3 Refactor CLI to use `CLIChannel` class
- [x] 5.4 Refactor Canvas/Web to use `CanvasChannel` class
- [x] 5.5 Implement `TelegramChannel` class with bot token support
- [x] 5.6 Implement `ChannelRouter` to dispatch messages to appropriate channel
- [x] 5.7 Implement message normalization (channel_id, user_id, content, metadata)
- [x] 5.8 Add Telegram bot token configuration to `.agentcraft/channels.yaml`

## 6. Gateway Protocol

- [x] 6.1 Add `X-Gateway-Version` header to all API responses
- [x] 6.2 Implement client version validation middleware
- [x] 6.3 Define version compatibility rules (major must match, minor compatible)
- [x] 6.4 Implement version negotiation for backward compatible changes
- [x] 6.5 Create version changelog documentation
- [x] 6.6 Add migration guide for breaking changes

## 7. Plugin System

- [x] 7.1 Create `plugins/` module directory structure
- [x] 7.2 Implement `Plugin` base class with name, version, on_load(), on_unload()
- [x] 7.3 Implement `PluginContext` providing registries and config
- [x] 7.4 Implement `PluginLoader` with load_from_dir() and load_from_package()
- [x] 7.5 Implement Python entry point discovery mechanism
- [x] 7.6 Implement plugin isolation (catch exceptions, log errors)
- [x] 7.7 Create `plugins/` directory for local plugins
- [x] 7.8 Document Plugin SDK API

## 8. Extension Lifecycle

- [x] 8.1 Define plugin package pyproject.toml schema
- [x] 8.2 Implement entry point registration `[project.entry-points."agentcraft.plugins"]`
- [x] 8.3 Add AgentCraft version compatibility check for plugins
- [x] 8.4 Implement plugin auto-discovery at startup
- [x] 8.5 Create sample plugin package `agentcraft-plugin-telegram`
- [x] 8.6 Document plugin installation guide (pip install)
- [x] 8.7 Add plugin-specific config support `[plugins.<name>]`

## 9. ACP Control Plane

- [x] 9.1 Create `acp/` module directory structure
- [x] 9.2 Implement `AgentControlPlane` class with spawn_child()
- [x] 9.3 Implement `ChildAgent` class with execution and result reporting
- [x] 9.4 Implement `parent_stream()` for result aggregation
- [x] 9.5 Implement parent-child communication (send_to_child, broadcast)
- [x] 9.6 Implement context inheritance with token limit
- [x] 9.7 Implement child agent limit (max 10) and timeout handling
- [x] 9.8 Disable Agent tool in child agents (recursion protection)
- [x] 9.9 Integrate ACP with gateway.py for multi-agent tasks
- [x] 9.10 Document ACP usage and best practices

## 10. Model Catalog

- [x] 10.1 Define YAML config schema for model definitions
- [x] 10.2 Implement `ModelCatalog` class to manage models
- [x] 10.3 Implement context window detection from API response
- [x] 10.4 Implement context window caching in `~/.agentcraft/model-cache.json`
- [x] 10.5 Implement model selection by name/alias/auto
- [x] 10.6 Implement model capability tracking (vision, streaming, tools)
- [x] 10.7 Implement model fallback within provider
- [x] 10.8 Create default models config template

## 11. Integration Testing

- [x] 11.1 Test provider fallback chain (DeepSeek → Anthropic → OpenAI)
- [x] 11.2 Test auth profile rotation (key1 fails → key2 → key3)
- [x] 11.3 Test vector memory search (semantic query)
- [x] 11.4 Test sandbox isolation (Bash in Docker container)
- [x] 11.5 Test Telegram channel message receive and send
- [x] 11.6 Test Gateway version compatibility (client version mismatch)
- [x] 11.7 Test plugin loading from directory and pip package
- [x] 11.8 Test ACP spawn child and parent stream
- [x] 11.9 Test model catalog context window detection

## 12. Automation & Scheduling

- [x] 12.1 Create `automation/` module directory structure
- [x] 12.2 Implement `CronSchedule` types (at/every/cron)
- [x] 12.3 Implement `CronJob` and `CronJobState` dataclasses
- [x] 12.4 Implement `CronStore` for SQLite persistence
- [x] 12.5 Implement `CronScheduler` using APScheduler
- [x] 12.6 Implement cron expression parsing (via APScheduler CronTrigger)
- [x] 12.7 Implement job execution in isolated agent environment
- [x] 12.8 Implement delivery mechanism (none/announce/webhook)
- [x] 12.9 Implement failure notification and alerting
- [x] 12.10 Implement heartbeat and health check
- [x] 12.11 Add `/cron` slash commands to CLI (list/show/create/delete)
- [x] 12.12 Integrate with Gateway API endpoints
- [x] 12.13 Create automation config file template at `.agentcraft/automation.yaml`

## 13. Webhook Integration

- [x] 13.1 Implement `WebhookTrigger` for external event invocation
- [x] 13.2 Implement webhook signature validation
- [x] 13.3 Add webhook endpoint `/webhook/trigger`
- [x] 13.4 Document webhook payload schema