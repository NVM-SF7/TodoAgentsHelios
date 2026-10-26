"""Agentic ReAct loop — connects local LLM (Ollama) to MCP tools."""

from __future__ import annotations

import asyncio
import json
import sys
import logging
from typing import Any

import httpx
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

import os
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from .config import OLLAMA_BASE_URL, OLLAMA_MODEL, MAX_AGENT_ITERATIONS, SYSTEM_PROMPT
from .database import TodoDatabase
from .models import Todo

logging.basicConfig(stream=sys.stderr, level=logging.INFO)
logger = logging.getLogger("todo-agent")
console = Console(force_terminal=True)

# ── Tool definitions for Ollama ──────────────────────────────

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_todo",
            "description": "Create a new todo item",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "The title of the todo"},
                    "description": {"type": "string", "description": "Detailed description", "default": ""},
                    "category": {"type": "string", "description": "Category for organization", "default": "general"},
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "Tags for the todo", "default": []},
                    "priority": {"type": "string", "enum": ["low", "medium", "high", "urgent"], "description": "Priority level", "default": "medium"},
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_todos",
            "description": "List todo items with optional filters",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "cancelled"], "description": "Filter by status"},
                    "category": {"type": "string", "description": "Filter by category"},
                    "tag": {"type": "string", "description": "Filter by tag"},
                    "priority": {"type": "string", "enum": ["low", "medium", "high", "urgent"], "description": "Filter by priority"},
                    "limit": {"type": "integer", "description": "Max results", "default": 20},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_todo",
            "description": "Get a single todo by its ID",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer", "description": "The todo ID"},
                },
                "required": ["id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_todo",
            "description": "Update a todo's fields. Only provided fields will be changed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer", "description": "The todo ID to update"},
                    "title": {"type": "string", "description": "New title"},
                    "description": {"type": "string", "description": "New description"},
                    "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "cancelled"], "description": "New status"},
                    "category": {"type": "string", "description": "New category"},
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "New tags (replaces existing)"},
                    "priority": {"type": "string", "enum": ["low", "medium", "high", "urgent"], "description": "New priority"},
                },
                "required": ["id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "complete_todo",
            "description": "Mark a todo as completed",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer", "description": "The todo ID to complete"},
                },
                "required": ["id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_todo",
            "description": "Delete a todo permanently",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer", "description": "The todo ID to delete"},
                },
                "required": ["id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_todos",
            "description": "Search todos by keyword across title, description, category, and tags",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "cancelled"], "description": "Optional status filter"},
                },
                "required": ["query"],
            },
        },
    },
]


class TodoAgent:
    """ReAct agent that uses a local LLM via Ollama to manage todos."""

    def __init__(self):
        self.db = TodoDatabase()
        self.client = httpx.AsyncClient(base_url=OLLAMA_BASE_URL, timeout=120.0)
        self.messages: list[dict[str, Any]] = []
        self._tool_handlers = {
            "create_todo": self._handle_create_todo,
            "list_todos": self._handle_list_todos,
            "get_todo": self._handle_get_todo,
            "update_todo": self._handle_update_todo,
            "complete_todo": self._handle_complete_todo,
            "delete_todo": self._handle_delete_todo,
            "search_todos": self._handle_search_todos,
        }

    async def start(self):
        """Initialize the agent."""
        await self.db.connect()
        logger.info(f"Agent started with model: {OLLAMA_MODEL}")
        logger.info(f"Database: {self.db.db_path}")

    async def stop(self):
        """Clean up resources."""
        await self.db.close()
        await self.client.aclose()

    async def chat(self, user_message: str) -> str:
        """Process a user message through the ReAct loop."""
        self.messages.append({"role": "user", "content": user_message})

        for iteration in range(MAX_AGENT_ITERATIONS):
            logger.info(f"Agent iteration {iteration + 1}/{MAX_AGENT_ITERATIONS}")

            # Call Ollama
            response = await self._call_llm()

            # Check if the model wants to call tools
            if response.get("message", {}).get("tool_calls"):
                tool_calls = response["message"]["tool_calls"]
                # Add assistant message with tool calls
                self.messages.append(response["message"])

                # Execute each tool call
                for tool_call in tool_calls:
                    tool_name = tool_call["function"]["name"]
                    tool_args = tool_call["function"]["arguments"]

                    logger.info(f"Tool call: {tool_name}({json.dumps(tool_args, ensure_ascii=False)})")

                    # Execute the tool
                    result = await self._execute_tool(tool_name, tool_args)
                    logger.info(f"Tool result: {result[:200]}...")

                    # Add tool result to messages
                    self.messages.append({
                        "role": "tool",
                        "content": result,
                    })
            else:
                # Model responded with text — we're done
                content = response.get("message", {}).get("content", "")
                self.messages.append({"role": "assistant", "content": content})
                return content

        return "I've reached the maximum number of steps. Please try a simpler request."

    async def _call_llm(self) -> dict:
        """Call Ollama chat API with tools."""
        payload = {
            "model": OLLAMA_MODEL,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + self.messages,
            "tools": TOOLS,
            "stream": False,
            "options": {
                "num_ctx": 4096,
                "num_thread": 6,  # 6 Performance cores on i5-13500HX (optimal for CPU inference)
            },
            "think": False,  # Disable thinking mode for fast CPU inference
        }

        try:
            resp = await self.client.post("/api/chat", json=payload)
            resp.raise_for_status()
            return resp.json()
        except httpx.ConnectError:
            console.print(
                Panel(
                    "[red]Cannot connect to Ollama![/red]\n\n"
                    "Make sure Ollama is running:\n"
                    "  [cyan]ollama serve[/cyan]\n\n"
                    "And the model is pulled:\n"
                    f"  [cyan]ollama pull {OLLAMA_MODEL}[/cyan]",
                    title="Connection Error",
                    border_style="red",
                )
            )
            raise SystemExit(1)
        except httpx.HTTPStatusError as e:
            logger.error(f"Ollama API error: {e.response.status_code} - {e.response.text}")
            raise

    async def _execute_tool(self, name: str, args: dict) -> str:
        """Execute a tool by name with arguments."""
        handler = self._tool_handlers.get(name)
        if not handler:
            return f"Unknown tool: {name}"
        try:
            return await handler(**args)
        except Exception as e:
            logger.error(f"Tool error: {name}: {e}")
            return f"Error executing {name}: {str(e)}"

    # ── Tool Handlers ───────────────────────────────────────────

    async def _handle_create_todo(self, **kwargs) -> str:
        todo_dict = await self.db.create_todo(**kwargs)
        todo = Todo.from_row(todo_dict)
        return f"Created todo: {todo.to_display()}"

    async def _handle_list_todos(self, **kwargs) -> str:
        rows = await self.db.list_todos(**kwargs)
        if not rows:
            return "No todos found."
        todos = [Todo.from_row(r) for r in rows]
        lines = [f"Found {len(todos)} todo(s):", ""]
        for t in todos:
            lines.append(t.to_display())
        return "\n".join(lines)

    async def _handle_get_todo(self, id: int) -> str:
        row = await self.db.get_todo(id)
        if not row:
            return f"Todo #{id} not found."
        todo = Todo.from_row(row)
        return f"{todo.to_display()}\n  Description: {todo.description or '(none)'}\n  Created: {todo.created_at}"

    async def _handle_update_todo(self, id: int, **kwargs) -> str:
        result = await self.db.update_todo(id, **kwargs)
        if not result:
            return f"Todo #{id} not found."
        todo = Todo.from_row(result)
        return f"Updated todo: {todo.to_display()}"

    async def _handle_complete_todo(self, id: int) -> str:
        result = await self.db.complete_todo(id)
        if not result:
            return f"Todo #{id} not found."
        todo = Todo.from_row(result)
        return f"Completed: {todo.to_display()}"

    async def _handle_delete_todo(self, id: int) -> str:
        deleted = await self.db.delete_todo(id)
        if not deleted:
            return f"Todo #{id} not found."
        return f"Deleted todo #{id}."

    async def _handle_search_todos(self, query: str, **kwargs) -> str:
        rows = await self.db.search_todos(query, **kwargs)
        if not rows:
            return f'No todos matching "{query}".'
        todos = [Todo.from_row(r) for r in rows]
        lines = [f'Found {len(todos)} todo(s) matching "{query}":', ""]
        for t in todos:
            lines.append(t.to_display())
        return "\n".join(lines)


async def run_interactive():
    """Run the agent in interactive mode."""
    agent = TodoAgent()
    await agent.start()

    console.print(
        Panel(
            f"[bold green]Todo Agent[/bold green] powered by [cyan]{OLLAMA_MODEL}[/cyan]\n"
            "Type your requests naturally. Type [bold]quit[/bold] or [bold]exit[/bold] to stop.\n\n"
            "Examples:\n"
            '  * "Add a todo to buy groceries, high priority"\n'
            '  * "Show me all my pending tasks"\n'
            '  * "Mark todo #3 as done"\n'
            '  * "Search for anything related to work"',
            title="Agentic Todo",
            border_style="blue",
        )
    )

    try:
        while True:
            console.print()
            try:
                user_input = console.input("[bold cyan]You:[/bold cyan] ").strip()
            except (EOFError, KeyboardInterrupt):
                break

            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit", "q"):
                break

            with console.status("[bold yellow]Thinking...[/bold yellow]", spinner="dots"):
                response = await agent.chat(user_input)

            console.print()
            console.print(Panel(Markdown(response), title="Agent", border_style="green"))
    finally:
        await agent.stop()
        console.print("\n[dim]Goodbye![/dim]")


def main():
    """Entry point."""
    asyncio.run(run_interactive())


if __name__ == "__main__":
    main()
