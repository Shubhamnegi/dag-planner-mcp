# dag-planner-mcp

A durable **DAG-based task planner** exposed as an [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server. It lets AI orchestrators (Claude, ADK-based agents, etc.) break a goal into a dependency graph of tasks, execute them in parallel where possible, track state durably, and handle human-in-the-loop approval — all through a clean set of 22 MCP tools.

---

## Table of Contents

- [Install this skill](#install-this-skill)
- [Requirements](#requirements)
- [Installation](#installation)
- [Database Configuration](#database-configuration)
  - [SQLite (development)](#sqlite-development)
  - [PostgreSQL (production)](#postgresql-production)
- [Environment Variables](#environment-variables)
- [Running the server](#running-the-server)
- [Using with Claude Desktop (stdio)](#using-with-claude-desktop-stdio)
- [Using with other MCP clients (streamable HTTP)](#using-with-other-mcp-clients-streamable-http)
- [Available MCP Tools](#available-mcp-tools)
- [Orchestrator Loop Example](#orchestrator-loop-example)
- [Running Tests](#running-tests)

---

## Install this skill

AI agents (Claude, Copilot, etc.) can pick up ready-made instructions for using this MCP server by installing the bundled skill:

```bash
npx skills add Shubhamnegi/dag-planner-mcp --skill use-mcp-tool
```

Or install directly from the skill path:

```bash
npx skills add https://github.com/Shubhamnegi/dag-planner-mcp/tree/main/skills/use-mcp-tool
```

### What the skill provides

| File | Purpose |
|---|---|
| [`skills/use-mcp-tool/SKILL.md`](skills/use-mcp-tool/SKILL.md) | Core instructions — when/how to use the tool |
| [`skills/use-mcp-tool/references/setup.md`](skills/use-mcp-tool/references/setup.md) | Full installation and client integration guide |
| [`skills/use-mcp-tool/references/examples.md`](skills/use-mcp-tool/references/examples.md) | Runnable code examples (parallel tasks, HITL gates, checkpoints) |
| [`skills/use-mcp-tool/references/troubleshooting.md`](skills/use-mcp-tool/references/troubleshooting.md) | Common failure cases and fixes |
| [`skills/use-mcp-tool/scripts/smoke_test.py`](skills/use-mcp-tool/scripts/smoke_test.py) | Quick sanity check — run after install |
| [`skills/use-mcp-tool/scripts/example_client.py`](skills/use-mcp-tool/scripts/example_client.py) | Complete orchestrator example (stdio + HTTP) |

### Requirements

* Python ≥ 3.11
* `DATABASE_URL` environment variable (defaults to `sqlite:///dag_planner.db`)

---

## Requirements

| Dependency | Version |
|---|---|
| Python | ≥ 3.11 |
| mcp[cli] | ≥ 1.6.0 |
| sqlalchemy | ≥ 2.0 |
| pydantic | ≥ 2.0 |
| jsonschema | ≥ 4.0 |
| aiosqlite | ≥ 0.19 |

Optional (PostgreSQL):

| Dependency | Version |
|---|---|
| asyncpg | ≥ 0.29 |

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/Shubhamnegi/dag-planner-mcp.git
cd dag-planner-mcp
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate        # Linux / macOS
.venv\Scripts\activate           # Windows
```

### 3. Install the package

**SQLite (dev — no extra dependencies):**

```bash
pip install -e .
```

**PostgreSQL (prod):**

```bash
pip install -e ".[postgres]"
```

**With development/test dependencies:**

```bash
pip install -e ".[dev]"
```

---

## Database Configuration

The server is controlled entirely via the `DATABASE_URL` environment variable. Tables are created automatically on first start.

### SQLite (development)

```bash
# Default — creates dag_planner.db in the current directory
export DATABASE_URL="sqlite:///dag_planner.db"

# Absolute path
export DATABASE_URL="sqlite:////home/user/data/dag_planner.db"

# In-memory (testing only — data lost on exit)
export DATABASE_URL="sqlite:///:memory:"
```

No additional setup is required for SQLite.

### PostgreSQL (production)

```bash
export DATABASE_URL="postgresql://user:password@localhost:5432/dag_planner"
```

Create the database first:

```sql
CREATE DATABASE dag_planner;
```

Then start the server — SQLAlchemy will create all tables automatically.

For connection pooling / SSL in production you can pass extra query parameters:

```bash
export DATABASE_URL="postgresql://user:password@host:5432/dag_planner?sslmode=require"
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///dag_planner.db` | SQLAlchemy connection URL (SQLite or PostgreSQL) |
| `MCP_HOST` | `127.0.0.1` | Host to bind when using HTTP transport |
| `MCP_PORT` | `8000` | Port to bind when using HTTP transport |

---

## Running the server

### stdio (recommended for Claude Desktop and most MCP clients)

```bash
dag-planner-mcp
# or
python -m dag_planner_mcp.server
```

The server reads from stdin and writes to stdout — no port is opened.

### Streamable HTTP

```bash
dag-planner-mcp --transport streamable-http --host 0.0.0.0 --port 8000
```

The MCP endpoint will be available at:

```
http://localhost:8000/mcp
```

---

## Using with Claude Desktop (stdio)

1. Open the Claude Desktop configuration file:

   - **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

2. Add the server under `mcpServers`:

```json
{
  "mcpServers": {
    "dag-planner-mcp": {
      "command": "/path/to/.venv/bin/dag-planner-mcp",
      "env": {
        "DATABASE_URL": "sqlite:////home/user/data/dag_planner.db"
      }
    }
  }
}
```

Replace `/path/to/.venv/bin/dag-planner-mcp` with the absolute path to the installed script (run `which dag-planner-mcp` after installation).

3. Restart Claude Desktop. The 22 DAG planner tools will appear in the tools panel.

---

## Using with other MCP clients (streamable HTTP)

Start the server in HTTP mode:

```bash
DATABASE_URL="sqlite:///dag_planner.db" \
dag-planner-mcp --transport streamable-http --host 0.0.0.0 --port 8000
```

Then point your MCP client at:

```
http://localhost:8000/mcp
```

### Example: Cursor IDE

```json
{
  "mcpServers": {
    "dag-planner-mcp": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

### Example: Windsurf / Continue / custom agent

```python
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

async with streamablehttp_client("http://localhost:8000/mcp") as (r, w, _):
    async with ClientSession(r, w) as session:
        await session.initialize()
        result = await session.call_tool("create_workflow_run", {"goal": "Analyze AWS costs"})
```

---

## Available MCP Tools

### Planning

| Tool | Description |
|---|---|
| `create_workflow_run` | Create a new workflow run (returns `run_id`) |
| `create_plan_graph` | Define the task DAG for a run (validates for cycles) |
| `replace_plan_branch` | Cancel downstream tasks and graft a new plan branch |

### Scheduling

| Tool | Description |
|---|---|
| `get_ready_tasks` | List tasks that are ready and unclaimed |
| `claim_task_for_execution` | Atomically claim a ready task with a time-bounded lease |

### State Management

| Tool | Description |
|---|---|
| `mark_task_running` | Transition a claimed task to running |
| `mark_task_completed` | Mark done; auto-promotes dependent tasks to ready |
| `mark_task_failed` | Mark failed with optional retry |
| `mark_task_blocked_human` | Block a task awaiting human decision |
| `resume_task` | Resume a human-blocked task after decision |

### Task I/O

| Tool | Description |
|---|---|
| `put_task_output` | Store working or final output |
| `put_task_checkpoint` | Save an incremental checkpoint |
| `get_task_payload_refs` | Retrieve all payload data for a task |

### Query

| Tool | Description |
|---|---|
| `get_task` | Full state of a single task |
| `list_tasks` | List tasks for a run with filters |
| `get_workflow_run` | Workflow run state |
| `get_blocked_tasks` | Tasks blocked on human or dependencies |
| `get_dag_edges` | All DAG edges for a run |

### Validation

| Tool | Description |
|---|---|
| `validate_task_output` | Validate output against the task's JSON Schema contract |
| `validate_dag_acyclic` | Check a task list for cycles before submitting |

### Subagent-safe wrappers

| Tool | Description |
|---|---|
| `get_my_task` | Narrow task view for a subagent |
| `update_my_progress` | Update working output and optional checkpoint |
| `submit_my_output` | Submit final output and complete the task |
| `request_human_input` | Block task and request a human decision |

---

## Orchestrator Loop Example

```python
import json
from mcp import ClientSession
from mcp.client.stdio import stdio_client

async def run():
    async with stdio_client(["dag-planner-mcp"]) as (r, w):
        async with ClientSession(r, w) as session:
            await session.initialize()

            # 1. Create a workflow
            res = await session.call_tool("create_workflow_run", {
                "goal": "Analyze AWS cost spike and send report"
            })
            run_id = json.loads(res.content[0].text)["data"]["run_id"]

            # 2. Define the task DAG
            await session.call_tool("create_plan_graph", {
                "run_id": run_id,
                "tasks": [
                    {
                        "task_key": "fetch_data",
                        "title": "Fetch cost data",
                        "description": "Pull last 3 weeks of AWS cost data",
                        "owner_agent": "data_agent",
                        "depends_on": [],
                        "output_contract": {"type": "object", "required": ["cost_data"]}
                    },
                    {
                        "task_key": "analyze",
                        "title": "Analyze spike",
                        "description": "Identify top services causing the spike",
                        "owner_agent": "analyst_agent",
                        "depends_on": ["fetch_data"],
                        "output_contract": {"type": "object", "required": ["summary"]}
                    }
                ]
            })

            # 3. Execution loop
            while True:
                res = await session.call_tool("get_ready_tasks", {"run_id": run_id})
                tasks = json.loads(res.content[0].text)["data"]["tasks"]

                if not tasks:
                    break  # All done (or blocked)

                for task in tasks:
                    task_id = task["task_id"]
                    await session.call_tool("claim_task_for_execution", {
                        "task_id": task_id, "executor_id": "orchestrator-1"
                    })
                    await session.call_tool("mark_task_running", {"task_id": task_id})

                    # ... dispatch to subagent, collect result ...
                    output = {"summary": "EC2 caused 40% increase"}

                    await session.call_tool("put_task_output", {
                        "task_id": task_id, "output": output, "is_final": True
                    })
                    await session.call_tool("validate_task_output", {"task_id": task_id})
                    await session.call_tool("mark_task_completed", {
                        "task_id": task_id, "final_output": output
                    })
```

---

## Running Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

All tests use an in-memory SQLite database and require no external services.
