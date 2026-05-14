"""ACP Types - 核心类型定义."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


class AcpEventType(enum.Enum):
    """子Agent事件类型."""
    STARTED = "started"           # 子Agent启动
    PROGRESS = "progress"         # 执行进度
    TOOL_CALL = "tool_call"       # Tool调用
    TOOL_RESULT = "tool_result"   # Tool结果
    CONTENT = "content"           # 内容输出
    COMPLETED = "completed"       # 执行完成
    FAILED = "failed"             # 执行失败
    TIMEOUT = "timeout"           # 超时


@dataclass
class AcpEvent:
    """子Agent事件."""
    child_id: str                 # 子Agent ID
    event_type: AcpEventType      # 事件类型
    data: Any                     # 事件数据
    timestamp: float = field(default_factory=lambda: 0.0)

    def __post_init__(self):
        import time
        if self.timestamp == 0.0:
            self.timestamp = time.time()


@dataclass
class AcpConfig:
    """ACP配置."""
    max_children: int = 10        # 最多同时运行的子Agent数量
    default_timeout: int = 180    # 默认超时时间（秒）
    context_inheritance_limit: int = 32000  # 继承上下文的token上限
    enable_parallel: bool = True  # 是否允许并行执行
    recursion_protection: bool = True  # 递归保护（子Agent不能再spawn）


class AcpSessionState(enum.Enum):
    """子Agent会话状态."""
    IDLE = "idle"          # 等待中
    RUNNING = "running"    # 正在执行
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"      # 失败
    TIMEOUT = "timeout"    # 超时


@dataclass
class ChildAgentHandle:
    """子Agent句柄."""
    child_id: str                 # 子Agent ID
    task: str                     # 任务描述
    agent_type: str               # Agent类型
    state: AcpSessionState        # 当前状态
    started_at: float             # 启动时间
    result: str | None = None     # 执行结果
    error: str | None = None      # 错误信息

    def elapsed_seconds(self) -> float:
        """计算已运行时间."""
        import time
        return time.time() - self.started_at

    def is_terminal(self) -> bool:
        """是否已结束."""
        return self.state in (
            AcpSessionState.COMPLETED,
            AcpSessionState.FAILED,
            AcpSessionState.TIMEOUT,
        )