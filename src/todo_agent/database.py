"""SQLite database layer for todo management."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import aiosqlite

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS todos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    description TEXT DEFAULT '',
    status      TEXT DEFAULT 'pending' CHECK(status IN ('pending','in_progress','completed','cancelled')),
    priority    TEXT DEFAULT 'medium' CHECK(priority IN ('low','medium','high','urgent')),
    category    TEXT DEFAULT 'general',
    tags        TEXT DEFAULT '[]',
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now')),
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_todos_status ON todos(status);
CREATE INDEX IF NOT EXISTS idx_todos_category ON todos(category);
CREATE INDEX IF NOT EXISTS idx_todos_priority ON todos(priority);
"""


class TodoDatabase:
    """Async SQLite database for todos."""

    def __init__(self, db_path: Path | str = DB_PATH):
        self.db_path = str(db_path)
        self._db: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        """Open connection and ensure schema exists."""
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._db

    # ── Create ──────────────────────────────────────────────────

    async def create_todo(
        self,
        title: str,
        description: str = "",
        category: str = "general",
        tags: list[str] | None = None,
        priority: str = "medium",
    ) -> dict:
        """Create a new todo and return it."""
        tags_json = json.dumps(tags or [])
        cursor = await self.db.execute(
            """INSERT INTO todos (title, description, category, tags, priority)
               VALUES (?, ?, ?, ?, ?)""",
            (title, description, category, tags_json, priority),
        )
        await self.db.commit()
        return await self.get_todo(cursor.lastrowid)

    # ── Read ────────────────────────────────────────────────────

    async def get_todo(self, todo_id: int) -> dict | None:
        """Get a single todo by ID."""
        async with self.db.execute(
            "SELECT * FROM todos WHERE id = ?", (todo_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def list_todos(
        self,
        status: str | None = None,
        category: str | None = None,
        tag: str | None = None,
        priority: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """List todos with optional filters."""
        conditions = []
        params = []

        if status:
            conditions.append("status = ?")
            params.append(status)
        if category:
            conditions.append("category = ?")
            params.append(category)
        if priority:
            conditions.append("priority = ?")
            params.append(priority)
        if tag:
            # Search within JSON array
            conditions.append("tags LIKE ?")
            params.append(f'%"{tag}"%')

        where = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)

        async with self.db.execute(
            f"SELECT * FROM todos WHERE {where} ORDER BY "
            f"CASE priority WHEN 'urgent' THEN 0 WHEN 'high' THEN 1 "
            f"WHEN 'medium' THEN 2 WHEN 'low' THEN 3 END, "
            f"created_at DESC LIMIT ?",
            params,
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def search_todos(
        self, query: str, status: str | None = None
    ) -> list[dict]:
        """Full-text search across title, description, category, and tags."""
        conditions = [
            "(title LIKE ? OR description LIKE ? OR category LIKE ? OR tags LIKE ?)"
        ]
        like = f"%{query}%"
        params: list = [like, like, like, like]

        if status:
            conditions.append("status = ?")
            params.append(status)

        where = " AND ".join(conditions)
        async with self.db.execute(
            f"SELECT * FROM todos WHERE {where} ORDER BY updated_at DESC",
            params,
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    # ── Update ──────────────────────────────────────────────────

    async def update_todo(self, todo_id: int, **fields) -> dict | None:
        """Update a todo's fields. Returns the updated todo or None."""
        existing = await self.get_todo(todo_id)
        if not existing:
            return None

        # Build dynamic SET clause
        allowed = {"title", "description", "status", "priority", "category", "tags"}
        updates = {}
        for key, value in fields.items():
            if key in allowed and value is not None:
                if key == "tags" and isinstance(value, list):
                    updates[key] = json.dumps(value)
                else:
                    updates[key] = value

        if not updates:
            return existing

        # Always update the updated_at timestamp
        updates["updated_at"] = "datetime('now')"

        # Check if we're completing the todo
        if updates.get("status") == "completed" and existing["status"] != "completed":
            set_parts = [f"{k} = ?" for k in updates if k != "updated_at"]
            set_parts.append("updated_at = datetime('now')")
            set_parts.append("completed_at = datetime('now')")
            values = [v for k, v in updates.items() if k != "updated_at"]
        else:
            set_parts = [f"{k} = ?" for k in updates if k != "updated_at"]
            set_parts.append("updated_at = datetime('now')")
            values = [v for k, v in updates.items() if k != "updated_at"]

        values.append(todo_id)
        set_clause = ", ".join(set_parts)

        await self.db.execute(
            f"UPDATE todos SET {set_clause} WHERE id = ?", values
        )
        await self.db.commit()
        return await self.get_todo(todo_id)

    async def complete_todo(self, todo_id: int) -> dict | None:
        """Mark a todo as complete."""
        return await self.update_todo(todo_id, status="completed")

    # ── Delete ──────────────────────────────────────────────────

    async def delete_todo(self, todo_id: int) -> bool:
        """Delete a todo. Returns True if deleted."""
        existing = await self.get_todo(todo_id)
        if not existing:
            return False
        await self.db.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
        await self.db.commit()
        return True
