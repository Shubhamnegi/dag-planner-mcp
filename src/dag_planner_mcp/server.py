"""MCP server exposing all DAG Planner tools."""

import logging
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP


def _configure_file_logging() -> None:
    """Attach a FileHandler when LOG_FILE env var is set. No-op otherwise."""
    log_path = os.environ.get("LOG_FILE", "").strip()
    if not log_path:
        return
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(
        logging.getLogger().level or logging.INFO
    )


_configure_file_logging()

logger = logging.getLogger("dag_planner_mcp")

from dag_planner_mcp.tools.planning import (
    create_workflow_run as _create_workflow_run,
    create_plan_graph as _create_plan_graph,
    replace_plan_branch as _replace_plan_branch,
)
from dag_planner_mcp.tools.scheduling import (
    get_ready_tasks as _get_ready_tasks,
    claim_task_for_execution as _claim_task_for_execution,
)
from dag_planner_mcp.tools.state import (
    mark_task_running as _mark_task_running,
    mark_task_completed as _mark_task_completed,
    mark_task_failed as _mark_task_failed,
    mark_task_blocked_human as _mark_task_blocked_human,
    resume_task as _resume_task,
)
from dag_planner_mcp.tools.io import (
    put_task_output as _put_task_output,
    put_task_checkpoint as _put_task_checkpoint,
    get_task_payload_refs as _get_task_payload_refs,
)
from dag_planner_mcp.tools.query import (
    get_task as _get_task,
    list_tasks as _list_tasks,
    get_workflow_run as _get_workflow_run,
    get_blocked_tasks as _get_blocked_tasks,
    get_dag_edges as _get_dag_edges,
)
from dag_planner_mcp.tools.validation import (
    validate_task_output as _validate_task_output,
    validate_dag_acyclic as _validate_dag_acyclic,
)
from dag_planner_mcp.tools.subagent import (
    get_my_task as _get_my_task,
    update_my_progress as _update_my_progress,
    submit_my_output as _submit_my_output,
    request_human_input as _request_human_input,
)

mcp = FastMCP("dag-planner-mcp")

def _log_db_status() -> None:
    """Log database URL and connectivity state at startup."""
    from sqlalchemy import text, inspect as sa_inspect
    from dag_planner_mcp.db import get_engine, _normalize_db_url
    import urllib.parse

    raw_url = _normalize_db_url(os.environ.get("DATABASE_URL", "sqlite:///dag_planner.db"))
    # Mask password in URL before logging
    try:
        parsed = urllib.parse.urlparse(raw_url)
        if parsed.password:
            raw_url = raw_url.replace(parsed.password, "***")
    except Exception:
        pass

    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        tables = sa_inspect(engine).get_table_names()
        logger.info("DB connected  : %s", raw_url)
        logger.info("DB tables     : %s", ", ".join(tables) if tables else "(none)")
    except Exception as exc:
        logger.error("DB connection FAILED : %s — %s", raw_url, exc)


logger.info("=" * 60)
logger.info("DAG Planner MCP server initialising")
logger.info("Log file  : %s", os.environ.get("LOG_FILE", "(none — file logging disabled)"))
_log_db_status()
logger.info("=" * 60)


# ── Planning ──────────────────────────────────────────────────────────────────

@mcp.tool()
def create_workflow_run(goal: str, session_id: str = None, user_id: str = None, metadata: dict = None) -> dict:
    """Create a new workflow run in draft status."""
    return _create_workflow_run(goal=goal, session_id=session_id, user_id=user_id, metadata=metadata)


@mcp.tool()
def create_plan_graph(run_id: str, tasks: list, activate: bool = True) -> dict:
    """Create a plan graph (DAG of tasks) for an existing run."""
    return _create_plan_graph(run_id=run_id, tasks=tasks, activate=activate)


@mcp.tool()
def replace_plan_branch(run_id: str, anchor_task_id: str, new_tasks: list) -> dict:
    """Cancel downstream tasks from anchor and replace with new tasks."""
    return _replace_plan_branch(run_id=run_id, anchor_task_id=anchor_task_id, new_tasks=new_tasks)


# ── Scheduling ────────────────────────────────────────────────────────────────

@mcp.tool()
def get_ready_tasks(run_id: str = None, owner_agent: str = None, limit: int = 10) -> dict:
    """Return tasks that are ready and not currently claimed."""
    return _get_ready_tasks(run_id=run_id, owner_agent=owner_agent, limit=limit)


@mcp.tool()
def claim_task_for_execution(task_id: str, executor_id: str, claim_duration_seconds: int = 300) -> dict:
    """Claim a ready task for exclusive execution."""
    return _claim_task_for_execution(
        task_id=task_id, executor_id=executor_id, claim_duration_seconds=claim_duration_seconds
    )


# ── State ─────────────────────────────────────────────────────────────────────

@mcp.tool()
def mark_task_running(task_id: str, executor_id: str = None) -> dict:
    """Transition a task to running status."""
    return _mark_task_running(task_id=task_id, executor_id=executor_id)


@mcp.tool()
def mark_task_completed(task_id: str, final_output: dict = None) -> dict:
    """Mark a task completed and activate dependent tasks."""
    return _mark_task_completed(task_id=task_id, final_output=final_output)


@mcp.tool()
def mark_task_failed(task_id: str, error: dict = None, retry: bool = True) -> dict:
    """Mark a task failed, with optional retry logic."""
    return _mark_task_failed(task_id=task_id, error=error, retry=retry)


@mcp.tool()
def mark_task_blocked_human(task_id: str, question: str, options: list = None, requested_by: str = None) -> dict:
    """Block a task pending human approval."""
    return _mark_task_blocked_human(
        task_id=task_id, question=question, options=options, requested_by=requested_by
    )


@mcp.tool()
def resume_task(task_id: str, decision: dict = None, decided_by: str = None) -> dict:
    """Resume a blocked task after human decision."""
    return _resume_task(task_id=task_id, decision=decision, decided_by=decided_by)


# ── IO ────────────────────────────────────────────────────────────────────────

@mcp.tool()
def put_task_output(task_id: str, output: dict, is_final: bool = False) -> dict:
    """Store working or final output for a task."""
    return _put_task_output(task_id=task_id, output=output, is_final=is_final)


@mcp.tool()
def put_task_checkpoint(task_id: str, checkpoint: dict) -> dict:
    """Save a checkpoint for a running task."""
    return _put_task_checkpoint(task_id=task_id, checkpoint=checkpoint)


@mcp.tool()
def get_task_payload_refs(task_id: str) -> dict:
    """Retrieve all payload data (input, output, checkpoint, contract) for a task."""
    return _get_task_payload_refs(task_id=task_id)


# ── Query ─────────────────────────────────────────────────────────────────────

@mcp.tool()
def get_task(task_id: str) -> dict:
    """Return full state of a single task."""
    return _get_task(task_id=task_id)


@mcp.tool()
def list_tasks(run_id: str, status: str = None, owner_agent: str = None, limit: int = 100) -> dict:
    """List tasks for a run with optional filters."""
    return _list_tasks(run_id=run_id, status=status, owner_agent=owner_agent, limit=limit)


@mcp.tool()
def get_workflow_run(run_id: str, include_tasks: bool = False) -> dict:
    """Return workflow run state."""
    return _get_workflow_run(run_id=run_id, include_tasks=include_tasks)


@mcp.tool()
def get_blocked_tasks(run_id: str) -> dict:
    """Return all blocked tasks for a run."""
    return _get_blocked_tasks(run_id=run_id)


@mcp.tool()
def get_dag_edges(run_id: str) -> dict:
    """Return all DAG edges for a run."""
    return _get_dag_edges(run_id=run_id)


# ── Validation ────────────────────────────────────────────────────────────────

@mcp.tool()
def validate_task_output(task_id: str, output: dict = None) -> dict:
    """Validate a task's output against its JSON Schema contract."""
    return _validate_task_output(task_id=task_id, output=output)


@mcp.tool()
def validate_dag_acyclic(tasks: list) -> dict:
    """Validate that a task list forms an acyclic DAG."""
    return _validate_dag_acyclic(tasks=tasks)


# ── Sub-agent ─────────────────────────────────────────────────────────────────

@mcp.tool()
def get_my_task(task_id: str, executor_id: str = None) -> dict:
    """Get task details from the executing agent's perspective."""
    return _get_my_task(task_id=task_id, executor_id=executor_id)


@mcp.tool()
def update_my_progress(task_id: str, working_output: dict, checkpoint: dict = None) -> dict:
    """Update working output and optionally checkpoint progress."""
    return _update_my_progress(task_id=task_id, working_output=working_output, checkpoint=checkpoint)


@mcp.tool()
def submit_my_output(task_id: str, final_output: dict) -> dict:
    """Submit final output and mark task completed."""
    return _submit_my_output(task_id=task_id, final_output=final_output)


@mcp.tool()
def request_human_input(task_id: str, question: str, options: list = None, requested_by: str = None) -> dict:
    """Request human input, blocking the task until decided."""
    return _request_human_input(
        task_id=task_id, question=question, options=options, requested_by=requested_by
    )


def main():
    logger.info("DAG Planner MCP server starting (transport=stdio)")
    mcp.run()
    logger.info("DAG Planner MCP server stopped")


if __name__ == "__main__":
    main()
