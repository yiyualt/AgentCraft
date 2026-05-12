# Goal Command - Session-level Objective Tracking

## Overview

/goal 命令允许用户设置一个可衡量的目标条件。系统通过 Stop hook 机制，在每次 turn 结束时检查条件是否满足。如果不满足，阻止 session 结束，注入反馈消息让 agent 继续工作直到目标达成。

## Goals

| Goal | Status | Description |
|------|--------|-------------|
| Goal设置 | ❌ | 用户通过 `/goal <condition>` 设置目标 |
| Stop Hook注册 | ❌ | Goal自动注册session-scoped Stop hook |
| 条件检查 | ❌ | Turn结束时检查目标条件是否满足 |
| 阻塞机制 | ❌ | 条件不满足时返回blockingError，session继续 |
| 自动清除 | ❌ | 条件满足时hook自动清除，session正常结束 |
| 反馈注入 | ❌ | 阻塞时注入反馈消息，指导agent继续 |

## Concept

### 工作流程

```
/goal "tests pass"  →  设置session-scoped Stop hook

┌─────────────────────────────────────────────────────────┐
│  Turn 1                                                 │
│  Agent工作... → 尝试结束turn → Stop hook检查           │
│  "tests pass" 满足？ → 否 → 返回blockingError          │
│  → 注入反馈: "Goal not met: tests not passing"         │
│  → Agent继续工作                                        │
├─────────────────────────────────────────────────────────┤
│  Turn 2                                                 │
│  Agent修复代码... → 尝试结束 → Stop hook检查          │
│  "tests pass" 满足？ → 否 → blocking                   │
│  → 注入反馈继续                                         │
├─────────────────────────────────────────────────────────┤
│  Turn 3                                                 │
│  Agent运行测试... → tests pass → 尝试结束             │
│  "tests pass" 满足？ → 是 → hook自动清除               │
│  → Session正常结束                                      │
└─────────────────────────────────────────────────────────┘
```

### 与普通Stop Hook的区别

| 特性 | 普通 Stop Hook | Goal Command |
|------|----------------|--------------|
| 来源 | 配置文件/代码 | 用户命令 |
| 生命周期 | 持久配置 | Session-scoped（会话结束自动清除） |
| 条件 | 固定规则 | 用户自定义字符串 |
| 清除时机 | 手动清除 | 条件满足自动清除 |

### 与 Autonomous Loop (/loop) 的区别

| 特性 | Goal (Stop hook) | Loop (autonomous mode) |
|------|------------------|------------------------|
| 触发时机 | Turn结束时检查 | 定时发送唤醒 |
| 用途 | 阻止session结束直到条件满足 | 保持agent循环运行 |
| 用户交互 | 目标达成后正常结束 | 持续运行直到手动停止 |
| 来源 | 用户命令 | Proactive mode系统 |

## Technical Design

### 1. Goal存储

```python
class GoalState:
    """Goal状态管理"""
    condition: str           # 目标条件描述
    created_at: float        # 创建时间
    check_count: int = 0     # 检查次数
    met: bool = False        # 是否达成

class GoalManager:
    """Goal管理器（session-scoped）"""

    def __init__(self):
        self._current_goal: GoalState | None = None

    def set_goal(self, condition: str) -> str:
        """设置目标"""
        self._current_goal = GoalState(
            condition=condition,
            created_at=time.time(),
        )
        return f"Goal set: {condition}"

    def clear_goal(self) -> str:
        """清除目标"""
        if self._current_goal:
            result = f"Goal cleared: {self._current_goal.condition}"
            self._current_goal = None
            return result
        return "No goal was set"

    def get_goal(self) -> GoalState | None:
        """获取当前目标"""
        return self._current_goal

    def check_goal(self, context: dict) -> tuple[bool, str]:
        """
        检查目标是否达成

        Args:
            context: 包含当前状态信息的字典
                - messages: 当前对话消息
                - tool_results: 最近工具执行结果
                - files_changed: 修改的文件列表
                - tests_status: 测试状态（如果有）

        Returns:
            (is_met, feedback_message)
        """
        if not self._current_goal:
            return True, ""  # 无目标，允许结束

        self._current_goal.check_count += 1

        # 检查条件
        is_met = self._evaluate_condition(
            self._current_goal.condition,
            context
        )

        self._current_goal.met = is_met

        if is_met:
            return True, f"Goal achieved: {self._current_goal.condition}"
        else:
            return False, self._generate_feedback(
                self._current_goal.condition,
                context
            )
```

### 2. 条件评估

```python
def _evaluate_condition(self, condition: str, context: dict) -> bool:
    """
    评估目标条件

    支持的条件类型：
    - "tests pass" → 检查测试结果
    - "file X exists" → 检查文件存在
    - "no errors" → 检查无错误输出
    - "function Y works" → 检查功能执行结果
    """
    condition_lower = condition.lower()

    # 测试相关
    if "tests pass" in condition_lower or "test passes" in condition_lower:
        return self._check_tests_pass(context)

    # 文件存在
    if "file" in condition_lower and "exists" in condition_lower:
        return self._check_file_exists(condition, context)

    # 无错误
    if "no errors" in condition_lower or "no error" in condition_lower:
        return self._check_no_errors(context)

    # 通用评估（使用LLM）
    return self._llm_evaluate(condition, context)

def _check_tests_pass(self, context: dict) -> bool:
    """检查测试是否通过"""
    tool_results = context.get("tool_results", [])

    for result in tool_results:
        # 查找Bash执行pytest的结果
        if "pytest" in result.get("command", ""):
            output = result.get("output", "")
            # 检查典型成功标记
            if "passed" in output.lower() and "failed" not in output.lower():
                return True
            if "0 failed" in output:
                return True

    return False

def _check_file_exists(self, condition: str, context: dict) -> bool:
    """检查文件是否存在"""
    import re
    # 提取文件名/路径
    match = re.search(r"file\s+['\"]?([^'\"]+)['\"]?\s+exists", condition.lower())
    if match:
        filepath = match.group(1)
        import os
        return os.path.exists(filepath)
    return False

def _check_no_errors(self, context: dict) -> bool:
    """检查是否有错误"""
    tool_results = context.get("tool_results", [])

    for result in tool_results:
        output = result.get("output", "")
        if "error" in output.lower() or "exception" in output.lower():
            return False

    return True

def _llm_evaluate(self, condition: str, context: dict) -> bool:
    """使用LLM评估复杂条件"""
    # 简化：检查消息内容中是否包含目标达成迹象
    messages = context.get("messages", [])

    for msg in messages[-3:]:  # 只看最近几条
        content = msg.get("content", "")
        if isinstance(content, str):
            # 检查是否声称完成
            if "done" in content.lower() or "completed" in content.lower():
                if condition.lower() in content.lower():
                    return True

    return False
```

### 3. 反馈生成

```python
def _generate_feedback(self, condition: str, context: dict) -> str:
    """生成反馈消息"""
    check_count = self._current_goal.check_count

    # 基础反馈
    feedback = f"Goal not yet met: '{condition}'"

    # 添加检查次数
    if check_count > 1:
        feedback += f" (checked {check_count} times)"

    # 添加建议（基于条件类型）
    suggestions = self._get_suggestions(condition, context)
    if suggestions:
        feedback += f"\n\nSuggestions:\n{suggestions}"

    return feedback

def _get_suggestions(self, condition: str, context: dict) -> str:
    """根据条件类型生成建议"""
    condition_lower = condition.lower()

    if "tests pass" in condition_lower:
        return "- Run the tests to see current status\n- Fix any failing tests\n- Check test output for specific failures"

    if "file" in condition_lower and "exists" in condition_lower:
        return "- Create the file if it doesn't exist\n- Check if the path is correct"

    if "no errors" in condition_lower:
        return "- Check recent tool outputs for errors\n- Fix any errors found"

    return "- Continue working toward the goal"
```

### 4. 集成到Session

```python
class SessionManager:
    """Session管理器"""

    def __init__(self):
        self._goal_manager = GoalManager()

    def handle_command(self, command: str, args: str) -> str:
        """处理斜杠命令"""
        if command == "goal":
            if args:
                return self._goal_manager.set_goal(args)
            else:
                return self._goal_manager.clear_goal()

        # 其他命令...

    async def check_stop_hooks(self, context: dict) -> tuple[bool, str]:
        """
        检查Stop hooks（包括Goal）

        Returns:
            (should_stop, blocking_message)
        """
        # 检查Goal条件
        is_met, feedback = self._goal_manager.check_goal(context)

        if not is_met:
            # 返回阻塞消息
            return False, feedback

        # Goal达成，清除并允许结束
        if self._goal_manager.get_goal() and is_met:
            self._goal_manager.clear_goal()

        return True, ""
```

### 5. Agent Executor集成

```python
class AgentExecutor:
    async def _run_loop(self, messages, tools, max_turns):
        while True:
            # LLM调用
            response = await self._call_llm(messages, tools)
            messages.append(response)

            # 检查是否结束
            if self._should_end_turn(response):
                # Stop hook检查
                context = {
                    "messages": messages,
                    "tool_results": self._recent_tool_results,
                }

                should_stop, blocking_msg = await self._session.check_stop_hooks(context)

                if not should_stop:
                    # 注入反馈，继续工作
                    logger.info(f"[Goal] Blocking: {blocking_msg}")
                    messages.append({
                        "role": "user",
                        "content": blocking_msg,
                        "is_meta": True,  # 标记为meta消息
                    })
                    continue  # 继续loop

                # 正常结束
                return self._extract_final_content(messages)
```

### 6. 命令处理

```python
# 在gateway.py或chat.py中处理斜杠命令

def process_user_input(input: str) -> str | None:
    """
    处理用户输入

    斜杠命令 → 执行命令，返回结果
    普通消息 → None，交给agent处理
    """
    if input.startswith("/"):
        parts = input.split(" ", 1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if command == "/goal":
            return session_manager.handle_command("goal", args)

        # 其他命令...

    return None  # 普通消息
```

## API Design

### 命令格式

```
/goal <condition>     设置目标
/goal                 清除当前目标
```

### 示例

```
用户: /goal tests pass
系统: Goal set: tests pass

用户: Fix the authentication bug
Agent: ... (修复代码)
Agent: Done, I fixed the auth bug
系统: Goal not yet met: 'tests pass' (checked 1 time)
      Suggestions:
      - Run the tests to see current status

Agent: Running tests...
Agent: All tests passed
系统: Goal achieved: tests pass
```

### 支持的条件类型

| 条件格式 | 检查方式 |
|----------|----------|
| `tests pass` | 检查pytest/jest输出无failed |
| `file X exists` | 检查文件系统 |
| `no errors` | 检查工具输出无error关键字 |
| `function X works` | LLM评估（简化版） |
| 自定义字符串 | LLM评估或关键词匹配 |

## Implementation Plan

### Phase 1: 基础框架
1. 实现 `GoalState` 和 `GoalManager` 类
2. 实现斜杠命令处理 `/goal`
3. 集成到 `SessionManager`

### Phase 2: 条件评估
1. 实现 `check_tests_pass()` 测试检查
2. 实现 `check_file_exists()` 文件检查
3. 实现 `check_no_errors()` 错误检查
4. 实现基础关键词匹配评估

### Phase 3: Stop Hook集成
1. 在 `AgentExecutor` 中添加Stop hook检查点
2. 实现阻塞消息注入
3. 实现Goal达成自动清除

### Phase 4: 反馈优化
1. 实现智能建议生成
2. 添加检查计数和进度显示
3. 支持更多条件类型

## Configuration

```yaml
# goals.yaml (可选配置)
default_check_interval: 1  # 每turn检查一次
max_check_count: 50        # 最大检查次数（防止无限循环）
feedback_template: |
  Goal not yet met: '{condition}'
  {suggestions}
```

## Success Criteria

- [ ] `/goal <condition>` 命令能设置目标
- [ ] `/goal` 能清除目标
- [ ] Turn结束时自动检查条件
- [ ] 条件不满足时阻塞session，注入反馈
- [ ] 条件满足时自动清除goal，正常结束
- [ ] 测试条件检查准确
- [ ] 文件存在条件检查准确
- [ ] 反馈消息对agent有帮助