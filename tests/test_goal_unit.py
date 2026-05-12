#!/usr/bin/env python3
"""Unit tests for Goal Command system."""

import os
import tempfile
import pytest
from sessions.goal import GoalState, GoalManager, check_stop_goal


# ============================================================
# GoalState
# ============================================================

class TestGoalState:
    def test_defaults(self):
        g = GoalState(condition="tests pass")
        assert g.condition == "tests pass"
        assert g.check_count == 0
        assert g.met is False
        assert g.created_at > 0


# ============================================================
# GoalManager
# ============================================================

class TestGoalManager:
    def test_set_goal(self):
        mgr = GoalManager()
        result = mgr.set_goal("tests pass")
        assert "Goal set" in result
        assert mgr.has_goal()
        assert mgr.get_goal().condition == "tests pass"

    def test_clear_goal(self):
        mgr = GoalManager()
        mgr.set_goal("tests pass")
        result = mgr.clear_goal()
        assert "Goal cleared" in result
        assert not mgr.has_goal()

    def test_clear_no_goal(self):
        mgr = GoalManager()
        result = mgr.clear_goal()
        assert "No goal was set" in result

    def test_has_goal_false_initially(self):
        mgr = GoalManager()
        assert not mgr.has_goal()

    def test_get_goal_none_initially(self):
        mgr = GoalManager()
        assert mgr.get_goal() is None

    def test_check_goal_met_true_when_no_goal(self):
        mgr = GoalManager()
        is_met, feedback = mgr.check_goal({})
        assert is_met is True
        assert feedback == ""


class TestGoalCheckTestsPass:
    def test_tests_pass_detected_in_tool_results(self):
        mgr = GoalManager()
        mgr.set_goal("tests pass")
        context = {
            "tool_results": [
                {"tool": "Bash", "output": "pytest: 10 passed, 0 failed in 2.3s"},
            ],
            "messages": [],
        }
        is_met, feedback = mgr.check_goal(context)
        assert is_met is True
        assert "Goal achieved" in feedback

    def test_tests_fail_not_met(self):
        mgr = GoalManager()
        mgr.set_goal("tests pass")
        context = {
            "tool_results": [
                {"tool": "Bash", "output": "pytest: 8 passed, 2 failed in 3.1s"},
            ],
            "messages": [],
        }
        is_met, feedback = mgr.check_goal(context)
        assert is_met is False
        assert "Goal not yet met" in feedback

    def test_0_failed_in_output(self):
        mgr = GoalManager()
        mgr.set_goal("tests pass")
        context = {
            "tool_results": [
                {"tool": "Bash", "output": "pytest results: 0 failed"},
            ],
            "messages": [],
        }
        is_met, feedback = mgr.check_goal(context)
        assert is_met is True

    def test_tests_pass_in_messages(self):
        mgr = GoalManager()
        mgr.set_goal("tests pass")
        context = {
            "tool_results": [],
            "messages": [
                {"role": "assistant", "content": "All tests passed with 0 failed!"},
            ],
        }
        is_met, feedback = mgr.check_goal(context)
        assert is_met is True


class TestGoalCheckFileExists:
    def test_file_exists(self):
        mgr = GoalManager()
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test")
            path = f.name

        try:
            mgr.set_goal(f"file '{path}' exists")
            is_met, feedback = mgr.check_goal({})
            assert is_met is True
        finally:
            os.unlink(path)

    def test_file_does_not_exist(self):
        mgr = GoalManager()
        mgr.set_goal("file '/nonexistent/path' exists")
        is_met, feedback = mgr.check_goal({})
        assert is_met is False


class TestGoalCheckNoErrors:
    def test_no_errors(self):
        mgr = GoalManager()
        mgr.set_goal("no errors")
        context = {
            "tool_results": [
                {"tool": "Bash", "output": "Everything went fine"},
                {"tool": "Write", "output": "File written successfully"},
            ],
        }
        is_met, feedback = mgr.check_goal(context)
        assert is_met is True

    def test_errors_found(self):
        mgr = GoalManager()
        mgr.set_goal("no errors")
        context = {
            "tool_results": [
                {"tool": "Bash", "output": "Error: file not found\nException occurred"},
            ],
        }
        is_met, feedback = mgr.check_goal(context)
        assert is_met is False


class TestGoalCheckMessages:
    def test_keyword_match_in_messages(self):
        mgr = GoalManager()
        mgr.set_goal("deploy completed")
        context = {
            "tool_results": [],
            "messages": [
                {"role": "assistant", "content": "The deploy completed successfully. We are done!"},
            ],
        }
        is_met, feedback = mgr.check_goal(context)
        assert is_met is True

    def test_keyword_not_found(self):
        mgr = GoalManager()
        mgr.set_goal("deploy completed")
        context = {
            "tool_results": [],
            "messages": [
                {"role": "assistant", "content": "Still working on the deployment..."},
            ],
        }
        is_met, feedback = mgr.check_goal(context)
        assert is_met is False


class TestGoalAutoClear:
    def test_goal_auto_clears_when_met(self):
        mgr = GoalManager()
        mgr.set_goal("tests pass")
        assert mgr.has_goal()
        context = {
            "tool_results": [{"tool": "Bash", "output": "pytest: 0 failed"}],
            "messages": [],
        }
        is_met, feedback = mgr.check_goal(context)
        assert is_met is True
        assert not mgr.has_goal()  # Auto-cleared

    def test_goal_persists_when_not_met(self):
        mgr = GoalManager()
        mgr.set_goal("tests pass")
        context = {
            "tool_results": [{"tool": "Bash", "output": "pytest: 2 failed"}],
            "messages": [],
        }
        mgr.check_goal(context)
        assert mgr.has_goal()  # Still active


class TestGoalCheckCounter:
    def test_max_checks_limit(self):
        mgr = GoalManager(max_checks=2)
        mgr.set_goal("tests pass")
        context = {"tool_results": [], "messages": []}
        mgr.check_goal(context)  # Check 1
        mgr.check_goal(context)  # Check 2
        is_met, feedback = mgr.check_goal(context)  # Check 3 (exceeds)
        assert is_met is True  # Forces clear
        assert "limit" in feedback.lower()
        assert not mgr.has_goal()


class TestGoalFeedback:
    def test_suggestions_for_tests(self):
        mgr = GoalManager()
        mgr.set_goal("tests pass")
        context = {
            "tool_results": [{"tool": "Bash", "output": "2 failed"}],
            "messages": [],
        }
        is_met, feedback = mgr.check_goal(context)
        assert "Run the tests" in feedback

    def test_suggestions_for_file(self):
        mgr = GoalManager()
        mgr.set_goal("file config.json exists")
        context = {}
        is_met, feedback = mgr.check_goal(context)
        assert "Create the file" in feedback

    def test_suggestions_for_no_errors(self):
        mgr = GoalManager()
        mgr.set_goal("no errors")
        context = {
            "tool_results": [{"tool": "Bash", "output": "Error occurred"}],
        }
        is_met, feedback = mgr.check_goal(context)
        assert "Check recent tool outputs" in feedback

    def test_check_count_in_feedback(self):
        mgr = GoalManager()
        mgr.set_goal("tests pass")
        context = {"tool_results": [], "messages": []}
        mgr.check_goal(context)  # Check 1
        is_met, feedback = mgr.check_goal(context)  # Check 2
        assert "checked 2 times" in feedback


# ============================================================
# check_stop_goal helper
# ============================================================

class TestCheckStopGoal:
    @pytest.mark.asyncio
    async def test_no_goal_allows_stop(self):
        mgr = GoalManager()
        should_stop, msg = await check_stop_goal(mgr, [], [])
        assert should_stop is True
        assert msg is None or msg == ""

    @pytest.mark.asyncio
    async def test_goal_met_allows_stop(self):
        mgr = GoalManager()
        mgr.set_goal("tests pass")
        should_stop, msg = await check_stop_goal(
            mgr, [],
            [{"tool": "Bash", "output": "pytest: 0 failed"}],
        )
        assert should_stop is True

    @pytest.mark.asyncio
    async def test_goal_not_met_blocks_stop(self):
        mgr = GoalManager()
        mgr.set_goal("tests pass")
        should_stop, msg = await check_stop_goal(
            mgr, [],
            [{"tool": "Bash", "output": "pytest: 2 failed"}],
        )
        assert should_stop is False
        assert msg is not None
        assert "Goal not yet met" in msg
