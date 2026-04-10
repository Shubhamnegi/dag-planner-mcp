"""
example_client.py — complete orchestrator example for dag-planner-mcp.

Demonstrates:
  - Creating a workflow run
  - Defining a three-task DAG with a parallel fan-out
  - Running the execution loop
  - Validating outputs

Usage:
    # stdio mode (server starts automatically)
    python skills/use-mcp-tool/scripts/example_client.py

    # HTTP mode (start server first: dag-planner-mcp --transport streamable-http)
    python skills/use-mcp-tool/scripts/example_client.py --http http://localhost:8000/mcp
"""

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))

os.environ.setdefault("DATABASE_URL", "sqlite:///dag_planner_example.db")


def _parse(res) -> dict:
    return json.loads(res.content[0].text)


# ---------------------------------------------------------------------------
# Simulated sub-agent work
# ---------------------------------------------------------------------------

SIMULATED_OUTPUTS = {
    "fetch_ec2": {"service": "EC2", "cost_usd": 1420.50},
    "fetch_s3":  {"service": "S3",  "cost_usd": 312.00},
    "report":    {"total_usd": 1732.50, "top_service": "EC2",
                  "summary": "EC2 accounts for 82% of spend."},
}


async def do_work(task_key: str) -> dict:
    """Simulate a sub-agent doing real work."""
    await asyncio.sleep(0.1)
    return SIMULATED_OUTPUTS.get(task_key, {"result": "ok"})


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def run_orchestrator(session):
    from mcp import ClientSession  # noqa: F401 — already imported via session arg

    await session.initialize()
    print("[orchestrator] connected to MCP server\n")

    # 1. Create run
    res = _parse(await session.call_tool("create_workflow_run", {
        "goal": "Analyse AWS cost spike for the last 3 weeks and produce a report"
    }))
    run_id = res["data"]["run_id"]
    print(f"[orchestrator] run_id = {run_id}")

    # 2. Define DAG — two parallel fetch tasks, then a dependent report task
    await session.call_tool("create_plan_graph", {
        "run_id": run_id,
        "tasks": [
            {
                "task_key": "fetch_ec2",
                "title": "Fetch EC2 costs",
                "description": "Pull EC2 spend for the last 3 weeks",
                "owner_agent": "cost_agent",
                "depends_on": [],
                "output_contract": {
                    "type": "object",
                    "required": ["service", "cost_usd"]
                }
            },
            {
                "task_key": "fetch_s3",
                "title": "Fetch S3 costs",
                "description": "Pull S3 spend for the last 3 weeks",
                "owner_agent": "cost_agent",
                "depends_on": [],
                "output_contract": {
                    "type": "object",
                    "required": ["service", "cost_usd"]
                }
            },
            {
                "task_key": "report",
                "title": "Build cost report",
                "description": "Combine service costs into a final report",
                "owner_agent": "report_agent",
                "depends_on": ["fetch_ec2", "fetch_s3"],
                "output_contract": {
                    "type": "object",
                    "required": ["total_usd", "top_service", "summary"]
                }
            }
        ]
    })
    print("[orchestrator] plan graph created\n")

    # 3. Execution loop
    iteration = 0
    while True:
        ready = _parse(
            await session.call_tool("get_ready_tasks", {"run_id": run_id})
        )["data"]["tasks"]

        if not ready:
            break

        iteration += 1
        print(f"[orchestrator] iteration {iteration}: {len(ready)} ready task(s)")

        # Dispatch all ready tasks concurrently
        await asyncio.gather(*[execute_task(session, task) for task in ready])

    # 4. Final run state
    run = _parse(await session.call_tool("get_workflow_run", {"run_id": run_id}))["data"]
    print(f"\n[orchestrator] workflow finished — status: {run['status']}")

    # 5. Print final report output
    tasks = _parse(await session.call_tool("list_tasks", {"run_id": run_id}))["data"]["tasks"]
    for t in tasks:
        if t["task_key"] == "report":
            refs = _parse(
                await session.call_tool("get_task_payload_refs", {"task_id": t["task_id"]})
            )["data"]
            print("\n=== Final Report ===")
            print(json.dumps(refs.get("final_output", {}), indent=2))


async def execute_task(session, task):
    tid = task["task_id"]
    tkey = task["task_key"]

    await session.call_tool("claim_task_for_execution",
                            {"task_id": tid, "executor_id": "example-orchestrator"})
    await session.call_tool("mark_task_running", {"task_id": tid})
    print(f"  → executing '{tkey}' ...")

    output = await do_work(tkey)

    await session.call_tool("put_task_output",
                            {"task_id": tid, "output": output, "is_final": True})
    await session.call_tool("validate_task_output", {"task_id": tid})
    await session.call_tool("mark_task_completed",
                            {"task_id": tid, "final_output": output})
    print(f"  ✔ '{tkey}' completed")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--http", metavar="URL",
                        help="Use HTTP transport (e.g. http://localhost:8000/mcp)")
    args = parser.parse_args()

    if args.http:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamablehttp_client

        async with streamablehttp_client(args.http) as (r, w, _):
            async with ClientSession(r, w) as session:
                await run_orchestrator(session)
    else:
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client

        cmd = [sys.executable, "-m", "dag_planner_mcp.server"]
        async with stdio_client(cmd) as (r, w):
            async with ClientSession(r, w) as session:
                await run_orchestrator(session)


if __name__ == "__main__":
    asyncio.run(main())
