"""Enhanced Permission System - Pattern Matching & Smart Classification.

Controls which tools agents can execute through:
- Pattern matching: `Bash(git *)`, `Read(/tmp/*)`
- Multi-source rules with priority
- Auto mode smart classifier
- Audit logging
"""

from __future__ import annotations

import fnmatch
import json
import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger("gateway")


# ============================================================
# Enums
# ============================================================

class PermissionMode(Enum):
    DEFAULT = "default"           # Ask for each tool
    ACCEPT_EDITS = "acceptEdits"  # Auto-accept Read/Write/Edit
    BYPASS = "bypassPermissions"  # No checks (dangerous)
    AUTO = "auto"                 # Smart decisions
    PLAN = "plan"                 # Read-only, no execution


class PermissionRuleKind(Enum):
    ALWAYS_ALLOW = "AlwaysAllow"
    ALWAYS_DENY = "AlwaysDeny"
    ALWAYS_ASK = "AlwaysAsk"


class PermissionResult(Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


class RuleSource(Enum):
    """Rule source priority (higher number = lower priority)."""
    CLI_ARG = 1      # Command line argument
    COMMAND = 2      # /permission command
    SESSION = 3      # Session settings
    PROJECT = 4      # Project .claude/settings.json
    USER = 5         # User global settings
    POLICY = 6       # Enterprise policy
    LOCAL = 7        # Local config
    DEFAULT = 8      # System default rules


# ============================================================
# Permission Pattern
# ============================================================

class PermissionPattern:
    """Parse and match permission patterns.

    Pattern format: Tool(sub_pattern)
    Examples:
        Bash(git *)       → Match all git commands
        Read(/tmp/*)      → Match all files in /tmp
        Write(*.py)       → Match all .py files
        mcp__weather      → Match MCP server (no sub_pattern)
    """

    @staticmethod
    def parse(pattern: str) -> tuple[str, str | None]:
        """Parse pattern into tool name and sub_pattern.

        Args:
            pattern: Pattern string like "Bash(git *)"

        Returns:
            (tool_name, sub_pattern) tuple
        """
        # Match: ToolName or ToolName(sub_pattern)
        match = re.match(r'^(\w+)(?:\((.+)\))?$', pattern)
        if not match:
            raise ValueError(f"Invalid pattern: {pattern}")

        tool = match.group(1)
        sub_pattern = match.group(2)
        return tool, sub_pattern

    @staticmethod
    def matches(pattern: str, tool_name: str, args: dict) -> bool:
        """Check if pattern matches tool call.

        Args:
            pattern: Pattern to match
            tool_name: Tool being called
            args: Tool arguments

        Returns:
            True if pattern matches
        """
        parsed_tool, sub_pattern = PermissionPattern.parse(pattern)

        # Tool name must match
        if parsed_tool != tool_name:
            return False

        # No sub_pattern → tool-level match
        if sub_pattern is None:
            return True

        # Has sub_pattern → match specific argument
        if tool_name == "Bash":
            command = args.get("command", "")
            return fnmatch.fnmatch(command, sub_pattern)

        if tool_name in ("Read", "Write", "Edit"):
            path = args.get("file_path", args.get("path", ""))
            return fnmatch.fnmatch(path, sub_pattern)

        # MCP tools: server-level match
        if tool_name.startswith("mcp__"):
            parts = tool_name.split("__")
            if len(parts) >= 2:
                server = parts[1]
                return fnmatch.fnmatch(server, sub_pattern)

        return False


# ============================================================
# Enhanced Permission Rule
# ============================================================

@dataclass
class PermissionRule:
    """Permission rule with pattern support."""
    kind: PermissionRuleKind
    pattern: str | None = None           # New: "Bash(git *)" format
    tool_name: str | None = None         # Legacy: tool name only
    command_pattern: str | None = None   # Legacy: command pattern
    path_pattern: str | None = None      # Legacy: path pattern
    source: RuleSource = RuleSource.DEFAULT
    reason: str | None = None
    created_at: float = field(default_factory=time.time)

    def __post_init__(self):
        """Normalize rule representation."""
        # If pattern provided, parse it
        if self.pattern:
            tool, sub = PermissionPattern.parse(self.pattern)
            self.tool_name = tool
            if tool == "Bash" and sub:
                self.command_pattern = sub
            elif tool in ("Read", "Write", "Edit") and sub:
                self.path_pattern = sub

    def matches(self, tool_name: str, args: dict) -> bool:
        """Check if rule matches tool call."""
        # Use pattern if available
        if self.pattern:
            return PermissionPattern.matches(self.pattern, tool_name, args)

        # Legacy matching
        if self.tool_name:
            if not self._match_value(self.tool_name, tool_name):
                return False
        if self.command_pattern:
            if tool_name != "Bash":
                return False
            command = args.get("command", "")
            if not self._match_value(self.command_pattern, command):
                return False
        if self.path_pattern:
            if tool_name not in ("Read", "Write", "Edit"):
                return False
            path = args.get("file_path", args.get("path", ""))
            if not self._match_value(self.path_pattern, path):
                return False
        return True

    @staticmethod
    def _match_value(pattern: str, value: str) -> bool:
        return fnmatch.fnmatch(value.lower(), pattern.lower())

    def to_dict(self) -> dict:
        return {
            "kind": self.kind.value,
            "pattern": self.pattern,
            "source": self.source.name,
            "reason": self.reason,
        }


# ============================================================
# Auto Mode Classifier (YoloClassifier)
# ============================================================

class YoloClassifier:
    """Smart classifier for AUTO mode.

    Classifies tool calls as allow/deny/ask based on
    safety heuristics, inspired by Claude Code.
    """

    # Safe operations
    SAFE_COMMANDS = {
        "git status", "git log", "git diff", "git branch", "git show",
        "npm install", "npm run", "npm test", "npm build",
        "ls", "cat", "head", "tail", "grep", "find", "which",
        "python -m", "pytest", "uv run", "uv pip",
        "echo", "pwd", "date", "whoami",
    }

    # Dangerous operations
    DANGEROUS_COMMANDS = {
        "rm -rf /", "rm -rf /*", "rm -rf ~", "rm -rf ~/",
        "sudo rm", "sudo rm -rf",
        "chmod 777", "chmod -R 777",
        "curl | bash", "wget | bash", "curl | sh",
        ":(){ :|:& };:",  # fork bomb
        "mkfs", "fdisk", "dd if=",
    }

    # Sensitive paths
    SENSITIVE_PATHS = {
        "~/.ssh", "~/.gnupg", "~/.password", "~/.aws",
        "/etc/passwd", "/etc/shadow", "/etc/ssh",
        ".env", ".env.local", ".env.production",
        "credentials", "secrets", "private",
        "*.pem", "*.key", "*.ssh",
    }

    def classify(self, tool_name: str, args: dict) -> PermissionResult:
        """Classify tool call.

        Returns:
            ALLOW - Safe operation
            DENY  - Dangerous operation
            ASK   - Needs user confirmation
        """
        if tool_name == "Bash":
            return self._classify_bash(args.get("command", ""))

        if tool_name in ("Read", "Write", "Edit"):
            path = args.get("file_path", args.get("path", ""))
            return self._classify_file_op(tool_name, path)

        if tool_name == "Agent":
            return PermissionResult.ASK  # Always ask for sub-agents

        # Read-only tools → allow in auto mode
        if tool_name in ("Glob", "Grep", "WebFetch", "WebSearch", "NotebookEdit"):
            return PermissionResult.ALLOW

        # Unknown → ask
        return PermissionResult.ASK

    def _classify_bash(self, command: str) -> PermissionResult:
        """Classify Bash command."""
        if not command:
            return PermissionResult.ASK

        # Check dangerous commands
        for dangerous in self.DANGEROUS_COMMANDS:
            if dangerous in command:
                return PermissionResult.DENY

        # Check safe commands
        command_lower = command.lower().strip()
        for safe in self.SAFE_COMMANDS:
            if command_lower.startswith(safe.lower()):
                return PermissionResult.ALLOW

        # Network commands → ask
        if any(cmd in command_lower for cmd in ["curl", "wget", "ssh", "scp", "rsync"]):
            return PermissionResult.ASK

        # Package install → allow
        if any(cmd in command_lower for cmd in ["install", "add", "pip install", "uv add"]):
            return PermissionResult.ALLOW

        # Deletion commands → ask
        if "rm" in command_lower:
            return PermissionResult.ASK

        # Unknown → ask
        return PermissionResult.ASK

    def _classify_file_op(self, tool_name: str, path: str) -> PermissionResult:
        """Classify file operation."""
        if not path:
            return PermissionResult.ASK

        path_lower = path.lower()

        # Check sensitive paths
        for sensitive in self.SENSITIVE_PATHS:
            if sensitive.lower() in path_lower or fnmatch.fnmatch(path_lower, sensitive.lower()):
                if tool_name == "Read":
                    return PermissionResult.ASK  # Ask for reading sensitive
                return PermissionResult.DENY  # Deny writing sensitive

        # Read safe paths → allow
        if tool_name == "Read":
            # Project files and temp files
            if path.startswith("./") or path.startswith("/tmp/") or path.startswith("~/"):
                return PermissionResult.ALLOW
            # Common safe extensions
            safe_extensions = {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".ini"}
            if any(path_lower.endswith(ext) for ext in safe_extensions):
                return PermissionResult.ALLOW
            return PermissionResult.ASK

        # Write/Edit → ask by default
        return PermissionResult.ASK


# ============================================================
# Permission Audit Log
# ============================================================

@dataclass
class PermissionAuditLog:
    """Audit record for permission decision."""
    timestamp: float
    tool_name: str
    args: dict
    result: PermissionResult
    matched_pattern: str | None = None
    matched_rule_source: str | None = None
    classifier_result: PermissionResult | None = None
    session_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "tool": self.tool_name,
            "args_summary": {k: str(v)[:50] for k, v in self.args.items()},
            "result": self.result.value,
            "matched_pattern": self.matched_pattern,
            "matched_rule_source": self.matched_rule_source,
            "classifier_result": self.classifier_result.value if self.classifier_result else None,
            "session_id": self.session_id,
        }


class PermissionAuditor:
    """Record permission decisions for audit."""

    def __init__(self, max_logs: int = 1000):
        self._logs: list[PermissionAuditLog] = []
        self._max_logs = max_logs

    def record(self, log: PermissionAuditLog) -> None:
        """Record audit log."""
        self._logs.append(log)

        # Trim if too many
        if len(self._logs) > self._max_logs:
            self._logs = self._logs[-self._max_logs:]

        logger.info(
            f"[AUDIT] {log.tool_name} → {log.result.value} "
            f"(pattern={log.matched_pattern}, source={log.matched_rule_source})"
        )

    def get_logs(self, session_id: str | None = None) -> list[dict]:
        """Get audit logs."""
        if session_id:
            return [l.to_dict() for l in self._logs if l.session_id == session_id]
        return [l.to_dict() for l in self._logs]

    def clear(self) -> None:
        """Clear all logs."""
        self._logs.clear()


# ============================================================
# Enhanced Permission Checker
# ============================================================

class PermissionChecker:
    """Enhanced permission checker with pattern matching and classifier."""

    def __init__(
        self,
        mode: PermissionMode = PermissionMode.DEFAULT,
        rules: list[PermissionRule] | None = None,
        classifier: YoloClassifier | None = None,
        auditor: PermissionAuditor | None = None,
    ):
        self._mode = mode
        self._rules: list[PermissionRule] = list(rules or [])
        self._classifier = classifier or YoloClassifier()
        self._auditor = auditor or PermissionAuditor()
        self._denied: dict[str, int] = {}

    @property
    def mode(self) -> PermissionMode:
        return self._mode

    @mode.setter
    def mode(self, value: PermissionMode) -> None:
        self._mode = value

    def set_rules(self, rules: list[PermissionRule]) -> None:
        self._rules = list(rules)

    def add_rule(self, rule: PermissionRule) -> None:
        self._rules.append(rule)

    def get_rules(self) -> list[PermissionRule]:
        return self._rules.copy()

    def check(
        self,
        tool_name: str,
        args: dict,
        session_id: str | None = None,
    ) -> PermissionResult:
        """Check if a tool call should be allowed."""
        # Bypass mode
        if self._mode == PermissionMode.BYPASS:
            self._record_audit(tool_name, args, PermissionResult.ALLOW, session_id)
            return PermissionResult.ALLOW

        # Plan mode: deny execution tools
        if self._mode == PermissionMode.PLAN:
            if tool_name in ("Bash", "Write", "Edit"):
                result = PermissionResult.DENY
                self._record_audit(tool_name, args, result, session_id, reason="plan_mode")
                return result
            result = PermissionResult.ALLOW
            self._record_audit(tool_name, args, result, session_id, reason="plan_mode_read")
            return result

        # Sort rules by source priority (lower number = higher priority)
        sorted_rules = sorted(self._rules, key=lambda r: r.source.value)

        # Check rules
        matched_pattern = None
        matched_source = None
        for rule in sorted_rules:
            if rule.matches(tool_name, args):
                matched_pattern = rule.pattern or f"{rule.tool_name}"
                matched_source = rule.source.name
                if rule.kind == PermissionRuleKind.ALWAYS_ALLOW:
                    self._record_audit(tool_name, args, PermissionResult.ALLOW, session_id,
                                       matched_pattern, matched_source)
                    return PermissionResult.ALLOW
                elif rule.kind == PermissionRuleKind.ALWAYS_DENY:
                    logger.info(f"[Permission] Denied by rule: {tool_name}")
                    self._record_audit(tool_name, args, PermissionResult.DENY, session_id,
                                       matched_pattern, matched_source)
                    return PermissionResult.DENY
                elif rule.kind == PermissionRuleKind.ALWAYS_ASK:
                    self._record_audit(tool_name, args, PermissionResult.ASK, session_id,
                                       matched_pattern, matched_source)
                    return PermissionResult.ASK

        # No matching rule → mode decides
        result = PermissionResult.ASK
        classifier_result = None

        if self._mode == PermissionMode.ACCEPT_EDITS:
            if tool_name in ("Read", "Write", "Edit", "Glob", "Grep"):
                result = PermissionResult.ALLOW

        elif self._mode == PermissionMode.AUTO:
            # Use classifier
            classifier_result = self._classifier.classify(tool_name, args)
            result = classifier_result

        elif self._mode == PermissionMode.DEFAULT:
            # Default: ask for all
            result = PermissionResult.ASK

        self._record_audit(tool_name, args, result, session_id,
                           matched_pattern, matched_source, classifier_result)
        return result

    def _record_audit(
        self,
        tool_name: str,
        args: dict,
        result: PermissionResult,
        session_id: str | None,
        matched_pattern: str | None = None,
        matched_source: str | None = None,
        classifier_result: PermissionResult | None = None,
        reason: str | None = None,
    ) -> None:
        """Record audit log."""
        log = PermissionAuditLog(
            timestamp=time.time(),
            tool_name=tool_name,
            args=args,
            result=result,
            matched_pattern=matched_pattern,
            matched_rule_source=matched_source,
            classifier_result=classifier_result,
            session_id=session_id,
        )
        self._auditor.record(log)

    def get_audit_logs(self, session_id: str | None = None) -> list[dict]:
        """Get audit logs."""
        return self._auditor.get_logs(session_id)

    def record_denial(self, tool_name: str, args: dict) -> None:
        key = f"{tool_name}:{json.dumps(args, sort_keys=True)}"
        self._denied[key] = self._denied.get(key, 0) + 1

    def was_denied(self, tool_name: str, args: dict) -> bool:
        key = f"{tool_name}:{json.dumps(args, sort_keys=True)}"
        return self._denied.get(key, 0) > 0


# ============================================================
# Default Rules (Enhanced)
# ============================================================

DEFAULT_RULES: list[PermissionRule] = [
    # Bash - deny dangerous
    PermissionRule(kind=PermissionRuleKind.ALWAYS_DENY, pattern="Bash(rm -rf /)"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_DENY, pattern="Bash(rm -rf /*)"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_DENY, pattern="Bash(rm -rf ~)"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_DENY, pattern="Bash(sudo rm *)"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_DENY, pattern="Bash(chmod 777 *)"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_DENY, pattern="Bash(curl | bash)"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_DENY, pattern="Bash(wget | bash)"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_DENY, pattern="Bash(mkfs *)"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_DENY, pattern="Bash(dd if=*)"),

    # Bash - allow safe
    PermissionRule(kind=PermissionRuleKind.ALWAYS_ALLOW, pattern="Bash(git *)"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_ALLOW, pattern="Bash(npm *)"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_ALLOW, pattern="Bash(uv *)"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_ALLOW, pattern="Bash(python *)"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_ALLOW, pattern="Bash(pytest *)"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_ALLOW, pattern="Bash(ls *)"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_ALLOW, pattern="Bash(cat *)"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_ALLOW, pattern="Bash(grep *)"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_ALLOW, pattern="Bash(find *)"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_ALLOW, pattern="Bash(echo *)"),

    # Bash - ask for network
    PermissionRule(kind=PermissionRuleKind.ALWAYS_ASK, pattern="Bash(curl *)"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_ASK, pattern="Bash(wget *)"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_ASK, pattern="Bash(ssh *)"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_ASK, pattern="Bash(rm *)"),

    # File - deny sensitive
    PermissionRule(kind=PermissionRuleKind.ALWAYS_DENY, pattern="Read(~/.ssh/*)"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_DENY, pattern="Write(~/.ssh/*)"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_DENY, pattern="Edit(~/.ssh/*)"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_DENY, pattern="Read(/etc/shadow)"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_DENY, pattern="Write(/etc/shadow)"),

    # File - ask for sensitive
    PermissionRule(kind=PermissionRuleKind.ALWAYS_ASK, pattern="Read(*.pem)"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_ASK, pattern="Read(*.key)"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_ASK, pattern="Read(*.env)"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_ASK, pattern="Read(*credentials*)"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_ASK, pattern="Read(/etc/*)"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_ASK, pattern="Write(*.env)"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_ASK, pattern="Write(*credentials*)"),

    # File - allow safe
    PermissionRule(kind=PermissionRuleKind.ALWAYS_ALLOW, pattern="Read(/tmp/*)"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_ALLOW, pattern="Read(*.py)"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_ALLOW, pattern="Read(*.md)"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_ALLOW, pattern="Read(*.txt)"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_ALLOW, pattern="Read(*.json)"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_ALLOW, pattern="Read(*.yaml)"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_ALLOW, pattern="Read(*.yml)"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_ALLOW, pattern="Read(*.toml)"),

    # MCP - default ask (user can configure)
    # These are added dynamically based on MCP servers
]


# ============================================================
# Multi-Source Rule Manager
# ============================================================

class MultiSourceRuleManager:
    """Manage rules from multiple sources with priority."""

    def __init__(self):
        self._rules_by_source: dict[RuleSource, list[PermissionRule]] = {}
        # Initialize with default rules
        self._rules_by_source[RuleSource.DEFAULT] = list(DEFAULT_RULES)

    def add_rule(self, rule: PermissionRule) -> None:
        """Add rule to its source bucket."""
        source = rule.source
        if source not in self._rules_by_source:
            self._rules_by_source[source] = []
        self._rules_by_source[source].append(rule)

    def get_effective_rules(self) -> list[PermissionRule]:
        """Get all rules sorted by priority."""
        all_rules = []
        for source in RuleSource:
            if source in self._rules_by_source:
                all_rules.extend(self._rules_by_source[source])
        # Sort by source value (lower = higher priority)
        return sorted(all_rules, key=lambda r: r.source.value)

    def clear_source(self, source: RuleSource) -> None:
        """Clear rules from a specific source."""
        if source != RuleSource.DEFAULT:  # Don't clear defaults
            self._rules_by_source[source] = []

    def get_source_stats(self) -> dict[str, int]:
        """Get count of rules per source."""
        return {s.name: len(self._rules_by_source.get(s, [])) for s in RuleSource}


__all__ = [
    "PermissionMode",
    "PermissionRuleKind",
    "PermissionResult",
    "PermissionRule",
    "PermissionChecker",
    "PermissionPattern",
    "PermissionAuditLog",
    "PermissionAuditor",
    "YoloClassifier",
    "RuleSource",
    "MultiSourceRuleManager",
    "DEFAULT_RULES",
]