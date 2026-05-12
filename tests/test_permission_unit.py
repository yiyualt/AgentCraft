#!/usr/bin/env python3
"""Unit tests for Permission system."""

import pytest
from sessions.permission import (
    PermissionMode,
    PermissionRuleKind,
    PermissionResult,
    PermissionRule,
    PermissionChecker,
    DEFAULT_RULES,
)


# ============================================================
# PermissionRule
# ============================================================

class TestPermissionRule:
    def test_name_match(self):
        rule = PermissionRule(kind=PermissionRuleKind.ALWAYS_DENY, tool_name="Bash")
        assert rule.matches("Bash", {})
        assert not rule.matches("Read", {})

    def test_command_pattern_match(self):
        rule = PermissionRule(
            kind=PermissionRuleKind.ALWAYS_DENY,
            tool_name="Bash",
            command_pattern="rm *",
        )
        assert rule.matches("Bash", {"command": "rm -rf /tmp/test"})
        assert not rule.matches("Bash", {"command": "ls -la"})
        assert not rule.matches("Read", {"command": "rm something"})

    def test_path_pattern_match(self):
        rule = PermissionRule(
            kind=PermissionRuleKind.ALWAYS_ASK,
            path_pattern="/etc/*",
        )
        assert rule.matches("Read", {"file_path": "/etc/hosts"})
        assert not rule.matches("Read", {"file_path": "/tmp/hosts"})
        # Only applies to Read/Write/Edit tools
        assert not rule.matches("Bash", {"file_path": "/etc/hosts"})

    def test_wildcard_pattern(self):
        rule = PermissionRule(kind=PermissionRuleKind.ALWAYS_ALLOW, tool_name="*")
        assert rule.matches("Bash", {})
        assert rule.matches("Read", {})
        assert rule.matches("Write", {})

    def test_path_with_wildcard(self):
        rule = PermissionRule(kind=PermissionRuleKind.ALWAYS_ASK, path_pattern="*.env")
        assert rule.matches("Read", {"file_path": ".env"})
        assert rule.matches("Read", {"file_path": "config/.env"})
        assert rule.matches("Write", {"file_path": "prod.env"})
        assert not rule.matches("Read", {"file_path": "config.json"})

    def test_combined_matchers(self):
        rule = PermissionRule(
            kind=PermissionRuleKind.ALWAYS_DENY,
            tool_name="Bash",
            command_pattern="sudo *",
        )
        assert rule.matches("Bash", {"command": "sudo rm -rf /"})
        assert not rule.matches("Bash", {"command": "ls -la"})  # Wrong command
        assert not rule.matches("Read", {"command": "sudo rm -rf /"})  # Wrong tool

    def test_empty_rule_matches_anything(self):
        rule = PermissionRule(kind=PermissionRuleKind.ALWAYS_ALLOW)
        assert rule.matches("Bash", {"command": "rm -rf /"})
        assert rule.matches("Read", {})
        assert rule.matches("Write", {})


# ============================================================
# PermissionChecker — Modes
# ============================================================

class TestPermissionCheckerBypass:
    def test_bypass_allows_all(self):
        checker = PermissionChecker(mode=PermissionMode.BYPASS)
        assert checker.check("Bash", {"command": "rm -rf /"}) == PermissionResult.ALLOW
        assert checker.check("Read", {"file_path": "/etc/shadow"}) == PermissionResult.ALLOW
        assert checker.check("UnknownTool", {}) == PermissionResult.ALLOW


class TestPermissionCheckerPlan:
    def test_plan_denies_execution_tools(self):
        checker = PermissionChecker(mode=PermissionMode.PLAN)
        assert checker.check("Bash", {"command": "ls"}) == PermissionResult.DENY
        assert checker.check("Write", {"file_path": "test.txt"}) == PermissionResult.DENY
        assert checker.check("Edit", {"file_path": "test.txt"}) == PermissionResult.DENY

    def test_plan_allows_readonly(self):
        checker = PermissionChecker(mode=PermissionMode.PLAN)
        assert checker.check("Read", {"file_path": "test.txt"}) == PermissionResult.ALLOW
        assert checker.check("Grep", {"pattern": "foo"}) == PermissionResult.ALLOW
        assert checker.check("Glob", {"pattern": "*.py"}) == PermissionResult.ALLOW


class TestPermissionCheckerAcceptEdits:
    def test_accept_edits_allows_editing_tools(self):
        checker = PermissionChecker(mode=PermissionMode.ACCEPT_EDITS)
        assert checker.check("Read", {"file_path": "x"}) == PermissionResult.ALLOW
        assert checker.check("Write", {"file_path": "x"}) == PermissionResult.ALLOW
        assert checker.check("Edit", {"file_path": "x"}) == PermissionResult.ALLOW
        assert checker.check("Glob", {"pattern": "*"}) == PermissionResult.ALLOW
        assert checker.check("Grep", {"pattern": "x"}) == PermissionResult.ALLOW

    def test_accept_edits_asks_for_other_tools(self):
        checker = PermissionChecker(mode=PermissionMode.ACCEPT_EDITS, rules=[])
        assert checker.check("Bash", {"command": "ls"}) == PermissionResult.ASK


class TestPermissionCheckerAuto:
    def test_auto_allows_safe_reads(self):
        checker = PermissionChecker(mode=PermissionMode.AUTO, rules=[])
        assert checker.check("Read", {"file_path": "x"}) == PermissionResult.ALLOW
        assert checker.check("Glob", {"pattern": "*"}) == PermissionResult.ALLOW
        assert checker.check("Grep", {"pattern": "x"}) == PermissionResult.ALLOW
        assert checker.check("WebFetch", {"url": "http://example.com"}) == PermissionResult.ALLOW
        assert checker.check("WebSearch", {"query": "test"}) == PermissionResult.ALLOW

    def test_auto_asks_for_write(self):
        checker = PermissionChecker(mode=PermissionMode.AUTO, rules=[])
        assert checker.check("Write", {"file_path": "x"}) == PermissionResult.ASK
        assert checker.check("Bash", {"command": "ls"}) == PermissionResult.ASK


class TestPermissionCheckerDefault:
    def test_default_asks_by_default(self):
        checker = PermissionChecker(mode=PermissionMode.DEFAULT, rules=[])
        assert checker.check("Read", {"file_path": "x"}) == PermissionResult.ASK
        assert checker.check("Bash", {"command": "ls"}) == PermissionResult.ASK


# ============================================================
# PermissionChecker — Rules
# ============================================================

class TestPermissionCheckerRules:
    def test_always_allow_rule_takes_priority(self):
        checker = PermissionChecker(
            mode=PermissionMode.DEFAULT,
            rules=[
                PermissionRule(kind=PermissionRuleKind.ALWAYS_ALLOW, tool_name="Read"),
            ],
        )
        assert checker.check("Read", {"file_path": "x"}) == PermissionResult.ALLOW
        assert checker.check("Bash", {"command": "x"}) == PermissionResult.ASK

    def test_always_deny_rule_blocks(self):
        checker = PermissionChecker(
            mode=PermissionMode.ACCEPT_EDITS,
            rules=[
                PermissionRule(kind=PermissionRuleKind.ALWAYS_DENY, tool_name="Bash", command_pattern="rm *"),
            ],
        )
        assert checker.check("Bash", {"command": "rm file.txt"}) == PermissionResult.DENY
        # In acceptEdits mode, Bash (without a dangerous command) is still asked
        assert checker.check("Bash", {"command": "ls"}) == PermissionResult.ASK

    def test_always_ask_rule(self):
        checker = PermissionChecker(
            mode=PermissionMode.DEFAULT,
            rules=[
                PermissionRule(kind=PermissionRuleKind.ALWAYS_ASK, path_pattern="*.env"),
            ],
        )
        assert checker.check("Read", {"file_path": ".env"}) == PermissionResult.ASK

    def test_first_matching_rule_wins(self):
        checker = PermissionChecker(
            mode=PermissionMode.DEFAULT,
            rules=[
                PermissionRule(kind=PermissionRuleKind.ALWAYS_ALLOW, tool_name="Bash"),
                PermissionRule(kind=PermissionRuleKind.ALWAYS_DENY, tool_name="Bash"),
            ],
        )
        assert checker.check("Bash", {"command": "ls"}) == PermissionResult.ALLOW


# ============================================================
# PermissionChecker — Deny Tracking
# ============================================================

class TestPermissionCheckerDenyTracking:
    def test_record_denial(self):
        checker = PermissionChecker()
        assert not checker.was_denied("Bash", {"command": "rm -rf"})
        checker.record_denial("Bash", {"command": "rm -rf"})
        assert checker.was_denied("Bash", {"command": "rm -rf"})

    def test_deny_count(self):
        checker = PermissionChecker()
        assert checker.get_deny_count("Bash", {"cmd": "x"}) == 0
        checker.record_denial("Bash", {"cmd": "x"})
        checker.record_denial("Bash", {"cmd": "x"})
        assert checker.get_deny_count("Bash", {"cmd": "x"}) == 2

    def test_different_args_tracked_separately(self):
        checker = PermissionChecker()
        checker.record_denial("Bash", {"command": "rm a"})
        checker.record_denial("Bash", {"command": "ls"})
        assert checker.get_deny_count("Bash", {"command": "rm a"}) == 1
        assert checker.get_deny_count("Bash", {"command": "ls"}) == 1


# ============================================================
# PermissionChecker — Config
# ============================================================

class TestPermissionCheckerConfig:
    def test_mode_switch(self):
        checker = PermissionChecker(mode=PermissionMode.DEFAULT)
        assert checker.mode == PermissionMode.DEFAULT
        checker.mode = PermissionMode.BYPASS
        assert checker.mode == PermissionMode.BYPASS
        assert checker.check("Bash", {"command": "rm -rf /"}) == PermissionResult.ALLOW

    def test_set_rules_replaces(self):
        checker = PermissionChecker(rules=DEFAULT_RULES)
        assert len(checker._rules) > 5
        checker.set_rules([])
        assert len(checker._rules) == 0

    def test_add_rule(self):
        checker = PermissionChecker(rules=[])
        checker.add_rule(PermissionRule(kind=PermissionRuleKind.ALWAYS_DENY, tool_name="Bash"))
        assert len(checker._rules) == 1


# ============================================================
# Default Rules
# ============================================================

class TestDefaultRules:
    def test_default_rules_not_empty(self):
        assert len(DEFAULT_RULES) > 0

    def test_default_rules_block_dangerous_commands(self):
        checker = PermissionChecker(mode=PermissionMode.DEFAULT, rules=list(DEFAULT_RULES))
        # The default rules should block rm -rf * and sudo *
        assert checker.check("Bash", {"command": "rm -rf /tmp/something"}) == PermissionResult.DENY
        assert checker.check("Bash", {"command": "rm -rf /"}) == PermissionResult.DENY
        assert checker.check("Bash", {"command": "sudo rm file"}) == PermissionResult.DENY
        # Safe commands should pass through
        assert checker.check("Bash", {"command": "ls -la"}) == PermissionResult.ASK

    def test_default_rules_ask_for_sensitive_files(self):
        sensitive_rules = [
            r for r in DEFAULT_RULES
            if r.kind == PermissionRuleKind.ALWAYS_ASK and r.path_pattern
        ]
        assert len(sensitive_rules) >= 4  # /etc/*, *.env, *credentials*, *.pem, *.key
