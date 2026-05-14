"""ACP - Agent Control Plane.

管理子Agent的派发、执行、监控和结果聚合。

核心功能:
- spawn_child(): 创建并派发子Agent
- parent_stream(): 聚合所有子Agent的实时输出
- 父子通信: send_to_child, broadcast
- 限制控制: 子Agent数量、超时、上下文大小
- 递归保护: 子Agent不能再spawn子Agent
"""

from __future__ import annotations

from acp.control_plane import AgentControlPlane
from acp.types import (
    AcpConfig,
    AcpSessionState,
    AcpEvent,
    AcpEventType,
    ChildAgentHandle,
)

__all__ = [
    "AgentControlPlane",
    "ChildAgentHandle",
    "AcpConfig",
    "AcpSessionState",
    "AcpEvent",
    "AcpEventType",
]