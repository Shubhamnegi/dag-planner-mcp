"""Scheduling tools: get ready tasks and claim them for execution."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from dag_planner_mcp.db import (
    WorkflowRun,
    WorkflowTask,
    WorkflowTaskEdge,
    WorkflowTaskAttempt,
    WorkflowEvent,
    get_engine,
)
from dag_planner_mcp.models import ok_response, err_response


def _short_id():
    return uuid.uuid4().hex[:8]


def _now():
    return datetime.utcnow().isoformat()


def _emit_event(session, run_id, task_id, event_type, payload=None, created_by="system"):
    evt = WorkflowEvent(
        event_id=f"evt_{_short_id()}",
        run_id=run_id,
        task_id=task_id,
        event_type=event_type,
        payload_json=payload or {},
        created_by=created_by,
        created_at=_now(),
    )
    session.add(evt)


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
        "output_contract_json": task.output_contract_json,
        "claimed_by": task.claimed_by,
        "claimed_until": task.claimed_until,
        "retry_count": task.retry_count,
        "max_retries": task.max_retries,
        "plan_version": task.plan_version,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def get_ready_tasks(
    run_id: Optional[str] = None,
    owner_agent: Optional[str] = None,
    limit: int = 10,
    _engine=None,
) -> dict:
    """Return tasks that are ready and not currently claimed (or with expired claim)."""
    engine = _engine or get_engine()
    now_str = _now()
    with Session(engine) as session:
        q = session.query(WorkflowTask).filter(WorkflowTask.status == "ready")
        if run_id:
            q = q.filter(WorkflowTask.run_id == run_id)
        if owner_agent:
            q = q.filter(WorkflowTask.owner_agent == owner_agent)
        # Not claimed, or claim expired
        q = q.filter(
            or_(
                WorkflowTask.claimed_until.is_(None),
                WorkflowTask.claimed_until < now_str,
            )
        )
        q = q.order_by(WorkflowTask.priority.desc(), WorkflowTask.created_at.asc())
        tasks = q.limit(limit).all()
        return ok_response([_task_to_dict(t) for t in tasks])


def claim_task_for_execution(
    task_id: str,
    executor_id: str,
    claim_duration_seconds: int = 300,
    _engine=None,
) -> dict:
    """Claim a ready task for execution. Returns error if already claimed or not ready."""
    engine = _engine or get_engine()
    now = datetime.utcnow()
    now_str = now.isoformat()
    claim_until = (now + timedelta(seconds=claim_duration_seconds)).isoformat()

    with Session(engine) as session:
        task = session.get(WorkflowTask, task_id)
        if task is None:
            return err_response("NOT_FOUND", f"Task '{task_id}' not found")
        if task.status != "ready":
            return err_response(
                "INVALID_STATE",
                f"Task '{task_id}' is not ready (status: {task.status})",
            )
        # Check if still claimed
        if task.claimed_until and task.claimed_until > now_str:
            return err_response(
                "ALREADY_CLAIMED",
                f"Task '{task_id}' is already claimed by '{task.claimed_by}' until {task.claimed_until}",
            )

        task.claimed_by = executor_id
        task.claimed_until = claim_until
        task.updated_at = now_str

        # Create an attempt record
        attempt_id = f"att_{_short_id()}"
        attempt_no = (task.retry_count or 0) + 1
        attempt = WorkflowTaskAttempt(
            attempt_id=attempt_id,
            task_id=task_id,
            run_id=task.run_id,
            attempt_no=attempt_no,
            executor_id=executor_id,
            status="claimed",
            started_at=now_str,
        )
        session.add(attempt)
        _emit_event(
            session,
            task.run_id,
            task_id,
            "task_claimed",
            {"executor_id": executor_id, "claim_until": claim_until, "attempt_id": attempt_id},
        )
        session.commit()
        return ok_response(
            {
                "task_id": task_id,
                "claimed_by": executor_id,
                "claimed_until": claim_until,
                "attempt_id": attempt_id,
            }
        )
