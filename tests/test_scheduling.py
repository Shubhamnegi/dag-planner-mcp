"""Tests for scheduling tools."""

import pytest
from dag_planner_mcp.tools.planning import create_workflow_run, create_plan_graph
from dag_planner_mcp.tools.scheduling import get_ready_tasks, claim_task_for_execution


TASKS = [
    {"task_key": "t1", "title": "Task 1", "depends_on": [], "owner_agent": "agent_x"},
    {"task_key": "t2", "title": "Task 2", "depends_on": ["t1"], "owner_agent": "agent_y"},
]


def _setup_run(engine):
    run = create_workflow_run(goal="Scheduling test", _engine=engine)
    run_id = run["data"]["run_id"]
    plan = create_plan_graph(run_id=run_id, tasks=TASKS, activate=True, _engine=engine)
    return run_id, plan["data"]["task_ids"]


def test_get_ready_tasks_returns_root(engine):
    run_id, task_ids = _setup_run(engine)
    result = get_ready_tasks(run_id=run_id, _engine=engine)
    assert result["ok"] is True
    ready_ids = [t["task_id"] for t in result["data"]]
    assert task_ids["t1"] in ready_ids
    assert task_ids["t2"] not in ready_ids


def test_get_ready_tasks_filtered_by_owner(engine):
    run_id, task_ids = _setup_run(engine)
    result = get_ready_tasks(run_id=run_id, owner_agent="agent_y", _engine=engine)
    assert result["ok"] is True
    assert len(result["data"]) == 0

    result2 = get_ready_tasks(run_id=run_id, owner_agent="agent_x", _engine=engine)
    assert result2["ok"] is True
    assert len(result2["data"]) == 1


def test_claim_task_for_execution(engine):
    run_id, task_ids = _setup_run(engine)
    t1_id = task_ids["t1"]
    result = claim_task_for_execution(task_id=t1_id, executor_id="exec1", _engine=engine)
    assert result["ok"] is True
    assert result["data"]["task_id"] == t1_id
    assert result["data"]["claimed_by"] == "exec1"
    assert "claim_until" in result["data"] or "claimed_until" in result["data"]


def test_claim_task_already_claimed(engine):
    run_id, task_ids = _setup_run(engine)
    t1_id = task_ids["t1"]
    claim_task_for_execution(task_id=t1_id, executor_id="exec1", claim_duration_seconds=3600, _engine=engine)
    result2 = claim_task_for_execution(task_id=t1_id, executor_id="exec2", _engine=engine)
    assert result2["ok"] is False
    assert result2["error_code"] == "ALREADY_CLAIMED"


def test_claim_task_not_ready(engine):
    run_id, task_ids = _setup_run(engine)
    # t2 is 'created', not ready
    result = claim_task_for_execution(task_id=task_ids["t2"], executor_id="exec1", _engine=engine)
    assert result["ok"] is False
    assert result["error_code"] == "INVALID_STATE"


def test_claim_task_not_found(engine):
    result = claim_task_for_execution(task_id="no_task", executor_id="exec1", _engine=engine)
    assert result["ok"] is False
    assert result["error_code"] == "NOT_FOUND"


def test_get_ready_tasks_all_runs(engine):
    run_id, task_ids = _setup_run(engine)
    result = get_ready_tasks(_engine=engine)
    assert result["ok"] is True
    ids = [t["task_id"] for t in result["data"]]
    assert task_ids["t1"] in ids


def test_claim_expired_allows_reclaim(engine):
    """A task with an expired claim can be re-claimed."""
    from datetime import datetime, timedelta
    from sqlalchemy.orm import Session
    from dag_planner_mcp.db import WorkflowTask

    run_id, task_ids = _setup_run(engine)
    t1_id = task_ids["t1"]

    # Manually set an expired claim
    with Session(engine) as session:
        task = session.get(WorkflowTask, t1_id)
        task.claimed_by = "old_exec"
        task.claimed_until = (datetime.utcnow() - timedelta(seconds=10)).isoformat()
        session.commit()

    result = claim_task_for_execution(task_id=t1_id, executor_id="new_exec", _engine=engine)
    assert result["ok"] is True
    assert result["data"]["claimed_by"] == "new_exec"
