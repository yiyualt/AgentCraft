# Auto-Compaction - Context Window Management

## Overview

Auto-compaction系统自动压缩对话历史，防止context window溢出。当对话过长时，系统自动摘要历史消息，保留关键信息，释放token空间。

## Goals

| Goal | Status | Description |
|------|--------|-------------|
| Token监控 | ❌ | 实时追踪对话token使用量 |
| 自动触发 | ❌ | 达到阈值时自动触发compaction |
| 智能摘要 | ❌ | LLM生成摘要，保留关键信息 |
| 多层压缩 | ❌ | Microcompact → Autocompact → Reactive |
| 熔断保护 | ❌ | 连续失败后停止尝试，避免浪费API |

## Current State

当前系统没有context管理：
- 对话历史无限增长
- 达到API限制时直接失败
- 用户需要手动清除对话

**问题**：
- 长对话无法继续
- API调用浪费（prompt_too_long错误）
- 用户体验差

## Target State

实现Auto-compaction后：
```
对话token接近阈值 → 自动摘要 → 释放空间 → 继续对话
失败 → Reactive compact → 再次尝试
连续失败3次 → 熔断，停止尝试
```

## Technical Design

### 1. Token阈值计算

```python
# 配置常量
AUTOCOMPACT_BUFFER_TOKENS = 13000  # 留出空间给输出
WARNING_THRESHOLD = 20000          # 警告阈值
ERROR_THRESHOLD = 20000            # 错误阈值

def get_autocompact_threshold(model: str) -> int:
    """计算自动压缩触发阈值"""
    context_window = get_model_context_window(model)
    effective_window = context_window - AUTOCOMPACT_BUFFER_TOKENS
    return effective_window

# 示例：deepseek-chat (64K context)
# threshold = 64000 - 13000 = 51000 tokens
```

### 2. 压缩层级

**层级1：Microcompact（轻量）**
- 移除早期的assistant/user消息对
- 保留最近N轮对话
- 不调用LLM，直接裁剪

**层级2：Autocompact（标准）**
- LLM生成摘要替换历史消息
- 保留关键信息：
  - 重要决策
  - 文件修改记录
  - 用户明确要求
  - 工具调用结果摘要

**层级3：Reactive Compact（恢复）**
- `prompt_too_long` 错误后触发
- 更激进的压缩策略
- 可能丢弃更多历史

### 3. 状态追踪

```python
class AutoCompactState:
    compacted: bool = False           # 本轮是否已压缩
    turn_counter: int = 0             # 轮次计数
    turn_id: str                      # 当前轮ID
    consecutive_failures: int = 0     # 连续失败次数

MAX_CONSECUTIVE_FAILURES = 3  # 熔断阈值

def should_autocompact(state: AutoCompactState, token_count: int, threshold: int) -> bool:
    """判断是否需要自动压缩"""
    if state.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
        return False  # 熔断，不再尝试

    return token_count >= threshold
```

### 4. 消息摘要格式

```python
SUMMARY_TEMPLATE = """
Summarize the following conversation history, preserving:
1. Key decisions made
2. Files modified (with brief description)
3. Important findings from tool calls
4. User's explicit requirements
5. Current task status

Format as bullet points, concise.

History to summarize:
{history}
"""

def compact_messages(messages: list, keep_recent: int = 5) -> tuple[list, list]:
    """
    压缩消息列表

    Returns:
        (compact_messages, preserved_messages)
    """
    # 保留最近几轮不压缩
    preserved = messages[-keep_recent:]

    # 压缩历史部分
    history = messages[:-keep_recent]

    # 调用LLM生成摘要
    summary = generate_summary(history)

    # 创建摘要消息
    summary_msg = {
        "role": "user",
        "content": f"<context_summary>\n{summary}\n</context_summary>"
    }

    return [summary_msg], preserved
```

### 5. 熔断机制

```python
def handle_compaction_failure(state: AutoCompactState, error: Exception):
    """处理压缩失败"""
    state.consecutive_failures += 1

    if state.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
        log.error(f"Auto-compaction熔断，连续失败{state.consecutive_failures}次")
        return "stop"  # 停止尝试

    return "retry"  # 可以重试
```

## Implementation Plan

### Phase 1: Token追踪
1. 实现 `token_count_with_estimation()` 函数
2. 实现 `AutoCompactState` 状态类
3. 在 `AgentExecutor._run_loop()` 中追踪token

### Phase 2: 基础Autocompact
1. 实现 `should_autocompact()` 判断逻辑
2. 实现 `compact_messages()` 消息压缩
3. 实现 LLM摘要调用
4. 集成到主loop中

### Phase 3: 多层压缩
1. 实现 Microcompact（轻量裁剪）
2. 实现 Reactive Compact（错误恢复）
3. 实现熔断机制

### Phase 4: 保留策略
1. 设计关键消息标记机制
2. 实现选择性保留
3. 防止重要信息丢失

## Integration Points

### AgentExecutor修改

```python
class AgentExecutor:
    def __init__(self, ...):
        self._compact_state = AutoCompactState()
        self._compact_threshold = get_autocompact_threshold(model)

    async def _run_loop(self, messages, tools, max_turns):
        while True:
            # 1. 检查token
            token_count = estimate_tokens(messages)
            if should_autocompact(self._compact_state, token_count, self._compact_threshold):
                messages = await self._do_compact(messages)

            # 2. 正常LLM调用
            response = await self._call_llm(messages, tools)
            ...
```

## Success Criteria

- [ ] Token实时追踪准确
- [ ] 达到阈值时自动触发压缩
- [ ] 摘要保留关键信息（用户可验证）
- [ ] 压缩后对话可继续
- [ ] 连续失败3次后熔断
- [ ] Prompt_too_long错误能恢复