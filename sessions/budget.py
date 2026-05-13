"""Token Budget tracking system for execution cost control.

Tracks token consumption during agent execution and detects
diminishing returns to prevent ineffective infinite loops.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("gateway")


# Constants
COMPLETION_THRESHOLD = 0.9      # 90% of budget - start evaluating
DIMINISHING_THRESHOLD = 200     # Tokens - marginal return threshold (lowered to be less aggressive)
MAX_CONTINUATIONS = 10          # Max continuations before evaluation (increased for longer tasks)
MIN_TOKENS_FOR_DIMINISHING = 3000  # Minimum tokens before checking diminishing returns
DEFAULT_BUDGET = 50000          # Default token budget


@dataclass
class BudgetTracker:
    """Track token consumption during execution."""

    continuation_count: int = 0           # Number of continuations
    last_delta_tokens: int = 0           # Last token delta
    last_global_turn_tokens: int = 0     # Total tokens at last check
    started_at: float = field(default_factory=time.time)
    total_tokens_used: int = 0           # Cumulative tokens


@dataclass
class ContinueDecision:
    """Decision to continue execution."""

    pct: int = 0                          # Progress percentage
    should_continue: bool = True
    nudge_message: str | None = None      # Optional nudge for agent


@dataclass
class StopDecision:
    """Decision to stop execution."""

    should_continue: bool = False
    completion_event: dict[str, Any] | None = None  # Final report
    reason: str = ""                      # Stop reason


BudgetDecision = ContinueDecision | StopDecision


def check_token_budget(
    tracker: BudgetTracker,
    budget: int | None,
    current_tokens: int,
) -> BudgetDecision:
    """Check token budget and decide whether to continue.

    Args:
        tracker: Budget tracker state
        budget: Token budget limit (None = no limit)
        current_tokens: Current token consumption

    Returns:
        BudgetDecision: Continue or Stop decision
    """
    # No budget set - allow unlimited
    if budget is None or budget <= 0:
        tracker.continuation_count += 1
        return ContinueDecision(pct=0, nudge_message=None)

    pct = int(current_tokens / budget * 100)
    delta = current_tokens - tracker.last_global_turn_tokens

    # Check for diminishing returns
    # Only check after minimum tokens used - early turns naturally have smaller deltas
    is_diminishing = (
        current_tokens >= MIN_TOKENS_FOR_DIMINISHING and
        tracker.continuation_count >= MAX_CONTINUATIONS and
        delta < DIMINISHING_THRESHOLD and
        tracker.last_delta_tokens < DIMINISHING_THRESHOLD
    )

    # Under 90% threshold and not diminishing - continue
    if not is_diminishing and current_tokens < budget * COMPLETION_THRESHOLD:
        tracker.continuation_count += 1
        tracker.last_delta_tokens = delta
        tracker.last_global_turn_tokens = current_tokens
        tracker.total_tokens_used = current_tokens

        nudge = f"Token budget: {pct}% used ({current_tokens}/{budget}). Continue efficiently."
        return ContinueDecision(pct=pct, nudge_message=nudge)

    # Over threshold or diminishing returns - stop
    reason = "diminishing_returns" if is_diminishing else "budget_exhausted"

    completion_event = {
        "continuation_count": tracker.continuation_count,
        "pct": pct,
        "tokens": current_tokens,
        "budget": budget,
        "diminishing_returns": is_diminishing,
        "duration_ms": int((time.time() - tracker.started_at) * 1000),
        "last_delta": delta,
    }

    logger.info(
        f"[BUDGET] Stopping: reason={reason}, "
        f"tokens={current_tokens}, budget={budget}, pct={pct}%"
    )

    return StopDecision(
        completion_event=completion_event,
        reason=reason,
    )


def get_budget_for_task(
    explicit_budget: int | None = None,
    agent_config_budget: int | None = None,
    default_budget: int = DEFAULT_BUDGET,
) -> int:
    """Get token budget for a task.

    Priority: explicit > agent_config > default

    Args:
        explicit_budget: User-specified budget
        agent_config_budget: Agent type default budget
        default_budget: System default

    Returns:
        Token budget value
    """
    if explicit_budget and explicit_budget > 0:
        return explicit_budget
    if agent_config_budget and agent_config_budget > 0:
        return agent_config_budget
    return default_budget


def generate_budget_report(event: dict[str, Any]) -> str:
    """Generate a budget usage report.

    Args:
        event: Completion event data

    Returns:
        Formatted report string
    """
    lines = [
        "## Token Budget Report",
        f"- Total used: **{event['tokens']} tokens** ({event['pct']}%)",
        f"- Budget limit: {event['budget']} tokens",
        f"- Execution turns: {event['continuation_count']}",
        f"- Duration: {event['duration_ms']}ms",
    ]

    if event['diminishing_returns']:
        lines.append("- Stop reason: **Diminishing returns** (low marginal benefit)")
    elif event['pct'] >= 90:
        lines.append("- Stop reason: **Budget threshold reached** (90%)")
    else:
        lines.append("- Stop reason: Task completed")

    return "\n".join(lines)


def estimate_tokens_simple(messages: list[dict]) -> int:
    """Estimate token count using simple heuristic.

    Approximation: 4 characters ≈ 1 token

    Args:
        messages: Message list

    Returns:
        Estimated token count
    """
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += len(content) // 4
        elif isinstance(content, list):
            # Multi-modal content
            for block in content:
                if block.get("type") == "text":
                    total += len(block.get("text", "")) // 4

        # Add overhead for role, tool_calls, etc.
        total += 4  # ~4 tokens overhead per message

    return total


class BudgetManager:
    """Manage token budgets for sessions and agents."""

    def __init__(self, default_budget: int = DEFAULT_BUDGET):
        self._default_budget = default_budget
        self._trackers: dict[str, BudgetTracker] = {}

    def get_tracker(self, session_id: str) -> BudgetTracker:
        """Get or create budget tracker for session."""
        if session_id not in self._trackers:
            self._trackers[session_id] = BudgetTracker()
        return self._trackers[session_id]

    def reset_tracker(self, session_id: str) -> None:
        """Reset budget tracker for a session."""
        self._trackers[session_id] = BudgetTracker()

    def check_budget(
        self,
        session_id: str,
        budget: int | None,
        current_tokens: int,
    ) -> BudgetDecision:
        """Check budget for a session."""
        tracker = self.get_tracker(session_id)
        return check_token_budget(tracker, budget, current_tokens)

    def get_budget_stats(self, session_id: str) -> dict[str, Any]:
        """Get budget statistics for a session."""
        tracker = self.get_tracker(session_id)
        return {
            "continuation_count": tracker.continuation_count,
            "total_tokens_used": tracker.total_tokens_used,
            "duration_ms": int((time.time() - tracker.started_at) * 1000),
        }


__all__ = [
    "BudgetTracker",
    "BudgetDecision",
    "ContinueDecision",
    "StopDecision",
    "check_token_budget",
    "get_budget_for_task",
    "generate_budget_report",
    "estimate_tokens_simple",
    "BudgetManager",
    "DEFAULT_BUDGET",
    "COMPLETION_THRESHOLD",
    "DIMINISHING_THRESHOLD",
]