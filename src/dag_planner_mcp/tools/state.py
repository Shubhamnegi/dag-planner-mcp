"""State transition tools for workflow tasks."""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from dag_planner_mcp.db import (
    WorkflowRun,
    WorkflowTask,
    WorkflowTaskEdge,
    WorkflowTaskAttempt,
    WorkflowEvent,
    HumanApproval,
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


def _try_activate_children(session, run_id: str, completed_task_id: str, now: str):
    """After a task completes, check its children and mark ready if all parents done."""
    child_edges = (
        session.query(WorkflowTaskEdge)
        .filter_by(run_id=run_id, parent_task_id=completed_task_id)
        .all()
    )
    for edge in child_edges:
        child_id = edge.child_task_id
        child = session.get(WorkflowTask, child_id)
        if child is None or child.status != "created":
            continue
        # Check all parents of this child
        parent_edges = (
            session.query(WorkflowTaskEdge)
            .filter_by(run_id=run_id, child_task_id=child_id)
            .all()
        )
        all_parents_done = all(
            (session.get(WorkflowTask, pe.parent_task_id) or WorkflowTask(status="completed")).status == "completed"
            for pe in parent_edges
        )
        if all_parents_done:
            child.status = "ready"
            child.updated_at = now
            _emit_event(session, run_id, child_id, "task_ready", {"triggered_by": completed_task_id})


def _check_run_completion(session, run_id: str, now: str):
    """If all tasks in a run are terminal, update run status."""
    tasks = session.query(WorkflowTask).filter_by(run_id=run_id).all()
    if not tasks:
        return
    terminal = {"completed", "cancelled", "failed"}
    statuses = {t.status for t in tasks}
    if statuses <= terminal:
        run = session.get(WorkflowRun, run_id)
        if run and run.status not in ("completed", "failed", "cancelled"):
            if "failed" in statuses:
                run.status = "failed"
            elif "cancelled" in statuses and statuses == {"cancelled"}:
                run.status = "cancelled"
            else:
                run.status = "completed"
            run.updated_at = now
            run.completed_at = now
            _emit_event(session, run_id, None, "run_completed", {"final_status": run.status})


def mark_task_running(task_id: str, executor_id: Optional[str] = None, _engine=None) -> dict:
    """Transition a claimed/ready task to running status."""
    engine = _engine or get_engine()
    now = _now()
    with Session(engine) as session:
        task = session.get(WorkflowTask, task_id)
        if task is None:
            return err_response("NOT_FOUND", f"Task '{task_id}' not found")
        if task.status != "ready":
            return err_response(
                "INVALID_STATE",
                f"Task '{task_id}' cannot transition to running from '{task.status}'",
            )
        task.status = "running"
        task.updated_at = now
        _emit_event(session, task.run_id, task_id, "task_running", {"executor_id": executor_id})
        session.commit()
    return ok_response({"task_id": task_id, "status": "running"})


def mark_task_completed(
    task_id: str,
    final_output: Optional[dict] = None,
    _engine=None,
) -> dict:
    """Mark a task as completed and activate its children if all deps satisfied."""
    engine = _engine or get_engine()
    now = _now()
    with Session(engine) as session:
        task = session.get(WorkflowTask, task_id)
        if task is None:
            return err_response("NOT_FOUND", f"Task '{task_id}' not found")
        if task.status not in ("running", "validating", "ready"):
            return err_response(
                "INVALID_STATE",
                f"Task '{task_id}' cannot be completed from status '{task.status}'",
            )
        task.status = "completed"
        task.updated_at = now
        if final_output is not None:
            task.final_output_json = final_output
        task.claimed_by = None
        task.claimed_until = None
        run_id = task.run_id
        _emit_event(session, run_id, task_id, "task_completed", {"final_output": final_output})
        _try_activate_children(session, run_id, task_id, now)
        session.flush()
        _check_run_completion(session, run_id, now)
        session.commit()
    return ok_response({"task_id": task_id, "status": "completed"})


def mark_task_failed(
    task_id: str,
    error: Optional[dict] = None,
    retry: bool = True,
    _engine=None,
) -> dict:
    """Mark a task as failed. If retry is True and retries remain, reset to ready."""
    engine = _engine or get_engine()
    now = _now()
    with Session(engine) as session:
        task = session.get(WorkflowTask, task_id)
        if task is None:
            return err_response("NOT_FOUND", f"Task '{task_id}' not found")
        if task.status not in ("running", "validating", "ready"):
            return err_response(
                "INVALID_STATE",
                f"Task '{task_id}' cannot be failed from status '{task.status}'",
            )
        run_id = task.run_id
        retry_count = (task.retry_count or 0) + 1
        task.retry_count = retry_count
        task.claimed_by = None
        task.claimed_until = None
        task.updated_at = now

        if retry and retry_count <= (task.max_retries or 3):
            task.status = "ready"
            new_status = "ready"
            _emit_event(session, run_id, task_id, "task_retry", {"retry_count": retry_count, "error": error})
        else:
            task.status = "failed"
            new_status = "failed"
            _emit_event(session, run_id, task_id, "task_failed", {"error": error, "retry_count": retry_count})
            session.flush()
            _check_run_completion(session, run_id, now)

        session.commit()
    return ok_response({"task_id": task_id, "status": new_status, "retry_count": retry_count})


def mark_task_blocked_human(
    task_id: str,
    question: str,
    options: Optional[list] = None,
    requested_by: Optional[str] = None,
    _engine=None,
) -> dict:
    """Block a task pending human approval and create an approval record."""
    engine = _engine or get_engine()
    now = _now()
    with Session(engine) as session:
        task = session.get(WorkflowTask, task_id)
        if task is None:
            return err_response("NOT_FOUND", f"Task '{task_id}' not found")
        if task.status not in ("running", "ready", "created"):
            return err_response(
                "INVALID_STATE",
                f"Task '{task_id}' cannot be blocked from status '{task.status}'",
            )
        run_id = task.run_id
        task.status = "blocked_human"
        task.updated_at = now

        approval_id = f"appr_{_short_id()}"
        approval = HumanApproval(
            approval_id=approval_id,
            run_id=run_id,
            task_id=task_id,
            status="pending",
            question=question,
            options_json=options or [],
            requested_by=requested_by,
            requested_at=now,
        )
        session.add(approval)
        _emit_event(
            session,
            run_id,
            task_id,
            "task_blocked_human",
            {"approval_id": approval_id, "question": question},
        )
        session.commit()
    return ok_response({"task_id": task_id, "approval_id": approval_id, "status": "blocked_human"})


def resume_task(
    task_id: str,
    decision: Optional[dict] = None,
    decided_by: Optional[str] = None,
    _engine=None,
) -> dict:
    """Resume a blocked task after human decision or unblocking."""
    engine = _engine or get_engine()
    now = _now()
    with Session(engine) as session:
        task = session.get(WorkflowTask, task_id)
        if task is None:
            return err_response("NOT_FOUND", f"Task '{task_id}' not found")
        if task.status not in ("blocked_human", "blocked_dependency"):
            return err_response(
                "INVALID_STATE",
                f"Task '{task_id}' is not blocked (status: {task.status})",
            )
        run_id = task.run_id

        # Update pending approval if exists
        if task.status == "blocked_human":
            approval = (
                session.query(HumanApproval)
                .filter_by(task_id=task_id, status="pending")
                .first()
            )
            if approval and decision is not None:
                approval.status = "decided"
                approval.decision_json = decision
                approval.decided_by = decided_by
                approval.decided_at = now

        task.status = "ready"
        task.updated_at = now
        _emit_event(session, run_id, task_id, "task_resumed", {"decision": decision})
        session.commit()
    return ok_response({"task_id": task_id, "status": "ready"})
