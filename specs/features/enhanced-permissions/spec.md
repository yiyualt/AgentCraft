# Enhanced Permission System - Pattern Matching & Smart Classification

## Overview

增强权限系统支持pattern matching（如`Bash(git *)`）和智能分类器（Auto模式），借鉴Claude Code的52k+行权限系统设计，为当前100行简单权限系统增加复杂度。

## Goals

| Goal | Status | Description |
|------|--------|-------------|
| Pattern Matching | ❌ | 支持`Bash(git *)`、`Read(/tmp/*)`等pattern |
| 多源规则 | ❌ | 支持8种规则来源（cliArg, session, settings等） |
| Auto分类器 | ❌ | Auto模式下智能判断allow/deny |
| MCP权限 | ❌ | MCP工具按server级别权限控制 |
| 权限审计 | ❌ | 记录所有权限决策日志 |

## Current State

当前权限系统（sessions/permission.py）：

```python
class PermissionMode:
    DEFAULT = "default"
    ACCEPT_EDITS = "accept_edits"
    BYPASS = "bypass"
    AUTO = "auto"
    PLAN = "plan"

class PermissionRule:
    action: str  # "allow", "deny", "ask"
    tool: str    # tool name
    path: str | None  # optional path pattern

class PermissionChecker:
    def check(self, tool: str, params: dict) -> str:
        # 简单规则匹配
        for rule in self._rules:
            if rule.tool == tool:
                return rule.action
        return "ask"  # default
```

**问题**：
- 无pattern matching能力
- 规则来源单一（只有配置文件）
- Auto模式只是概念，无实际智能分类
- 无权限决策日志

## Target State

实现Enhanced Permission后：

```python
# Pattern matching示例
rules = [
    PermissionRule(action="allow", pattern="Bash(git *)"),
    PermissionRule(action="allow", pattern="Bash(npm *)"),
    PermissionRule(action="ask", pattern="Bash(rm *)"),
    PermissionRule(action="deny", pattern="Bash(rm -rf /*)"),
    PermissionRule(action="allow", pattern="Read(/tmp/*)"),
    PermissionRule(action="ask", pattern="Read(/etc/*)"),
    PermissionRule(action="deny", pattern="Read(~/.ssh/*)"),
    PermissionRule(action="allow", pattern="mcp__weather"),  # MCP server级别
]

# Auto模式智能分类
checker = PermissionChecker(mode="auto")
checker.check("Bash", {"command": "git status"})  # → "allow" (安全操作)
checker.check("Bash", {"command": "rm -rf /"})    # → "deny" (危险操作)
checker.check("Bash", {"command": "npm install"}) # → "allow" (常见操作)
checker.check("Bash", {"command": "curl evil.com"}) # → "ask" (未知风险)
```

## Technical Design

### 1. Pattern Matching引擎

```python
import fnmatch
import re

class PermissionPattern:
    """权限pattern解析与匹配"""
    
    # Pattern格式: Tool(path_pattern) 或 Tool(arg_pattern)
    # Examples:
    #   Bash(git *)       → 匹配所有git命令
    #   Read(/tmp/*)      → 匹配/tmp下所有文件
    #   Write(*.py)       → 匹配所有.py文件
    #   mcp__weather      → 匹配MCP server所有工具
    
    @staticmethod
    def parse(pattern: str) -> tuple[str, str | None]:
        """解析pattern为tool和sub_pattern"""
        match = re.match(r'^(\w+)(?:\((.+)\))?$', pattern)
        if not match:
            raise ValueError(f"Invalid pattern: {pattern}")
        
        tool = match.group(1)
        sub_pattern = match.group(2)
        return tool, sub_pattern
    
    @staticmethod
    def matches(pattern: str, tool: str, params: dict) -> bool:
        """检查pattern是否匹配tool调用"""
        parsed_tool, sub_pattern = PermissionPattern.parse(pattern)
        
        # 工具名必须匹配
        if parsed_tool != tool:
            return False
        
        # 无子pattern → 工具级别匹配
        if sub_pattern is None:
            return True
        
        # 有子pattern → 参数匹配
        if tool == "Bash":
            command = params.get("command", "")
            return fnmatch.fnmatch(command, sub_pattern)
        
        if tool in ("Read", "Write", "Edit"):
            path = params.get("file_path", "")
            return fnmatch.fnmatch(path, sub_pattern)
        
        # MCP工具：server级别匹配
        if tool.startswith("mcp__"):
            server = tool.split("__")[1]
            return fnmatch.fnmatch(server, sub_pattern)
        
        return False

class PermissionMatcher:
    """多pattern匹配器"""
    
    def __init__(self, rules: list[PermissionRule]):
        self._rules = rules
    
    def match(self, tool: str, params: dict) -> str | None:
        """找到匹配的规则，返回action"""
        for rule in self._rules:
            if PermissionPattern.matches(rule.pattern, tool, params):
                return rule.action
        return None
```

### 2. 多源规则系统

```python
from enum import Enum

class RuleSource(Enum):
    """规则来源优先级（从高到低）"""
    CLI_ARG = 1      # 命令行参数 --permission
    COMMAND = 2      # /permission 命令
    SESSION = 3      # Session级设置
    PROJECT = 4      # 项目.claude/settings.json
    USER = 5         # 用户全局settings
    POLICY = 6       # 企业policy设置
    LOCAL = 7        # 本地默认配置
    DEFAULT = 8      # 系统默认规则

class PermissionRule:
    """增强的权限规则"""
    
    pattern: str           # "Bash(git *)" 等
    action: str            # "allow", "deny", "ask"
    source: RuleSource     # 规则来源
    priority: int          # 优先级（source决定）
    reason: str | None     # 规则原因（用于审计）
    created_at: datetime   # 创建时间

class MultiSourceRuleManager:
    """多源规则管理器"""
    
    def __init__(self):
        self._rules_by_source: dict[RuleSource, list[PermissionRule]] = {}
    
    def add_rule(self, rule: PermissionRule):
        """添加规则到对应source"""
        if rule.source not in self._rules_by_source:
            self._rules_by_source[rule.source] = []
        self._rules_by_source[rule.source].append(rule)
    
    def get_effective_rules(self) -> list[PermissionRule]:
        """获取有效规则列表（按优先级排序）"""
        all_rules = []
        for source in RuleSource:
            if source in self._rules_by_source:
                all_rules.extend(self._rules_by_source[source])
        
        # 按priority排序，高优先级先匹配
        return sorted(all_rules, key=lambda r: r.priority)
    
    def merge_conflicts(self) -> list[PermissionRule]:
        """解决规则冲突（高优先级覆盖低优先级）"""
        effective = self.get_effective_rules()
        
        # 同一pattern只保留最高优先级的规则
        seen_patterns: dict[str, PermissionRule] = {}
        for rule in effective:
            if rule.pattern not in seen_patterns:
                seen_patterns[rule.pattern] = rule
            # 已存在 → 当前优先级更高才覆盖
        
        return list(seen_patterns.values())
```

### 3. Auto模式智能分类器

```python
class YoloClassifier:
    """Auto模式智能分类器（借鉴Claude Code）"""
    
    # 安全操作分类
    SAFE_COMMANDS = {
        "git status", "git log", "git diff", "git branch",
        "npm install", "npm run", "npm test",
        "ls", "cat", "head", "tail", "grep", "find",
        "python -m", "pytest", "uv run",
    }
    
    DANGEROUS_COMMANDS = {
        "rm -rf", "rm -rf /", "rm -rf ~",
        "sudo rm", "chmod 777",
        "curl | bash", "wget | bash",
        ":(){ :|:& };:",  # fork bomb
    }
    
    SENSITIVE_PATHS = {
        "~/.ssh", "~/.gnupg", "~/.password",
        "/etc/passwd", "/etc/shadow",
        ".env", "credentials", "secrets",
    }
    
    def classify(self, tool: str, params: dict) -> str:
        """
        分类工具调用
        
        Returns:
            "allow" - 安全操作，自动允许
            "deny"  - 危险操作，自动拒绝
            "ask"   - 需要用户确认
        """
        if tool == "Bash":
            return self._classify_bash(params.get("command", ""))
        
        if tool in ("Read", "Write", "Edit"):
            return self._classify_file_op(tool, params.get("file_path", ""))
        
        if tool == "Agent":
            return self._classify_agent(params)
        
        # 未知工具 → ask
        return "ask"
    
    def _classify_bash(self, command: str) -> str:
        """分类Bash命令"""
        # 检查危险命令
        for dangerous in self.DANGEROUS_COMMANDS:
            if dangerous in command:
                return "deny"
        
        # 检查安全命令
        command_base = command.split()[0] if command else ""
        for safe in self.SAFE_COMMANDS:
            if command.startswith(safe) or command_base == safe.split()[0]:
                return "allow"
        
        # 网络命令 → ask（可能风险）
        if any(cmd in command for cmd in ["curl", "wget", "ssh", "scp"]):
            return "ask"
        
        # 未知 → ask
        return "ask"
    
    def _classify_file_op(self, tool: str, path: str) -> str:
        """分类文件操作"""
        # 检查敏感路径
        for sensitive in self.SENSITIVE_PATHS:
            if sensitive in path:
                return "deny" if tool == "Read" else "ask"
        
        # Read安全路径 → allow
        if tool == "Read":
            if path.startswith("/tmp/") or path.startswith("./"):
                return "allow"
        
        # Write/Edit → 默认ask
        return "ask"
    
    def _classify_agent(self, params: dict) -> str:
        """分类Agent调用"""
        # Agent调用默认ask（需要用户确认子任务）
        return "ask"
```

### 4. MCP权限控制

```python
class MCPPermissionManager:
    """MCP工具权限管理"""
    
    def __init__(self):
        self._server_permissions: dict[str, str] = {}
        # server_permissions格式:
        # {"weather": "allow", "database": "ask", "admin": "deny"}
    
    def set_server_permission(self, server: str, action: str):
        """设置MCP server级别权限"""
        self._server_permissions[server] = action
    
    def check_mcp_tool(self, tool: str) -> str:
        """检查MCP工具权限"""
        # MCP工具名格式: mcp__server__tool
        parts = tool.split("__")
        if len(parts) < 2:
            return "ask"
        
        server = parts[1]
        return self._server_permissions.get(server, "ask")
```

### 5. 权限审计日志

```python
import logging
from dataclasses import dataclass
from datetime import datetime

@dataclass
class PermissionAuditLog:
    """权限决策审计记录"""
    
    timestamp: datetime
    tool: str
    params: dict
    action: str           # 最终决策
    matched_pattern: str | None  # 匹配的pattern
    matched_rule_source: str | None  # 规则来源
    classifier_result: str | None  # 分类器结果（auto模式）
    session_id: str
    user_id: str | None

class PermissionAuditor:
    """权限审计器"""
    
    def __init__(self):
        self._logger = logging.getLogger("permission_audit")
        self._logs: list[PermissionAuditLog] = []
    
    def record(self, log: PermissionAuditLog):
        """记录审计日志"""
        self._logs.append(log)
        
        # 写入文件
        self._logger.info(
            f"[{log.timestamp}] {log.tool} → {log.action} "
            f"(pattern={log.matched_pattern}, source={log.matched_rule_source})"
        )
    
    def get_logs(self, session_id: str | None = None) -> list[PermissionAuditLog]:
        """获取审计日志"""
        if session_id:
            return [l for l in self._logs if l.session_id == session_id]
        return self._logs
    
    def export_to_file(self, path: str):
        """导出审计日志到文件"""
        with open(path, "w") as f:
            for log in self._logs:
                f.write(json.dumps(asdict(log)) + "\n")
```

## Implementation Plan

### Phase 1: Pattern Matching
1. 创建 `PermissionPattern` 类 — sessions/permission_pattern.py
2. 实现 pattern 解析与匹配 — sessions/permission_pattern.py
3. 实现 `PermissionMatcher` — sessions/permission_pattern.py
4. 测试常见pattern

### Phase 2: 多源规则
1. 创建 `RuleSource` enum — sessions/permission_sources.py
2. 创建 `MultiSourceRuleManager` — sessions/permission_sources.py
3. 实现规则优先级与冲突解决
4. 集成到gateway初始化

### Phase 3: Auto分类器
1. 创建 `YoloClassifier` 类 — sessions/permission_classifier.py
2. 实现Bash命令分类 — sessions/permission_classifier.py
3. 实现文件操作分类 — sessions/permission_classifier.py
4. 实现敏感路径检测

### Phase 4: MCP权限
1. 创建 `MCPPermissionManager` — sessions/permission_mcp.py
2. 实现server级别权限控制
3. 集成到UnifiedToolRegistry

### Phase 5: 审计日志
1. 创建 `PermissionAuditor` — sessions/permission_audit.py
2. 实现审计记录与导出
3. 实现 `/permission-logs` API端点

## API Changes

### Permission命令扩展

```python
# /permission 命令格式扩展
/permission allow Bash(git *)
/permission deny Bash(rm -rf /*)
/permission ask Read(/etc/*)
/permission show               # 显示当前规则
/permission clear Bash         # 清除Bash相关规则
/permission export             # 导出规则到文件
```

### Permission API端点

```python
@app.get("/permission/rules")
async def get_permission_rules():
    """获取当前权限规则"""
    return {
        "rules": [asdict(r) for r in rule_manager.get_effective_rules()],
        "sources": {s.name: len(rule_manager._rules_by_source.get(s, [])) for s in RuleSource},
    }

@app.post("/permission/rules")
async def add_permission_rule(rule: PermissionRuleRequest):
    """添加权限规则"""
    rule_manager.add_rule(PermissionRule(
        pattern=rule.pattern,
        action=rule.action,
        source=RuleSource.COMMAND,
        reason=rule.reason,
    ))

@app.get("/permission/logs")
async def get_permission_logs(session_id: str | None = None):
    """获取权限审计日志"""
    return auditor.get_logs(session_id)
```

## Integration Points

### Gateway初始化

```python
# gateway.py lifespan()
async def lifespan(app: FastAPI):
    # 初始化权限系统
    state._rule_manager = MultiSourceRuleManager()
    state._classifier = YoloClassifier()
    state._auditor = PermissionAuditor()
    
    # 加载默认规则
    state._rule_manager.add_rule(PermissionRule(
        pattern="Bash(rm -rf /*)",
        action="deny",
        source=RuleSource.DEFAULT,
        reason="Dangerous: deletes entire filesystem",
    ))
    ...
    yield
```

### PermissionChecker增强

```python
# sessions/permission.py
class PermissionChecker:
    def __init__(
        self,
        rule_manager: MultiSourceRuleManager,
        classifier: YoloClassifier,
        auditor: PermissionAuditor,
        mode: str = "default",
    ):
        self._rule_manager = rule_manager
        self._classifier = classifier
        self._auditor = auditor
        self._mode = mode
    
    def check(self, tool: str, params: dict, session_id: str) -> str:
        """检查权限"""
        # 1. Pattern匹配
        action = self._rule_manager.get_matcher().match(tool, params)
        matched_pattern = action.pattern if action else None
        
        # 2. Auto模式分类器
        classifier_result = None
        if self._mode == "auto" and action is None:
            classifier_result = self._classifier.classify(tool, params)
            action = classifier_result
        
        # 3. 默认ask
        if action is None:
            action = "ask"
        
        # 4. 记录审计
        self._auditor.record(PermissionAuditLog(
            timestamp=datetime.now(),
            tool=tool,
            params=params,
            action=action,
            matched_pattern=matched_pattern,
            classifier_result=classifier_result,
            session_id=session_id,
        ))
        
        return action
```

## Success Criteria

- [ ] Pattern matching支持`Tool(path/cmd pattern)`格式
- [ ] 多源规则系统正确处理优先级
- [ ] Auto分类器准确判断安全/危险操作
- [ ] MCP权限按server级别控制
- [ ] 审计日志完整记录所有决策
- [ ] `/permission`命令支持pattern语法

## Default Rules示例

```python
DEFAULT_RULES = [
    # Bash规则
    PermissionRule("Bash(git *)", "allow", RuleSource.DEFAULT, "Git operations safe"),
    PermissionRule("Bash(npm *)", "allow", RuleSource.DEFAULT, "NPM operations safe"),
    PermissionRule("Bash(uv *)", "allow", RuleSource.DEFAULT, "UV operations safe"),
    PermissionRule("Bash(python *)", "allow", RuleSource.DEFAULT, "Python operations safe"),
    PermissionRule("Bash(rm -rf /*)", "deny", RuleSource.DEFAULT, "Dangerous: filesystem delete"),
    PermissionRule("Bash(rm -rf ~)", "deny", RuleSource.DEFAULT, "Dangerous: home delete"),
    PermissionRule("Bash(curl | *)", "ask", RuleSource.DEFAULT, "Potential security risk"),
    
    # File规则
    PermissionRule("Read(/tmp/*)", "allow", RuleSource.DEFAULT, "Temp files safe to read"),
    PermissionRule("Read(./*)", "allow", RuleSource.DEFAULT, "Project files safe to read"),
    PermissionRule("Read(~/.ssh/*)", "deny", RuleSource.DEFAULT, "SSH keys sensitive"),
    PermissionRule("Read(/etc/*)", "ask", RuleSource.DEFAULT, "System config sensitive"),
    PermissionRule("Write(./*)", "ask", RuleSource.DEFAULT, "Project writes need confirm"),
    
    # MCP规则
    PermissionRule("mcp__weather", "allow", RuleSource.DEFAULT, "Weather MCP safe"),
    PermissionRule("mcp__database", "ask", RuleSource.DEFAULT, "Database MCP needs confirm"),
]
```