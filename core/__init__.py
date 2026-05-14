"""Core module - shared logic for CLI and Gateway.

This module contains the shared components between CLI and Gateway:
- System prompt building
- Memory loading (task-based retrieval)
- Tool execution coordination
"""

from core.prompt_builder import PromptBuilder, build_system_prompt
from core.memory_loader import MemoryLoader, load_relevant_memories

__all__ = [
    "PromptBuilder",
    "build_system_prompt",
    "MemoryLoader",
    "load_relevant_memories",
]