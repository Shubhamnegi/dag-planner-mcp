---
name: use-mcp-tool
description: Use this skill when you need to break a goal into a dependency graph of tasks, execute them in parallel, track state durably, and handle human-in-the-loop approvals via the dag-planner-mcp MCP server.
---

# dag-planner-mcp Skill

A **durable DAG-based task planner** exposed as an MCP server. Lets AI orchestrators plan a goal as a directed-acyclic graph (DAG) of tasks, execute them in topological order (with parallelism), and track state persistently in SQLite or PostgreSQL.

---

## When to use

- You need to decompose a multi-step goal into parallel, dependent tasks.
- You need durable task state (survives restarts, retries, checkpoints).
- You need human-in-the-loop approval gates inside a task graph.
- You are building or running an agent orchestration loop that dispatches work to sub-agents.

## When NOT to use

- Single, atomic actions that need no ordering or retry logic.
- One-off scripts where state persistence adds no value.
- Real-time streaming pipelines — this is a planner, not a streaming bus.

---

## Setup

> Full setup details: [`references/setup.md`](references/setup.md)

```bash
# 1. Clone & install
git clone https://github.com/Shubhamnegi/dag-planner-mcp.git
cd dag-planner-mcp
python -m venv .venv && source .venv/bin/activate
pip install -e .

# 2. Set the database URL (SQLite default — no extra setup needed)
export DATABASE_URL="sqlite:///dag_planner.db"

# 3. Start the server (stdio mode — for Claude Desktop / most MCP clients)
dag-planner-mcp
```

Environment variables:

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `sqlite:///dag_planner.db` | SQLAlchemy URL (SQLite or PostgreSQL) |
| `MCP_HOST` | `127.0.0.1` | Bind host for HTTP transport |
| `MCP_PORT` | `8000` | Bind port for HTTP transport |

---

## Workflow

### Step 1 — Create a workflow run

```python
result = await session.call_tool("create_workflow_run", {
    "goal": "Analyze AWS cost spike and send a report"
})
run_id = result["data"]["run_id"]
```

### Step 2 — Define the task DAG

```python
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
```

### Step 3 — Orchestrator execution loop

```python
while True:
    res = await session.call_tool("get_ready_tasks", {"run_id": run_id})
    tasks = res["data"]["tasks"]
    if not tasks:
        break  # All done or blocked

    for task in tasks:
        task_id = task["task_id"]
        await session.call_tool("claim_task_for_execution",
                                {"task_id": task_id, "executor_id": "agent-1"})
        await session.call_tool("mark_task_running", {"task_id": task_id})

        # ... dispatch to sub-agent and collect output ...
        output = {"summary": "EC2 caused 40% spike"}

        await session.call_tool("put_task_output",
                                {"task_id": task_id, "output": output, "is_final": True})
        await session.call_tool("validate_task_output", {"task_id": task_id})
        await session.call_tool("mark_task_completed",
                                {"task_id": task_id, "final_output": output})
```

### Step 4 — Handle human-in-the-loop gates (optional)

```python
# Block a task and ask a human
await session.call_tool("request_human_input", {
    "task_id": task_id,
    "question": "Should I proceed with deleting the stale S3 buckets?"
})

# After human responds, resume
await session.call_tool("resume_task", {
    "task_id": task_id,
    "decision": "approved"
})
```

---

## Key Tools Reference

| Category | Tool | What it does |
|---|---|---|
| Planning | `create_workflow_run` | Start a new run (returns `run_id`) |
| Planning | `create_plan_graph` | Define the task DAG |
| Planning | `replace_plan_branch` | Graft a new branch at any point |
| Scheduling | `get_ready_tasks` | List tasks ready to execute |
| Scheduling | `claim_task_for_execution` | Atomically claim a task with a lease |
| State | `mark_task_running` / `mark_task_completed` / `mark_task_failed` | Lifecycle transitions |
| State | `mark_task_blocked_human` / `resume_task` | Human-in-the-loop gates |
| I/O | `put_task_output` / `put_task_checkpoint` | Store outputs and checkpoints |
| Query | `get_task` / `list_tasks` / `get_workflow_run` | Inspect state |
| Validation | `validate_task_output` / `validate_dag_acyclic` | Schema & cycle checks |
| Subagent | `get_my_task` / `update_my_progress` / `submit_my_output` | Safe wrappers for sub-agents |

> Full tool list with parameters: [`references/examples.md`](references/examples.md)

---

## Examples

> See [`references/examples.md`](references/examples.md) for complete, runnable examples.
> See [`scripts/example_client.py`](scripts/example_client.py) for a working stdio client.

---

## Troubleshooting

> See [`references/troubleshooting.md`](references/troubleshooting.md) for common failure cases.

Quick fixes:

- **`ModuleNotFoundError: dag_planner_mcp`** → Run `pip install -e .` inside the repo root.
- **`DATABASE_URL` not set** → Export it before starting: `export DATABASE_URL="sqlite:///dag_planner.db"`.
- **Cycle detected error** → Use `validate_dag_acyclic` before calling `create_plan_graph`.
- **Task stuck in `claimed`** → The lease expired. Call `claim_task_for_execution` again.
