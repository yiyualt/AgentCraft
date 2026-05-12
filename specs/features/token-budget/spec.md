# Token Budget - Execution Cost Control

## Overview

Token Budget系统追踪和控制agent执行的token消耗。当消耗接近预算时，系统评估是否值得继续，检测边际收益递减，防止无效的无限循环。

## Goals

| Goal | Status | Description |
|------|--------|-------------|
| Token追踪 | ❌ | 追踪每轮、累积、增量token消耗 |
| 预算设置 | ❌ | 支持设置任务级token预算 |
| 边际收益检测 | ❌ | 检测连续低产出轮次，判定递减 |
| 自动停止 | ❌ | 预算耗尽或收益递减时自动停止 |
| 预算报告 | ❌ | 任务结束时报告token使用情况 |

## Current State

当前系统只有简单timeout：
```python
timeout: int = 180  # 秒
```

**问题**：
- 无法控制API成本
- 无法检测无效循环
- 不知道任务消耗了多少token

## Target State

实现Token Budget后：
```
设置预算: budget=50000 tokens
执行中:
  - 追踪每轮消耗
  - 检测边际收益（增量 < 500 tokens）
  - 预算90%时评估是否继续
决策:
  - 收益递减 → 自动停止
  - 预算耗尽 → 停止并报告
  - 正常 → 继续执行
```

## Technical Design

### 1. Budget Tracker

```python
class BudgetTracker:
    continuation_count: int = 0       # 连续继续次数
    last_delta_tokens: int = 0        # 上次增量
    last_global_turn_tokens: int = 0  # 上次总tokens
    started_at: float                 # 开始时间

COMPLETION_THRESHOLD = 0.9  # 90%时评估
DIMINISHING_THRESHOLD = 500  # 边际收益阈值

def check_token_budget(
    tracker: BudgetTracker,
    budget: int | None,
    current_tokens: int,
) -> BudgetDecision:
    """
    检查token预算，决定是否继续

    Returns:
        ContinueDecision: 继续执行，附带nudge消息
        StopDecision: 停止执行，附带完成报告
    """
    if budget is None or budget <= 0:
        return StopDecision(completion_event=None)

    pct = int(current_tokens / budget * 100)
    delta = current_tokens - tracker.last_global_turn_tokens

    # 检测边际收益递减
    is_diminishing = (
        tracker.continuation_count >= 3 and
        delta < DIMINISHING_THRESHOLD and
        tracker.last_delta_tokens < DIMINISHING_THRESHOLD
    )

    # 未达90%且无收益递减 → 继续
    if not is_diminishing and current_tokens < budget * COMPLETION_THRESHOLD:
        tracker.continuation_count += 1
        tracker.last_delta_tokens = delta
        tracker.last_global_turn_tokens = current_tokens
        return ContinueDecision(
            nudge_message=f"进度 {pct}%，tokens: {current_tokens}/{budget}",
            pct=pct
        )

    # 收益递减或预算接近 → 停止
    return StopDecision(
        completion_event={
            "continuation_count": tracker.continuation_count,
            "pct": pct,
            "tokens": current_tokens,
            "budget": budget,
            "diminishing_returns": is_diminishing,
            "duration_ms": int((time.time() - tracker.started_at) * 1000)
        }
    )
```

### 2. 预算来源

```python
# 预算可来自多个来源（优先级从高到低）
def get_budget_for_task(
    explicit_budget: int | None,     # 用户显式设置
    agent_config_budget: int | None, # Agent配置
    default_budget: int = 50000,     # 默认值
) -> int:
    if explicit_budget:
        return explicit_budget
    if agent_config_budget:
        return agent_config_budget
    return default_budget
```

### 3. Token估算

```python
def estimate_tokens(messages: list) -> int:
    """
    估算消息列表的token数量

    使用简单估算：每4字符≈1token
    精确估算需要调用tokenizer（可选）
    """
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += len(content) // 4
        elif isinstance(content, list):
            for block in content:
                if block.get("type") == "text":
                    total += len(block.get("text", "")) // 4
    return total
```

### 4. 继续消息（Nudge）

当决定继续时，注入提示消息：
```python
NUDGE_TEMPLATE = """
Token预算进度: {pct}%
当前消耗: {tokens} tokens
预算上限: {budget} tokens

继续执行任务，保持高效。
"""

def get_nudge_message(pct: int, tokens: int, budget: int) -> str:
    return NUDGE_TEMPLATE.format(pct=pct, tokens=tokens, budget=budget)
```

### 5. 完成报告

任务结束时生成报告：
```python
def generate_budget_report(event: dict) -> str:
    """
    生成token使用报告
    """
    lines = [
        "Token使用报告:",
        f"- 总消耗: {event['tokens']} tokens ({event['pct']}%)",
        f"- 预算上限: {event['budget']} tokens",
        f"- 继续次数: {event['continuation_count']}",
        f"- 执行时间: {event['duration_ms']}ms",
    ]

    if event['diminishing_returns']:
        lines.append("- 停止原因: 边际收益递减")
    else:
        lines.append("- 停止原因: 预算接近上限")

    return "\n".join(lines)
```

## Implementation Plan

### Phase 1: 基础追踪
1. 实现 `BudgetTracker` 类
2. 实现 `estimate_tokens()` 函数
3. 在 `AgentExecutor` 中集成追踪

### Phase 2: 预算决策
1. 实现 `check_token_budget()` 决策逻辑
2. 实现边际收益检测
3. 实现nudge消息注入

### Phase 3: 报告
1. 实现完成报告生成
2. 实现预算超限处理
3. 添加日志记录

## API Changes

### AgentExecutor参数

```python
async def run(
    self,
    task: str,
    agent_type: str = "general-purpose",
    context: str | None = None,
    timeout: int = 180,
    budget: int | None = None,  # 新增：token预算
) -> str:
```

### 返回值扩展

```python
# 返回值包含预算信息
{
    "result": "任务结果...",
    "budget_report": {
        "tokens": 45000,
        "budget": 50000,
        "pct": 90,
        "diminishing_returns": False
    }
}
```

## Success Criteria

- [ ] Token实时追踪准确（误差<10%）
- [ ] 边际收益递减检测有效
- [ ] 预算90%时正确评估
- [ ] 任务结束生成预算报告
- [ ] 连续低产出时自动停止