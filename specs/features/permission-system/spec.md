# Permission System - Tool Execution Control

## Overview

Permission系统控制agent执行工具时的权限，防止危险操作。支持多种权限模式、规则配置、交互式确认，确保安全执行。

## Goals

| Goal | Status | Description |
|------|--------|-------------|
| 权限模式 | ❌ | 支持多种模式（default, acceptEdits, bypass等） |
| 规则配置 | ❌ | 支持AlwaysAllow/AlwaysDeny/AlwaysAsk规则 |
| 工具过滤 | ❌ | 根据规则过滤工具调用 |
| 拒绝追踪 | ❌ | 追踪被拒绝的操作，防止重复请求 |
| 交互确认 | ❌ | 需要确认的工具请求用户批准 |

## Current State

当前系统没有权限控制：
- 所有工具无条件执行
- Bash可执行任意命令
- Write可写入任意文件
- 无安全防护

**问题**：
- 危险命令可能执行（rm -rf等）
- 敏感文件可能被修改
- 用户无法控制执行范围

## Target State

实现Permission后：
```
工具调用 → Permission检查 → 决策
决策:
  - AlwaysAllow规则 → 直接执行
  - AlwaysDeny规则 → 拒绝，返回错误
  - AlwaysAsk规则 → 请求用户确认
  - 无匹配规则 → 根据模式决定
模式:
  - default → 询问用户（默认）
  - acceptEdits → 自动接受编辑类工具
  - bypassPermissions → 绕过所有检查（危险）
  - auto → 智能决策
```

## Technical Design

### 1. 权限模式

```python
from enum import Enum

class PermissionMode(Enum):
    DEFAULT = "default"           # 默认：每次询问
    ACCEPT_EDITS = "acceptEdits"  # 自动接受编辑
    BYPASS = "bypassPermissions"  # 绕过所有（危险）
    AUTO = "auto"                 # 智能决策
    PLAN = "plan"                 # 计划模式（只规划不执行）

def get_default_mode() -> PermissionMode:
    """获取默认权限模式"""
    return PermissionMode.DEFAULT
```

### 2. 规则定义

```python
class PermissionRuleKind(Enum):
    ALWAYS_ALLOW = "AlwaysAllow"
    ALWAYS_DENY = "AlwaysDeny"
    ALWAYS_ASK = "AlwaysAsk"

class PermissionRule:
    kind: PermissionRuleKind
    tool_name: str | None         # 匹配工具名（支持通配符）
    command_pattern: str | None   # 匹配命令（Bash工具）
    path_pattern: str | None      # 匹配路径（Read/Write工具）

    def matches(self, tool_name: str, args: dict) -> bool:
        """检查规则是否匹配"""
        # 工具名匹配
        if self.tool_name:
            if not self._match_pattern(self.tool_name, tool_name):
                return False

        # 命令匹配（Bash）
        if self.command_pattern and tool_name == "Bash":
            command = args.get("command", "")
            if not self._match_pattern(self.command_pattern, command):
                return False

        # 路径匹配（Read/Write）
        if self.path_pattern and tool_name in ["Read", "Write", "Edit"]:
            path = args.get("file_path", args.get("path", ""))
            if not self._match_pattern(self.path_pattern, path):
                return False

        return True

    def _match_pattern(self, pattern: str, value: str) -> bool:
        """模式匹配（支持通配符*）"""
        import fnmatch
        return fnmatch.fnmatch(value.lower(), pattern.lower())
```

### 3. Permission检查器

```python
class PermissionChecker:
    """权限检查器"""

    def __init__(
        self,
        mode: PermissionMode = PermissionMode.DEFAULT,
        rules: list[PermissionRule] = [],
    ):
        self._mode = mode
        self._rules = rules
        self._denied_count: dict[str, int] = {}  # 拒绝计数

    def check(
        self,
        tool_name: str,
        args: dict,
    ) -> PermissionResult:
        """
        检查工具调用权限

        Returns:
            PermissionResult: ALLOW / DENY / ASK
        """
        # Bypass模式：全部允许
        if self._mode == PermissionMode.BYPASS:
            return PermissionResult.ALLOW

        # Plan模式：拒绝执行类工具
        if self._mode == PermissionMode.PLAN:
            if tool_name in ["Bash", "Write", "Edit"]:
                return PermissionResult.DENY

        # 检查规则
        for rule in self._rules:
            if rule.matches(tool_name, args):
                if rule.kind == PermissionRuleKind.ALWAYS_ALLOW:
                    return PermissionResult.ALLOW
                elif rule.kind == PermissionRuleKind.ALWAYS_DENY:
                    return PermissionResult.DENY
                elif rule.kind == PermissionRuleKind.ALWAYS_ASK:
                    return PermissionResult.ASK

        # 无匹配规则 → 根据模式决定
        if self._mode == PermissionMode.ACCEPT_EDITS:
            if tool_name in ["Read", "Write", "Edit"]:
                return PermissionResult.ALLOW

        if self._mode == PermissionMode.AUTO:
            # 智能决策（后续实现）
            return self._auto_decision(tool_name, args)

        # Default模式：询问
        return PermissionResult.ASK

    def _auto_decision(self, tool_name: str, args: dict) -> PermissionResult:
        """智能决策（AUTO模式）"""
        # 读取类操作自动允许
        if tool_name in ["Read", "Glob", "Grep"]:
            return PermissionResult.ALLOW

        # 其他需要确认
        return PermissionResult.ASK

    def record_denial(self, tool_name: str, args: dict):
        """记录拒绝"""
        key = f"{tool_name}:{json.dumps(args)}"
        self._denied_count[key] = self._denied_count.get(key, 0) + 1

    def was_denied(self, tool_name: str, args: dict) -> bool:
        """检查是否曾被拒绝"""
        key = f"{tool_name}:{json.dumps(args)}"
        return self._denied_count.get(key, 0) > 0
```

### 4. 结果类型

```python
from enum import Enum

class PermissionResult(Enum):
    ALLOW = "allow"   # 允许执行
    DENY = "deny"     # 拒绝执行
    ASK = "ask"       # 需要用户确认

class PermissionDecision:
    result: PermissionResult
    reason: str | None  # 拒绝/询问原因
    matched_rule: PermissionRule | None  # 匹配的规则
```

### 5. 默认规则

```python
DEFAULT_RULES = [
    # 始终拒绝危险命令
    PermissionRule(
        kind=PermissionRuleKind.ALWAYS_DENY,
        tool_name="Bash",
        command_pattern="rm -rf *",
    ),
    PermissionRule(
        kind=PermissionRuleKind.ALWAYS_DENY,
        tool_name="Bash",
        command_pattern="rm -rf /",
    ),
    PermissionRule(
        kind=PermissionRuleKind.ALWAYS_DENY,
        tool_name="Bash",
        command_pattern="sudo *",
    ),

    # 始终询问敏感路径
    PermissionRule(
        kind=PermissionRuleKind.ALWAYS_ASK,
        path_pattern="/etc/*",
    ),
    PermissionRule(
        kind=PermissionRuleKind.ALWAYS_ASK,
        path_pattern="*.env",
    ),
    PermissionRule(
        kind=PermissionRuleKind.ALWAYS_ASK,
        path_pattern="*credentials*",
    ),

    # 始终允许安全读取
    PermissionRule(
        kind=PermissionRuleKind.ALWAYS_ALLOW,
        tool_name="Read",
        path_pattern="*.py",
    ),
    PermissionRule(
        kind=PermissionRuleKind.ALWAYS_ALLOW,
        tool_name="Read",
        path_pattern="*.md",
    ),
]
```

### 6. 集成到工具执行

```python
class UnifiedToolRegistry:
    async def dispatch(
        self,
        name: str,
        args: dict,
        permission_checker: PermissionChecker | None = None,
    ) -> str:
        """带权限检查的工具执行"""
        # Permission检查
        if permission_checker:
            result = permission_checker.check(name, args)

            if result == PermissionResult.DENY:
                permission_checker.record_denial(name, args)
                return f"[Permission Denied] {name}({args})"

            if result == PermissionResult.ASK:
                # 请求用户确认（通过Channel或其他机制）
                approved = await self._request_user_approval(name, args)
                if not approved:
                    permission_checker.record_denial(name, args)
                    return f"[Permission Denied by User] {name}({args})"

        # 执行工具
        return await self._execute_tool(name, args)
```

## Implementation Plan

### Phase 1: 基础框架
1. 实现 `PermissionMode` 和 `PermissionResult` 枚举
2. 实现 `PermissionRule` 规则类
3. 实现 `PermissionChecker` 检查器

### Phase 2: 规则配置
1. 实现默认规则列表
2. 实现规则匹配逻辑（通配符支持）
3. 实现拒绝追踪

### Phase 3: 集成
1. 在 `UnifiedToolRegistry.dispatch()` 中集成检查
2. 实现用户确认请求机制
3. 修改 `AgentExecutor` 使用permission

### Phase 4: 配置加载
1. 支持从配置文件加载规则
2. 支持Agent级权限模式覆盖
3. 支持运行时修改权限

## Configuration Example

```yaml
# permissions.yaml
mode: default

rules:
  # 禁止危险命令
  - kind: AlwaysDeny
    tool: Bash
    command: "rm -rf *"

  # 允许项目内读写
  - kind: AlwaysAllow
    path: "./src/*"

  # 询问敏感文件
  - kind: AlwaysAsk
    path: "*.env"
```

## Success Criteria

- [ ] 多种权限模式工作正常
- [ ] 规则匹配准确（通配符支持）
- [ ] 危险操作被拒绝
- [ ] 拒绝追踪防止重复请求
- [ ] 用户确认机制有效
- [ ] 可从配置文件加载规则