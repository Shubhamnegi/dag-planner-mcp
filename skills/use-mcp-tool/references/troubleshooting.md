# Troubleshooting

## Installation Issues

### `ModuleNotFoundError: No module named 'dag_planner_mcp'`

You haven't installed the package. Inside the repo root with your virtualenv active:

```bash
pip install -e .
```

### `command not found: dag-planner-mcp`

The script is not on your `PATH`. Either activate the virtual environment first:

```bash
source .venv/bin/activate
dag-planner-mcp
```

Or use the full path:

```bash
/path/to/.venv/bin/dag-planner-mcp
```

Run `which dag-planner-mcp` (after activating) to find the exact path.

---

## Database Issues

### `DATABASE_URL not set` / server uses wrong database

Export the variable before starting the server:

```bash
export DATABASE_URL="sqlite:///dag_planner.db"
dag-planner-mcp
```

### PostgreSQL connection refused

1. Confirm PostgreSQL is running: `pg_isready`
2. Confirm the database exists: `psql -c "\l"`
3. Confirm the URL format: `postgresql://user:password@host:5432/dbname`
4. Install the async driver: `pip install -e ".[postgres]"`

### `OperationalError: no such table`

Tables are auto-created on first start. If they're missing, the server may have started with a different `DATABASE_URL` than you expect. Check the value with `echo $DATABASE_URL`.

---

## Task / DAG Errors

### `Cycle detected` when calling `create_plan_graph`

Your `depends_on` lists contain a circular reference. Use `validate_dag_acyclic` first:

```python
await session.call_tool("validate_dag_acyclic", {"tasks": your_task_list})
```

Fix any reported cycles before re-submitting the plan.

### Task stuck in `claimed` state

The lease expired (no heartbeat / executor crashed). Simply claim the task again:

```python
await session.call_tool("claim_task_for_execution",
                        {"task_id": task_id, "executor_id": "new-executor"})
```

### `validate_task_output` fails

The output stored for the task doesn't match the `output_contract` JSON Schema. Check:

1. The schema defined in `create_plan_graph` for the task.
2. The output stored via `put_task_output` — ensure all `required` fields are present.

### `get_ready_tasks` returns empty but not all tasks are done

Some tasks may be blocked:

```python
res = await session.call_tool("get_blocked_tasks", {"run_id": run_id})
```

Common causes:
- A task is `blocked_human` — waiting for `resume_task`.
- An upstream task is `failed` — resolve it with `mark_task_failed` (retry) or `replace_plan_branch`.

---

## MCP Client Issues

### Claude Desktop: tools not appearing

1. Verify the config path: macOS `~/Library/Application Support/Claude/claude_desktop_config.json`.
2. Confirm the `command` path is absolute and the binary is executable.
3. Restart Claude Desktop completely after config changes.
4. Check the MCP server log in `~/Library/Logs/Claude/` (macOS).

### HTTP transport: `Connection refused` at `http://localhost:8000/mcp`

Ensure you started the server in HTTP mode:

```bash
dag-planner-mcp --transport streamable-http --host 0.0.0.0 --port 8000
```

And that port 8000 is not occupied by another process: `lsof -i :8000`.

---

## Running Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

All tests use an in-memory SQLite database and require no external services. If tests fail after a fresh install, try:

```bash
pip install -e ".[dev]" --upgrade
pytest tests/ -v --tb=short
```
