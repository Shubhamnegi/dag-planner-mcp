# Troubleshooting

## The DAG Planner Tools Are Not Available

**Symptom:** You try to call `create_workflow_run` (or any other tool) and get a "tool not found" error or no response.

**Cause:** The MCP server is not connected to your client.

**Fix:** Ask the user to follow the server setup guide: [`setup.md`](setup.md).
- For Claude Desktop: check `claude_desktop_config.json` and restart Claude.
- For Cursor/HTTP: confirm the server is running at `http://localhost:8000/mcp`.

---

## `get_ready_tasks` Returns Empty, But the Workflow Is Not Complete

**Symptom:** You call `get_ready_tasks` and get an empty list, but `get_workflow_run` shows status is not `completed`.

**Cause:** One or more tasks are blocked.

**Fix:** Call `get_blocked_tasks` with the `run_id`.

Tool: `get_blocked_tasks`
Input: `{ "run_id": "run_abc" }`

Possible causes:
- A task is `blocked_human` — surface the question to the user, then call `resume_task` after their response.
- An upstream task is `failed` — call `mark_task_failed` with a retry flag, or use `replace_plan_branch` to substitute a new recovery path.

---

## Cycle Detected When Calling `create_plan_graph`

**Symptom:** `create_plan_graph` returns an error about a circular dependency.

**Fix:** Call `validate_dag_acyclic` with your task list before submitting.

Tool: `validate_dag_acyclic`
Input: `{ "tasks": [ ... your task list ... ] }`

Fix any cycles the tool reports (task A depends on B, B depends on A), then re-submit.

---

## Task Stuck in `claimed` State

**Symptom:** A task was claimed but never progressed. It does not appear in `get_ready_tasks` even after a long wait.

**Cause:** The executor that claimed the task failed or timed out. The lease has expired.

**Fix:** Call `claim_task_for_execution` again for the same `task_id`. The server will re-issue the lease.

Tool: `claim_task_for_execution`
Input: `{ "task_id": "t_xyz", "executor_id": "me" }`

---

## `validate_task_output` Fails

**Symptom:** After calling `put_task_output`, `validate_task_output` returns a schema violation.

**Cause:** The output you stored does not satisfy the `output_contract` JSON Schema defined for this task (missing required fields, wrong types, etc.).

**Fix:**
1. Call `get_task` to read the `output_contract` for the task.
2. Check your output against the schema — add missing required fields.
3. Call `put_task_output` again with the corrected output.
4. Re-call `validate_task_output`.

---

## A Task Failed — How to Recover

**Option A — Retry the same task:**

Tool: `mark_task_failed`
Input: `{ "task_id": "t_xyz", "error": "Timeout fetching data", "retry": true }`

The task re-enters the `ready` state on the next `get_ready_tasks` call.

**Option B — Replace the branch with a different plan:**

Tool: `replace_plan_branch`
Input:
```json
{
  "run_id": "run_abc",
  "cancel_from_task_key": "failed_task_key",
  "new_tasks": [ { ... replacement task(s) ... } ]
}
```

All descendants of the failed task are cancelled and the new branch is grafted in.

---

## How to Check Overall Run Progress

Tool: `get_workflow_run`
Input: `{ "run_id": "run_abc" }`

Returns overall status (`pending`, `in_progress`, `completed`, `failed`) and task counts.

Tool: `list_tasks`
Input: `{ "run_id": "run_abc" }`

Returns every task with its current status — useful for spotting which tasks are stuck.

---

## Server-Side Issues (ask the user to check)

| Symptom | Likely cause | Fix |
|---|---|---|
| Tools respond with DB errors | `DATABASE_URL` wrong or DB not reachable | Check `echo $DATABASE_URL`; confirm DB is running |
| Server crashes on start | Missing `aiosqlite` or `asyncpg` | Re-run `pip install -e .` (add `[postgres]` for PostgreSQL) |
| Tables missing on first call | Server started before DB was created (PostgreSQL) | Create the DB first: `CREATE DATABASE dag_planner;` |
