"""SessionManager — CRUD for sessions and messages."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from sessions.models import (
    Session,
    Message,
    init_db,
    now_iso,
    new_id,
)
from sessions.tokens import TokenCalculator
from sessions.memory import SlidingWindowStrategy


def _default_db_path() -> str:
    return os.path.expanduser("~/.agentcraft/sessions.db")


class SessionManager:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or _default_db_path()
        self._conn = init_db(self.db_path)

    # ===== Sessions =====

    def create_session(
        self,
        name: str,
        model: str = "deepseek-chat",
        system_prompt: str | None = None,
        skills: str = "",
        context_window: int = 64000,
        memory_strategy: str = "sliding_window",
    ) -> Session:
        sid = new_id()
        now = now_iso()
        self._conn.execute(
            "INSERT INTO sessions (id, name, model, system_prompt, skills, "
            "context_window, memory_strategy, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (sid, name, model, system_prompt, skills, context_window, memory_strategy, now, now),
        )
        self._conn.commit()
        return Session(
            id=sid, name=name, model=model,
            system_prompt=system_prompt, skills=skills,
            context_window=context_window, memory_strategy=memory_strategy,
            created_at=now, updated_at=now,
        )

    def get_session(self, session_id: str) -> Session | None:
        row = self._conn.execute(
            "SELECT * FROM sessions WHERE id=?", (session_id,)
        ).fetchone()
        return self._row_to_session(row) if row else None

    def list_sessions(self, status: str = "active") -> list[Session]:
        rows = self._conn.execute(
            "SELECT * FROM sessions WHERE status=? ORDER BY updated_at DESC",
            (status,),
        ).fetchall()
        return [self._row_to_session(r) for r in rows]

    def update_session(self, session_id: str, **fields: Any) -> Session | None:
        session = self.get_session(session_id)
        if not session:
            return None

        allowed = {"name", "model", "system_prompt", "status", "skills", "context_window", "memory_strategy"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return session

        updates["updated_at"] = now_iso()
        set_clause = ", ".join(f"{k}=?" for k in updates)
        values = list(updates.values()) + [session_id]

        self._conn.execute(
            f"UPDATE sessions SET {set_clause} WHERE id=?",
            values,
        )
        self._conn.commit()
        return self.get_session(session_id)

    def delete_session(self, session_id: str) -> bool:
        cursor = self._conn.execute(
            "DELETE FROM sessions WHERE id=?", (session_id,)
        )
        self._conn.commit()
        return cursor.rowcount > 0

    # ===== Messages =====

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        tool_calls: str | None = None,
        tool_call_id: str | None = None,
        name: str | None = None,
    ) -> Message:
        mid = new_id()
        now = now_iso()

        # Calculate token count for this message
        session = self.get_session(session_id)
        calculator = TokenCalculator(session.model if session else "deepseek-chat")
        msg_dict = {"role": role, "content": content}
        if tool_calls:
            msg_dict["tool_calls"] = json.loads(tool_calls)
        if tool_call_id:
            msg_dict["tool_call_id"] = tool_call_id
        if name:
            msg_dict["name"] = name
        token_count = calculator.count_message(msg_dict)

        self._conn.execute(
            "INSERT INTO messages (id, session_id, role, content, tool_calls, "
            "tool_call_id, name, created_at, token_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (mid, session_id, role, content, tool_calls, tool_call_id, name, now, token_count),
        )
        # Update session counters
        self._conn.execute(
            "UPDATE sessions SET message_count = message_count + 1, "
            "token_count = token_count + ?, updated_at = ? WHERE id = ?",
            (token_count, now, session_id),
        )
        self._conn.commit()
        return Message(
            id=mid, session_id=session_id, role=role,
            content=content, tool_calls=tool_calls,
            tool_call_id=tool_call_id, name=name,
            created_at=now, token_count=token_count,
        )

    def get_messages(
        self, session_id: str, limit: int = 50
    ) -> list[Message]:
        rows = self._conn.execute(
            "SELECT * FROM messages WHERE session_id=? ORDER BY created_at ASC LIMIT ?",
            (session_id, limit),
        ).fetchall()
        return [self._row_to_message(r) for r in rows]

    def get_messages_openai(
        self, session_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Return messages in OpenAI-compatible format for LLM calls."""
        return [m.to_openai_format() for m in self.get_messages(session_id, limit)]

    def clear_messages(self, session_id: str) -> None:
        self._conn.execute(
            "DELETE FROM messages WHERE session_id=?", (session_id,)
        )
        self._conn.execute(
            "UPDATE sessions SET message_count=0, updated_at=? WHERE id=?",
            (now_iso(), session_id),
        )
        self._conn.commit()

    def count_tokens(self, session_id: str) -> int:
        """Count total tokens in session using TokenCalculator."""
        session = self.get_session(session_id)
        if not session:
            return 0
        # Use stored token_count if available
        if session.token_count > 0:
            return session.token_count
        # Calculate from messages
        calculator = TokenCalculator(session.model)
        messages = self.get_messages_openai(session_id, limit=1000)
        return calculator.count_messages(messages)

    # ===== Memory Management =====

    def get_messages_with_limit(
        self, session_id: str, max_tokens: int = 64000
    ) -> list[dict[str, Any]]:
        """Get messages truncated to fit within token limit."""
        session = self.get_session(session_id)
        if not session:
            return []

        calculator = TokenCalculator(session.model)
        messages = self.get_messages_openai(session_id, limit=1000)

        if not messages:
            return []

        strategy = SlidingWindowStrategy()
        return strategy.truncate_messages(messages, max_tokens, calculator)

    # ===== Helpers =====

    @staticmethod
    def _row_to_session(row: tuple) -> Session:
        return Session(
            id=row[0], name=row[1], model=row[2],
            system_prompt=row[3], created_at=row[4],
            updated_at=row[5], message_count=row[6],
            token_count=row[7], status=row[8],
            skills=row[9] if len(row) > 9 else "",
            context_window=row[10] if len(row) > 10 else 64000,
            memory_strategy=row[11] if len(row) > 11 else "sliding_window",
        )

    @staticmethod
    def _row_to_message(row: tuple) -> Message:
        return Message(
            id=row[0], session_id=row[1], role=row[2],
            content=row[3], tool_calls=row[4],
            tool_call_id=row[5], name=row[6],
            created_at=row[7],
            token_count=row[8] if len(row) > 8 else 0,
        )
