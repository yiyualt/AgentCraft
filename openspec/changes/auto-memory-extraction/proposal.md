## Why

当前用户需要手动调用 `remember` tool 来保存记忆，或者在对话中明确说"请记住XXX"才能触发记忆保存。但实际上，很多有价值的信息隐式存在于对话中（用户偏好、项目约束、工作习惯等），用户不会主动说"记住"，但这些信息对后续对话很有价值。

我们需要一个**自动记忆提取机制**，定期扫描对话内容，识别值得记录的信息，自动保存到 memory.db。

## What Changes

### 核心功能
- **消息计数触发**: 每 5 个 user 消息触发一次检查（不阻塞主流程）
- **检查范围**: 最近 20 条消息（包含 user + assistant + tool，保证完整对话）
- **智能判断**: 关键词检测 + LLM 分析，识别值得记录的内容
- **自动保存**: 后台异步调用 `memory_tools.remember()`，用户无感知

### 计数逻辑
- 只对 role=user 的消息计数
- 计数器清零方式：每凑够 5 个 user 消息触发后清零
- 后台异步执行，不影响用户响应时间

## Capabilities

### New Capabilities
- `auto-memory-extraction`: 自动从对话中提取有价值信息并保存为长期记忆

### Modified Capabilities
- `session-manager`: 在 add_message() 中增加计数器和触发逻辑

## Impact

### 直接影响
- `sessions/manager.py`: 增加 batch_count 字段和触发判断逻辑
- `sessions/models.py`: Session 表增加 message_count_batch 字段
- 新增 `sessions/memory_extractor.py`: MemoryExtractor 模块

### API 影响
- 无 API 变化（后台功能，用户无感知）

### 性能影响
- 每 5 个 user 消息触发一次后台 Task
- LLM 分析成本：每次检查约 20 条消息（约 1000-2000 tokens）
- 不阻塞主流程（asyncio.create_task）