---
name: use-mcp-tool
description: Use this skill when you (an AI agent) need to orchestrate a multi-step goal by planning a DAG of tasks, executing them in dependency order, tracking state across turns, and optionally pausing for human approval — all through the dag-planner-mcp MCP tools you have available.
---

# dag-planner-mcp Skill

You have access to the **dag-planner-mcp** MCP server. It gives you a set of tools to plan any goal as a **Directed Acyclic Graph (DAG)** of tasks, drive execution step-by-step, persist state across conversation turns, and gate progress on human approval when needed.

You call these tools directly — no code, no SDK. The server handles persistence, dependency resolution, and scheduling.

---

## When to use

- The user's request involves multiple steps that have dependencies (do A before B, do B and C in parallel, then D).
- You need to track progress across many turns or a long session.
- Some steps need human approval before proceeding.
- You are acting as an orchestrator dispatching work to sub-agents or tools, and need to coordinate their outputs.
- The workflow might fail mid-way and needs retry or replanning capability.

## When NOT to use

- The task is a single, self-contained action with no sequencing needed.
- No persistence or state tracking is required.
- You are only reading or querying — not executing a multi-step plan.

---

## Server Setup (human prerequisite)

> The server must already be running and connected to your MCP client before you can call these tools.
> If the tools are not available in your context, ask the user to set up the server first.
> Full setup instructions: [`references/setup.md`](references/setup.md)

Quick check — if you can call `get_workflow_run` and it responds, the server is connected.

---

## Orchestration Workflow

This is the standard loop you follow when executing any multi-step plan.

### Step 1 — Create a workflow run

Call `create_workflow_run` with the user's goal. Save the `run_id` — you need it for all subsequent calls.

**Tool:** `create_workflow_run`
```json
{ "goal": "Analyze AWS cost spike and send a report" }
```

**Response:**
```json
{ "data": { "run_id": "run_abc123" } }
```

---

### Step 2 — Define the task DAG

Call `create_plan_graph` with the full list of tasks and their dependencies. Each task needs:
- `task_key` — unique short identifier (snake_case)
- `title` — human-readable name
- `description` — what the task should do
- `owner_agent` — which agent/tool handles this (can be `"me"` if you do it yourself)
- `depends_on` — list of `task_key` values that must complete first (empty = runs immediately)
- `output_contract` — JSON Schema the task's output must satisfy

**Tool:** `create_plan_graph`
```json
{
  "run_id": "run_abc123",
  "tasks": [
    {
      "task_key": "fetch_data",
      "title": "Fetch cost data",
      "description": "Pull last 3 weeks of AWS cost data",
      "owner_agent": "me",
      "depends_on": [],
      "output_contract": { "type": "object", "required": ["cost_data"] }
    },
    {
      "task_key": "analyze",
      "title": "Analyze spike",
      "description": "Identify top services causing the spike",
      "owner_agent": "me",
      "depends_on": ["fetch_data"],
      "output_contract": { "type": "object", "required": ["summary"] }
    }
  ]
}
```

> **Tip:** Before calling `create_plan_graph`, call `validate_dag_acyclic` with your task list to catch any circular dependencies early.

---

### Step 3 — Drive the execution loop

Repeat this loop until all tasks are done:

1. **Get ready tasks** — call `get_ready_tasks` with the `run_id`.
   - If the response list is empty, check `get_blocked_tasks` to see if anything is waiting on human input or a failed upstream.
   - If no tasks are ready and none are blocked, the workflow is complete.

2. **For each ready task:**
   - Call `claim_task_for_execution` (marks it as yours, prevents double-execution).
   - Call `mark_task_running`.
   - Do the actual work (call other tools, read files, compute, etc.).
   - Call `put_task_output` with `is_final: true` when done.
   - Call `validate_task_output` to confirm the output matches the contract.
   - Call `mark_task_completed` with the final output.

**Tool sequence per task:**
```
get_ready_tasks           → pick a task
claim_task_for_execution  → lock it
mark_task_running         → signal start
... do the work ...
put_task_output           → store result
validate_task_output      → confirm schema
mark_task_completed       → unlock dependents
```

---

### Step 4 — Handle human-in-the-loop gates (when needed)

When a task requires human approval before proceeding:

**Tool:** `request_human_input`
```json
{
  "task_id": "task_xyz",
  "question": "Should I proceed with deleting the 47 stale S3 buckets costing $230/month?"
}
```

The task is now `blocked_human`. Pause and surface the question to the user. When the user responds:

**Tool:** `resume_task`
```json
{
  "task_id": "task_xyz",
  "decision": "approved"
}
```

The task re-enters the ready queue and execution continues.

---

### Step 5 — Handle failures and replanning

If a task fails:

- Call `mark_task_failed` to record the failure (with optional retry flag).
- To swap out a failed branch without restarting the whole run, call `replace_plan_branch` — cancel from the failed task and graft in new tasks.

**Tool:** `replace_plan_branch`
```json
{
  "run_id": "run_abc123",
  "cancel_from_task_key": "analyze",
  "new_tasks": [
    {
      "task_key": "fallback_analyze",
      "title": "Fallback analysis (simplified)",
      "depends_on": ["fetch_data"],
      ...
    }
  ]
}
```

---

## Sub-Agent Pattern

When you dispatch a task to another agent or sub-process, use the **subagent-safe wrappers** instead of the full lifecycle tools. These give a narrower, safer view:

| Tool | Use when |
|---|---|
| `get_my_task` | Sub-agent reads its own task details |
| `update_my_progress` | Sub-agent saves incremental output / checkpoint |
| `submit_my_output` | Sub-agent completes the task |
| `request_human_input` | Sub-agent needs a human decision |

---

## Full Tool Reference

| Category | Tool | Purpose |
|---|---|---|
| Planning | `create_workflow_run` | Start a new run → get `run_id` |
| Planning | `create_plan_graph` | Submit the task DAG |
| Planning | `replace_plan_branch` | Cancel + regraft a branch mid-run |
| Scheduling | `get_ready_tasks` | List tasks whose dependencies are satisfied |
| Scheduling | `claim_task_for_execution` | Atomically lock a task with a time-bounded lease |
| Lifecycle | `mark_task_running` | Signal task is being worked on |
| Lifecycle | `mark_task_completed` | Mark done; auto-promotes dependent tasks to ready |
| Lifecycle | `mark_task_failed` | Record failure with optional retry |
| Lifecycle | `mark_task_blocked_human` | Block awaiting human decision |
| Lifecycle | `resume_task` | Resume after human decision |
| I/O | `put_task_output` | Store working or final output |
| I/O | `put_task_checkpoint` | Save an incremental checkpoint (survives restarts) |
| I/O | `get_task_payload_refs` | Retrieve all stored output/checkpoints for a task |
| Query | `get_task` | Full state of a single task |
| Query | `list_tasks` | List tasks for a run with status filters |
| Query | `get_workflow_run` | Overall run state and progress |
| Query | `get_blocked_tasks` | Tasks blocked on human input or failed upstreams |
| Query | `get_dag_edges` | All dependency edges for a run |
| Validation | `validate_task_output` | Check output against the task's JSON Schema contract |
| Validation | `validate_dag_acyclic` | Detect cycles in a task list before submitting |
| Sub-agent | `get_my_task` | Narrow task view for a sub-agent |
| Sub-agent | `update_my_progress` | Save incremental progress + checkpoint |
| Sub-agent | `submit_my_output` | Submit final output and complete the task |
| Sub-agent | `request_human_input` | Block task and surface a question to the human |

> Annotated examples: [`references/examples.md`](references/examples.md)

---

## Troubleshooting

> Full troubleshooting guide: [`references/troubleshooting.md`](references/troubleshooting.md)

Quick fixes:

- **Tools not available** → Server is not connected. Ask the user to follow [`references/setup.md`](references/setup.md).
- **`get_ready_tasks` returns empty but run is not complete** → Call `get_blocked_tasks` to find what is stuck and why.
- **Cycle detected on `create_plan_graph`** → Call `validate_dag_acyclic` with your task list first and fix reported cycles.
- **Task stuck in `claimed`** → The lease expired. Call `claim_task_for_execution` again with the same `task_id`.
- **`validate_task_output` fails** → The output you stored does not satisfy the `output_contract` schema. Add the missing required fields and call `put_task_output` again before retrying validation.
