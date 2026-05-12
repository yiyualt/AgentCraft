"""Goal Command - Session-level objective tracking via Stop hooks.

/goal <condition> sets a measurable goal. At each turn end, the goal
condition is checked. If unmet, the session is blocked from ending
and feedback is injected to keep the agent working.
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("gateway")


@dataclass
class GoalState:
    condition: str
    created_at: float = field(default_factory=time.time)
    check_count: int = 0
    met: bool = False


class GoalManager:
    """Manages session-scoped goals with condition evaluation."""

    def __init__(self, max_checks: int = 5000):
        self._current_goal: GoalState | None = None
        self._max_checks = max_checks

    def set_goal(self, condition: str) -> str:
        self._current_goal = GoalState(condition=condition)
        logger.info(f"[Goal] Set: '{condition}'")
        return f"Goal set: {condition}"

    def clear_goal(self) -> str:
        if self._current_goal:
            result = f"Goal cleared: {self._current_goal.condition}"
            self._current_goal = None
            return result
        return "No goal was set"

    def get_goal(self) -> GoalState | None:
        return self._current_goal

    def has_goal(self) -> bool:
        return self._current_goal is not None

    def check_goal(self, context: dict[str, Any]) -> tuple[bool, str]:
        """Check if the goal is met.

        Returns (is_met, feedback_message).
        """
        if not self._current_goal:
            return True, ""

        self._current_goal.check_count += 1

        # Enforce max checks
        if self._current_goal.check_count > self._max_checks:
            logger.warning(f"[Goal] Max checks ({self._max_checks}) exceeded")
            self._current_goal = None
            return True, f"Goal check limit ({self._max_checks}) reached. Giving up."

        is_met = self._evaluate(self._current_goal.condition, context)
        self._current_goal.met = is_met

        if is_met:
            msg = f"Goal achieved: {self._current_goal.condition}"
            logger.info(f"[Goal] {msg}")
            self._current_goal = None  # Auto-clear
            return True, msg

        feedback = self._generate_feedback(self._current_goal, context)
        logger.info(f"[Goal] Not met (check #{self._current_goal.check_count}): {self._current_goal.condition}")
        return False, feedback

    def _evaluate(self, condition: str, context: dict[str, Any]) -> bool:
        cond = condition.lower()

        if "tests pass" in cond or "test passes" in cond:
            return self._check_tests_pass(context)

        if "file" in cond and "exists" in cond:
            return self._check_file_exists(condition, context)

        if "no error" in cond or "no errors" in cond:
            return self._check_no_errors(context)

        # Default: check recent messages for completion
        return self._check_messages(condition, context)

    def _check_tests_pass(self, context: dict[str, Any]) -> bool:
        tool_results = context.get("tool_results", [])
        for r in tool_results:
            output = r.get("output", "")
            # Check for test pass patterns in output
            if "passed" in output.lower():
                if "failed" not in output.lower() or "0 failed" in output:
                    return True
            if "0 failed" in output:
                return True
        # Also check recent messages
        messages = context.get("messages", [])
        for msg in messages[-5:]:
            content = msg.get("content", "")
            if isinstance(content, str):
                if "passed" in content.lower():
                    if "failed" not in content.lower() or "0 failed" in content:
                        return True
        return False

    def _check_file_exists(self, condition: str, context: dict[str, Any]) -> bool:
        match = re.search(r"file\s+['\"]?([^'\"]+)['\"]?\s+exists", condition.lower())
        if match:
            return os.path.exists(match.group(1))
        return False

    def _check_no_errors(self, context: dict[str, Any]) -> bool:
        tool_results = context.get("tool_results", [])
        for r in tool_results:
            output = r.get("output", "")
            if "error" in output.lower() or "exception" in output.lower():
                return False
        return True

    def _check_messages(self, condition: str, context: dict[str, Any]) -> bool:
        messages = context.get("messages", [])
        cond_lower = condition.lower()
        for msg in messages[-3:]:
            content = msg.get("content", "")
            if isinstance(content, str):
                if cond_lower in content.lower():
                    if any(w in content.lower() for w in ("done", "completed", "finished", "pass")):
                        return True
        return False

    def _generate_feedback(self, goal: GoalState, context: dict[str, Any]) -> str:
        parts = [f"Goal not yet met: '{goal.condition}'"]
        if goal.check_count > 1:
            parts[0] += f" (checked {goal.check_count} times)"

        suggestions = self._get_suggestions(goal.condition)
        if suggestions:
            parts.append(f"\nSuggestions:\n{suggestions}")

        return "\n".join(parts)

    @staticmethod
    def _get_suggestions(condition: str) -> str:
        cond = condition.lower()
        if "tests pass" in cond:
            return "- Run the tests to see current status\n- Fix any failing tests\n- Check test output for specific failures"
        if "file" in cond and "exists" in cond:
            return "- Create the file if it doesn't exist\n- Check if the path is correct"
        if "no error" in cond:
            return "- Check recent tool outputs for errors\n- Fix any errors found"
        return "- Continue working toward the goal"


# ============================================================
# Goal check integration helper
# ============================================================

async def check_stop_goal(
    goal_manager: GoalManager,
    messages: list[dict],
    tool_results: list[dict],
) -> tuple[bool, str | None]:
    """Check goal and return whether to stop + optional blocking message.

    Returns (should_stop, blocking_message).
    - should_stop=True: goal met or no goal set
    - should_stop=False: goal not met, blocking_message has feedback
    """
    context = {
        "messages": messages,
        "tool_results": tool_results,
    }
    is_met, feedback = goal_manager.check_goal(context)

    if is_met:
        return True, feedback or None

    return False, feedback


__all__ = [
    "GoalState",
    "GoalManager",
    "check_stop_goal",
]
