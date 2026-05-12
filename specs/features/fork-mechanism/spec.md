# Fork Mechanism - Sub-agent Context Inheritance

## Overview

Fork机制允许子agent继承父agent的完整对话上下文，而不是从零开始。这解决了当前sub-agent需要"重新解释任务背景"的问题，同时通过prompt cache共享提高API效率。

## Goals

| Goal | Status | Description |
|------|--------|-------------|
| Context继承 | ✅ | 子agent继承父agent的完整对话历史 |
| Prompt Cache共享 | ✅ | 通过FORK_PLACEHOLDER固定token实现前缀共享 |
| Placeholder机制 | ✅ | 所有fork children使用相同placeholder，保证cache命中 |
| 递归保护 | ✅ | fork child移除Agent tool + BOILERPLATE指令防止再次fork |
| Worktree隔离 | ❌ | Fork可在独立git worktree执行（可选，Phase 3未实现） |

## Current State

当前AgentExecutor每次启动sub-agent时：
```python
messages = [
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": task},
]
```

**问题**：
- 子agent没有父对话上下文，需要重新解释背景
- 无法利用prompt cache（每次请求前缀不同）
- 用户需要写很长的prompt来解释背景

## Target State

实现Fork机制后：
```
父agent对话历史: [msg1, msg2, msg3, assistant(tool_calls), ...]
                    ↓ Fork
子agent继承: [FORK_CHILD_BOILERPLATE, ...parent_history, user(FORK_PLACEHOLDER)]
                    ↓ build_fork_messages()
实际发送: [FORK_CHILD_BOILERPLATE, ...parent_history, user(actual_task)]
```

**效果**：
- 子agent自动理解背景，无需重复解释
- 所有fork children共享相同的前缀 → cache命中
- 只需写简短task描述

## Technical Design

### 1. Fork触发条件

**显式Fork**: 用户调用Agent tool时指定 `fork_from_current=true` 参数

- 无此参数 → 传统sub-agent（从零开始，使用agent type的system prompt）
- 有此参数 → Fork模式（继承当前session的完整context）

### 2. ForkContext数据流

```
Agent tool (fork_from_current=true)
  → get_current_session_id() → 获取父session_id
  → ForkManager.create_fork_context(parent_session_id)
    → 获取父session消息
    → _clean_orphan_tool_messages() 清理孤立tool消息
    → 如果超过max_tokens，应用SlidingWindowStrategy截断
    → 构建: [FORK_CHILD_BOILERPLATE, ...parent_msgs, FORK_PLACEHOLDER]
    → 返回 ForkContext
  → AgentExecutor.run(fork_context=fork_context, is_fork_child=True)
    → 替换FORK_PLACEHOLDER为实际task
    → 移除Agent tool（递归保护）
    → 执行agent loop
```

### 3. Placeholder机制（已简化实现）

原始spec设计为每个tool_result使用相同placeholder。实际实现简化为：
- 在继承消息列表末尾插入单个 `FORK_PLACEHOLDER` 占位符
- `build_fork_messages()` 将其替换为实际task文本
- 多个fork children继承相同的前缀（FORK_CHILD_BOILERPLATE + 父消息），保证prompt cache命中

```python
FORK_PLACEHOLDER = "[FORK_TASK_PLACEHOLDER_8F2A]"

# create_fork_context() 在消息列表末尾插入placeholder
inherited_messages = [fork_system_msg, ...parent_msgs, {"role": "user", "content": FORK_PLACEHOLDER}]

# build_fork_messages() 或 run() 内联替换placeholder为实际task
for i, msg in enumerate(messages):
    if msg.get("content") == FORK_PLACEHOLDER:
        messages[i] = {"role": "user", "content": task}
```

### 4. Fork Child行为约束

Fork child收到特殊系统消息 `FORK_CHILD_BOILERPLATE`：
```
<fork>
STOP. READ THIS FIRST.

You are a forked worker process. You are NOT the main agent.

RULES:
1. Do NOT spawn sub-agents (Agent tool is disabled for you)
2. Do NOT ask questions - execute your task directly
3. Use tools directly: Bash, Read, Write, Edit, Glob, Grep
4. If you modify files, commit changes before reporting
5. Report once at the end, be factual and concise
6. Stay strictly within your assigned scope

Output format:
  Scope: <your assigned scope>
  Result: <key findings>
  Key files: <relevant paths>
  Files changed: <list with commit hash if applicable>
  Issues: <list if any>
</fork>
```

### 5. 递归保护（三层防护）

1. **工具层**: `is_fork_child=True` 时，从tool列表中移除Agent tool
2. **指令层**: FORK_CHILD_BOILERPLATE 指示LLM不要生成子agent
3. **检测层**: `ForkManager.is_in_fork_child()` 扫描消息检测`<fork>`标签

```python
# AgentExecutor.run() 中
if is_fork_child:
    tools = [t for t in tools if t["function"]["name"] != "Agent"]

# ForkManager.is_in_fork_child() 中
def is_in_fork_child(self, messages: list) -> bool:
    for msg in messages:
        if msg["role"] == "system" and "<fork>" in msg.get("content", ""):
            return True
        if msg["role"] == "user" and msg.get("content") == FORK_PLACEHOLDER:
            return True
    return False
```

### 6. Worktree隔离（可选，未实现）

```python
def create_worktree_isolation() -> str:
    """创建独立git worktree供fork执行"""
    # git worktree add .claude/worktrees/fork-{uuid}
    # 返回worktree路径
    # fork执行完成后清理
```

## API Changes

### Agent Tool参数

```python
# Agent tool参数（tools/builtin.py）
{
    "prompt": "任务描述",
    "subagent_type": "explore | general-purpose | plan",
    "fork_from_current": True/False,  # 是否继承当前对话context
}
```

**行为逻辑**（tools/builtin.py `agent_delegate()`）：
- `fork_from_current=False`（默认）→ 传统sub-agent（从零开始）
- `fork_from_current=True` → Fork模式：
  1. 获取当前session_id
  2. 通过ForkManager创建ForkContext
  3. 传递fork_context和is_fork_child=True给AgentExecutor

### ForkManager API

```python
class ForkManager:
    def create_fork_context(parent_session_id, max_tokens=32000) -> ForkContext | None
    def build_fork_messages(fork_context, task) -> list[dict]
    def is_in_fork_child(messages) -> bool
    def get_fork_stats(fork_context) -> dict

@dataclass
class ForkContext:
    parent_session_id: str
    inherited_messages: list[dict]
    placeholder_index: int
    is_fork_child: bool = True
    max_inherited_tokens: int = 32000
```

## Implementation Plan

### Phase 1: 基础Fork ✅ 完成
1. ForkManager.create_fork_context() — sessions/fork.py
2. ForkContext — sessions/fork.py
3. FORK_PLACEHOLDER 和 FORK_CHILD_BOILERPLATE — sessions/fork.py
4. ForkManager.is_in_fork_child() 递归保护 — sessions/fork.py
5. AgentExecutor.run() fork参数支持 — tools/agent_executor.py
6. Agent tool fork_from_current参数 — tools/builtin.py
7. Gateway初始化ForkManager — gateway.py

### Phase 2: Fork指令模板 ✅ 完成
1. FORK_CHILD_BOILERPLATE指令模板 — sessions/fork.py
2. 递归保护（工具移除 + 指令 + 检测）— tools/agent_executor.py, sessions/fork.py

### Phase 3: Worktree隔离（可选）❌ 未实现
1. 实现worktree创建/清理
2. 实现路径翻译
3. 集成到fork流程

## Success Criteria

- [x] Fork child能访问父对话历史
- [x] Fork child使用FORK_PLACEHOLDER占位符
- [x] Fork child不会再次fork（三层防护）
- [x] Fork child输出符合规范格式（BOILERPLATE约束）
- [ ] Prompt cache命中率提升（可测量 — 需生产环境验证）
- [ ] Worktree隔离（Phase 3，可选）
