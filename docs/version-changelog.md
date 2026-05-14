# Gateway Version Changelog

## Version 1.0.0 (2025-05-15)

**Initial Stable Release**

### New Features
- Multi-provider support (DeepSeek, Anthropic, OpenAI)
- Provider fallback with automatic retry
- Auth profile management with key rotation
- Vector memory with semantic search
- ACP (Agent Control Plane) for multi-agent tasks
- Automation & scheduling (cron jobs)
- Webhook triggers for external events
- Fork mechanism for sub-agent context inheritance
- Auto-compaction for context window management
- Canvas workspace (visual agent workspace)
- Sandbox execution (Docker isolation)
- MCP tool integration
- Channel routing (CLI, Telegram, Web, WeCom)
- Model catalog with capability tracking

### API Changes
- Added `/webhook/{name}` endpoint
- Added `/cron/status`, `/cron/jobs` endpoints
- Added `/providers/status` endpoint
- Added `/models/list` endpoint

### Headers
- All responses include `X-Gateway-Version` header
- Clients should send `X-Client-Version` header

---

## Version 0.9.0 (2025-05-10)

### New Features
- Fork mechanism for sub-agent context inheritance
- Auto-compaction for context window management
- Canvas workspace (SSE-based visual workspace)

### Changes
- Session manager enhanced with fork support
- Compaction manager added for automatic context trimming

---

## Version 0.8.0 (2025-05-01)

### New Features
- Sandbox execution (Docker isolation for Bash tool)
- MCP (Model Context Protocol) tool integration
- Channel routing for multi-platform messaging

### Changes
- Tools now support sandbox execution
- Unified tool registry for local + MCP tools

---

## Migration Guides

### From 0.8.x to 1.0.0

1. **Multi-Provider Support**
   - Previously: Only DeepSeek supported via direct OpenAI client
   - Now: ProviderRegistry with fallback
   - Migration: Set `DEEPSEEK_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` env vars

2. **Vector Memory**
   - Previously: Markdown-based memory files
   - Now: SQLite vector store with semantic search
   - Migration: Old memories auto-migrated on first run

3. **Automation**
   - New feature: Cron scheduling
   - Config: Create `.agentcraft/automation.yaml`

4. **Headers**
   - Add `X-Client-Version: 1.0.0` to requests
   - Check `X-Gateway-Version` in responses

### From 0.9.x to 1.0.0

1. **Auth Profiles**
   - New: Multi-key rotation per provider
   - Config: Create `.agentcraft/providers.yaml`

2. **Model Catalog**
   - New: Model capability tracking
   - Config: Create `.agentcraft/models.yaml`

3. **Webhooks**
   - New: External event triggers
   - Config: Create `.agentcraft/webhooks.json`

---

## Version Compatibility Rules

- **Major version**: Must match exactly (1.x clients with 1.x gateway)
- **Minor version**: Client can be lower (deprecated) but works
- **Patch version**: Any difference is acceptable

| Client | Gateway | Status |
|--------|---------|--------|
| 1.0.0  | 1.0.0   | Compatible |
| 0.9.0  | 1.0.0   | Deprecated (works, warning) |
| 2.0.0  | 1.0.0   | Future (works, info) |
| 0.8.0  | 1.0.0   | Deprecated |
| 1.1.0  | 1.0.0   | Future |
| 0.1.0  | 1.0.0   | Incompatible (major mismatch) |

---

## Deprecation Policy

- Deprecated versions work for 2 minor releases
- Breaking changes only in major releases
- Migration guides provided for all major upgrades