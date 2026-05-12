# Hooks System - Lifecycle Event Handlers

## Overview

Hooks系统允许用户在agent生命周期的特定事件点执行自定义shell命令。支持多种事件类型，可用于安全检查、自动化验证、通知推送等场景。

## Goals

| Goal | Status | Description |
|------|--------|-------------|
| 事件定义 | ❌ | 定义20+种生命周期事件 |
| Hook配置 | ❌ | 支持配置事件对应的shell命令 |
| 执行机制 | ❌ | 事件触发时执行hook命令 |
| 输入输出 | ❌ | Hook接收事件数据，可返回决策 |
| 错误处理 | ❌ | Hook失败不阻塞主流程（可配置） |

## Current State

当前系统没有hooks：
- 无法在工具执行前后触发操作
- 无法自动验证或检查
- 无法注入自定义逻辑

**问题**：
- 安全检查需要手动执行
- 无法自动化测试验证
- 无法记录详细审计日志

## Target State

实现Hooks后：
```
事件发生 → 触发Hook → 执行shell命令 → 处理结果
事件示例:
  - PreToolUse → 检查命令安全性
  - PostToolUse → 自动验证结果
  - SessionStart → 初始化环境
  - SessionEnd → 清理资源
  - SubagentStart → 记录子agent启动
```

## Technical Design

### 1. 事件类型

```python
from enum import Enum

class HookEvent(Enum):
    # 工具执行相关
    PRE_TOOL_USE = "PreToolUse"          # 工具执行前
    POST_TOOL_USE = "PostToolUse"        # 工具执行后
    POST_TOOL_USE_FAILURE = "PostToolUseFailure"  # 工具执行失败后

    # 会话相关
    SESSION_START = "SessionStart"       # 会话开始
    SESSION_END = "SessionEnd"           # 会话结束
    SETUP = "Setup"                      # 初始化设置

    # 子Agent相关
    SUBAGENT_START = "SubagentStart"     # 子agent启动
    SUBAGENT_STOP = "SubagentStop"       # 子agent停止

    # 压缩相关
    PRE_COMPACT = "PreCompact"           # 压缩前
    POST_COMPACT = "PostCompact"         # 压缩后

    # 权限相关
    PERMISSION_REQUEST = "PermissionRequest"  # 权限请求
    PERMISSION_DENIED = "PermissionDenied"    # 权限拒绝

    # 停止相关
    STOP = "Stop"                        # 正常停止
    STOP_FAILURE = "StopFailure"         # 异常停止

    # 任务相关
    TASK_CREATED = "TaskCreated"         # 任务创建
    TASK_COMPLETED = "TaskCompleted"     # 任务完成

    # 文件相关
    FILE_CHANGED = "FileChanged"         # 文件变化
    CONFIG_CHANGED = "ConfigChange"      # 配置变化

    # 用户交互相关
    USER_PROMPT_SUBMIT = "UserPromptSubmit"  # 用户提交prompt
    INSTRUCTIONS_LOADED = "InstructionsLoaded"  # 指令加载
```

### 2. Hook定义

```python
class HookMatcher:
    """Hook匹配器"""
    event: HookEvent              # 监听的事件
    matcher: str | None           # 匹配条件（工具名、路径等）
    command: str                  # 要执行的shell命令
    timeout: int = 30             # 执行超时（秒）
    blocking: bool = False        # 是否阻塞主流程

class HookInput:
    """Hook输入数据"""
    event: HookEvent
    tool_name: str | None
    args: dict | None
    result: str | None            # Post事件的结果
    error: str | None             # Failure事件的错误
    session_id: str | None
    agent_type: str | None
    timestamp: float

class HookOutput:
    """Hook输出"""
    status: str                   # "success" / "failure" / "blocked"
    message: str | None           # 返回消息
    decision: str | None          # 决策："allow" / "deny" / "ask"
    exit_code: int | None
```

### 3. Hook执行器

```python
import subprocess
import json

class HookExecutor:
    """Hook执行器"""

    def __init__(self, hooks: list[HookMatcher]):
        self._hooks = hooks

    async def execute(
        self,
        event: HookEvent,
        input_data: HookInput,
    ) -> HookOutput | None:
        """
        执行匹配的hooks

        Returns:
            HookOutput或None（无匹配hook时）
        """
        # 查找匹配的hooks
        matched_hooks = self._find_matching_hooks(event, input_data)

        if not matched_hooks:
            return None

        # 执行每个hook
        for hook in matched_hooks:
            output = await self._run_hook(hook, input_data)

            # 阻塞式hook：返回结果可能影响主流程
            if hook.blocking and output.status == "blocked":
                return output

        return HookOutput(status="success")

    def _find_matching_hooks(
        self,
        event: HookEvent,
        input_data: HookInput,
    ) -> list[HookMatcher]:
        """查找匹配的hooks"""
        matched = []
        for hook in self._hooks:
            if hook.event != event:
                continue

            # 检查matcher条件
            if hook.matcher:
                if input_data.tool_name:
                    if not self._match(hook.matcher, input_data.tool_name):
                        continue

            matched.append(hook)

        return matched

    async def _run_hook(
        self,
        hook: HookMatcher,
        input_data: HookInput,
    ) -> HookOutput:
        """执行单个hook"""
        try:
            # 构建输入JSON
            input_json = json.dumps({
                "event": input_data.event.value,
                "tool_name": input_data.tool_name,
                "args": input_data.args,
                "result": input_data.result,
                "session_id": input_data.session_id,
            })

            # 执行shell命令
            proc = await asyncio.create_subprocess_shell(
                hook.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input_json.encode()),
                timeout=hook.timeout,
            )

            # 解析输出
            if stdout:
                try:
                    output_data = json.loads(stdout.decode())
                    return HookOutput(
                        status=output_data.get("status", "success"),
                        message=output_data.get("message"),
                        decision=output_data.get("decision"),
                        exit_code=proc.returncode,
                    )
                except json.JSONDecodeError:
                    return HookOutput(
                        status="success",
                        message=stdout.decode(),
                        exit_code=proc.returncode,
                    )

            return HookOutput(status="success", exit_code=proc.returncode)

        except asyncio.TimeoutError:
            logger.warning(f"Hook timeout: {hook.command}")
            return HookOutput(status="failure", message="Timeout")

        except Exception as e:
            logger.error(f"Hook error: {e}")
            return HookOutput(status="failure", message=str(e))
```

### 4. 集成到执行流程

```python
class AgentExecutor:
    def __init__(self, ..., hooks: list[HookMatcher] = []):
        self._hook_executor = HookExecutor(hooks)

    async def _run_loop(self, messages, tools, max_turns):
        # SessionStart hook
        await self._hook_executor.execute(
            HookEvent.SESSION_START,
            HookInput(event=HookEvent.SESSION_START, session_id=self._session_id)
        )

        while True:
            # ...

            # PreToolUse hook
            for tc in message.get("tool_calls", []):
                hook_output = await self._hook_executor.execute(
                    HookEvent.PRE_TOOL_USE,
                    HookInput(
                        event=HookEvent.PRE_TOOL_USE,
                        tool_name=tc["function"]["name"],
                        args=json.loads(tc["function"]["arguments"]),
                    )
                )

                # Hook可以阻止执行
                if hook_output and hook_output.decision == "deny":
                    # 返回拒绝结果
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": f"[Blocked by Hook] {hook_output.message}",
                    })
                    continue

                # 执行工具
                result = await self._registry.dispatch(fn_name, fn_args)

                # PostToolUse hook
                await self._hook_executor.execute(
                    HookEvent.POST_TOOL_USE,
                    HookInput(
                        event=HookEvent.POST_TOOL_USE,
                        tool_name=fn_name,
                        args=fn_args,
                        result=result,
                    )
                )
```

### 5. 配置示例

```yaml
# hooks.yaml
hooks:
  # 工具执行前检查
  - event: PreToolUse
    matcher: Bash
    command: "./scripts/check-dangerous-command.sh"
    blocking: true  # 可以阻止执行

  # 文件修改后自动测试
  - event: PostToolUse
    matcher: Write
    command: "pytest tests/ --quiet"
    timeout: 60

  # 会话结束清理
  - event: SessionEnd
    command: "./scripts/cleanup.sh"

  # 子agent启动通知
  - event: SubagentStart
    command: "echo 'Subagent started: $AGENT_TYPE' >> logs/subagents.log"
```

### 6. Hook脚本示例

```bash
#!/bin/bash
# check-dangerous-command.sh

# 读取stdin JSON
input=$(cat)
tool_name=$(echo "$input" | jq -r '.tool_name')
args=$(echo "$input" | jq -r '.args')

# 检查危险命令
command=$(echo "$args" | jq -r '.command')
if [[ "$command" =~ "rm -rf" ]] || [[ "$command" =~ "sudo" ]]; then
    # 返回JSON阻止执行
    jq -n '{"status": "blocked", "decision": "deny", "message": "Dangerous command detected"}'
    exit 1
fi

# 允许执行
jq -n '{"status": "success", "decision": "allow"}'
exit 0
```

## Implementation Plan

### Phase 1: 基础框架
1. 实现 `HookEvent` 事件枚举
2. 实现 `HookMatcher`、`HookInput`、`HookOutput` 类
3. 实现 `HookExecutor` 执行器

### Phase 2: 集成
1. 在 `AgentExecutor` 中集成hook触发点
2. 实现PreToolUse/PostToolUse hooks
3. 实现SessionStart/SessionEnd hooks

### Phase 3: 配置
1. 支持从YAML文件加载hooks配置
2. 支持Agent级hooks覆盖
3. 实现matcher匹配逻辑

### Phase 4: 高级特性
1. 实现阻塞式hook（可阻止执行）
2. 实现hook返回决策
3. 实现hook超时处理

## Success Criteria

- [ ] 20+事件类型定义完整
- [ ] Hook触发时机准确
- [ ] Hook命令执行成功
- [ ] 阻塞式hook能阻止执行
- [ ] Hook失败不影响主流程（可配置）
- [ ] 可从配置文件加载hooks