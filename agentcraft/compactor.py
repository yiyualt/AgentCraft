"""
AgentCraft — Core context compaction engine.

Tracks a moving-window context of conversation turns and compacts them
when usage crosses configurable thresholds.
"""

from __future__ import annotations

import abc
import json
import math
import textwrap
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any, Callable, Generic, Optional, TypeVar

T = TypeVar("T")


# ──────────────────────────────────────────────────────────────────────
# Compaction Levels
# ──────────────────────────────────────────────────────────────────────

class CompactionLevel(Enum):
    """Three compaction tiers, from lightest to heaviest."""

    L1 = auto()  # 60%  — light summarization
    L2 = auto()  # 80%  — medium merging
    L3 = auto()  # 90%  — deep distillation

    @classmethod
    def from_threshold(cls, usage_ratio: float) -> Optional["CompactionLevel"]:
        if usage_ratio >= 0.90:
            return cls.L3
        if usage_ratio >= 0.80:
            return cls.L2
        if usage_ratio >= 0.60:
            return cls.L1
        return None

    @property
    def threshold(self) -> float:
        return {CompactionLevel.L1: 0.6, CompactionLevel.L2: 0.8, CompactionLevel.L3: 0.9}[self]

    def describe(self) -> str:
        return {
            CompactionLevel.L1: "Light compaction — summarize oldest messages, trim verbose logs",
            CompactionLevel.L2: "Medium compaction — merge similar chains, drop resolved sub-tasks",
            CompactionLevel.L3: "Deep compaction — aggressive distillation, keep only decisions + final state",
        }[self]


# ──────────────────────────────────────────────────────────────────────
# Core data types
# ──────────────────────────────────────────────────────────────────────

@dataclass
class ContextMessage:
    """A single message in the agent's context window."""

    role: str                     # "user" | "assistant" | "system" | "tool"
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    token_count: int = 0
    priority: int = 0             # higher = more important, less likely to be dropped

    def __len__(self) -> int:
        return self.token_count or len(self.content)


@dataclass
class ContextSnapshot:
    """Point-in-time view of the context window."""

    messages: list[ContextMessage]
    total_tokens: int
    max_tokens: int
    usage_ratio: float
    compaction_level: Optional[CompactionLevel] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def compactable(self) -> bool:
        return self.usage_ratio >= 0.60


@dataclass
class CompactionReport:
    """Result of a compaction operation."""

    level: CompactionLevel
    original_tokens: int
    final_tokens: int
    tokens_reclaimed: int
    messages_before: int
    messages_after: int
    techniques_applied: list[str]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    duration_ms: float = 0.0

    @property
    def compression_ratio(self) -> float:
        if self.original_tokens == 0:
            return 0.0
        return round((self.original_tokens - self.final_tokens) / self.original_tokens * 100, 1)

    def summary(self) -> str:
        return (
            f"[Compaction {self.level.name}] "
            f"{self.tokens_reclaimed} tokens reclaimed "
            f"({self.compression_ratio}% compression), "
            f"{self.messages_before}→{self.messages_after} messages. "
            f"Used: {', '.join(self.techniques_applied)}"
        )


# ──────────────────────────────────────────────────────────────────────
# Compactable interface
# ──────────────────────────────────────────────────────────────────────

class Compactable(abc.ABC, Generic[T]):
    """Abstract interface for an object that can be compacted."""

    @abc.abstractmethod
    def compact(self, level: CompactionLevel) -> T:
        ...


# ──────────────────────────────────────────────────────────────────────
# Compaction strategies
# ──────────────────────────────────────────────────────────────────────

class CompactionStrategy(abc.ABC):
    """Base class for a single compaction technique."""

    @abc.abstractmethod
    def can_apply(self, level: CompactionLevel, messages: list[ContextMessage]) -> bool:
        ...

    @abc.abstractmethod
    def apply(self, level: CompactionLevel, messages: list[ContextMessage]) -> list[ContextMessage]:
        ...

    @abc.abstractproperty
    def name(self) -> str:
        ...


class SummarizeOldMessages(CompactionStrategy):
    """L1: Summarize messages outside the 'recent window' into condensed notes."""

    name = "summarize_old_messages"
    _RECENT_KEEP = 5  # always keep last N messages intact

    def can_apply(self, level: CompactionLevel, messages: list[ContextMessage]) -> bool:
        return level == CompactionLevel.L1 and len(messages) > self._RECENT_KEEP + 1

    def apply(self, level: CompactionLevel, messages: list[ContextMessage]) -> list[ContextMessage]:
        if not self.can_apply(level, messages):
            return messages

        recent = messages[-self._RECENT_KEEP:]
        old = messages[:-self._RECENT_KEEP]

        # Build a condensed summary of old messages
        summary_lines: list[str] = []
        for msg in old:
            prefix = f"[{msg.role}]"
            snippet = msg.content[:200].replace("\n", " ")
            summary_lines.append(f"{prefix} {snippet}")

        summary_text = (
            "📋 [L1 Compaction] Summary of earlier conversation:\n"
            + "\n".join(summary_lines)
        )

        summary_msg = ContextMessage(
            role="system",
            content=summary_text,
            metadata={"compacted": True, "original_count": len(old)},
            priority=5,
            token_count=len(summary_text) // 2,  # rough token estimate
        )

        return [summary_msg] + recent


class TrimVerboseToolLogs(CompactionStrategy):
    """L1: Replace long tool outputs with short summary markers."""

    name = "trim_verbose_tool_logs"
    _MAX_TOOL_LENGTH = 500

    def can_apply(self, level: CompactionLevel, messages: list[ContextMessage]) -> bool:
        return level == CompactionLevel.L1

    def apply(self, level: CompactionLevel, messages: list[ContextMessage]) -> list[ContextMessage]:
        trimmed: list[ContextMessage] = []
        for msg in messages:
            if msg.role == "tool" and len(msg.content) > self._MAX_TOOL_LENGTH:
                trimmed.append(ContextMessage(
                    role="tool",
                    content=f"[Tool output truncated: {len(msg.content)} chars → ~{self._MAX_TOOL_LENGTH} chars summary] "
                            f"{msg.content[:self._MAX_TOOL_LENGTH]}...",
                    metadata={**msg.metadata, "compacted": True, "original_length": len(msg.content)},
                    priority=msg.priority,
                    timestamp=msg.timestamp,
                    token_count=self._MAX_TOOL_LENGTH // 2,
                ))
            else:
                trimmed.append(msg)
        return trimmed


class MergeSimilarChains(CompactionStrategy):
    """L2: Merge adjacent user→assistant→tool chains into a single exchange."""

    name = "merge_similar_chains"

    def can_apply(self, level: CompactionLevel, messages: list[ContextMessage]) -> bool:
        return level == CompactionLevel.L2

    def apply(self, level: CompactionLevel, messages: list[ContextMessage]) -> list[ContextMessage]:
        merged: list[ContextMessage] = []
        i = 0

        while i < len(messages):
            # Look for user → assistant → (tool)* pattern
            if (i + 2 < len(messages)
                    and messages[i].role == "user"
                    and messages[i + 1].role == "assistant"
                    and messages[i + 2].role == "tool"):

                user_msg = messages[i]
                asst_msg = messages[i + 1]

                # Collect all consecutive tool messages
                tool_msgs: list[ContextMessage] = []
                j = i + 2
                while j < len(messages) and messages[j].role == "tool":
                    tool_msgs.append(messages[j])
                    j += 1

                merged_content = (
                    f"🔄 [Merged Exchange]\n"
                    f"User: {user_msg.content[:300]}\n"
                    f"Assistant: {asst_msg.content[:300]}\n"
                    f"Tools ({len(tool_msgs)} calls): "
                    + "; ".join(
                        f"{k + 1}. {t.content[:100]}"
                        for k, t in enumerate(tool_msgs)
                    )
                )

                merged.append(ContextMessage(
                    role="system",
                    content=merged_content,
                    metadata={"compacted": True, "merged_count": 2 + len(tool_msgs)},
                    priority=3,
                    token_count=len(merged_content) // 2,
                ))
                i = j
            else:
                merged.append(messages[i])
                i += 1

        return merged


class DropResolvedSubtasks(CompactionStrategy):
    """L2: Remove messages tagged as 'resolved' or 'done' from sub-agents."""

    name = "drop_resolved_subtasks"

    def can_apply(self, level: CompactionLevel, messages: list[ContextMessage]) -> bool:
        return level == CompactionLevel.L2

    def apply(self, level: CompactionLevel, messages: list[ContextMessage]) -> list[ContextMessage]:
        kept: list[ContextMessage] = []
        dropped = 0

        for msg in messages:
            meta = msg.metadata or {}
            status = meta.get("status", "")
            tags = meta.get("tags", [])

            if status in ("resolved", "completed", "done") or "resolved" in tags:
                dropped += 1
                continue

            # Drop messages that are purely confirmations
            if msg.content.strip().lower() in ("ok", "done", "✅", "acknowledged"):
                dropped += 1
                continue

            kept.append(msg)

        if dropped:
            # Add a note about dropped messages
            note = ContextMessage(
                role="system",
                content=f"🗑️ [L2 Compaction] Dropped {dropped} resolved/completed messages.",
                metadata={"compacted": True, "dropped_count": dropped},
                priority=5,
                token_count=20,
            )
            kept.insert(0, note)

        return kept


class AggressiveDistillation(CompactionStrategy):
    """L3: Keep only decisions, final states, and high-priority messages."""

    name = "aggressive_distillation"
    _KEEP_PRIORITY_ABOVE = 3
    _MAX_KEEP_MESSAGES = 10

    def can_apply(self, level: CompactionLevel, messages: list[ContextMessage]) -> bool:
        return level == CompactionLevel.L3

    def apply(self, level: CompactionLevel, messages: list[ContextMessage]) -> list[ContextMessage]:
        # 1. Keep high-priority messages
        high_prio = [m for m in messages if m.priority >= self._KEEP_PRIORITY_ABOVE]

        # 2. Keep the last exchange (user+assistant)
        last_exchange: list[ContextMessage] = []
        for m in reversed(messages):
            last_exchange.append(m)
            if len(last_exchange) >= 2 and {msg.role for msg in last_exchange} == {"user", "assistant"}:
                break
        last_exchange.reverse()

        # 3. Build a distilled summary of everything else
        distilled: list[ContextMessage] = []
        seen = {id(m) for m in high_prio + last_exchange}

        summary_lines: list[str] = []
        for m in messages:
            if id(m) not in seen:
                role_icon = {"user": "👤", "assistant": "🤖", "tool": "🔧", "system": "⚙️"}.get(m.role, "❓")
                snippet = m.content[:150].replace("\n", " ")
                summary_lines.append(f"{role_icon} [{m.role}] {snippet}")

        if summary_lines:
            distilled.append(ContextMessage(
                role="system",
                content=(
                    "🏗️ [L3 Deep Compaction] Distilled summary of intermediate steps:\n"
                    + "\n".join(summary_lines)
                ),
                metadata={"compacted": True, "distilled_count": len(summary_lines)},
                priority=5,
                token_count=len(summary_lines) * 20,
            ))

        # 4. Final context: high priority → distilled summary → last exchange
        final_context = high_prio + distilled + last_exchange

        # Ensure we don't exceed the max keep
        if len(final_context) > self._MAX_KEEP_MESSAGES:
            final_context = final_context[-self._MAX_KEEP_MESSAGES:]

        return final_context


# ──────────────────────────────────────────────────────────────────────
# Main AgentCraft engine
# ──────────────────────────────────────────────────────────────────────

class AgentCraft:
    """
    Context compaction engine with 3 levels (L1=60%, L2=80%, L3=90%).

    Usage:
        craft = AgentCraft(max_tokens=8192)
        craft.add_message(ContextMessage(role="user", content="..."))
        craft.add_message(ContextMessage(role="assistant", content="..."))

        if craft.should_compact():
            report = craft.compact()
            print(report.summary())
    """

    def __init__(
        self,
        max_tokens: int = 8192,
        l1_threshold: float = 0.60,
        l2_threshold: float = 0.80,
        l3_threshold: float = 0.90,
        auto_compact: bool = True,
        token_estimator: Optional[Callable[[str], int]] = None,
    ):
        self.max_tokens = max_tokens
        self._thresholds = {0.60: CompactionLevel.L1, 0.80: CompactionLevel.L2, 0.90: CompactionLevel.L3}

        if not (0 < l1_threshold < l2_threshold < l3_threshold < 1):
            raise ValueError("Thresholds must satisfy: 0 < L1 < L2 < L3 < 1")
        self.l1_threshold = l1_threshold
        self.l2_threshold = l2_threshold
        self.l3_threshold = l3_threshold

        self.auto_compact = auto_compact
        self._messages: list[ContextMessage] = []
        self._history: list[CompactionReport] = []
        self._token_estimator = token_estimator or self._default_token_estimate

        # Register default strategies per level
        self._strategies: dict[CompactionLevel, list[CompactionStrategy]] = {
            CompactionLevel.L1: [SummarizeOldMessages(), TrimVerboseToolLogs()],
            CompactionLevel.L2: [MergeSimilarChains(), DropResolvedSubtasks()],
            CompactionLevel.L3: [AggressiveDistillation()],
        }

    # ── message management ──────────────────────────────────────────

    def add_message(self, message: ContextMessage) -> "AgentCraft":
        """Add a message, optionally triggering auto-compaction."""
        self._messages.append(message)
        if self.auto_compact and self.should_compact():
            self.compact()
        return self

    def add(self, role: str, content: str, **metadata) -> "AgentCraft":
        """Convenience: create and add a message in one call."""
        return self.add_message(ContextMessage(role=role, content=content, metadata=metadata))

    @property
    def messages(self) -> list[ContextMessage]:
        return list(self._messages)

    @property
    def total_tokens(self) -> int:
        return sum(self._token_estimator(m.content) for m in self._messages)

    @property
    def usage_ratio(self) -> float:
        if self.max_tokens <= 0:
            return 0.0
        return self.total_tokens / self.max_tokens

    def snapshot(self) -> ContextSnapshot:
        return ContextSnapshot(
            messages=list(self._messages),
            total_tokens=self.total_tokens,
            max_tokens=self.max_tokens,
            usage_ratio=self.usage_ratio,
            compaction_level=CompactionLevel.from_threshold(self.usage_ratio),
        )

    def should_compact(self) -> bool:
        """Check if current usage exceeds any compaction threshold."""
        return self.usage_ratio >= self.l1_threshold

    # ── strategies ──────────────────────────────────────────────────

    def register_strategy(self, level: CompactionLevel, strategy: CompactionStrategy) -> "AgentCraft":
        """Add a custom compaction strategy."""
        self._strategies.setdefault(level, []).append(strategy)
        return self

    def clear_strategies(self, level: Optional[CompactionLevel] = None) -> "AgentCraft":
        """Remove all strategies for a level (or all levels)."""
        if level:
            self._strategies[level] = []
        else:
            self._strategies = {lvl: [] for lvl in CompactionLevel}
        return self

    # ── compaction ──────────────────────────────────────────────────

    def compact(self, level: Optional[CompactionLevel] = None) -> CompactionReport:
        """
        Run compaction at the given level (or auto-detect from usage ratio).
        Returns a report of what happened.
        """
        import time

        start = time.perf_counter()

        if level is None:
            level = CompactionLevel.from_threshold(self.usage_ratio)
            if level is None:
                raise RuntimeError(
                    f"Usage ratio {self.usage_ratio:.1%} is below L1 threshold "
                    f"({self.l1_threshold:.0%}). No compaction needed."
                )

        original_tokens = self.total_tokens
        messages_before = len(self._messages)

        strategies = self._strategies.get(level, [])
        techniques_applied: list[str] = []

        for strategy in strategies:
            if strategy.can_apply(level, self._messages):
                self._messages = strategy.apply(level, self._messages)
                techniques_applied.append(strategy.name)

        final_tokens = self.total_tokens
        messages_after = len(self._messages)

        elapsed = (time.perf_counter() - start) * 1000

        report = CompactionReport(
            level=level,
            original_tokens=original_tokens,
            final_tokens=final_tokens,
            tokens_reclaimed=original_tokens - final_tokens,
            messages_before=messages_before,
            messages_after=messages_after,
            techniques_applied=techniques_applied,
            duration_ms=round(elapsed, 1),
        )

        self._history.append(report)
        return report

    # ── history & inspection ────────────────────────────────────────

    @property
    def compaction_history(self) -> list[CompactionReport]:
        return list(self._history)

    @property
    def total_tokens_reclaimed(self) -> int:
        return sum(r.tokens_reclaimed for r in self._history)

    def summary(self) -> str:
        """Full status report as a readable string."""
        snap = self.snapshot()
        level_str = snap.compaction_level.name if snap.compaction_level else "None (below L1)"
        return textwrap.dedent(f"""
        ╔════════════════════════════════════════╗
        ║   AgentCraft Context Status            ║
        ╚════════════════════════════════════════╝
          Messages     : {len(self._messages)}
          Total tokens : {snap.total_tokens} / {self.max_tokens}
          Usage        : {snap.usage_ratio:.1%}
          Level        : {level_str}
          Compactions  : {len(self._history)}
          Tokens reclaimed: {self.total_tokens_reclaimed}
        """).strip()

    # ── internal helpers ────────────────────────────────────────────

    @staticmethod
    def _default_token_estimate(text: str) -> int:
        """Rough token estimate: ~4 chars per token for English text."""
        return max(1, len(text) // 4)
