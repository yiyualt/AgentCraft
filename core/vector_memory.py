"""Vector Memory Store - SQLite + FTS5 + Vector embedding semantic search.

Storage:
- memories table: id, name, type, content, embedding (BLOB), created_at
- memories_fts: FTS5 virtual table for full-text search
- Vector similarity computed in Python (numpy)

Search modes:
- fts: keyword matching
- vector: semantic similarity
- hybrid: combined scoring
"""

from __future__ import annotations

import json
import sqlite3
import time
import numpy as np
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class EmbeddingModel(Protocol):
    """Protocol for embedding models."""

    def embed(self, text: str) -> list[float]:
        """Generate embedding vector for text."""
        ...

    def dimension(self) -> int:
        """Return embedding dimension."""
        ...


class MockEmbeddingModel:
    """Mock embedding model for testing (uses hash-based pseudo vectors)."""

    def __init__(self, dimension: int = 384):
        self._dimension = dimension

    def embed(self, text: str) -> list[float]:
        """Generate pseudo embedding from text hash."""
        import hashlib
        # Use text hash to generate deterministic pseudo-vector
        hash_bytes = hashlib.sha256(text.encode()).digest()
        # Convert to floats
        floats = []
        for i in range(self._dimension):
            # Use bytes cyclically
            byte_val = hash_bytes[i % len(hash_bytes)]
            # Normalize to [-1, 1]
            floats.append((byte_val - 128) / 128.0)
        return floats

    def dimension(self) -> int:
        """Return embedding dimension."""
        return self._dimension


class LocalEmbeddingModel:
    """Local embedding model using sentence-transformers."""

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(model_name)
            self._dimension = self._model.get_sentence_embedding_dimension()
            self._available = True
        except ImportError:
            # Fall back to mock if sentence-transformers not available
            self._model = None
            self._dimension = 384
            self._available = False

    def embed(self, text: str) -> list[float]:
        """Generate embedding for text."""
        if self._available and self._model:
            embedding = self._model.encode(text, convert_to_numpy=True)
            return embedding.tolist()
        else:
            # Use mock when not available
            return MockEmbeddingModel(self._dimension).embed(text)

    def dimension(self) -> int:
        """Return embedding dimension."""
        return self._dimension


class RemoteEmbeddingModel:
    """Remote embedding model using OpenAI API."""

    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        base_url: str | None = None,
    ):
        from openai import OpenAI
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        # text-embedding-3-small has 1536 dimensions
        self._dimension = 1536 if "small" in model else 3072

    def embed(self, text: str) -> list[float]:
        """Generate embedding for text via API."""
        response = self._client.embeddings.create(
            input=text,
            model=self._model,
        )
        return response.data[0].embedding

    def dimension(self) -> int:
        """Return embedding dimension."""
        return self._dimension


@dataclass
class MemoryEntry:
    """A memory entry."""
    id: int
    name: str
    type: str  # user/feedback/project/reference
    content: str
    embedding: list[float] | None = None
    similarity: float = 0.0  # search result score
    created_at: float = 0.0


class VectorMemoryStore:
    """SQLite + FTS5 + Vector embedding memory store."""

    DEFAULT_DB_PATH = Path.home() / ".agentcraft" / "memory.db"

    def __init__(
        self,
        db_path: Path | str | None = None,
        embedding_model: EmbeddingModel | None = None,
    ):
        self._db_path = Path(db_path) if db_path else self.DEFAULT_DB_PATH
        self._embedding_model = embedding_model or LocalEmbeddingModel()
        self._dimension = self._embedding_model.dimension()
        self._init_database()

    def _get_connection(self) -> sqlite3.Connection:
        """Get SQLite connection."""
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_database(self):
        """Initialize SQLite database with FTS5."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = self._get_connection()

        # Main table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                type TEXT NOT NULL,
                content TEXT NOT NULL,
                embedding BLOB,
                created_at REAL NOT NULL
            )
        """)

        # FTS5 virtual table with trigram tokenizer (better for Chinese)
        # Note: trigram requires SQLite 3.34+
        try:
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
                USING fts5(
                    name,
                    content,
                    tokenize='trigram',
                    content='memories',
                    content_rowid='id'
                )
            """)
        except sqlite3.OperationalError:
            # Fallback to unicode61 if trigram not available
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
                USING fts5(
                    name,
                    content,
                    content='memories',
                    content_rowid='id'
                )
            """)

        # Index on type for filtering
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_memories_type
            ON memories(type)
        """)

        conn.commit()
        conn.close()

    def save(self, name: str, type: str, content: str) -> int:
        """Save a memory entry with embedding."""
        # Generate embedding
        embedding = self._embedding_model.embed(content)
        embedding_blob = np.array(embedding, dtype=np.float32).tobytes()

        conn = self._get_connection()

        # Check if exists (update or insert)
        existing = conn.execute(
            "SELECT id FROM memories WHERE name = ?", (name,)
        ).fetchone()

        if existing:
            # Update
            conn.execute("""
                UPDATE memories
                SET type = ?, content = ?, embedding = ?, created_at = ?
                WHERE name = ?
            """, (type, content, embedding_blob, time.time(), name))
            memory_id = existing["id"]
        else:
            # Insert
            cursor = conn.execute("""
                INSERT INTO memories (name, type, content, embedding, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (name, type, content, embedding_blob, time.time()))
            memory_id = cursor.lastrowid

        # Update FTS (trigger should handle this, but manual for reliability)
        conn.execute("""
            INSERT OR REPLACE INTO memories_fts (rowid, name, content)
            VALUES (?, ?, ?)
        """, (memory_id, name, content))

        conn.commit()
        conn.close()

        return memory_id

    def load(self, name: str) -> MemoryEntry | None:
        """Load a memory by name."""
        conn = self._get_connection()

        row = conn.execute("""
            SELECT id, name, type, content, embedding, created_at
            FROM memories WHERE name = ?
        """, (name,)).fetchone()

        conn.close()

        if row is None:
            return None

        embedding = self._decode_embedding(row["embedding"])
        return MemoryEntry(
            id=row["id"],
            name=row["name"],
            type=row["type"],
            content=row["content"],
            embedding=embedding,
            created_at=row["created_at"],
        )

    def list(self, type: str | None = None, limit: int = 100) -> list[MemoryEntry]:
        """List all memories, optionally filtered by type."""
        conn = self._get_connection()

        if type:
            rows = conn.execute("""
                SELECT id, name, type, content, created_at
                FROM memories WHERE type = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (type, limit)).fetchall()
        else:
            rows = conn.execute("""
                SELECT id, name, type, content, created_at
                FROM memories
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,)).fetchall()

        conn.close()

        return [
            MemoryEntry(
                id=row["id"],
                name=row["name"],
                type=row["type"],
                content=row["content"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def delete(self, name: str) -> bool:
        """Delete a memory by name."""
        conn = self._get_connection()

        row = conn.execute(
            "SELECT id FROM memories WHERE name = ?", (name,)
        ).fetchone()

        if row is None:
            conn.close()
            return False

        memory_id = row["id"]

        # Delete from main table
        conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))

        # Delete from FTS
        conn.execute("DELETE FROM memories_fts WHERE rowid = ?", (memory_id,))

        conn.commit()
        conn.close()

        return True

    def search_fts(self, query: str, limit: int = 10) -> list[MemoryEntry]:
        """Full-text search (keyword matching)."""
        conn = self._get_connection()

        # FTS5 MATCH query - need to handle special characters
        # Use simple token matching for Chinese
        try:
            rows = conn.execute("""
                SELECT m.id, m.name, m.type, m.content, m.created_at
                FROM memories m
                JOIN memories_fts fts ON m.id = fts.rowid
                WHERE memories_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """, (query, limit)).fetchall()
        except sqlite3.OperationalError:
            # FTS may fail on special chars, fallback to LIKE
            rows = conn.execute("""
                SELECT id, name, type, content, created_at
                FROM memories
                WHERE content LIKE ? OR name LIKE ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (f'%{query}%', f'%{query}%', limit)).fetchall()

        conn.close()

        return [
            MemoryEntry(
                id=row["id"],
                name=row["name"],
                type=row["type"],
                content=row["content"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def search_vector(self, query: str, limit: int = 10) -> list[MemoryEntry]:
        """Vector search (semantic similarity)."""
        # Generate query embedding
        query_embedding = np.array(
            self._embedding_model.embed(query),
            dtype=np.float32
        )

        conn = self._get_connection()

        # Fetch all embeddings (for pure Python similarity computation)
        rows = conn.execute("""
            SELECT id, name, type, content, embedding, created_at
            FROM memories
            WHERE embedding IS NOT NULL
        """).fetchall()

        conn.close()

        # Compute similarities
        results = []
        for row in rows:
            embedding = self._decode_embedding(row["embedding"])
            if embedding is None:
                continue

            # Cosine similarity
            similarity = self._cosine_similarity(query_embedding, np.array(embedding))

            results.append(MemoryEntry(
                id=row["id"],
                name=row["name"],
                type=row["type"],
                content=row["content"],
                embedding=embedding,
                similarity=similarity,
                created_at=row["created_at"],
            ))

        # Sort by similarity (descending)
        results.sort(key=lambda e: e.similarity, reverse=True)

        return results[:limit]

    def search_hybrid(
        self,
        query: str,
        limit: int = 10,
        fts_weight: float = 0.4,
        vector_weight: float = 0.6,
    ) -> list[MemoryEntry]:
        """Hybrid search (FTS + Vector combined)."""
        # Get FTS results
        fts_results = self.search_fts(query, limit * 2)
        fts_scores: dict[int, float] = {}
        fts_entries: dict[int, MemoryEntry] = {}

        for i, entry in enumerate(fts_results):
            # Rank score: 1.0 for first, decreasing for others
            fts_scores[entry.id] = fts_weight * (1.0 - i / len(fts_results))
            fts_entries[entry.id] = entry

        # Get Vector results
        vec_results = self.search_vector(query, limit * 2)
        vec_scores: dict[int, float] = {}
        vec_entries: dict[int, MemoryEntry] = {}

        for entry in vec_results:
            vec_scores[entry.id] = vector_weight * entry.similarity
            vec_entries[entry.id] = entry

        # Combine scores
        all_ids = set(fts_scores.keys()) | set(vec_scores.keys())
        combined: list[tuple[int, float]] = []

        for id in all_ids:
            score = fts_scores.get(id, 0.0) + vec_scores.get(id, 0.0)
            combined.append((id, score))

        # Sort by combined score
        combined.sort(key=lambda x: x[1], reverse=True)

        # Build final results
        final_results: list[MemoryEntry] = []
        for id, score in combined[:limit]:
            entry = fts_entries.get(id) or vec_entries.get(id)
            if entry:
                entry.similarity = score
                final_results.append(entry)

        return final_results

    def _decode_embedding(self, blob: bytes | None) -> list[float] | None:
        """Decode embedding from BLOB."""
        if blob is None:
            return None
        return np.frombuffer(blob, dtype=np.float32).tolist()

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two vectors."""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return float(np.dot(a, b) / (norm_a * norm_b))

    def get_index_content(self) -> str:
        """Get memory index for context loading (similar to MEMORY.md)."""
        entries = self.list(limit=200)

        if not entries:
            return "# Memory Index\n\nNo memories saved.\n"

        lines = ["# Memory Index\n\n"]
        for entry in entries:
            # Truncate content for display
            desc = entry.content[:100] if len(entry.content) > 100 else entry.content
            lines.append(f"- [{entry.name}] (type: {entry.type}) — {desc}\n")

        return "".join(lines)

    def migrate_from_markdown(self, memory_dir: Path) -> int:
        """Migrate existing Markdown memories to SQLite.

        Args:
            memory_dir: Directory containing .md memory files

        Returns:
            Number of memories migrated
        """
        import yaml

        count = 0
        for md_file in memory_dir.glob("*.md"):
            if md_file.name == "MEMORY.md":
                continue

            try:
                content = md_file.read_text()

                # Parse YAML frontmatter
                if content.startswith("---\n"):
                    parts = content.split("---\n", 2)
                    if len(parts) >= 3:
                        frontmatter = yaml.safe_load(parts[1])
                        body = parts[2].strip()

                        name = frontmatter.get("name", md_file.stem)
                        type = frontmatter.get("metadata", {}).get("type", "project")

                        self.save(name, type, body)
                        count += 1
            except Exception as e:
                print(f"Migration error for {md_file}: {e}")
                continue

        return count


__all__ = [
    "EmbeddingModel",
    "MockEmbeddingModel",
    "LocalEmbeddingModel",
    "RemoteEmbeddingModel",
    "MemoryEntry",
    "VectorMemoryStore",
]