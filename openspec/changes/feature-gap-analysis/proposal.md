## Why

对比 OpenClaw 企业级 Agent 网关，AgentCraft 缺失多个关键基础设施功能。当前系统无法支持多 Provider fallback、多渠道接入、向量检索、多 agent 协作、认证轮询、安全隔离、插件扩展等能力。这些差距限制了系统的可靠性、扩展性和生产级部署能力。

本 proposal 记录完整功能差距，作为后续实现的规划基础。

## What Changes

### 缺失功能清单

**高优先级 (生产必备)**:

- **多 Provider 支持**: 当前只支持 DeepSeek，无法 fallback 到 Anthropic、OpenAI、Azure、Bedrock 等
- **Auth Profile 轮询**: 单 API Key 配置，失败后无自动切换机制
- **向量记忆检索**: 当前只有 Markdown 文件列表，无语义搜索能力
- **Tool 沙箱隔离**: Bash 直接执行，无安全隔离

**中优先级 (扩展性)**:

- **多 Channel 接入**: 只支持 CLI 和 Canvas，无法接入 Discord、Slack、Telegram、LINE、Feishu 等
- **Gateway 协议**: 无版本化协议概念，客户端兼容性无保障
- **插件系统**: 无插件扩展机制，无法动态加载外部能力
- **Extension Lifecycle**: 无包管理，无法版本化发布和更新扩展

**高价值高级功能**:

- **ACP 控制面**: 无多 agent 协作能力，无 spawn parent stream，子 agent 无法与父 agent 通信
- **Model Catalog**: 无动态模型发现，context window 硬编码

## Capabilities

### New Capabilities

以下每个能力需要独立 spec 文件：

**基础设施 (高优先级)**:
- `multi-provider`: 多 Provider 支持 + 自动 fallback 链
- `auth-profiles`: 多 API Key 配置 + 失败轮询切换
- `vector-memory`: SQLite + FTS + Vector embedding 语义检索
- `tool-sandbox`: Bash 工具隔离执行

**扩展框架 (中优先级)**:
- `multi-channel`: 多渠道接入框架 (Discord/Slack/Telegram)
- `gateway-protocol`: 版本化 Gateway 协议
- `plugin-system`: 插件扩展机制 + Plugin SDK
- `extension-lifecycle`: 包管理 + 版本化发布

**高级功能**:
- `agent-control-plane`: ACP 控制面 + 多 agent 协作 + spawn/parent stream
- `model-catalog`: 动态模型发现 + context window 自动检测

### Modified Capabilities

无现有 spec 需要修改。

## Impact

**架构影响**:

- 需要引入 Provider 抽象层 (替代当前直接调用 DeepSeek)
- 需要引入 Channel 抽象层 (替代当前 CLI/Gateway 入口)
- 需要引入 Plugin 抽象层 (动态加载扩展)
- 需要增强 Memory 系统 (SQLite 存储 + 向量检索)
- 需要增强 Tool 执行 (沙箱隔离)
- 需要引入 ACP 控制面 (多 agent 协作)

**代码影响**:

- `gateway.py`: 需要重构为多 Provider 支持 + Plugin 加载
- `sessions/memory_persistence.py`: 需要增强为向量检索
- `tools/builtin.py`: Bash 工具需要沙箱化
- 新增 `channels/` 抽象层
- 新增 `providers/` 抽象层
- 新增 `plugins/` 抽象层
- 新增 `acp/` 控制面模块

**依赖影响**:

- sqlite3, sqlite-vec 扩展
- embedding 模型依赖
- 可能需要进程间通信库 (ACP)