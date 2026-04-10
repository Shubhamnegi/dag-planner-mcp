"""Validation tools: validate task output against JSON Schema contract."""

import uuid
from datetime import datetime, timezone
from typing import Optional

import jsonschema
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


def validate_task_output(task_id: str, output: Optional[dict] = None, _engine=None) -> dict:
    """
    Validate a task's output (final_output_json or provided output) against
    its output_contract_json JSON Schema.

    Returns ok=True with validation result, or error if task not found.
    """
    engine = _engine or get_engine()
    with Session(engine) as session:
        task = session.get(WorkflowTask, task_id)
        if task is None:
            return err_response("NOT_FOUND", f"Task '{task_id}' not found")

        contract = task.output_contract_json
        data_to_validate = output if output is not None else task.final_output_json

        if not contract:
            return ok_response({"task_id": task_id, "valid": True, "message": "No contract defined"})

        if data_to_validate is None:
            return ok_response(
                {"task_id": task_id, "valid": False, "errors": ["No output available to validate"]}
            )

        try:
            jsonschema.validate(instance=data_to_validate, schema=contract)
            _emit_event(session, task.run_id, task_id, "output_validated", {"valid": True})
            session.commit()
            return ok_response({"task_id": task_id, "valid": True})
        except jsonschema.ValidationError as exc:
            errors = [exc.message]
            _emit_event(
                session,
                task.run_id,
                task_id,
                "output_validation_failed",
                {"valid": False, "errors": errors},
            )
            session.commit()
            return ok_response({"task_id": task_id, "valid": False, "errors": errors})
        except jsonschema.SchemaError as exc:
            return err_response("INVALID_SCHEMA", f"Output contract is not a valid JSON Schema: {exc.message}")


def validate_dag_acyclic(tasks: list[dict]) -> dict:
    """
    Validate that a list of task dicts (with task_key and depends_on) forms an acyclic DAG.
    Does not require a database.
    """
    from graphlib import TopologicalSorter, CycleError

    keys = {t["task_key"] for t in tasks}
    graph = {}
    for t in tasks:
        deps = t.get("depends_on") or []
        for dep in deps:
            if dep not in keys:
                return ok_response(
                    {"valid": False, "errors": [f"Unknown dependency '{dep}' in task '{t['task_key']}'"]}
                )
        graph[t["task_key"]] = set(deps)
    try:
        sorter = TopologicalSorter(graph)
        order = list(sorter.static_order())
        return ok_response({"valid": True, "topological_order": order})
    except CycleError as exc:
        return ok_response({"valid": False, "errors": [f"Cycle detected: {exc}"]})
