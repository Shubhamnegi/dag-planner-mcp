"""Tests for state transition tools."""

import pytest
from dag_planner_mcp.tools.planning import create_workflow_run, create_plan_graph
from dag_planner_mcp.tools.state import (
    mark_task_running,
    mark_task_completed,
    mark_task_failed,
    mark_task_blocked_human,
    resume_task,
)
from dag_planner_mcp.tools.query import list_tasks, get_workflow_run


TASKS = [
    {"task_key": "t1", "title": "Task 1", "depends_on": [], "owner_agent": "a"},
    {"task_key": "t2", "title": "Task 2", "depends_on": ["t1"], "owner_agent": "b"},
    {"task_key": "t3", "title": "Task 3", "depends_on": ["t2"], "owner_agent": "c"},
]


def _setup(engine):
    run = create_workflow_run(goal="State test", _engine=engine)
    run_id = run["data"]["run_id"]
    plan = create_plan_graph(run_id=run_id, tasks=TASKS, activate=True, _engine=engine)
    return run_id, plan["data"]["task_ids"]


def test_mark_task_running(engine):
    run_id, ids = _setup(engine)
    result = mark_task_running(task_id=ids["t1"], _engine=engine)
    assert result["ok"] is True
    assert result["data"]["status"] == "running"


def test_mark_task_running_invalid_state(engine):
    run_id, ids = _setup(engine)
    # t2 is 'created', not 'ready'
    result = mark_task_running(task_id=ids["t2"], _engine=engine)
    assert result["ok"] is False
    assert result["error_code"] == "INVALID_STATE"


def test_mark_task_completed_activates_children(engine):
    run_id, ids = _setup(engine)
    mark_task_running(task_id=ids["t1"], _engine=engine)
    result = mark_task_completed(task_id=ids["t1"], _engine=engine)
    assert result["ok"] is True

    tasks = list_tasks(run_id=run_id, _engine=engine)
    statuses = {t["task_key"]: t["status"] for t in tasks["data"]}
    assert statuses["t1"] == "completed"
    assert statuses["t2"] == "ready"
    assert statuses["t3"] == "created"


def test_mark_task_completed_stores_output(engine):
    from dag_planner_mcp.tools.query import get_task
    run_id, ids = _setup(engine)
    mark_task_running(task_id=ids["t1"], _engine=engine)
    mark_task_completed(task_id=ids["t1"], final_output={"result": 42}, _engine=engine)

    task = get_task(task_id=ids["t1"], _engine=engine)
    assert task["data"]["final_output_json"] == {"result": 42}


def test_full_run_completion(engine):
    run_id, ids = _setup(engine)
    for key in ["t1", "t2", "t3"]:
        mark_task_running(task_id=ids[key], _engine=engine)
        mark_task_completed(task_id=ids[key], _engine=engine)

    run = get_workflow_run(run_id=run_id, _engine=engine)
    assert run["data"]["status"] == "completed"
    assert run["data"]["completed_at"] is not None


def test_mark_task_failed_with_retry(engine):
    run_id, ids = _setup(engine)
    mark_task_running(task_id=ids["t1"], _engine=engine)
    result = mark_task_failed(task_id=ids["t1"], error={"msg": "timeout"}, retry=True, _engine=engine)
    assert result["ok"] is True
    assert result["data"]["status"] == "ready"
    assert result["data"]["retry_count"] == 1


def test_mark_task_failed_no_retry(engine):
    run_id, ids = _setup(engine)
    mark_task_running(task_id=ids["t1"], _engine=engine)
    result = mark_task_failed(task_id=ids["t1"], error={"msg": "fatal"}, retry=False, _engine=engine)
    assert result["ok"] is True
    assert result["data"]["status"] == "failed"


def test_mark_task_failed_exhausted_retries(engine):
    from sqlalchemy.orm import Session
    from dag_planner_mcp.db import WorkflowTask

    run_id, ids = _setup(engine)
    t1_id = ids["t1"]

    # Exhaust retries manually
    with Session(engine) as session:
        task = session.get(WorkflowTask, t1_id)
        task.retry_count = task.max_retries
        session.commit()

    mark_task_running(task_id=t1_id, _engine=engine)
    result = mark_task_failed(task_id=t1_id, retry=True, _engine=engine)
    assert result["ok"] is True
    assert result["data"]["status"] == "failed"


def test_mark_task_blocked_human(engine):
    run_id, ids = _setup(engine)
    result = mark_task_blocked_human(
        task_id=ids["t1"],
        question="Approve?",
        options=["yes", "no"],
        _engine=engine,
    )
    assert result["ok"] is True
    assert result["data"]["status"] == "blocked_human"
    assert "approval_id" in result["data"]


def test_resume_task(engine):
    run_id, ids = _setup(engine)
    mark_task_blocked_human(task_id=ids["t1"], question="Proceed?", _engine=engine)
    result = resume_task(
        task_id=ids["t1"],
        decision={"answer": "yes"},
        decided_by="human1",
        _engine=engine,
    )
    assert result["ok"] is True
    assert result["data"]["status"] == "ready"


def test_resume_task_not_blocked(engine):
    run_id, ids = _setup(engine)
    result = resume_task(task_id=ids["t1"], _engine=engine)
    assert result["ok"] is False
    assert result["error_code"] == "INVALID_STATE"


def test_mark_task_not_found(engine):
    result = mark_task_running(task_id="no_task", _engine=engine)
    assert result["ok"] is False
    assert result["error_code"] == "NOT_FOUND"
