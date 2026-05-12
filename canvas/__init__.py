"""Canvas module - Agent-driven visual workspace."""

from .manager import CanvasManager, set_current_session_id, get_current_session_id
from .server import CanvasChannel

__all__ = [
    "CanvasManager",
    "CanvasChannel",
    "set_current_session_id",
    "get_current_session_id",
]