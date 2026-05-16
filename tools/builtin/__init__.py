"""Built-in tools aggregator.

Imports all tool modules to register them with the default ToolRegistry.
"""

from __future__ import annotations

# Import all tool modules to register their tools
from .utility_tools import *  # noqa: F401,F403 — current_time, calculator
from .file_tools import *     # noqa: F401,F403 — Read, Write, Edit
from .search_tools import *   # noqa: F401,F403 — Glob, Grep
from .shell_tools import *    # noqa: F401,F403 — Bash
from .web_tools import *      # noqa: F401,F403 — WebFetch, WebSearch
from .agent_tools import *    # noqa: F401,F403 — Agent
from .token_tools import *    # noqa: F401,F403 — CountTokens
from .memory_tools import *   # noqa: F401,F403 — remember, forget, recall
from .canvas_tools import *   # noqa: F401,F403 — canvas_update, canvas_interact

__all__ = [
    "current_time",
    "calculator",
    "read_file",
    "write_file",
    "edit_file",
    "glob_files",
    "grep_files",
    "bash",
    "web_fetch",
    "web_search",
    "agent_delegate",
    "count_tokens",
    "canvas_update",
    "canvas_interact",
]