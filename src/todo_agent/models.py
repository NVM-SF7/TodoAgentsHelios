"""Pydantic models for todo items."""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TodoStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TodoPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class Todo(BaseModel):
    """A todo item."""

    id: int
    title: str
    description: str = ""
    status: TodoStatus = TodoStatus.PENDING
    priority: TodoPriority = TodoPriority.MEDIUM
    category: str = "general"
    tags: list[str] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    completed_at: Optional[str] = None

    @classmethod
    def from_row(cls, row: dict) -> Todo:
        """Create a Todo from a database row."""
        data = dict(row)
        # Parse JSON tags
        if isinstance(data.get("tags"), str):
            try:
                data["tags"] = json.loads(data["tags"])
            except (json.JSONDecodeError, TypeError):
                data["tags"] = []
        return cls(**data)

    def to_display(self) -> str:
        """Format for display."""
        status_icon = {
            "pending": "[P]",
            "in_progress": "[>]",
            "completed": "[X]",
            "cancelled": "[-]",
        }
        priority_icon = {
            "low": "(L)",
            "medium": "(M)",
            "high": "(H)",
            "urgent": "(!)",
        }
        icon = status_icon.get(self.status.value, "(?)")
        prio = priority_icon.get(self.priority.value, "( )")
        tags_str = f" [{', '.join(self.tags)}]" if self.tags else ""
        return (
            f"{icon} #{self.id} {prio} {self.title}"
            f" | {self.category}{tags_str}"
            f" | {self.status.value}"
        )


class CreateTodoRequest(BaseModel):
    title: str
    description: str = ""
    category: str = "general"
    tags: list[str] = Field(default_factory=list)
    priority: str = "medium"


class UpdateTodoRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[list[str]] = None
    priority: Optional[str] = None
