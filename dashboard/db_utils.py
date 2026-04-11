"""Read-only synchronous query helpers for the Streamlit dashboard.

All functions use the same SQLAlchemy engine (and DATABASE_URL env var) as
the MCP server itself — no writes are ever performed here.
"""

import sys
import os

# Allow importing dag_planner_mcp from the src layout without installing
_src = os.path.join(os.path.dirname(__file__), "..", "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from sqlalchemy.orm import Session
from sqlalchemy import func

from dag_planner_mcp.db import (
    get_engine as _get_engine,
    WorkflowRun,
    WorkflowTask,
    WorkflowTaskEdge,
    WorkflowEvent,
    HumanApproval,
)


def get_engine():
    return _get_engine()


# ---------------------------------------------------------------------------
# Workflow runs
# ---------------------------------------------------------------------------

def list_workflow_runs(
    search: str = "",
    status_filter: str = "all",
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[dict], int]:
    """Return (rows, total_count) for the workflow run list page."""
    engine = get_engine()
    with Session(engine) as session:
        q = session.query(WorkflowRun)
        if search:
            q = q.filter(WorkflowRun.goal.ilike(f"%{search}%"))
        if status_filter and status_filter != "all":
            q = q.filter(WorkflowRun.status == status_filter)
        total = q.count()
        q = q.order_by(WorkflowRun.updated_at.desc())
        offset = (page - 1) * page_size
        runs = q.offset(offset).limit(page_size).all()
        rows = [
            {
                "run_id": r.run_id,
                "goal": r.goal,
                "status": r.status,
                "user_id": r.user_id or "",
                "plan_version": r.plan_version,
                "created_at": r.created_at,
                "updated_at": r.updated_at,
            }
            for r in runs
        ]
    return rows, total


def get_workflow_run(run_id: str) -> dict | None:
    """Return a single run with its tasks and edges, or None if not found."""
    engine = get_engine()
    with Session(engine) as session:
        run = session.get(WorkflowRun, run_id)
        if run is None:
            return None
        tasks = session.query(WorkflowTask).filter_by(run_id=run_id).all()
        edges = session.query(WorkflowTaskEdge).filter_by(run_id=run_id).all()
        return {
            "run_id": run.run_id,
            "session_id": run.session_id,
            "user_id": run.user_id,
            "goal": run.goal,
            "status": run.status,
            "plan_version": run.plan_version,
            "metadata_json": run.metadata_json,
            "created_at": run.created_at,
            "updated_at": run.updated_at,
            "completed_at": run.completed_at,
            "tasks": [
                {
                    "task_id": t.task_id,
                    "task_key": t.task_key,
                    "title": t.title,
                    "description": t.description,
                    "owner_agent": t.owner_agent,
                    "status": t.status,
                    "priority": t.priority,
                    "retry_count": t.retry_count,
                    "max_retries": t.max_retries,
                    "plan_version": t.plan_version,
                    "claimed_by": t.claimed_by,
                    "claimed_until": t.claimed_until,
                    "input_json": t.input_json,
                    "final_output_json": t.final_output_json,
                    "working_output_json": t.working_output_json,
                    "output_contract_json": t.output_contract_json,
                    "checkpoint_json": t.checkpoint_json,
                    "created_at": t.created_at,
                    "updated_at": t.updated_at,
                }
                for t in tasks
            ],
            "edges": [
                {
                    "parent_task_id": e.parent_task_id,
                    "child_task_id": e.child_task_id,
                    "edge_type": e.edge_type,
                }
                for e in edges
            ],
        }


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

def get_task(task_id: str) -> dict | None:
    """Return full task detail or None if not found."""
    engine = get_engine()
    with Session(engine) as session:
        t = session.get(WorkflowTask, task_id)
        if t is None:
            return None
        return {
            "task_id": t.task_id,
            "run_id": t.run_id,
            "task_key": t.task_key,
            "title": t.title,
            "description": t.description,
            "owner_agent": t.owner_agent,
            "status": t.status,
            "priority": t.priority,
            "retry_count": t.retry_count,
            "max_retries": t.max_retries,
            "plan_version": t.plan_version,
            "claimed_by": t.claimed_by,
            "claimed_until": t.claimed_until,
            "input_json": t.input_json,
            "final_output_json": t.final_output_json,
            "working_output_json": t.working_output_json,
            "output_contract_json": t.output_contract_json,
            "checkpoint_json": t.checkpoint_json,
            "created_at": t.created_at,
            "updated_at": t.updated_at,
        }


# ---------------------------------------------------------------------------
# Events & Approvals
# ---------------------------------------------------------------------------

def list_events(run_id: str) -> list[dict]:
    """Return events for a run, newest first."""
    engine = get_engine()
    with Session(engine) as session:
        events = (
            session.query(WorkflowEvent)
            .filter_by(run_id=run_id)
            .order_by(WorkflowEvent.created_at.desc())
            .all()
        )
        return [
            {
                "event_id": e.event_id,
                "event_type": e.event_type,
                "task_id": e.task_id or "",
                "created_by": e.created_by,
                "created_at": e.created_at,
                "payload_json": e.payload_json,
            }
            for e in events
        ]


def list_approvals(run_id: str) -> list[dict]:
    """Return human approvals for a run."""
    engine = get_engine()
    with Session(engine) as session:
        approvals = (
            session.query(HumanApproval)
            .filter_by(run_id=run_id)
            .order_by(HumanApproval.requested_at.desc())
            .all()
        )
        return [
            {
                "approval_id": a.approval_id,
                "task_id": a.task_id,
                "status": a.status,
                "question": a.question,
                "options_json": a.options_json,
                "decision_json": a.decision_json,
                "requested_by": a.requested_by or "",
                "decided_by": a.decided_by or "",
                "requested_at": a.requested_at,
                "decided_at": a.decided_at or "",
            }
            for a in approvals
        ]


# ---------------------------------------------------------------------------
# Aggregate stats
# ---------------------------------------------------------------------------

def get_run_stats() -> dict:
    """Return aggregate run counts by status plus task status counts."""
    engine = get_engine()
    with Session(engine) as session:
        run_rows = session.query(WorkflowRun.status, func.count()).group_by(WorkflowRun.status).all()
        task_rows = session.query(WorkflowTask.status, func.count()).group_by(WorkflowTask.status).all()
    run_counts = {status: count for status, count in run_rows}
    task_counts = {status: count for status, count in task_rows}
    total = sum(run_counts.values())
    return {
        "total": total,
        "by_status": run_counts,
        "task_by_status": task_counts,
    }
