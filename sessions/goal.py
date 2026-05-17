"""Goal Command - Session-level objective tracking with LLM verification.

/goal <condition> sets a measurable goal. At each turn end, the goal
condition is checked via LLM verification. If unmet, feedback is injected
to keep the agent working until the goal is truly achieved.
"""

from __future__ import annotations

import asyncio
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


VERIFIER_SYSTEM_PROMPT = """你是一个独立验证者，检查任务目标是否达成。

规则:
1. 只依据提供的对话内容判断，不要假设
2. 如果有数值指标，严格比较（f1=0.88 < 0.90 就是未达标）
3. 如果未达标，给出具体反馈和建议下一步行动
4. 回复格式必须严格遵循:
   - 达标: "VERIFIED: 目标已达成"
   - 未达标: "NOT_MET: <当前状态描述>，建议<下一步行动>"
"""


class GoalVerifier:
    """使用LLM验证目标是否达成。"""

    def __init__(self, llm_client: Any, model: str = "deepseek-chat"):
        self._client = llm_client
        self._model = model

    async def verify(
        self,
        condition: str,
        messages: list[dict],
        tool_results: list[dict] | None = None,
    ) -> tuple[bool, str]:
        """验证目标是否达成。

        Args:
            condition: 目标条件（如 "f1 > 0.90"）
            messages: 最近几轮对话
            tool_results: 最近工具执行结果（可选）

        Returns:
            (is_met, feedback): 是否达成 + 反馈信息
        """
        # 构建验证输入
        recent_content = self._extract_recent_content(messages, tool_results)

        verifier_messages = [
            {"role": "system", "content": VERIFIER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"目标条件: {condition}\n\n最近对话内容:\n{recent_content}\n\n请判断目标是否达成。",
            },
        ]

        try:
            response = await asyncio.to_thread(
                self._client.chat.completions.create,
                model=self._model,
                messages=verifier_messages,
            )

            content = response.choices[0].message.content or ""
            is_met = content.startswith("VERIFIED:")
            feedback = content

            logger.info(f"[GoalVerifier] Result: is_met={is_met}, content={content[:100]}")
            return is_met, feedback

        except Exception as e:
            logger.error(f"[GoalVerifier] Error: {e}")
            # 出错时保守处理：允许继续
            return True, f"验证出错: {str(e)}"

    def _extract_recent_content(
        self,
        messages: list[dict],
        tool_results: list[dict] | None,
    ) -> str:
        """提取最近对话内容用于验证。"""
        parts = []

        # 取最近3-5条消息
        for msg in messages[-5:]:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if content and role != "system":
                parts.append(f"[{role}]: {content[:500]}")

        # 添加工具结果
        if tool_results:
            for r in tool_results[-3:]:
                output = r.get("output", r.get("content", ""))
                if output:
                    parts.append(f"[tool]: {output[:500]}")

        return "\n".join(parts) if parts else "无最近对话内容"


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


# ============================================================
# Goal Verification for Tool Loop
# ============================================================

async def verify_goal_in_loop(
    goal_manager: GoalManager,
    verifier: GoalVerifier,
    messages: list[dict],
    tool_results: list[dict] | None = None,
) -> tuple[bool, str]:
    """在 tool loop 中验证目标。

    Args:
        goal_manager: GoalManager 实例
        verifier: GoalVerifier 实例
        messages: 当前对话消息
        tool_results: 最近工具结果（可选）

    Returns:
        (should_continue, feedback):
        - should_continue=True: 目标未达成，需要继续循环
        - should_continue=False: 目标已达成或无目标，可以退出
    """
    if not goal_manager.has_goal():
        return False, ""

    goal = goal_manager.get_goal()
    goal.check_count += 1

    # 检查次数上限
    if goal.check_count > 500:
        logger.warning(f"[Goal] 达到 500 次验证上限")
        goal_manager.clear_goal()
        return False, "目标验证达到500次上限，已自动终止。"

    # LLM 验证
    is_met, feedback = await verifier.verify(
        condition=goal.condition,
        messages=messages,
        tool_results=tool_results,
    )

    if is_met:
        logger.info(f"[Goal] 目标已达成: {goal.condition}")
        goal_manager.clear_goal()
        return False, f"目标已达成: {goal.condition}"

    logger.info(f"[Goal] 未达成 (#{goal.check_count}): {goal.condition}")
    return True, feedback


__all__ = [
    "GoalState",
    "GoalManager",
    "GoalVerifier",
    "VERIFIER_SYSTEM_PROMPT",
    "check_stop_goal",
    "verify_goal_in_loop",
]
