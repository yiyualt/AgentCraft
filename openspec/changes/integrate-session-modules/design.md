## Context

当前 `app.py` 的 `_handle_streaming_via_queue` 函数（第1084行）实现了流式 LLM 调用和工具执行循环。sessions 目录下的三个模块已实例化但未实际调用：

- **BudgetManager** (`app.py:204-206`): 用于追踪 token 消耗、检测边际收益递减
- **ResilientExecutor** (`app.py:218-230`): 用于错误分类、重试、熔断器保护
- **ForkManager** (`app.py:236-246`): 已通过 `set_agent_context()` 设置，但 Agent 工具内部调用时机不明确

## Goals / Non-Goals

**Goals:**
- BudgetManager 在每轮工具循环前检查预算，超过阈值或边际收益递减时优雅终止
- ResilientExecutor 包装 LLM 流式调用，捕获错误后执行分类、重试、压缩恢复
- ForkManager 确保 Agent 工具能正确继承父对话历史（已有部分设置，需验证调用链）

**Non-Goals:**
- 不修改 `core/tool_loop.py` 的 `run_tool_loop` 函数（用户明确排除）
- 不修改 API 接口，保持 `/v1/chat/completions` 兼容性
- 不修改 CompactionManager 和 Permission 相关模块（不在本次范围）

## Decisions

### Decision 1: BudgetManager 整合位置

**选择**: 在 `_handle_streaming_via_queue` 的 while 循环开始处调用

**理由**: 
- 每轮工具循环前检查预算是最自然的时机
- 与 `tool_loop.py:130-139` 的设计意图一致
- 可以在 nudge 消息中告知 Agent 当前预算状态

**替代方案**: 在 LLM 调用后检查（延迟感知，可能导致浪费）

### Decision 2: ResilientExecutor 整合方式

**选择**: 包装 `_provider_registry.stream_iterator()` 调用

**理由**:
- 流式调用可能抛出网络错误、超时、rate limit 等
- 现有的 try/except 块可以替换为 `ResilientExecutor.run_with_recovery()`
- compaction callback 已设置，可处理 prompt_too_long

**替代方案**: 在 executor 级别包装（错过流式错误分类）

### Decision 3: ForkManager 调用验证

**选择**: 验证现有 `set_agent_context()` 设置是否完整传递到 Agent 工具

**理由**:
- ForkManager 已通过 `set_agent_context()` 设置 (`app.py:241-246`)
- 需确认 `tools/builtin/agent_tools.py` 中的 `get_fork_manager()` 能正确获取
- 子 Agent 执行时需调用 `fork_manager.create_fork_context()`

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| BudgetManager 过早终止导致任务未完成 | 设置合理的 DEFAULT_BUDGET (50000) 和 MIN_TOKENS_FOR_DIMINISHING (3000) |
| ResilientExecutor 重试增加延迟 | 网络错误 2s base_delay，rate_limit 10s base_delay，最大 30s |
| ForkManager placeholder 与流式响应不兼容 | placeholder 在子 Agent 独立调用时生效，不影响主链路流式响应 |

## Migration Plan

1. 阶段 1: BudgetManager 整合（无破坏性变更）
2. 阶段 2: ResilientExecutor 整合（替换 try/except）
3. 阶段 3: ForkManager 调用链验证（可能需要微调 agent_tools）

## Open Questions

- session 的 token_budget 字段是否需要从 SessionManager 读取？（当前 session 对象有该属性）