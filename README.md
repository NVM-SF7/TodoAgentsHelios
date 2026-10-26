# 🧠 Agentic Todo App

A local AI-powered todo manager that uses a lightweight LLM running on your CPU to understand natural language and manage todos via MCP (Model Context Protocol).

## Stack

- **LLM**: Qwen3.5-4B via Ollama (CPU-only)
- **MCP**: FastMCP Python SDK
- **Database**: SQLite
- **Agent**: Custom ReAct loop

## Setup

### 1. Install Ollama

```powershell
winget install Ollama.Ollama
```

### 2. Pull the model

```powershell
# Force CPU-only (no GPU)
$env:CUDA_VISIBLE_DEVICES=""
ollama pull qwen3.5:4b
```

### 3. Install Python dependencies

```powershell
cd E:\todo
pip install -e .
```

### 4. Run the agent (interactive CLI)

```powershell
# Ensure CPU-only mode
$env:CUDA_VISIBLE_DEVICES=""

# Start Ollama (if not already running)
ollama serve

# In another terminal, run the agent
python -m todo_agent.agent
```

### 5. Run as MCP server (for your apps)

```powershell
python -m todo_agent.mcp_server
```

## MCP Server Configuration

To connect this to any MCP-compatible app, add to your MCP config:

```json
{
  "mcpServers": {
    "todo-manager": {
      "command": "python",
      "args": ["-m", "todo_agent.mcp_server"],
      "cwd": "E:\\todo",
      "env": {
        "CUDA_VISIBLE_DEVICES": ""
      }
    }
  }
}
```

## Available Tools

| Tool | Description |
|------|-------------|
| `create_todo` | Create a new todo with title, description, category, tags, priority |
| `list_todos` | List todos with filters (status, category, tag, priority) |
| `get_todo` | Get details of a specific todo by ID |
| `update_todo` | Update any fields of a todo |
| `complete_todo` | Mark a todo as complete |
| `delete_todo` | Delete a todo permanently |
| `search_todos` | Full-text search across all todo fields |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama API URL |
| `OLLAMA_MODEL` | `qwen3.5:4b` | Model to use |
| `TODO_DB_PATH` | `./todos.db` | SQLite database path |
| `MAX_AGENT_ITERATIONS` | `10` | Max ReAct loop steps |
| `CUDA_VISIBLE_DEVICES` | (not set) | Set to `""` for CPU-only |

## CPU Optimization Note

For Intel hybrid CPUs (such as the i5-13500HX with 6 Performance + 8 Efficient cores), running across all cores causes thread-synchronization bottlenecks between core types. The agent is pre-configured to bind to **6 worker threads** (the P-cores) with `think: false` to bypass chain-of-thought overhead, providing rapid tool invocation and conversational response times purely on CPU without touching any GPU.

## Usage Examples

```
You: Add a todo to buy groceries with high priority
Agent: ✅ Created todo: ⏳ #1 🟠 Buy groceries | general | pending

You: Create a work task to finish the report, tag it as "deadline" and "Q4"
Agent: ✅ Created todo: ⏳ #2 🟡 Finish the report | work [deadline, Q4] | pending

You: Show all my pending todos
Agent: Found 2 todo(s):
  ⏳ #1 🟠 Buy groceries | general | pending
  ⏳ #2 🟡 Finish the report | work [deadline, Q4] | pending

You: Mark #1 as done
Agent: ✅ Completed: ✅ #1 🟠 Buy groceries | general | completed
```
