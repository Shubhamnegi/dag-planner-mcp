"""Query tools: inspect workflow runs and tasks."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from dag_planner_mcp.db import WorkflowRun, WorkflowTask, WorkflowTaskEdge, WorkflowEvent, get_engine
from dag_planner_mcp.models import ok_response, err_response


def _task_to_dict(task: WorkflowTask) -> dict:
    return {
        "task_id": task.task_id,
        "run_id": task.run_id,
        "task_key": task.task_key,
        "title": task.title,
        "description": task.description,
        "owner_agent": task.owner_agent,
        "status": task.status,
        "priority": task.priority,
        "input_json": task.input_json,
        "final_output_json": task.final_output_json,
        "working_output_json": task.working_output_json,
        "output_contract_json": task.output_contract_json,
        "checkpoint_json": task.checkpoint_json,
        "claimed_by": task.claimed_by,
        "claimed_until": task.claimed_until,
        "retry_count": task.retry_count,
        "max_retries": task.max_retries,
        "plan_version": task.plan_version,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def get_task(task_id: str, _engine=None) -> dict:
    """Return full state of a single task."""
    engine = _engine or get_engine()
    with Session(engine) as session:
        task = session.get(WorkflowTask, task_id)
        if task is None:
            return err_response("NOT_FOUND", f"Task '{task_id}' not found")
        return ok_response(_task_to_dict(task))


def list_tasks(
    run_id: str,
    status: Optional[str] = None,
    owner_agent: Optional[str] = None,
    limit: int = 100,
    _engine=None,
) -> dict:
    """List tasks for a run, optionally filtered by status or owner_agent."""
    engine = _engine or get_engine()
    with Session(engine) as session:
        q = session.query(WorkflowTask).filter_by(run_id=run_id)
        if status:
            q = q.filter(WorkflowTask.status == status)
        if owner_agent:
            q = q.filter(WorkflowTask.owner_agent == owner_agent)
        q = q.order_by(WorkflowTask.priority.desc(), WorkflowTask.created_at.asc())
        tasks = q.limit(limit).all()
        return ok_response([_task_to_dict(t) for t in tasks])


def get_workflow_run(run_id: str, include_tasks: bool = False, _engine=None) -> dict:
    """Return workflow run state, optionally including all tasks."""
    engine = _engine or get_engine()
    with Session(engine) as session:
        run = session.get(WorkflowRun, run_id)
        if run is None:
            return err_response("NOT_FOUND", f"Run '{run_id}' not found")
        data = {
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
        }
        if include_tasks:
            tasks = session.query(WorkflowTask).filter_by(run_id=run_id).all()
            data["tasks"] = [_task_to_dict(t) for t in tasks]
        return ok_response(data)


def get_blocked_tasks(run_id: str, _engine=None) -> dict:
    """Return all tasks that are blocked (by human or dependency)."""
    engine = _engine or get_engine()
    with Session(engine) as session:
        tasks = (
            session.query(WorkflowTask)
            .filter(
                WorkflowTask.run_id == run_id,
                WorkflowTask.status.in_(["blocked_human", "blocked_dependency"]),
            )
            .all()
        )
        return ok_response([_task_to_dict(t) for t in tasks])


def get_dag_edges(run_id: str, _engine=None) -> dict:
    """Return all edges for a run as parent->child adjacency pairs."""
    engine = _engine or get_engine()
    with Session(engine) as session:
        edges = session.query(WorkflowTaskEdge).filter_by(run_id=run_id).all()
        return ok_response(
            [
                {
                    "parent_task_id": e.parent_task_id,
                    "child_task_id": e.child_task_id,
                    "edge_type": e.edge_type,
                }
                for e in edges
            ]
        )
