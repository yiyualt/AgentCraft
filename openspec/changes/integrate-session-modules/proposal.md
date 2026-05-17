## Why

当前 sessions 目录下的 BudgetManager、ResilientExecutor、ForkManager 三个模块仅被实例化，未在主链路中实际调用。这些模块设计完善但处于闲置状态，无法发挥其应有功能（预算控制、错误恢复、子 Agent 上下文继承）。需要将它们整合进 `/v1/chat/completions` 的流式处理流程，激活这些关键能力。

## What Changes

1. **BudgetManager 整合**: 在每轮 LLM 调用前检查 token 预算，防止无限循环和资源浪费
2. **ResilientExecutor 整合**: 包装 LLM 流式调用，提供错误分类、重试、熔断器保护
3. **ForkManager 整合**: 通过 Agent 工具的上下文继承机制，让子 Agent 可以继承父对话历史

## Capabilities

### New Capabilities

- `budget-control`: Token 预算控制能力，追踪消耗、检测边际收益递减、生成预算报告
- `error-recovery`: 多层错误恢复能力，错误分类、指数退避重试、熔断器保护、prompt_too_long 压缩恢复
- `fork-context`: 子 Agent 上下文继承能力，支持 placeholder 机制用于 prompt cache 优化

### Modified Capabilities

无（这三个模块均为新增整合，不修改现有 spec 行为）

## Impact

- **核心文件**: `app.py` 的 `_handle_streaming_via_queue` 函数
- **依赖模块**: `sessions/budget.py`, `sessions/error_recovery.py`, `sessions/fork.py`
- **间接影响**: `tools/builtin/agent_tools.py`（ForkManager 已通过 set_agent_context 设置）
- **API 影响**: 无 API 变化，内部实现优化