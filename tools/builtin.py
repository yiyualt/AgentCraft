"""Built-in tools aggregator.

Imports all tool modules to register them with the default ToolRegistry.
"""

from __future__ import annotations

# Import all tool modules to register their tools
from tools.utility_tools import *  # noqa: F401,F403 — current_time, calculator
from tools.file_tools import *     # noqa: F401,F403 — Read, Write, Edit
from tools.search_tools import *   # noqa: F401,F403 — Glob, Grep
from tools.shell_tools import *    # noqa: F401,F403 — Bash
from tools.web_tools import *      # noqa: F401,F403 — WebFetch, WebSearch
from tools.agent_tools import *    # noqa: F401,F403 — Agent
from tools.token_tools import *    # noqa: F401,F403 — CountTokens

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
]