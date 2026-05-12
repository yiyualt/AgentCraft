"""
AgentCraft Demo — see all 3 compaction levels in action.
"""

from agentcraft import AgentCraft, CompactionLevel, ContextMessage


def simulate_conversation(craft: AgentCraft, num_turns: int = 15):
    """Add enough conversation turns to trigger compaction."""

    long_tool_output = "Result: " + "data=" * 400  # ~3200 chars
    very_long_tool = "VeryLongOutput: " + "verbose_log_entry\n" * 500  # ~8000 chars

    for i in range(num_turns):
        # User message
        craft.add_message(ContextMessage(
            role="user",
            content=f"User query #{i + 1}: What is the status of task-{i + 1}?",
            priority=1,
        ))

        # Assistant response (gets longer over time)
        craft.add_message(ContextMessage(
            role="assistant",
            content=f"Task-{i + 1} is in progress. Analyzing dependencies... "
                    f"We need to check modules A, B, and C. "
                    f"Iteration {i + 1} requires validation. " * (2 + i),
            priority=2,
        ))

        # Tool call results (some long, some tagged resolved)
        craft.add_message(ContextMessage(
            role="tool",
            content=long_tool_output if i % 3 != 0 else very_long_tool,
            metadata={"status": "completed" if i % 2 == 0 else "in_progress",
                      "tags": ["resolved"] if i % 3 == 0 else []},
            priority=0,
        ))

        # Print progress
        snap = craft.snapshot()
        bar = "█" * int(snap.usage_ratio * 40) + "░" * (40 - int(snap.usage_ratio * 40))
        print(f"  Turn {i + 1:2d}  [{bar}] {snap.usage_ratio:.0%}  ({snap.total_tokens:5d} tokens)")


def run_demo():
    print("=" * 68)
    print("  🏗️  AgentCraft — 3-Level Context Compaction Demo")
    print("=" * 68)
    print()
    print("  Thresholds:  L1 = 60%   |   L2 = 80%   |   L3 = 90%")
    print()

    # ── Demo: L1 (60% threshold) ──────────────────────────────────
    print("─" * 68)
    print("  📊 DEMO 1: L1 Compaction (60% threshold)")
    print("─" * 68)
    print()

    craft = AgentCraft(max_tokens=4000, auto_compact=False)
    simulate_conversation(craft, num_turns=8)

    print()
    print(f"  Usage before compaction: {craft.usage_ratio:.1%}")
    print()

    if craft.should_compact():
        report = craft.compact()
        print(f"  ✅ {report.summary()}")
        print(f"  ⏱  Duration: {report.duration_ms} ms")
    print()

    # ── Demo: L2 (80% threshold) ──────────────────────────────────
    print("─" * 68)
    print("  📊 DEMO 2: L2 Compaction (80% threshold)")
    print("─" * 68)
    print()

    craft2 = AgentCraft(max_tokens=4000, auto_compact=False)
    simulate_conversation(craft2, num_turns=12)

    print()
    print(f"  Usage before compaction: {craft2.usage_ratio:.1%}")
    print()

    level = CompactionLevel.from_threshold(craft2.usage_ratio)
    print(f"  Triggering: {level.name} ({level.describe()})")
    print()

    if craft2.should_compact():
        report = craft2.compact()
        print(f"  ✅ {report.summary()}")
        print(f"  ⏱  Duration: {report.duration_ms} ms")
    print()

    # ── Demo: L3 (90% threshold) ──────────────────────────────────
    print("─" * 68)
    print("  📊 DEMO 3: L3 Compaction (90% threshold)")
    print("─" * 68)
    print()

    craft3 = AgentCraft(max_tokens=4000, auto_compact=False)
    simulate_conversation(craft3, num_turns=15)

    print()
    print(f"  Usage before compaction: {craft3.usage_ratio:.1%}")
    print()

    level = CompactionLevel.from_threshold(craft3.usage_ratio)
    print(f"  Triggering: {level.name} ({level.describe()})")
    print()

    if craft3.should_compact():
        report = craft3.compact()
        print(f"  ✅ {report.summary()}")
        print(f"  ⏱  Duration: {report.duration_ms} ms")
    print()

    # ── Summary ───────────────────────────────────────────────────
    print("=" * 68)
    print("  🏁  OVERALL SUMMARY")
    print("=" * 68)
    print()
    for i, c in enumerate([craft, craft2, craft3], 1):
        print(f"  Agent {i}:")
        print(f"    Messages     : {len(c.messages)}")
        print(f"    Usage ratio  : {c.usage_ratio:.1%}")
        print(f"    Compactions  : {len(c.compaction_history)}")
        for r in c.compaction_history:
            print(f"    → {r.summary()}")
        print()

    # ── Show remaining messages ───────────────────────────────────
    print("─" * 68)
    print("  📋  FINAL CONTEXT (after all compactions)")
    print("─" * 68)
    print()
    for i, c in enumerate([craft, craft2, craft3], 1):
        print(f"  Agent {i} messages ({len(c.messages)} total):")
        for j, msg in enumerate(c.messages):
            compacted = " [compacted]" if msg.metadata.get("compacted") else ""
            content_preview = msg.content[:80].replace("\n", " ")
            print(f"    {j + 1:2d}. [{msg.role:9s}] {content_preview}...{compacted}")
        print()


if __name__ == "__main__":
    run_demo()
