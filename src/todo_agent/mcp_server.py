"""MCP Server exposing todo management tools."""

from __future__ import annotations

import asyncio
import json
import sys
import logging
from typing import Optional

from mcp.server.fastmcp import FastMCP

from .database import TodoDatabase
from .models import Todo

# Never use print() with stdio transport — use stderr logging
logging.basicConfig(stream=sys.stderr, level=logging.INFO)
logger = logging.getLogger("todo-mcp")

# Initialize MCP server
mcp = FastMCP("Todo Manager")

# Global database instance
db = TodoDatabase()


@mcp.tool()
async def create_todo(
    title: str,
    description: str = "",
    category: str = "general",
    tags: Optional[list[str]] = None,
    priority: str = "medium",
) -> str:
    """Create a new todo item.

    Args:
        title: The title of the todo (required)
        description: Optional detailed description
        category: Category to organize the todo (default: "general")
        tags: Optional list of tags for the todo
        priority: Priority level - "low", "medium", "high", or "urgent" (default: "medium")
    """
    await _ensure_connected()
    todo_dict = await db.create_todo(
        title=title,
        description=description,
        category=category,
        tags=tags,
        priority=priority,
    )
    todo = Todo.from_row(todo_dict)
    return f"Created todo: {todo.to_display()}"


@mcp.tool()
async def list_todos(
    status: Optional[str] = None,
    category: Optional[str] = None,
    tag: Optional[str] = None,
    priority: Optional[str] = None,
    limit: int = 20,
) -> str:
    """List todo items with optional filters.

    Args:
        status: Filter by status - "pending", "in_progress", "completed", "cancelled"
        category: Filter by category
        tag: Filter by a specific tag
        priority: Filter by priority - "low", "medium", "high", "urgent"
        limit: Maximum number of todos to return (default: 20)
    """
    await _ensure_connected()
    rows = await db.list_todos(
        status=status, category=category, tag=tag, priority=priority, limit=limit
    )
    if not rows:
        filters = []
        if status:
            filters.append(f"status={status}")
        if category:
            filters.append(f"category={category}")
        if tag:
            filters.append(f"tag={tag}")
        if priority:
            filters.append(f"priority={priority}")
        filter_str = f" (filters: {', '.join(filters)})" if filters else ""
        return f"No todos found{filter_str}."

    todos = [Todo.from_row(r) for r in rows]
    lines = [f"Found {len(todos)} todo(s):", ""]
    for t in todos:
        lines.append(t.to_display())
    return "\n".join(lines)


@mcp.tool()
async def get_todo(id: int) -> str:
    """Get a single todo by its ID.

    Args:
        id: The todo ID to retrieve
    """
    await _ensure_connected()
    row = await db.get_todo(id)
    if not row:
        return f"Todo #{id} not found."
    todo = Todo.from_row(row)
    parts = [
        todo.to_display(),
        f"  Description: {todo.description or '(none)'}",
        f"  Created: {todo.created_at}",
        f"  Updated: {todo.updated_at}",
    ]
    if todo.completed_at:
        parts.append(f"  Completed: {todo.completed_at}")
    return "\n".join(parts)


@mcp.tool()
async def update_todo(
    id: int,
    title: Optional[str] = None,
    description: Optional[str] = None,
    status: Optional[str] = None,
    category: Optional[str] = None,
    tags: Optional[list[str]] = None,
    priority: Optional[str] = None,
) -> str:
    """Update a todo's fields. Only provided fields will be updated.

    Args:
        id: The todo ID to update (required)
        title: New title
        description: New description
        status: New status - "pending", "in_progress", "completed", "cancelled"
        category: New category
        tags: New list of tags (replaces existing tags)
        priority: New priority - "low", "medium", "high", "urgent"
    """
    await _ensure_connected()
    fields = {}
    if title is not None:
        fields["title"] = title
    if description is not None:
        fields["description"] = description
    if status is not None:
        fields["status"] = status
    if category is not None:
        fields["category"] = category
    if tags is not None:
        fields["tags"] = tags
    if priority is not None:
        fields["priority"] = priority

    if not fields:
        return "No fields provided to update."

    result = await db.update_todo(id, **fields)
    if not result:
        return f"Todo #{id} not found."
    todo = Todo.from_row(result)
    return f"Updated todo: {todo.to_display()}"


@mcp.tool()
async def complete_todo(id: int) -> str:
    """Mark a todo as completed.

    Args:
        id: The todo ID to mark as complete
    """
    await _ensure_connected()
    result = await db.complete_todo(id)
    if not result:
        return f"Todo #{id} not found."
    todo = Todo.from_row(result)
    return f"Completed: {todo.to_display()}"


@mcp.tool()
async def delete_todo(id: int) -> str:
    """Delete a todo permanently.

    Args:
        id: The todo ID to delete
    """
    await _ensure_connected()
    deleted = await db.delete_todo(id)
    if not deleted:
        return f"Todo #{id} not found."
    return f"Deleted todo #{id}."


@mcp.tool()
async def search_todos(query: str, status: Optional[str] = None) -> str:
    """Search todos by keyword across title, description, category, and tags.

    Args:
        query: Search query string
        status: Optional status filter - "pending", "in_progress", "completed", "cancelled"
    """
    await _ensure_connected()
    rows = await db.search_todos(query, status=status)
    if not rows:
        return f'No todos matching "{query}".'

    todos = [Todo.from_row(r) for r in rows]
    lines = [f'Found {len(todos)} todo(s) matching "{query}":', ""]
    for t in todos:
        lines.append(t.to_display())
    return "\n".join(lines)


async def _ensure_connected():
    """Ensure the database is connected."""
    if db._db is None:
        await db.connect()
        logger.info(f"Connected to database: {db.db_path}")


def main():
    """Run the MCP server."""
    logger.info("Starting Todo MCP Server...")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
