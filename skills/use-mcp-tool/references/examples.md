# Examples

## 1. Minimal Two-Task Pipeline

```python
import json, asyncio
from mcp import ClientSession
from mcp.client.stdio import stdio_client

async def main():
    async with stdio_client(["dag-planner-mcp"]) as (r, w):
        async with ClientSession(r, w) as session:
            await session.initialize()

            # Create run
            res = await session.call_tool("create_workflow_run",
                                          {"goal": "Summarise a document"})
            run_id = json.loads(res.content[0].text)["data"]["run_id"]

            # Define DAG
            await session.call_tool("create_plan_graph", {
                "run_id": run_id,
                "tasks": [
                    {
                        "task_key": "read",
                        "title": "Read document",
                        "description": "Load and chunk the document",
                        "owner_agent": "reader",
                        "depends_on": [],
                        "output_contract": {"type": "object", "required": ["chunks"]}
                    },
                    {
                        "task_key": "summarise",
                        "title": "Summarise chunks",
                        "description": "Produce a 200-word summary",
                        "owner_agent": "writer",
                        "depends_on": ["read"],
                        "output_contract": {"type": "object", "required": ["summary"]}
                    }
                ]
            })

            # Execute
            while True:
                res = await session.call_tool("get_ready_tasks", {"run_id": run_id})
                tasks = json.loads(res.content[0].text)["data"]["tasks"]
                if not tasks:
                    break

                for task in tasks:
                    tid = task["task_id"]
                    await session.call_tool("claim_task_for_execution",
                                            {"task_id": tid, "executor_id": "demo"})
                    await session.call_tool("mark_task_running", {"task_id": tid})

                    # Simulate work
                    output = {"chunks": ["chunk1"]} if task["task_key"] == "read" \
                             else {"summary": "The document is about ..."}

                    await session.call_tool("put_task_output",
                                            {"task_id": tid, "output": output, "is_final": True})
                    await session.call_tool("validate_task_output", {"task_id": tid})
                    await session.call_tool("mark_task_completed",
                                            {"task_id": tid, "final_output": output})

asyncio.run(main())
```

---

## 2. Parallel Fan-Out

All three leaf tasks run in parallel because they share no dependencies:

```python
await session.call_tool("create_plan_graph", {
    "run_id": run_id,
    "tasks": [
        {"task_key": "fetch_ec2",  "title": "Fetch EC2 costs",  "depends_on": [], ...},
        {"task_key": "fetch_s3",   "title": "Fetch S3 costs",   "depends_on": [], ...},
        {"task_key": "fetch_rds",  "title": "Fetch RDS costs",  "depends_on": [], ...},
        {
            "task_key": "report",
            "title": "Build cost report",
            "depends_on": ["fetch_ec2", "fetch_s3", "fetch_rds"],
            ...
        }
    ]
})
```

Call `get_ready_tasks` in a loop — the first iteration returns all three fetch tasks.

---

## 3. Human-in-the-Loop Gate

```python
# Sub-agent blocks on a decision
await session.call_tool("request_human_input", {
    "task_id": task_id,
    "question": "Delete 47 stale S3 buckets costing $230/month? (yes/no)"
})

# Human reviews, then the orchestrator resumes
await session.call_tool("resume_task", {
    "task_id": task_id,
    "decision": "yes"
})
```

---

## 4. Incremental Progress + Checkpoint

Sub-agents that process many items can save checkpoints so a retry picks up where it left off:

```python
for i, item in enumerate(items):
    result = process(item)
    await session.call_tool("update_my_progress", {
        "task_id": task_id,
        "working_output": {"processed": i + 1, "last_result": result},
        "checkpoint": {"last_index": i}
    })
```

On restart, read the checkpoint:

```python
refs = await session.call_tool("get_task_payload_refs", {"task_id": task_id})
# contains checkpoint data from the last run
```

---

## 5. Validate DAG Before Submitting

Detect cycles before sending the plan:

```python
await session.call_tool("validate_dag_acyclic", {
    "tasks": [
        {"task_key": "a", "depends_on": ["b"]},
        {"task_key": "b", "depends_on": ["a"]}   # cycle!
    ]
})
# Returns error: "Cycle detected involving task 'a'"
```

---

## 6. Dynamic Branch Replacement

Replace a failing branch mid-flight:

```python
await session.call_tool("replace_plan_branch", {
    "run_id": run_id,
    "cancel_from_task_key": "analyze",  # cancel this and all descendants
    "new_tasks": [
        {
            "task_key": "fallback_analyze",
            "title": "Fallback analysis",
            "depends_on": ["fetch_data"],
            ...
        }
    ]
})
```
