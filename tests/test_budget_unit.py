#!/usr/bin/env python3
"""Unit tests for Token Budget system."""

import time
import pytest
from sessions.budget import (
    BudgetTracker,
    BudgetManager,
    ContinueDecision,
    StopDecision,
    check_token_budget,
    get_budget_for_task,
    generate_budget_report,
    estimate_tokens_simple,
    DEFAULT_BUDGET,
    COMPLETION_THRESHOLD,
    DIMINISHING_THRESHOLD,
    MAX_CONTINUATIONS,
)


class TestBudgetTracker:
    def test_init(self):
        t = BudgetTracker()
        assert t.continuation_count == 0
        assert t.last_delta_tokens == 0
        assert t.total_tokens_used == 0
        assert t.started_at > 0

    def test_field_assignment(self):
        t = BudgetTracker(continuation_count=3, last_delta_tokens=100, total_tokens_used=5000)
        assert t.continuation_count == 3
        assert t.last_delta_tokens == 100
        assert t.total_tokens_used == 5000


class TestCheckBudget:
    def test_no_budget_returns_continue(self):
        t = BudgetTracker()
        result = check_token_budget(t, budget=0, current_tokens=100000)
        assert isinstance(result, ContinueDecision)
        assert result.should_continue is True

    def test_none_budget_returns_continue(self):
        t = BudgetTracker()
        result = check_token_budget(t, budget=None, current_tokens=999999)
        assert isinstance(result, ContinueDecision)
        assert result.should_continue is True

    def test_under_threshold_continues(self):
        t = BudgetTracker()
        result = check_token_budget(t, budget=50000, current_tokens=20000)  # 40%
        assert isinstance(result, ContinueDecision)
        assert result.should_continue is True
        assert result.pct == 40
        assert result.nudge_message is not None
        assert "40%" in result.nudge_message

    def test_over_90_percent_stops(self):
        t = BudgetTracker()
        result = check_token_budget(t, budget=50000, current_tokens=48000)  # 96%
        assert isinstance(result, StopDecision)
        assert result.should_continue is False
        assert result.reason == "budget_exhausted"
        assert result.completion_event["pct"] == 96

    def test_diminishing_returns_stops(self):
        t = BudgetTracker(
            continuation_count=MAX_CONTINUATIONS + 1,
            last_delta_tokens=200,  # Below threshold
        )
        result = check_token_budget(t, budget=50000, current_tokens=20000)  # Under 90%
        # Delta from last check is 20000 - 0 = 20000, which is NOT diminishing
        # Need current_tokens to produce small delta
        result2 = check_token_budget(
            BudgetTracker(
                continuation_count=MAX_CONTINUATIONS + 1,
                last_delta_tokens=200,
                last_global_turn_tokens=19500,
            ),
            budget=50000,
            current_tokens=20000,
        )
        # delta = 20000 - 19500 = 500, still >= threshold
        assert isinstance(result2, ContinueDecision)

        # Now truly diminishing
        result3 = check_token_budget(
            BudgetTracker(
                continuation_count=MAX_CONTINUATIONS + 1,
                last_delta_tokens=200,
                last_global_turn_tokens=19800,
            ),
            budget=50000,
            current_tokens=20000,
        )
        # delta = 20000 - 19800 = 200, both < 500
        assert isinstance(result3, StopDecision)
        assert result3.reason == "diminishing_returns"
        assert result3.completion_event["diminishing_returns"] is True

    def test_continuation_count_increments(self):
        t = BudgetTracker()
        check_token_budget(t, budget=50000, current_tokens=10000)
        assert t.continuation_count == 1
        check_token_budget(t, budget=50000, current_tokens=15000)
        assert t.continuation_count == 2

    def test_total_tokens_tracked(self):
        t = BudgetTracker()
        check_token_budget(t, budget=50000, current_tokens=25000)
        assert t.total_tokens_used == 25000


class TestGetBudgetForTask:
    def test_explicit_budget_wins(self):
        assert get_budget_for_task(explicit_budget=30000, agent_config_budget=40000, default_budget=50000) == 30000

    def test_agent_config_fallback(self):
        assert get_budget_for_task(explicit_budget=None, agent_config_budget=40000, default_budget=50000) == 40000

    def test_default_fallback(self):
        assert get_budget_for_task(explicit_budget=None, agent_config_budget=None, default_budget=50000) == 50000

    def test_ignores_zero_budget(self):
        assert get_budget_for_task(explicit_budget=0, agent_config_budget=40000) == 40000

    def test_ignores_negative_budget(self):
        assert get_budget_for_task(explicit_budget=-1, agent_config_budget=None) == DEFAULT_BUDGET


class TestGenerateBudgetReport:
    def test_diminishing_report(self):
        event = {
            "tokens": 30000,
            "budget": 50000,
            "pct": 60,
            "continuation_count": 6,
            "duration_ms": 45000,
            "diminishing_returns": True,
        }
        report = generate_budget_report(event)
        assert "## Token Budget Report" in report
        assert "**Diminishing returns**" in report
        assert "30000" in report

    def test_threshold_report(self):
        event = {
            "tokens": 48000,
            "budget": 50000,
            "pct": 96,
            "continuation_count": 4,
            "duration_ms": 30000,
            "diminishing_returns": False,
        }
        report = generate_budget_report(event)
        assert "90%" in report
        assert "Budget threshold reached" in report

    def test_completed_report(self):
        event = {
            "tokens": 20000,
            "budget": 50000,
            "pct": 40,
            "continuation_count": 2,
            "duration_ms": 15000,
            "diminishing_returns": False,
        }
        report = generate_budget_report(event)
        assert "Task completed" in report


class TestEstimateTokensSimple:
    def test_empty_messages(self):
        assert estimate_tokens_simple([]) == 0

    def test_simple_text(self):
        msgs = [{"role": "user", "content": "Hello, how are you?"}]
        tokens = estimate_tokens_simple(msgs)
        assert tokens > 0  # 19 chars / 4 + 4 overhead ≈ 8
        assert tokens == len("Hello, how are you?") // 4 + 4

    def test_multiple_messages(self):
        msgs = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello!"},
        ]
        tokens = estimate_tokens_simple(msgs)
        # system: 30/4 + 4 = 11, user: 6/4 + 4 = 5, total = 16
        expected = len("You are a helpful assistant.") // 4 + 4 + len("Hello!") // 4 + 4
        assert tokens == expected

    def test_multimodal_content(self):
        msgs = [{
            "role": "user",
            "content": [
                {"type": "text", "text": "Describe this image"},
                {"type": "image_url", "image_url": {"url": "http://example.com/img.jpg"}},
            ],
        }]
        tokens = estimate_tokens_simple(msgs)
        # Only text block counts: 19//4 + 4 overhead = 8
        assert tokens == len("Describe this image") // 4 + 4


class TestBudgetManager:
    def test_get_tracker_creates_new(self):
        mgr = BudgetManager()
        tracker = mgr.get_tracker("session-1")
        assert isinstance(tracker, BudgetTracker)
        assert tracker.continuation_count == 0

    def test_get_tracker_returns_same(self):
        mgr = BudgetManager()
        t1 = mgr.get_tracker("session-1")
        t1.continuation_count = 5
        t2 = mgr.get_tracker("session-1")
        assert t2.continuation_count == 5

    def test_reset_tracker(self):
        mgr = BudgetManager()
        t1 = mgr.get_tracker("session-1")
        t1.continuation_count = 10
        mgr.reset_tracker("session-1")
        t2 = mgr.get_tracker("session-1")
        assert t2.continuation_count == 0

    def test_check_budget_delegates(self):
        mgr = BudgetManager()
        result = mgr.check_budget("session-1", budget=50000, current_tokens=48000)
        assert isinstance(result, StopDecision)

    def test_get_budget_stats(self):
        mgr = BudgetManager()
        mgr.check_budget("session-1", budget=50000, current_tokens=10000)
        stats = mgr.get_budget_stats("session-1")
        assert stats["continuation_count"] == 1
        assert "total_tokens_used" in stats
        assert "duration_ms" in stats
