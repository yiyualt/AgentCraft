"""Session and Message data models."""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class Session:
    id: str
    name: str
    model: str = "deepseek-chat"
    system_prompt: str | None = None
    created_at: str = ""
    updated_at: str = ""
    message_count: int = 0
    token_count: int = 0
    status: str = "active"
    skills: str = ""
    context_window: int = 64000
    memory_strategy: str = "sliding_window"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "model": self.model,
            "system_prompt": self.system_prompt,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "message_count": self.message_count,
            "token_count": self.token_count,
            "status": self.status,
            "skills": self.skills,
            "context_window": self.context_window,
            "memory_strategy": self.memory_strategy,
        }


@dataclass
class Message:
    id: str
    session_id: str
    role: str  # user | assistant | system | tool
    content: str
    tool_calls: str | None = None  # JSON string
    tool_call_id: str | None = None
    name: str | None = None  # tool name for tool role
    created_at: str = ""
    token_count: int = 0

    def to_openai_format(self) -> dict[str, Any]:
        """Convert to OpenAI-compatible message dict."""
        msg: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_calls:
            import json
            msg["tool_calls"] = json.loads(self.tool_calls)
        if self.tool_call_id:
            msg["tool_call_id"] = self.tool_call_id
        if self.name:
            msg["name"] = self.name
        return msg


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return uuid.uuid4().hex[:12]


SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT 'deepseek-chat',
    system_prompt TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    message_count INTEGER NOT NULL DEFAULT 0,
    token_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    skills TEXT NOT NULL DEFAULT '',
    context_window INTEGER NOT NULL DEFAULT 64000,
    memory_strategy TEXT NOT NULL DEFAULT 'sliding_window'
);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    tool_calls TEXT,
    tool_call_id TEXT,
    name TEXT,
    created_at TEXT NOT NULL,
    token_count INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, created_at);
"""


def init_db(db_path: str) -> sqlite3.Connection:
    """Initialize the SQLite database and return a connection."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)

    # Migrate existing databases
    # 1. skills column
    try:
        conn.execute("SELECT skills FROM sessions LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE sessions ADD COLUMN skills TEXT NOT NULL DEFAULT ''")

    # 2. context_window column
    try:
        conn.execute("SELECT context_window FROM sessions LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE sessions ADD COLUMN context_window INTEGER NOT NULL DEFAULT 64000")

    # 3. memory_strategy column
    try:
        conn.execute("SELECT memory_strategy FROM sessions LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE sessions ADD COLUMN memory_strategy TEXT NOT NULL DEFAULT 'sliding_window'")

    # 4. token_count column in messages
    try:
        conn.execute("SELECT token_count FROM messages LIMIT 1")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE messages ADD COLUMN token_count INTEGER NOT NULL DEFAULT 0")

    conn.commit()
    return conn


__all__ = ["Session", "Message", "now_iso", "new_id", "init_db", "SCHEMA"]
