"""
AgentCraft — Fork Mechanism

Enables spawning child AgentCraft instances that inherit parent context.
Supports deep copy, shallow reference, and compact-on-fork strategies.
"""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .compactor import AgentCraft, CompactionLevel


@dataclass
class ForkRecord:
    """Records a fork event in the parent's history."""
    child_id: str
    generation: int
    fork_type: str
    compaction_level: Optional[str] = None
    parent_messages_at_fork: int = 0
    child_messages_initial: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def summary(self) -> str:
        base = f"[Fork -> {self.child_id}] type={self.fork_type}, gen={self.generation}, parent_msgs={self.parent_messages_at_fork}"
        if self.compaction_level:
            base += f", compacted_at={self.compaction_level}"
        return base


class ForkError(Exception):
    pass


class Fork:
    """Fork context manager. Usage: with Fork.deep(parent) as child: ..."""

    _fork_counter: int = 0

    def __init__(self, parent, child_max_tokens=None, fork_type="deep",
                 compact_level=None, inherit_history=True):
        from .compactor import AgentCraft as AC
        self.parent = parent
        self.child_max_tokens = child_max_tokens or parent.max_tokens
        self.fork_type = fork_type
        self.compact_level = compact_level
        self.inherit_history = inherit_history
        self.child = None

    @classmethod
    def deep(cls, parent, child_max_tokens=None, compact_level=None):
        return cls(parent, child_max_tokens, "deep", compact_level)

    @classmethod
    def shallow(cls, parent, child_max_tokens=None):
        return cls(parent, child_max_tokens, "shallow")

    @classmethod
    def compact_on_fork(cls, parent, level, child_max_tokens=None):
        return cls(parent, child_max_tokens, "deep", compact_level=level)

    def __enter__(self):
        from .compactor import AgentCraft as AC
        Fork._fork_counter += 1
        child_id = f"fork_{Fork._fork_counter}_gen_{self.parent.generation + 1}"

        self.child = AC(
            max_tokens=self.child_max_tokens,
            l1_threshold=self.parent.l1_threshold,
            l2_threshold=self.parent.l2_threshold,
            l3_threshold=self.parent.l3_threshold,
            auto_compact=self.parent.auto_compact,
            token_estimator=self.parent._token_estimator,
        )

        if self.inherit_history:
            if self.fork_type == "deep":
                self.child._messages = copy.deepcopy(self.parent._messages)
                self.child._history = copy.deepcopy(self.parent._history)
                self.child._strategies = copy.deepcopy(self.parent._strategies)
            elif self.fork_type == "shallow":
                self.child._messages = self.parent._messages
                self.child._history = self.parent._history
                self.child._strategies = self.parent._strategies
            else:
                raise ForkError(f"Unknown fork_type: {self.fork_type}")

        self.child._parent_id = self.parent._agent_id
        self.child._generation = self.parent.generation + 1
        self.child._fork_id = child_id

        if self.compact_level is not None:
            self.child.compact(level=self.compact_level)

        record = ForkRecord(
            child_id=child_id,
            generation=self.child._generation,
            fork_type=self.fork_type,
            compaction_level=self.compact_level.name if self.compact_level else None,
            parent_messages_at_fork=len(self.parent._messages),
            child_messages_initial=len(self.child._messages),
        )
        self.parent._forks.append(record)
        return self.child

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


def enable_fork(agentcraft_cls):
    """Monkey-patch AgentCraft with fork capabilities."""
    orig_init = agentcraft_cls.__init__

    def _forked_init(self, *args, **kwargs):
        orig_init(self, *args, **kwargs)
        self._agent_id = str(uuid.uuid4())[:8]
        self._generation = 0
        self._parent_id = None
        self._fork_id = None
        self._forks = []

    agentcraft_cls.__init__ = _forked_init

    def fork_deep(self, child_max_tokens=None, compact_level=None):
        with Fork.deep(self, child_max_tokens, compact_level) as child:
            return child

    def fork_shallow(self, child_max_tokens=None):
        with Fork.shallow(self, child_max_tokens) as child:
            return child

    def fork_compacted(self, level):
        with Fork.compact_on_fork(self, level) as child:
            return child

    @property
    def fork_history(self):
        return list(self._forks)

    @property
    def generation(self):
        return self._generation

    @property
    def parent_id(self):
        return self._parent_id

    @property
    def fork_id(self):
        return self._fork_id

    def lineage(self):
        return [{"agent_id": self._agent_id, "generation": self._generation, "fork_id": self._fork_id}]

    agentcraft_cls.fork_deep = fork_deep
    agentcraft_cls.fork_shallow = fork_shallow
    agentcraft_cls.fork_compacted = fork_compacted
    agentcraft_cls.fork_history = property(fork_history)
    agentcraft_cls.generation = property(generation)
    agentcraft_cls.parent_id = property(parent_id)
    agentcraft_cls.fork_id = property(fork_id)
    agentcraft_cls.lineage = lineage

    return agentcraft_cls


# Auto-enable when imported
from .compactor import AgentCraft
enable_fork(AgentCraft)
