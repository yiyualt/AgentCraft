"""
AgentCraft — Context Memory Compaction System

3-Level compaction for LLM context window management:
  L1 (60%)  → Light: summarize old messages, trim verbose logs
  L2 (80%)  → Medium: merge chains, drop resolved subtasks
  L3 (90%)  → Deep: aggressive distillation, keep only decisions + state
"""

from .compactor import AgentCraft, CompactionLevel, ContextMessage, ContextSnapshot, CompactionReport

__all__ = [
    "AgentCraft",
    "CompactionLevel",
    "ContextMessage",
    "ContextSnapshot",
    "CompactionReport",
]
