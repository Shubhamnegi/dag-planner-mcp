"""Sub-agent tools: narrow task interface for executing agents."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from dag_planner_mcp.db import WorkflowTask, WorkflowEvent, get_engine
from dag_planner_mcp.models import ok_response, err_response
from dag_planner_mcp.tools.io import put_task_output, put_task_checkpoint
from dag_planner_mcp.tools.state import mark_task_completed, mark_task_failed, mark_task_blocked_human


def _short_id():
    return uuid.uuid4().hex[:8]


def _now():
    return datetime.now(timezone.utc).isoformat()


def get_my_task(task_id: str, executor_id: Optional[str] = None, _engine=None) -> dict:
    """
    Return a narrow view of a task for the executing agent.
    Includes input, contract, checkpoint, and current working output.
    """
    engine = _engine or get_engine()
    with Session(engine) as session:
        task = session.get(WorkflowTask, task_id)
        if task is None:
            return err_response("NOT_FOUND", f"Task '{task_id}' not found")
        if executor_id and task.claimed_by and task.claimed_by != executor_id:
            return err_response(
                "FORBIDDEN",
                f"Task '{task_id}' is claimed by '{task.claimed_by}', not '{executor_id}'",
            )
        return ok_response(
            {
                "task_id": task.task_id,
                "run_id": task.run_id,
                "task_key": task.task_key,
                "title": task.title,
                "description": task.description,
                "owner_agent": task.owner_agent,
                "status": task.status,
                "input_json": task.input_json,
                "output_contract_json": task.output_contract_json,
                "working_output_json": task.working_output_json,
                "checkpoint_json": task.checkpoint_json,
                "claimed_by": task.claimed_by,
                "claimed_until": task.claimed_until,
            }
        )


def update_my_progress(
    task_id: str,
    working_output: dict,
    checkpoint: Optional[dict] = None,
    _engine=None,
) -> dict:
    """Update working output and optionally save a checkpoint for a running task."""
    result = put_task_output(task_id=task_id, output=working_output, is_final=False, _engine=_engine)
    if not result["ok"]:
        return result
    if checkpoint is not None:
        cp_result = put_task_checkpoint(task_id=task_id, checkpoint=checkpoint, _engine=_engine)
        if not cp_result["ok"]:
            return cp_result
    return ok_response({"task_id": task_id, "updated": True})


def submit_my_output(
    task_id: str,
    final_output: dict,
    _engine=None,
) -> dict:
    """Submit final output and mark the task completed."""
    put_result = put_task_output(task_id=task_id, output=final_output, is_final=True, _engine=_engine)
    if not put_result["ok"]:
        return put_result
    return mark_task_completed(task_id=task_id, final_output=final_output, _engine=_engine)


def request_human_input(
    task_id: str,
    question: str,
    options: Optional[list] = None,
    requested_by: Optional[str] = None,
    _engine=None,
) -> dict:
    """Block a task pending human input and create an approval record."""
    return mark_task_blocked_human(
        task_id=task_id,
        question=question,
        options=options,
        requested_by=requested_by,
        _engine=_engine,
    )
