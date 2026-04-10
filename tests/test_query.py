"""Tests for query tools."""

import pytest
from dag_planner_mcp.tools.planning import create_workflow_run, create_plan_graph
from dag_planner_mcp.tools.state import mark_task_running, mark_task_completed, mark_task_blocked_human
from dag_planner_mcp.tools.query import get_task, list_tasks, get_workflow_run, get_blocked_tasks, get_dag_edges


TASKS = [
    {"task_key": "t1", "depends_on": [], "owner_agent": "alpha"},
    {"task_key": "t2", "depends_on": ["t1"], "owner_agent": "beta"},
    {"task_key": "t3", "depends_on": ["t1"], "owner_agent": "alpha"},
]


def _setup(engine):
    run = create_workflow_run(goal="Query test", _engine=engine)
    run_id = run["data"]["run_id"]
    plan = create_plan_graph(run_id=run_id, tasks=TASKS, activate=True, _engine=engine)
    return run_id, plan["data"]["task_ids"]


def test_get_task(engine):
    _, ids = _setup(engine)
    result = get_task(task_id=ids["t1"], _engine=engine)
    assert result["ok"] is True
    assert result["data"]["task_key"] == "t1"
    assert result["data"]["status"] == "ready"


def test_get_task_not_found(engine):
    result = get_task(task_id="nope", _engine=engine)
    assert result["ok"] is False
    assert result["error_code"] == "NOT_FOUND"


def test_list_tasks_all(engine):
    run_id, ids = _setup(engine)
    result = list_tasks(run_id=run_id, _engine=engine)
    assert result["ok"] is True
    assert len(result["data"]) == 3


def test_list_tasks_by_status(engine):
    run_id, ids = _setup(engine)
    result = list_tasks(run_id=run_id, status="ready", _engine=engine)
    assert result["ok"] is True
    ready_keys = [t["task_key"] for t in result["data"]]
    assert "t1" in ready_keys


def test_list_tasks_by_owner(engine):
    run_id, ids = _setup(engine)
    result = list_tasks(run_id=run_id, owner_agent="alpha", _engine=engine)
    assert result["ok"] is True
    keys = [t["task_key"] for t in result["data"]]
    assert "t1" in keys
    assert "t3" in keys
    assert "t2" not in keys


def test_get_workflow_run(engine):
    run_id, _ = _setup(engine)
    result = get_workflow_run(run_id=run_id, _engine=engine)
    assert result["ok"] is True
    assert result["data"]["run_id"] == run_id
    assert result["data"]["goal"] == "Query test"
    assert "tasks" not in result["data"]


def test_get_workflow_run_with_tasks(engine):
    run_id, _ = _setup(engine)
    result = get_workflow_run(run_id=run_id, include_tasks=True, _engine=engine)
    assert result["ok"] is True
    assert "tasks" in result["data"]
    assert len(result["data"]["tasks"]) == 3


def test_get_workflow_run_not_found(engine):
    result = get_workflow_run(run_id="no_run", _engine=engine)
    assert result["ok"] is False
    assert result["error_code"] == "NOT_FOUND"


def test_get_blocked_tasks(engine):
    run_id, ids = _setup(engine)
    mark_task_blocked_human(task_id=ids["t1"], question="OK?", _engine=engine)

    result = get_blocked_tasks(run_id=run_id, _engine=engine)
    assert result["ok"] is True
    blocked_ids = [t["task_id"] for t in result["data"]]
    assert ids["t1"] in blocked_ids


def test_get_blocked_tasks_empty(engine):
    run_id, _ = _setup(engine)
    result = get_blocked_tasks(run_id=run_id, _engine=engine)
    assert result["ok"] is True
    assert len(result["data"]) == 0


def test_get_dag_edges(engine):
    run_id, ids = _setup(engine)
    result = get_dag_edges(run_id=run_id, _engine=engine)
    assert result["ok"] is True
    # t1->t2 and t1->t3
    edges = result["data"]
    assert len(edges) == 2
    parent_ids = {e["parent_task_id"] for e in edges}
    assert ids["t1"] in parent_ids
