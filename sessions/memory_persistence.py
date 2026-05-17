"""Memory persistence for AgentCraft - File-based memory system.

Memory types:
- user: User preferences, role, knowledge level
- feedback: User guidance on behavior ("don't do X", "keep doing Y")
- project: Project context, decisions, constraints
- reference: External resource pointers (Linear, Slack, docs)

Storage: ~/.agentcraft/projects/<project-hash>/memory/
Format: Markdown files with YAML frontmatter
Index: MEMORY.md (limited to 200 lines)
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

import yaml


class MemoryType(Enum):
    """Memory type classification."""
    USER = "user"
    FEEDBACK = "feedback"
    PROJECT = "project"
    REFERENCE = "reference"


@dataclass
class MemoryEntry:
    """A single memory entry."""
    name: str                           # kebab-case identifier
    description: str                    # one-line summary
    type: MemoryType
    content: str                        # full memory content
    created_at: datetime = field(default_factory=datetime.now)

    def to_markdown(self) -> str:
        """Convert to Markdown with YAML frontmatter."""
        frontmatter = {
            "name": self.name,
            "description": self.description,
            "metadata": {
                "type": self.type.value,
            },
            "created_at": self.created_at.isoformat(),
        }
        return f"---\n{yaml.dump(frontmatter, default_flow_style=False)}---\n\n{self.content}"

    @classmethod
    def from_markdown(cls, content: str) -> MemoryEntry:
        """Parse from Markdown with YAML frontmatter."""
        match = re.match(r"^---\n(.*?)\n---\n\n(.*)$", content, re.DOTALL)
        if not match:
            raise ValueError("Invalid memory file format")

        frontmatter = yaml.safe_load(match.group(1))
        body = match.group(2)

        return cls(
            name=frontmatter["name"],
            description=frontmatter["description"],
            type=MemoryType(frontmatter["metadata"]["type"]),
            content=body,
            created_at=datetime.fromisoformat(frontmatter.get("created_at", datetime.now().isoformat())),
        )


def _project_path_hash(project_path: str) -> str:
    """Generate a hash for project path to use as directory name."""
    return hashlib.sha256(project_path.encode()).hexdigest()[:16]


def _get_memory_dir(project_path: str) -> Path:
    """Get memory directory for a project."""
    base_dir = Path.home() / ".agentcraft" / "projects"
    project_hash = _project_path_hash(project_path)
    return base_dir / project_hash / "memory"


class MemoryStore:
    """Memory storage manager."""

    MEMORY_INDEX_FILE = "MEMORY.md"
    MAX_INDEX_LINES = 200

    def __init__(self, project_path: str):
        self._project_path = project_path
        self._memory_dir = _get_memory_dir(project_path)

    def _ensure_dir(self) -> None:
        """Ensure memory directory exists."""
        self._memory_dir.mkdir(parents=True, exist_ok=True)

    def save(self, entry: MemoryEntry) -> Path:
        """Save a memory entry to file."""
        self._ensure_dir()
        file_path = self._memory_dir / f"{entry.name}.md"
        file_path.write_text(entry.to_markdown())
        self._update_index()
        return file_path

    def load(self, name: str) -> MemoryEntry | None:
        """Load a memory entry by name."""
        file_path = self._memory_dir / f"{name}.md"
        if not file_path.exists():
            return None
        return MemoryEntry.from_markdown(file_path.read_text())

    def list(self) -> list[MemoryEntry]:
        """List all memory entries."""
        if not self._memory_dir.exists():
            return []
        entries = []
        for file_path in self._memory_dir.glob("*.md"):
            if file_path.name == self.MEMORY_INDEX_FILE:
                continue
            try:
                entries.append(MemoryEntry.from_markdown(file_path.read_text()))
            except ValueError:
                continue  # Skip invalid files
        return sorted(entries, key=lambda e: e.created_at, reverse=True)

    def delete(self, name: str) -> bool:
        """Delete a memory entry by name."""
        file_path = self._memory_dir / f"{name}.md"
        if not file_path.exists():
            return False
        file_path.unlink()
        self._update_index()
        return True

    def link(self, source: str, target: str) -> bool:
        """Add a link from source memory to target memory.

        Links are stored as [[target-name]] in memory content.
        """
        source_entry = self.load(source)
        if source_entry is None:
            return False

        # Add link if not already present
        link_pattern = f"[[{target}]]"
        if link_pattern not in source_entry.content:
            source_entry.content = source_entry.content.rstrip() + f"\n\nRelated: [[{target}]]"
            self.save(source_entry)
        return True

    def _update_index(self) -> None:
        """Update MEMORY.md index file."""
        entries = self.list()
        index_lines = ["# Memory Index\n\n"]

        for entry in entries:
            line = f"- [{entry.name}]({entry.name}.md) — {entry.description}\n"
            index_lines.append(line)

        # Truncate if exceeds limit (leave room for truncation marker)
        max_lines = self.MAX_INDEX_LINES - 3  # Header + 2 blank lines + truncation marker
        if len(index_lines) > max_lines:
            index_lines = index_lines[:max_lines]
            index_lines.append("\n... (older entries truncated)\n")

        index_content = "".join(index_lines)
        index_path = self._memory_dir / self.MEMORY_INDEX_FILE
        index_path.write_text(index_content)

    def get_index_content(self) -> str:
        """Get MEMORY.md content for loading into context."""
        index_path = self._memory_dir / self.MEMORY_INDEX_FILE
        if index_path.exists():
            return index_path.read_text()
        return ""

    def get_all_content(self) -> str:
        """Get all memory content concatenated (for full context load)."""
        entries = self.list()
        if not entries:
            return ""
        parts = [self.get_index_content()]
        for entry in entries:
            parts.append(f"\n---\n## {entry.name}\n\n{entry.content}")
        return "\n".join(parts)


class MemoryExtractor:
    """LLM-based memory extraction from conversation."""

    EXTRACTION_PROMPT = """Analyze the conversation and extract potential memories.

Look for:
1. User preferences/knowledge (user type): "I'm a senior Go engineer", "I prefer X over Y"
2. Behavioral guidance (feedback type): "don't mock the database", "use single-file solutions"
3. Project context/decisions (project type): "auth rewrite is for compliance", "merge freeze starts Thursday"

Output JSON format:
{
  "memories": [
    {
      "type": "user|feedback|project|reference",
      "name": "kebab-case-name",
      "description": "one-line summary",
      "content": "Full content with **Why:** and **How to apply:** for feedback/project types"
    }
  ]
}

If nothing notable found, return {"memories": []}

Conversation:
{conversation}
"""

    def __init__(self, llm_client: Any):
        self._client = llm_client

    def extract(self, conversation: str) -> list[dict]:
        """Extract memories from conversation using LLM."""
        prompt = self.EXTRACTION_PROMPT.format(conversation=conversation)

        try:
            response = self._client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            import json
            result = json.loads(response.choices[0].message.content)
            return result.get("memories", [])
        except Exception:
            return []

    def save_extracted(self, store: MemoryStore, memories: list[dict]) -> list[str]:
        """Save extracted memories to store."""
        saved_names = []
        for mem in memories:
            entry = MemoryEntry(
                name=mem["name"],
                description=mem["description"],
                type=MemoryType(mem["type"]),
                content=mem["content"],
            )
            store.save(entry)
            saved_names.append(entry.name)
        return saved_names


__all__ = ["MemoryType", "MemoryEntry", "MemoryStore", "MemoryExtractor"]