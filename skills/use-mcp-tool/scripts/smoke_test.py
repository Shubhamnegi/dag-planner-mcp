"""
smoke_test.py — quick sanity check for dag-planner-mcp.

Starts an in-process server backed by an in-memory SQLite database and
exercises the core planning/execution loop:

  create_workflow_run → create_plan_graph → get_ready_tasks →
  claim → mark_running → put_output → validate → mark_completed

Run:
    python skills/use-mcp-tool/scripts/smoke_test.py
"""

import asyncio
import json
import os
import sys

# Ensure the repo src is importable when running from the repo root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from mcp import ClientSession
from mcp.client.stdio import stdio_client


def call_result(res) -> dict:
    return json.loads(res.content[0].text)


async def smoke_test():
    cmd = [sys.executable, "-m", "dag_planner_mcp.server"]
    env = {**os.environ, "DATABASE_URL": "sqlite:///:memory:"}

    async with stdio_client(cmd) as (r, w):
        async with ClientSession(r, w) as session:
            await session.initialize()
            print("✔ Server connected")

            # 1. Create workflow run
            res = call_result(
                await session.call_tool("create_workflow_run",
                                        {"goal": "Smoke test goal"})
            )
            run_id = res["data"]["run_id"]
            print(f"✔ create_workflow_run  run_id={run_id}")

            # 2. Define a two-task DAG
            await session.call_tool("create_plan_graph", {
                "run_id": run_id,
                "tasks": [
                    {
                        "task_key": "step_a",
                        "title": "Step A",
                        "description": "First step",
                        "owner_agent": "smoke_tester",
                        "depends_on": [],
                        "output_contract": {
                            "type": "object",
                            "required": ["value_a"]
                        }
                    },
                    {
                        "task_key": "step_b",
                        "title": "Step B",
                        "description": "Second step — depends on A",
                        "owner_agent": "smoke_tester",
                        "depends_on": ["step_a"],
                        "output_contract": {
                            "type": "object",
                            "required": ["value_b"]
                        }
                    }
                ]
            })
            print("✔ create_plan_graph")

            # 3. Execution loop
            iterations = 0
            while True:
                ready = call_result(
                    await session.call_tool("get_ready_tasks", {"run_id": run_id})
                )["data"]["tasks"]

                if not ready:
                    break

                iterations += 1
                for task in ready:
                    tid = task["task_id"]
                    tkey = task["task_key"]

                    await session.call_tool("claim_task_for_execution",
                                            {"task_id": tid, "executor_id": "smoke"})
                    await session.call_tool("mark_task_running", {"task_id": tid})

                    output = {"value_a": 42} if tkey == "step_a" else {"value_b": 99}

                    await session.call_tool("put_task_output",
                                            {"task_id": tid, "output": output, "is_final": True})
                    await session.call_tool("validate_task_output", {"task_id": tid})
                    await session.call_tool("mark_task_completed",
                                            {"task_id": tid, "final_output": output})
                    print(f"  ✔ completed task '{tkey}'")

            # 4. Verify run state
            run = call_result(
                await session.call_tool("get_workflow_run", {"run_id": run_id})
            )["data"]
            print(f"✔ Workflow run status: {run['status']}")
            assert run["status"] == "completed", f"Expected completed, got {run['status']}"

            print("\n✅ Smoke test passed")


if __name__ == "__main__":
    asyncio.run(smoke_test())
