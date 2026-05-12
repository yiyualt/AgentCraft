"""
Tests for AgentCraft compaction engine.
"""

import pytest
from agentcraft import AgentCraft, CompactionLevel, ContextMessage, CompactionReport


def _make_msg(role: str, size: int, **kw):
    """Create a message with approximately `size` tokens of content."""
    content = "x" * (size * 4)
    if "content" in kw:
        content = kw.pop("content") + content
    return ContextMessage(role=role, content=content, **kw)


class TestAgentCraft:
    def test_basic_add_message(self):
        craft = AgentCraft(max_tokens=1000, auto_compact=False)
        craft.add_message(ContextMessage(role="user", content="Hello"))
        assert len(craft.messages) == 1
        assert craft.messages[0].content == "Hello"

    def test_usage_ratio(self):
        craft = AgentCraft(max_tokens=1000, auto_compact=False)
        craft.add_message(_make_msg("user", 250))
        assert 0.20 < craft.usage_ratio < 0.30

    def test_should_not_compact_below_l1(self):
        craft = AgentCraft(max_tokens=10000, auto_compact=False)
        craft.add_message(ContextMessage(role="user", content="Small message"))
        assert craft.should_compact() is False

    def test_l1_compaction(self):
        """Hit ~60-79% usage so CompactionLevel.from_threshold returns L1."""
        craft = AgentCraft(max_tokens=2000, auto_compact=False)
        for i in range(5):
            craft.add_message(_make_msg("user", 100, content=f"Query {i}: "))
            craft.add_message(_make_msg("assistant", 100, content=f"Response {i}: "))
            craft.add_message(_make_msg("tool", 100, content=f"Output {i}: "))

        ratio = craft.usage_ratio
        assert 0.60 <= ratio < 0.80, f"Expected L1 range, got {ratio:.1%}"
        assert craft.should_compact()

        report = craft.compact()
        assert report.level == CompactionLevel.L1
        assert report.tokens_reclaimed > 0
        assert len(report.techniques_applied) > 0

    def test_l2_compaction(self):
        """Hit ~80-89% usage so CompactionLevel.from_threshold returns L2."""
        craft = AgentCraft(max_tokens=2500, auto_compact=False)
        # 5 turns × 3 messages × ~80 tokens each = ~1200 tokens = 48%
        for i in range(5):
            craft.add_message(_make_msg("user", 80, content=f"Query {i}: "))
            craft.add_message(_make_msg("assistant", 80, content=f"Response {i}: "))
            craft.add_message(_make_msg(
                "tool", 80, content=f"Output {i}: ",
                metadata={"status": "resolved", "tags": ["resolved"]}
            ))

        # Now add extra messages to push into L2 territory (~80-89%)
        while craft.usage_ratio < 0.80:
            craft.add_message(_make_msg("user", 80))

        ratio = craft.usage_ratio
        assert 0.80 <= ratio < 0.90, f"Expected L2 range, got {ratio:.1%}"

        level = CompactionLevel.from_threshold(ratio)
        assert level == CompactionLevel.L2

        report = craft.compact(CompactionLevel.L2)
        assert report.tokens_reclaimed > 0
        assert "merge_similar_chains" in report.techniques_applied or \
               "drop_resolved_subtasks" in report.techniques_applied

    def test_l3_deep_compaction(self):
        """Hit >=90% usage so CompactionLevel.from_threshold returns L3."""
        craft = AgentCraft(max_tokens=1200, auto_compact=False)
        # Keep adding until we hit 90%+
        # Use low priority so distillation actually removes things
        while craft.usage_ratio < 0.90:
            craft.add_message(_make_msg("user", 80, priority=1))
            craft.add_message(_make_msg("assistant", 80, priority=1))
            craft.add_message(_make_msg("tool", 80, priority=1))

        ratio = craft.usage_ratio
        assert ratio >= 0.90, f"Expected L3 range (>=90%), got {ratio:.1%}"

        level = CompactionLevel.from_threshold(ratio)
        assert level == CompactionLevel.L3

        report = craft.compact(CompactionLevel.L3)
        assert report.tokens_reclaimed > 0
        assert report.messages_after <= 10  # Max keep = 10

    def test_auto_compact(self):
        craft = AgentCraft(max_tokens=1000, auto_compact=True)
        for i in range(10):
            craft.add_message(_make_msg("user", 200))
        assert len(craft.compaction_history) > 0

    def test_compaction_report(self):
        craft = AgentCraft(max_tokens=2000, auto_compact=False)
        for i in range(6):
            craft.add_message(_make_msg("user", 100))
            craft.add_message(_make_msg("assistant", 100))

        report = craft.compact()
        assert isinstance(report, CompactionReport)
        assert report.original_tokens > 0
        assert report.final_tokens > 0
        assert report.messages_before > 0
        assert report.messages_after > 0
        assert report.duration_ms >= 0
        assert report.compression_ratio > 0
        assert "L1" in report.summary()

    def test_custom_strategy(self):
        from agentcraft.compactor import CompactionStrategy

        class RemoveAll(CompactionStrategy):
            name = "remove_all"

            def can_apply(self, level, messages):
                return level == CompactionLevel.L1

            def apply(self, level, messages):
                return []

        craft = AgentCraft(max_tokens=2000, auto_compact=False)
        craft.add_message(_make_msg("user", 100))
        craft.register_strategy(CompactionLevel.L1, RemoveAll())
        craft.compact(CompactionLevel.L1)
        assert len(craft.messages) == 0

    def test_invalid_thresholds(self):
        with pytest.raises(ValueError):
            AgentCraft(l1_threshold=0.7, l2_threshold=0.5, l3_threshold=0.9)

    def test_snapshot(self):
        craft = AgentCraft(max_tokens=1000, auto_compact=False)
        craft.add_message(ContextMessage(role="user", content="test"))
        snap = craft.snapshot()
        assert snap.total_tokens > 0
        assert snap.max_tokens == 1000
        assert 0 < snap.usage_ratio < 1
        assert snap.compactable is False

    def test_summary(self):
        craft = AgentCraft(max_tokens=1000, auto_compact=False)
        craft.add_message(ContextMessage(role="user", content="test"))
        summary = craft.summary()
        assert "AgentCraft" in summary or "Context" in summary
