"""Core module - 底层基础设施.

This module contains the底层 components:
- Vector Memory: SQLite + FTS5 + Vector embedding storage
- Tokens: Token counting using tiktoken
- Executor: Tool execution with concurrency control
- Concurrency: Safety classification
- LLM Queue: Request queue for concurrent handling
- Stream Handler: Provider to SSE bridge
"""

from core.vector_memory import (
    EmbeddingModel,
    MockEmbeddingModel,
    LocalEmbeddingModel,
    RemoteEmbeddingModel,
    VectorMemoryStore,
    MemoryEntry,
)
from core.tokens import TokenCalculator
from core.executor import ToolExecutor, ToolResult
from core.concurrency import is_safe, SAFE_TOOLS, UNSAFE_TOOLS
from core.llm_queue import LLMRequestQueue, QueuedRequest, QueueMetrics, RequestStatus
from core.stream_handler import StreamHandler

__all__ = [
    # Vector Memory (底层存储)
    "EmbeddingModel",
    "MockEmbeddingModel",
    "LocalEmbeddingModel",
    "RemoteEmbeddingModel",
    "VectorMemoryStore",
    "MemoryEntry",
    # Tokens (底层计算)
    "TokenCalculator",
    # Executor & Concurrency
    "ToolExecutor",
    "ToolResult",
    "is_safe",
    "SAFE_TOOLS",
    "UNSAFE_TOOLS",
    # LLM Queue
    "LLMRequestQueue",
    "QueuedRequest",
    "QueueMetrics",
    "RequestStatus",
    # Stream Handler
    "StreamHandler",
]