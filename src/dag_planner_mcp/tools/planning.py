"""Planning tools: create runs, build plan DAGs, replace plan branches."""

import uuid
from datetime import datetime, timezone
from graphlib import TopologicalSorter, CycleError
from typing import Optional

from sqlalchemy.orm import Session

from dag_planner_mcp.db import (
    Base,
    WorkflowRun,
    WorkflowTask,
    WorkflowTaskEdge,
    WorkflowEvent,
    get_engine,
)
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


def _validate_dag(tasks: list[dict]) -> tuple[bool, str]:
    """Validate that the task list forms a valid DAG. Returns (ok, error_message)."""
    keys = {t["task_key"] for t in tasks}
    graph = {}
    for t in tasks:
        deps = t.get("depends_on") or []
        for dep in deps:
            if dep not in keys:
                return False, f"Unknown dependency '{dep}' in task '{t['task_key']}'"
        graph[t["task_key"]] = set(deps)
    try:
        sorter = TopologicalSorter(graph)
        list(sorter.static_order())
    except CycleError as e:
        return False, f"Cycle detected in task graph: {e}"
    return True, ""


def create_workflow_run(
    goal: str,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    metadata: Optional[dict] = None,
    _engine=None,
):
    """Create a new workflow run in draft status."""
    engine = _engine or get_engine()
    run_id = f"run_{_short_id()}"
    now = _now()
    with Session(engine) as session:
        run = WorkflowRun(
            run_id=run_id,
            session_id=session_id,
            user_id=user_id,
            goal=goal,
            status="draft",
            plan_version=0,
            metadata_json=metadata or {},
            created_at=now,
            updated_at=now,
        )
        session.add(run)
        _emit_event(session, run_id, None, "run_created", {"goal": goal})
        session.commit()
    return ok_response({"run_id": run_id, "status": "draft"})


def create_plan_graph(
    run_id: str,
    tasks: list[dict],
    activate: bool = True,
    _engine=None,
):
    """
    Create a plan graph for the given run.

    Each task dict has:
      task_key, title, description, owner_agent, depends_on (list of task_keys),
      input_json, output_contract_json, priority, max_retries
    """
    engine = _engine or get_engine()
    with Session(engine) as session:
        run = session.get(WorkflowRun, run_id)
        if run is None:
            return err_response("NOT_FOUND", f"Run '{run_id}' not found")
        if run.status not in ("draft", "running"):
            return err_response(
                "INVALID_STATE",
                f"Cannot create plan for run in status '{run.status}'",
            )

        ok, msg = _validate_dag(tasks)
        if not ok:
            return err_response("INVALID_DAG", msg)

        now = _now()
        plan_version = (run.plan_version or 0) + 1
        run.plan_version = plan_version
        run.updated_at = now

        # Map task_key -> task_id for edge creation
        key_to_id: dict[str, str] = {}
        created_tasks = []

        for task_data in tasks:
            task_id = f"task_{_short_id()}"
            key_to_id[task_data["task_key"]] = task_id
            deps = task_data.get("depends_on") or []
            status = "created"
            task = WorkflowTask(
                task_id=task_id,
                run_id=run_id,
                task_key=task_data["task_key"],
                title=task_data.get("title", task_data["task_key"]),
                description=task_data.get("description", ""),
                owner_agent=task_data.get("owner_agent", ""),
                status=status,
                priority=task_data.get("priority", 0),
                input_json=task_data.get("input_json") or {},
                output_contract_json=task_data.get("output_contract_json") or {},
                max_retries=task_data.get("max_retries", 3),
                plan_version=plan_version,
                created_at=now,
                updated_at=now,
            )
            session.add(task)
            created_tasks.append((task_id, task_data["task_key"], deps))

        session.flush()

        # Create edges
        for task_id, task_key, deps in created_tasks:
            for dep_key in deps:
                parent_id = key_to_id[dep_key]
                edge = WorkflowTaskEdge(
                    run_id=run_id,
                    parent_task_id=parent_id,
                    child_task_id=task_id,
                    edge_type="depends_on",
                    created_at=now,
                )
                session.add(edge)

        # Mark tasks with no dependencies as ready if activating
        if activate:
            run.status = "running"
            for task_id, task_key, deps in created_tasks:
                if not deps:
                    task = session.get(WorkflowTask, task_id)
                    task.status = "ready"
                    task.updated_at = now
                    _emit_event(session, run_id, task_id, "task_ready", {"task_key": task_key})

        _emit_event(session, run_id, None, "plan_created", {"plan_version": plan_version, "task_count": len(tasks)})
        session.commit()

    return ok_response(
        {
            "run_id": run_id,
            "plan_version": plan_version,
            "task_count": len(tasks),
            "task_ids": {k: v for k, v in key_to_id.items()},
        }
    )


def _get_downstream_task_ids(session, run_id: str, anchor_task_id: str) -> set[str]:
    """BFS to collect all downstream task IDs from anchor (not including anchor itself)."""
    visited = set()
    queue = [anchor_task_id]
    while queue:
        current = queue.pop()
        edges = (
            session.query(WorkflowTaskEdge)
            .filter_by(run_id=run_id, parent_task_id=current)
            .all()
        )
        for edge in edges:
            child_id = edge.child_task_id
            if child_id not in visited:
                visited.add(child_id)
                queue.append(child_id)
    return visited


def replace_plan_branch(
    run_id: str,
    anchor_task_id: str,
    new_tasks: list[dict],
    _engine=None,
):
    """
    Cancel all non-completed tasks downstream of anchor_task_id and replace
    them with new_tasks. The anchor task itself is preserved.
    """
    engine = _engine or get_engine()
    with Session(engine) as session:
        run = session.get(WorkflowRun, run_id)
        if run is None:
            return err_response("NOT_FOUND", f"Run '{run_id}' not found")

        anchor = session.get(WorkflowTask, anchor_task_id)
        if anchor is None:
            return err_response("NOT_FOUND", f"Anchor task '{anchor_task_id}' not found")

        ok, msg = _validate_dag(new_tasks)
        if not ok:
            return err_response("INVALID_DAG", msg)

        now = _now()
        plan_version = (run.plan_version or 0) + 1
        run.plan_version = plan_version
        run.updated_at = now

        # Cancel downstream tasks
        downstream_ids = _get_downstream_task_ids(session, run_id, anchor_task_id)
        for task_id in downstream_ids:
            task = session.get(WorkflowTask, task_id)
            if task and task.status not in ("completed", "cancelled"):
                task.status = "cancelled"
                task.updated_at = now
                _emit_event(session, run_id, task_id, "task_cancelled", {"reason": "branch_replace"})

        # Remove old edges from anchor to cancelled children
        session.query(WorkflowTaskEdge).filter_by(
            run_id=run_id, parent_task_id=anchor_task_id
        ).delete()

        session.flush()

        # Create new tasks
        key_to_id: dict[str, str] = {}
        created_tasks = []
        for task_data in new_tasks:
            task_id = f"task_{_short_id()}"
            key_to_id[task_data["task_key"]] = task_id
            deps = task_data.get("depends_on") or []
            task = WorkflowTask(
                task_id=task_id,
                run_id=run_id,
                task_key=task_data["task_key"],
                title=task_data.get("title", task_data["task_key"]),
                description=task_data.get("description", ""),
                owner_agent=task_data.get("owner_agent", ""),
                status="created",
                priority=task_data.get("priority", 0),
                input_json=task_data.get("input_json") or {},
                output_contract_json=task_data.get("output_contract_json") or {},
                max_retries=task_data.get("max_retries", 3),
                plan_version=plan_version,
                created_at=now,
                updated_at=now,
            )
            session.add(task)
            created_tasks.append((task_id, task_data["task_key"], deps))

        session.flush()

        # Create edges inside new subgraph
        for task_id, task_key, deps in created_tasks:
            for dep_key in deps:
                parent_id = key_to_id[dep_key]
                edge = WorkflowTaskEdge(
                    run_id=run_id,
                    parent_task_id=parent_id,
                    child_task_id=task_id,
                    edge_type="depends_on",
                    created_at=now,
                )
                session.add(edge)

        # Connect anchor to root new tasks (those with no deps in new_tasks)
        for task_id, task_key, deps in created_tasks:
            if not deps:
                edge = WorkflowTaskEdge(
                    run_id=run_id,
                    parent_task_id=anchor_task_id,
                    child_task_id=task_id,
                    edge_type="depends_on",
                    created_at=now,
                )
                session.add(edge)
                # Mark root new tasks as ready if anchor is completed
                if anchor.status == "completed":
                    task = session.get(WorkflowTask, task_id)
                    task.status = "ready"
                    task.updated_at = now
                    _emit_event(session, run_id, task_id, "task_ready", {"task_key": task_key})

        _emit_event(
            session,
            run_id,
            anchor_task_id,
            "branch_replaced",
            {"plan_version": plan_version, "new_task_count": len(new_tasks)},
        )
        session.commit()

    return ok_response(
        {
            "run_id": run_id,
            "plan_version": plan_version,
            "cancelled_task_ids": list(downstream_ids),
            "new_task_ids": {k: v for k, v in key_to_id.items()},
        }
    )
