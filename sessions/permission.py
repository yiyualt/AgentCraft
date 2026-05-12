"""Permission System - Tool execution control.

Controls which tools agents can execute through permission modes,
rule matching (AlwaysAllow/AlwaysDeny/AlwaysAsk), and deny tracking.
"""

from __future__ import annotations

import fnmatch
import json
import logging
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


# ============================================================
# Permission Rule
# ============================================================

@dataclass
class PermissionRule:
    kind: PermissionRuleKind
    tool_name: str | None = None
    command_pattern: str | None = None
    path_pattern: str | None = None

    def matches(self, tool_name: str, args: dict) -> bool:
        if self.tool_name:
            if not self._match_pattern(self.tool_name, tool_name):
                return False
        if self.command_pattern:
            if tool_name != "Bash":
                return False
            command = args.get("command", "")
            if not self._match_pattern(self.command_pattern, command):
                return False
        if self.path_pattern:
            if tool_name not in ("Read", "Write", "Edit"):
                return False
            path = args.get("file_path", args.get("path", ""))
            if not self._match_pattern(self.path_pattern, path):
                return False
        return True

    @staticmethod
    def _match_pattern(pattern: str, value: str) -> bool:
        return fnmatch.fnmatch(value.lower(), pattern.lower())


# ============================================================
# Permission Checker
# ============================================================

class PermissionChecker:
    """Checks tool permissions based on mode and rules."""

    def __init__(
        self,
        mode: PermissionMode = PermissionMode.DEFAULT,
        rules: list[PermissionRule] | None = None,
    ):
        self._mode = mode
        self._rules: list[PermissionRule] = list(rules or [])
        self._denied: dict[str, int] = {}  # key → deny count

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

    def check(self, tool_name: str, args: dict) -> PermissionResult:
        """Check if a tool call should be allowed."""
        # Bypass mode
        if self._mode == PermissionMode.BYPASS:
            return PermissionResult.ALLOW

        # Plan mode: deny execution tools
        if self._mode == PermissionMode.PLAN:
            if tool_name in ("Bash", "Write", "Edit", "Delete"):
                return PermissionResult.DENY
            return PermissionResult.ALLOW

        # Check rules
        for rule in self._rules:
            if rule.matches(tool_name, args):
                if rule.kind == PermissionRuleKind.ALWAYS_ALLOW:
                    return PermissionResult.ALLOW
                elif rule.kind == PermissionRuleKind.ALWAYS_DENY:
                    logger.info(f"[Permission] Denied by rule: {tool_name}")
                    return PermissionResult.DENY
                elif rule.kind == PermissionRuleKind.ALWAYS_ASK:
                    return PermissionResult.ASK

        # No matching rule → mode decides
        if self._mode == PermissionMode.ACCEPT_EDITS:
            if tool_name in ("Read", "Write", "Edit", "Glob", "Grep"):
                return PermissionResult.ALLOW

        if self._mode == PermissionMode.AUTO:
            if tool_name in ("Read", "Glob", "Grep", "WebFetch", "WebSearch"):
                return PermissionResult.ALLOW
            return PermissionResult.ASK

        # Default: ask
        return PermissionResult.ASK

    def record_denial(self, tool_name: str, args: dict) -> None:
        key = f"{tool_name}:{json.dumps(args, sort_keys=True)}"
        self._denied[key] = self._denied.get(key, 0) + 1

    def was_denied(self, tool_name: str, args: dict) -> bool:
        key = f"{tool_name}:{json.dumps(args, sort_keys=True)}"
        return self._denied.get(key, 0) > 0

    def get_deny_count(self, tool_name: str, args: dict) -> int:
        key = f"{tool_name}:{json.dumps(args, sort_keys=True)}"
        return self._denied.get(key, 0)


# ============================================================
# Default Rules
# ============================================================

DEFAULT_RULES: list[PermissionRule] = [
    # Always deny dangerous commands
    PermissionRule(kind=PermissionRuleKind.ALWAYS_DENY, tool_name="Bash", command_pattern="rm -rf *"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_DENY, tool_name="Bash", command_pattern="rm -rf /"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_DENY, tool_name="Bash", command_pattern="sudo *"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_DENY, tool_name="Bash", command_pattern="chmod 777 *"),

    # Always ask for sensitive paths
    PermissionRule(kind=PermissionRuleKind.ALWAYS_ASK, path_pattern="/etc/*"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_ASK, path_pattern="*.env"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_ASK, path_pattern="*credentials*"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_ASK, path_pattern="*.pem"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_ASK, path_pattern="*.key"),

    # Always allow safe reads
    PermissionRule(kind=PermissionRuleKind.ALWAYS_ALLOW, tool_name="Read", path_pattern="*.py"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_ALLOW, tool_name="Read", path_pattern="*.md"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_ALLOW, tool_name="Read", path_pattern="*.txt"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_ALLOW, tool_name="Read", path_pattern="*.json"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_ALLOW, tool_name="Read", path_pattern="*.yaml"),
    PermissionRule(kind=PermissionRuleKind.ALWAYS_ALLOW, tool_name="Read", path_pattern="*.yml"),
]


__all__ = [
    "PermissionMode",
    "PermissionRuleKind",
    "PermissionResult",
    "PermissionRule",
    "PermissionChecker",
    "DEFAULT_RULES",
]
