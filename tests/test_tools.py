"""Tests for the todo database layer."""

import asyncio
import json
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio

# Add src to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from todo_agent.database import TodoDatabase


@pytest_asyncio.fixture
async def db(tmp_path):
    """Create a temporary database for testing."""
    db = TodoDatabase(tmp_path / "test_todos.db")
    await db.connect()
    yield db
    await db.close()


@pytest.mark.asyncio
async def test_create_todo(db):
    todo = await db.create_todo(title="Test todo")
    assert todo["title"] == "Test todo"
    assert todo["status"] == "pending"
    assert todo["priority"] == "medium"
    assert todo["category"] == "general"


@pytest.mark.asyncio
async def test_create_todo_with_all_fields(db):
    todo = await db.create_todo(
        title="Full todo",
        description="A detailed description",
        category="work",
        tags=["urgent", "meeting"],
        priority="high",
    )
    assert todo["title"] == "Full todo"
    assert todo["description"] == "A detailed description"
    assert todo["category"] == "work"
    assert json.loads(todo["tags"]) == ["urgent", "meeting"]
    assert todo["priority"] == "high"


@pytest.mark.asyncio
async def test_get_todo(db):
    created = await db.create_todo(title="Get me")
    fetched = await db.get_todo(created["id"])
    assert fetched is not None
    assert fetched["title"] == "Get me"


@pytest.mark.asyncio
async def test_get_nonexistent_todo(db):
    result = await db.get_todo(9999)
    assert result is None


@pytest.mark.asyncio
async def test_list_todos(db):
    await db.create_todo(title="Todo 1")
    await db.create_todo(title="Todo 2")
    await db.create_todo(title="Todo 3")

    todos = await db.list_todos()
    assert len(todos) == 3


@pytest.mark.asyncio
async def test_list_todos_filter_status(db):
    await db.create_todo(title="Pending")
    todo2 = await db.create_todo(title="Completed")
    await db.update_todo(todo2["id"], status="completed")

    pending = await db.list_todos(status="pending")
    assert len(pending) == 1
    assert pending[0]["title"] == "Pending"


@pytest.mark.asyncio
async def test_list_todos_filter_category(db):
    await db.create_todo(title="Work task", category="work")
    await db.create_todo(title="Home task", category="home")

    work = await db.list_todos(category="work")
    assert len(work) == 1
    assert work[0]["title"] == "Work task"


@pytest.mark.asyncio
async def test_update_todo(db):
    todo = await db.create_todo(title="Original")
    updated = await db.update_todo(todo["id"], title="Updated", priority="high")
    assert updated["title"] == "Updated"
    assert updated["priority"] == "high"


@pytest.mark.asyncio
async def test_complete_todo(db):
    todo = await db.create_todo(title="To complete")
    completed = await db.complete_todo(todo["id"])
    assert completed["status"] == "completed"
    assert completed["completed_at"] is not None


@pytest.mark.asyncio
async def test_delete_todo(db):
    todo = await db.create_todo(title="To delete")
    assert await db.delete_todo(todo["id"]) is True
    assert await db.get_todo(todo["id"]) is None


@pytest.mark.asyncio
async def test_delete_nonexistent(db):
    assert await db.delete_todo(9999) is False


@pytest.mark.asyncio
async def test_search_todos(db):
    await db.create_todo(title="Buy groceries", category="shopping")
    await db.create_todo(title="Write report", category="work")
    await db.create_todo(title="Buy new shoes", category="shopping")

    results = await db.search_todos("buy")
    assert len(results) == 2

    results = await db.search_todos("report")
    assert len(results) == 1


@pytest.mark.asyncio
async def test_search_with_status_filter(db):
    todo1 = await db.create_todo(title="Buy milk")
    todo2 = await db.create_todo(title="Buy bread")
    await db.complete_todo(todo1["id"])

    results = await db.search_todos("buy", status="pending")
    assert len(results) == 1
    assert results[0]["title"] == "Buy bread"
