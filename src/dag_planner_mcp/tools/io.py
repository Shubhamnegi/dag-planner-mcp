"""IO tools: store task outputs, checkpoints, and retrieve payload refs."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from dag_planner_mcp.db import WorkflowTask, WorkflowEvent, get_engine
from dag_planner_mcp.models import ok_response, err_response


def _short_id():
    return uuid.uuid4().hex[:8]


def _now():
    return datetime.now(timezone.utc).isoformat()


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


def put_task_output(
    task_id: str,
    output: dict,
    is_final: bool = False,
    _engine=None,
) -> dict:
    """Store working or final output for a task."""
    engine = _engine or get_engine()
    now = _now()
    with Session(engine) as session:
        task = session.get(WorkflowTask, task_id)
        if task is None:
            return err_response("NOT_FOUND", f"Task '{task_id}' not found")
        task.working_output_json = output
        task.updated_at = now
        if is_final:
            task.final_output_json = output
            _emit_event(session, task.run_id, task_id, "output_finalized", {"is_final": True})
        else:
            _emit_event(session, task.run_id, task_id, "output_updated", {})
        session.commit()
    return ok_response({"task_id": task_id, "is_final": is_final})


def put_task_checkpoint(
    task_id: str,
    checkpoint: dict,
    _engine=None,
) -> dict:
    """Save a checkpoint for a running task (for resumability)."""
    engine = _engine or get_engine()
    now = _now()
    with Session(engine) as session:
        task = session.get(WorkflowTask, task_id)
        if task is None:
            return err_response("NOT_FOUND", f"Task '{task_id}' not found")
        task.checkpoint_json = checkpoint
        task.updated_at = now
        _emit_event(session, task.run_id, task_id, "checkpoint_saved", {})
        session.commit()
    return ok_response({"task_id": task_id, "checkpointed": True})


def get_task_payload_refs(task_id: str, _engine=None) -> dict:
    """Return input, output, checkpoint, and contract data for a task."""
    engine = _engine or get_engine()
    with Session(engine) as session:
        task = session.get(WorkflowTask, task_id)
        if task is None:
            return err_response("NOT_FOUND", f"Task '{task_id}' not found")
        return ok_response(
            {
                "task_id": task_id,
                "input_json": task.input_json,
                "working_output_json": task.working_output_json,
                "final_output_json": task.final_output_json,
                "output_contract_json": task.output_contract_json,
                "checkpoint_json": task.checkpoint_json,
            }
        )
