# Examples

Each example shows the exact tool calls an agent makes, the expected response shape, and what to do next. No Python SDK required — you call these tools directly.

---

## 1. Minimal Two-Task Sequential Pipeline

**Goal:** "Summarise a document"

**Step 1 — Start the run**

Tool: `create_workflow_run`
Input: `{ "goal": "Summarise a document" }`
Response: `{ "data": { "run_id": "run_001" } }`

**Step 2 — Submit the plan**

Tool: `create_plan_graph`
Input:
```json
{
  "run_id": "run_001",
  "tasks": [
    {
      "task_key": "read",
      "title": "Read document",
      "description": "Load and chunk the document into sections",
      "owner_agent": "me",
      "depends_on": [],
      "output_contract": { "type": "object", "required": ["chunks"] }
    },
    {
      "task_key": "summarise",
      "title": "Summarise chunks",
      "description": "Produce a 200-word summary from the chunks",
      "owner_agent": "me",
      "depends_on": ["read"],
      "output_contract": { "type": "object", "required": ["summary"] }
    }
  ]
}
```

**Step 3 — First loop iteration: only "read" is ready**

Tool: `get_ready_tasks` → `{ "data": { "tasks": [{ "task_id": "t_read", "task_key": "read" }] } }`

Tool: `claim_task_for_execution` → `{ "task_id": "t_read", "executor_id": "me" }`
Tool: `mark_task_running` → `{ "task_id": "t_read" }`
*(Do the work — load and chunk the document)*
Tool: `put_task_output` → `{ "task_id": "t_read", "output": { "chunks": ["..."] }, "is_final": true }`
Tool: `validate_task_output` → `{ "task_id": "t_read" }` ✔
Tool: `mark_task_completed` → `{ "task_id": "t_read", "final_output": { "chunks": ["..."] } }`

**Step 4 — Second loop iteration: "summarise" is now ready**

Repeat claim → run → output → validate → complete for `t_summarise`.

**Step 5 — Third iteration: empty list → workflow complete**

Tool: `get_ready_tasks` → `{ "data": { "tasks": [] } }`

Call `get_workflow_run` to confirm: `{ "data": { "status": "completed" } }`

---

## 2. Parallel Fan-Out (Three Independent Tasks + One Aggregator)

Tasks with no `depends_on` all become ready at the same time. Claim and execute them in any order (or in parallel if your setup supports it).

Tool: `create_plan_graph`
Input:
```json
{
  "run_id": "run_002",
  "tasks": [
    { "task_key": "fetch_ec2", "title": "Fetch EC2 costs", "depends_on": [], "owner_agent": "me",
      "output_contract": { "type": "object", "required": ["cost_usd"] } },
    { "task_key": "fetch_s3",  "title": "Fetch S3 costs",  "depends_on": [], "owner_agent": "me",
      "output_contract": { "type": "object", "required": ["cost_usd"] } },
    { "task_key": "fetch_rds", "title": "Fetch RDS costs", "depends_on": [], "owner_agent": "me",
      "output_contract": { "type": "object", "required": ["cost_usd"] } },
    { "task_key": "report", "title": "Build cost report",
      "depends_on": ["fetch_ec2", "fetch_s3", "fetch_rds"], "owner_agent": "me",
      "output_contract": { "type": "object", "required": ["total_usd", "summary"] } }
  ]
}
```

First `get_ready_tasks` call returns all three fetch tasks simultaneously. Execute all three, then call `get_ready_tasks` again — now `report` is ready.

---

## 3. Human-in-the-Loop Gate

Use when a task requires explicit user approval before proceeding.

**Inside the execution loop, instead of doing the work yourself:**

Tool: `request_human_input`
Input: `{ "task_id": "t_delete", "question": "Delete 47 stale S3 buckets costing $230/month? (yes/no)" }`

The task moves to `blocked_human`. Surface the question to the user and wait.

**When the user responds "yes":**

Tool: `resume_task`
Input: `{ "task_id": "t_delete", "decision": "approved" }`

The task re-enters the ready queue. Next `get_ready_tasks` call will return it.

**Checking what is blocked:**

Tool: `get_blocked_tasks`
Input: `{ "run_id": "run_003" }`
Response: lists all tasks currently in `blocked_human` or blocked by a failed upstream.

---

## 4. Incremental Progress and Checkpoint

For long-running tasks that process many items, save checkpoints so a retry picks up where it left off.

**While processing items, call periodically:**

Tool: `update_my_progress`
Input:
```json
{
  "task_id": "t_process",
  "working_output": { "processed_count": 42, "last_item_id": "item_042" },
  "checkpoint": { "last_index": 41 }
}
```

**If the task restarts, read the last checkpoint:**

Tool: `get_task_payload_refs`
Input: `{ "task_id": "t_process" }`
Response contains `checkpoint` with `{ "last_index": 41 }` — resume from index 42.

---

## 5. Validate DAG Before Submitting

Always call this before `create_plan_graph` when the dependency graph is non-trivial.

Tool: `validate_dag_acyclic`
Input:
```json
{
  "tasks": [
    { "task_key": "a", "depends_on": ["b"] },
    { "task_key": "b", "depends_on": ["a"] }
  ]
}
```
Response: error — `"Cycle detected involving task 'a'"`

Fix the cycle, then call `create_plan_graph`.

---

## 6. Dynamic Branch Replacement (Replanning Mid-Run)

When a task fails and its planned recovery path is no longer valid, swap in a new branch without restarting the whole run.

Tool: `replace_plan_branch`
Input:
```json
{
  "run_id": "run_005",
  "cancel_from_task_key": "analyze",
  "new_tasks": [
    {
      "task_key": "fallback_analyze",
      "title": "Simplified fallback analysis",
      "description": "Use cached data instead of fresh pull",
      "owner_agent": "me",
      "depends_on": ["fetch_data"],
      "output_contract": { "type": "object", "required": ["summary"] }
    }
  ]
}
```

`analyze` and all its descendants are cancelled. `fallback_analyze` is grafted in their place and becomes ready as soon as `fetch_data` completes.

---

## 7. Querying Run State Mid-Execution

**Get full run status:**

Tool: `get_workflow_run`
Input: `{ "run_id": "run_001" }`
Response: `{ "data": { "status": "in_progress", "goal": "...", "completed_tasks": 2, "total_tasks": 4 } }`

**List all tasks with their current status:**

Tool: `list_tasks`
Input: `{ "run_id": "run_001" }`
Response: array of tasks each with `status` (`pending`, `ready`, `claimed`, `running`, `completed`, `failed`, `blocked_human`)

**Inspect a specific task:**

Tool: `get_task`
Input: `{ "task_id": "t_analyze" }`
Response: full task record including status, owner, output, and dependency list.
