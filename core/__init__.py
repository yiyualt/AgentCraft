"""Core module - shared logic for CLI and Gateway.

This module contains the core components:
- Tool Loop: Agent execution loop
- Executor: Tool execution with concurrency control
- Concurrency: Safety classification
- Prompt builder: System prompt generation
- Memory loader: Task-based retrieval
- LLM Queue: Request queue for concurrent handling
- Stream Handler: Provider to SSE bridge
"""

from core.prompt_builder import PromptBuilder, build_system_prompt
from core.memory_loader import MemoryLoader, load_relevant_memories
from core.tool_loop import run_tool_loop, clean_orphan_tool_messages
from core.executor import ToolExecutor, ToolResult
from core.concurrency import is_safe, SAFE_TOOLS, UNSAFE_TOOLS
from core.llm_queue import LLMRequestQueue, QueuedRequest, QueueMetrics, RequestStatus
from core.stream_handler import StreamHandler

__all__ = [
    # Tool Loop
    "run_tool_loop",
    "clean_orphan_tool_messages",
    # Executor
    "ToolExecutor",
    "ToolResult",
    # Concurrency
    "is_safe",
    "SAFE_TOOLS",
    "UNSAFE_TOOLS",
    # Prompt & Memory
    "PromptBuilder",
    "build_system_prompt",
    "MemoryLoader",
    "load_relevant_memories",
    # LLM Queue
    "LLMRequestQueue",
    "QueuedRequest",
    "QueueMetrics",
    "RequestStatus",
    # Stream Handler
    "StreamHandler",
]