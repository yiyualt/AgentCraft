# Fork Mechanism - Sub-agent Context Inheritance

## Overview

Fork机制允许子agent继承父agent的完整对话上下文，而不是从零开始。这解决了当前sub-agent需要"重新解释任务背景"的问题，同时通过prompt cache共享提高API效率。

## Goals

| Goal | Status | Description |
|------|--------|-------------|
| Context继承 | ❌ | 子agent继承父agent的完整对话历史 |
| Prompt Cache共享 | ❌ | 多个fork children共享相同的API请求前缀，最大化cache命中率 |
| Placeholder机制 | ❌ | 用相同placeholder填充tool_result，保证byte-identical |
| 递归保护 | ❌ | 防止fork children再次fork（避免无限递归） |
| Worktree隔离 | ❌ | Fork可在独立git worktree执行，不影响主agent文件 |

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
子agent继承: [...历史, assistant(tool_calls), user(placeholder_results..., directive)]
```

**效果**：
- 子agent自动理解背景，无需重复解释
- 所有fork children共享相同的placeholder → cache命中
- 只需写简短directive

## Technical Design

### 1. Fork触发条件

两种模式：
- **显式Fork**: 用户调用时指定 `fork=True` 参数
- **隐式Fork**: 省略 `subagent_type` 时自动fork（继承完整context）

### 2. Placeholder机制（关键）

```python
PLACEHOLDER_RESULT = "Fork started — processing in background"

def build_forked_messages(directive: str, last_assistant_msg: dict) -> list:
    """
    构建fork子agent的消息列表

    关键：所有tool_result使用相同的placeholder文本
    保证byte-identical → prompt cache共享
    """
    # 1. 保留父agent最后的assistant消息（包含所有tool_use）
    assistant_msg = {...last_assistant_msg, "uuid": new_uuid()}

    # 2. 为每个tool_use创建相同placeholder的tool_result
    tool_results = [
        {
            "role": "tool",
            "tool_call_id": tc["id"],
            "content": PLACEHOLDER_RESULT  # 所有fork相同！
        }
        for tc in last_assistant_msg.get("tool_calls", [])
    ]

    # 3. 最后加上唯一的directive
    directive_msg = {
        "role": "user",
        "content": f"<fork>\nSTOP. READ THIS FIRST.\n...\n</fork>\nDirective: {directive}"
    }

    return [...parent_history, assistant_msg, *tool_results, directive_msg]
```

### 3. Fork Child行为约束

Fork child收到特殊指令模板：
```
STOP. READ THIS FIRST.
You are a forked worker process. You are NOT the main agent.

RULES:
1. Do NOT spawn sub-agents (you are the executor)
2. Do NOT converse or ask questions
3. USE tools directly: Bash, Read, Write
4. If you modify files, commit changes before reporting
5. Report once at the end, be factual and concise
6. Stay strictly within your directive's scope

Output format:
  Scope: <your assigned scope>
  Result: <key findings>
  Key files: <relevant paths>
  Files changed: <list with commit hash>
  Issues: <list if any>
```

### 4. 递归保护

```python
FORK_BOILERPLATE_TAG = "fork"

def is_in_fork_child(messages: list) -> bool:
    """检测是否已在fork child中，防止递归fork"""
    for msg in messages:
        if msg["role"] == "user":
            content = msg.get("content", "")
            if isinstance(content, str) and f"<{FORK_BOILERPLATE_TAG}>" in content:
                return True
    return False

# 在AgentExecutor.run()中检查
if is_in_fork_child(messages):
    return "[Error] Cannot fork from a fork child. Execute directly."
```

### 5. Worktree隔离（可选）

```python
def create_worktree_isolation() -> str:
    """创建独立git worktree供fork执行"""
    # git worktree add .claude/worktrees/fork-{uuid}
    # 返回worktree路径
    # fork执行完成后清理
```

Fork child收到额外提示：
```
You are operating in an isolated git worktree at {path}.
Your changes stay in this worktree and will not affect the parent's files.
```

## API Changes

### Tool参数扩展

```python
# Agent tool参数
{
    "prompt": "任务描述",
    "subagent_type": "explore",  # 可选，指定则从零开始
    "fork": True,                # 可选，强制fork模式
    "isolation": "worktree"      # 可选，worktree隔离
}
```

**行为逻辑**：
- 有 `subagent_type` → 传统sub-agent（从零开始）
- 无 `subagent_type` + `fork=True` → Fork模式（继承context）
- 无 `subagent_type` + 无 `fork` → 默认general-purpose（从零开始）

## Implementation Plan

### Phase 1: 基础Fork
1. 实现 `build_forked_messages()` 函数
2. 实现 placeholder 机制
3. 实现 `is_in_fork_child()` 递归保护
4. 修改 `AgentExecutor.run()` 支持fork模式

### Phase 2: Fork指令模板
1. 设计fork child指令模板（约束行为）
2. 实现directive注入
3. 测试fork child输出格式

### Phase 3: Worktree隔离（可选）
1. 实现worktree创建/清理
2. 实现路径翻译
3. 集成到fork流程

## Success Criteria

- [ ] Fork child能访问父对话历史
- [ ] 多个fork children使用相同placeholder
- [ ] Fork child不会再次fork
- [ ] Fork child输出符合规范格式
- [ ] Prompt cache命中率提升（可测量）