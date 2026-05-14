## Context

对比 OpenClaw 的企业级架构，AgentCraft 当前是轻量单体设计。本设计文档规划完整的架构升级路线，包括插件系统、ACP 控制面等高级能力。

**当前状态**:
- Provider: 直接调用 DeepSeek API，无 fallback
- Memory: Markdown 文件 + YAML frontmatter，无语义检索
- Channels: CLI + Canvas/Web，无其他渠道
- Tools: 直接执行，无沙箱隔离
- Plugins: 无扩展机制
- ACP: 无多 agent 协作

## Goals / Non-Goals

**Goals**:
- 多 Provider 支持 + 失败自动 fallback
- Auth Profile 轮询机制
- 向量记忆检索 (SQLite + FTS + embedding)
- Bash 工具沙箱隔离
- 多 Channel 接入框架
- Gateway 协议版本化
- **插件系统** + Plugin SDK
- **Extension Lifecycle** 包管理
- **ACP 控制面** + 多 agent 协作
- Model Catalog 动态发现

**Non-Goals**:
- 不实现 OpenClaw 的全部 100+ 扩展 (只实现核心框架)
- 不实现分布式部署 (保持单机)

## Decisions

### D1: Provider 抽象层设计

**决定**: 创建 `providers/` 模块，Provider 基类 + 具体实现

```python
class Provider(ABC):
    def complete(messages, tools) -> Response
    def stream(messages, tools) -> AsyncIterator

class DeepSeekProvider(Provider): ...
class AnthropicProvider(Provider): ...
class OpenAIProvider(Provider): ...
```

**理由**: 保持简单抽象，新增 Provider 只需继承基类。

### D2: Auth Profile 轮询

**决定**: 配置文件支持多个 API Key，失败自动切换下一个

```yaml
providers:
  - name: deepseek
    api_keys: ["key1", "key2", "key3"]
    priority: 1
  - name: anthropic
    api_keys: ["key-ant-1"]
    priority: 2  # fallback
```

### D3: 向量记忆存储

**决定**: SQLite + sqlite-vec 扩展 + 本地/远程 embedding 模型

### D4: Tool 沙箱

**决定**: Docker 容器隔离执行 Bash 命令

### D5: Channel 抽象层

**决定**: 创建 `channels/` 模块，Channel 基类 + 具体实现

```python
class Channel(ABC):
    async def receive() -> Message
    async def send(message) -> None

class CLIChannel(Channel): ...
class TelegramChannel(Channel): ...
```

### D6: Gateway 协议

**决定**: HTTP Header `X-Gateway-Version: 1.0`，版本不兼容返回 400

### D7: Plugin System (新增)

**决定**: Python 包插件机制 + Plugin SDK

```python
# 插件基类
class Plugin(ABC):
    name: str
    version: str
    
    def on_load(self, context: PluginContext): ...
    def on_unload(self): ...
    
    def register_tools(self, registry: ToolRegistry): ...
    def register_providers(self, registry: ProviderRegistry): ...
    def register_channels(self, registry: ChannelRegistry): ...

# 插件加载
class PluginLoader:
    def load_from_dir(self, path: Path): ...
    def load_from_package(self, name: str): ...
```

**理由**: Python 包天然支持模块化，无需复杂机制。插件可以是本地目录或 pip 包。

**备选方案**:
- 入口点机制 - ✓ 更规范，支持 pip install 后自动发现
- 纯目录扫描 - ✓ 简单，适合本地开发

### D8: Extension Lifecycle (新增)

**决定**: pyproject.toml 元数据 + 版本化管理

```toml
# 插件包的 pyproject.toml
[project]
name = "agentcraft-plugin-telegram"
version = "1.0.0"

[project.entry-points."agentcraft.plugins"]
telegram = "agentcraft_plugin_telegram:TelegramPlugin"
```

**理由**: Python 入口点机制标准化，pip install 后自动注册。

### D9: ACP Control Plane (新增)

**决定**: 进程内多 agent 协作 + Parent Stream

```python
class AgentControlPlane:
    def spawn_child(self, task: str, context: dict) -> ChildAgent:
        """创建子 agent，继承部分父 context"""
        child = ChildAgent(
            task=task,
            parent_id=self.id,
            inherited_context=context
        )
        self.children[child.id] = child
        return child
    
    async def parent_stream(self) -> AsyncIterator[ChildResult]:
        """流式接收所有子 agent 的结果"""
        while self.active_children:
            result = await self.result_queue.get()
            yield result
    
    def send_to_child(self, child_id: str, message: str):
        """向特定子 agent 发送消息"""
        self.children[child_id].receive(message)
    
    def broadcast(self, message: str):
        """向所有子 agent 广播消息"""
        for child in self.children.values():
            child.receive(message)

class ChildAgent:
    async def run(self) -> ChildResult:
        """执行任务，结果通过 parent_stream 返回"""
        result = await self.execute(self.task)
        await self.parent.result_queue.put(result)
```

**理由**: 进程内协作足够满足当前需求，无需分布式。使用 asyncio Queue 实现通信。

**备选方案**:
- 多进程 + IPC - ❌ 过于复杂
- 分布式消息队列 - ❌ 需要额外基础设施

### D10: Model Catalog (新增)

**决定**: 配置文件 + 自动检测 context window

```yaml
models:
  deepseek-chat:
    context_window: 64000
    provider: deepseek
  
  claude-sonnet-4:
    context_window: 200000
    provider: anthropic
    # 未指定时，从 API response 自动检测
```

**理由**: 配置驱动 + 运行时检测补充。

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| Plugin API 变化频繁 | 版本化 Plugin SDK，保持向后兼容 |
| ACP 子 agent 数量爆炸 | 限制最大子 agent 数量，超时终止 |
| 入口点机制需要 pip install | 同时支持本地目录扫描 |
| embedding 模型大小 | 可选远程 API |

## Open Questions

1. Plugin SDK 版本如何与 AgentCraft 版本关联？
2. ACP 子 agent 是否限制继承的 context 大小？
3. Model Catalog 是否支持动态添加（不从配置）？