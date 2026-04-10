"""Tests for planning tools."""

import pytest
from dag_planner_mcp.tools.planning import create_workflow_run, create_plan_graph, replace_plan_branch


SIMPLE_TASKS = [
    {"task_key": "t1", "title": "Task 1", "depends_on": [], "owner_agent": "agent_a"},
    {"task_key": "t2", "title": "Task 2", "depends_on": ["t1"], "owner_agent": "agent_b"},
    {"task_key": "t3", "title": "Task 3", "depends_on": ["t1"], "owner_agent": "agent_c"},
    {"task_key": "t4", "title": "Task 4", "depends_on": ["t2", "t3"], "owner_agent": "agent_d"},
]


def test_create_workflow_run(engine):
    result = create_workflow_run(goal="Test goal", session_id="sess1", user_id="user1", _engine=engine)
    assert result["ok"] is True
    assert "run_id" in result["data"]
    assert result["data"]["status"] == "draft"


def test_create_workflow_run_no_metadata(engine):
    result = create_workflow_run(goal="No metadata", _engine=engine)
    assert result["ok"] is True
    assert result["data"]["run_id"].startswith("run_")


def test_create_plan_graph_basic(engine):
    run = create_workflow_run(goal="Plan test", _engine=engine)
    run_id = run["data"]["run_id"]

    result = create_plan_graph(run_id=run_id, tasks=SIMPLE_TASKS, _engine=engine)
    assert result["ok"] is True
    assert result["data"]["task_count"] == 4
    assert result["data"]["plan_version"] == 1
    assert "t1" in result["data"]["task_ids"]
    assert "t4" in result["data"]["task_ids"]


def test_create_plan_graph_activates_root_tasks(engine):
    from dag_planner_mcp.tools.query import list_tasks
    run = create_workflow_run(goal="Activate test", _engine=engine)
    run_id = run["data"]["run_id"]
    create_plan_graph(run_id=run_id, tasks=SIMPLE_TASKS, activate=True, _engine=engine)

    tasks = list_tasks(run_id=run_id, _engine=engine)
    assert tasks["ok"] is True
    statuses = {t["task_key"]: t["status"] for t in tasks["data"]}
    assert statuses["t1"] == "ready"
    assert statuses["t2"] == "created"
    assert statuses["t3"] == "created"
    assert statuses["t4"] == "created"


def test_create_plan_graph_not_activate(engine):
    from dag_planner_mcp.tools.query import list_tasks
    run = create_workflow_run(goal="No activate", _engine=engine)
    run_id = run["data"]["run_id"]
    create_plan_graph(run_id=run_id, tasks=SIMPLE_TASKS, activate=False, _engine=engine)

    tasks = list_tasks(run_id=run_id, _engine=engine)
    statuses = {t["task_key"]: t["status"] for t in tasks["data"]}
    assert all(s == "created" for s in statuses.values())


def test_create_plan_graph_cycle_detection(engine):
    run = create_workflow_run(goal="Cycle test", _engine=engine)
    run_id = run["data"]["run_id"]
    cyclic_tasks = [
        {"task_key": "a", "depends_on": ["b"]},
        {"task_key": "b", "depends_on": ["a"]},
    ]
    result = create_plan_graph(run_id=run_id, tasks=cyclic_tasks, _engine=engine)
    assert result["ok"] is False
    assert result["error_code"] == "INVALID_DAG"


def test_create_plan_graph_unknown_dependency(engine):
    run = create_workflow_run(goal="Bad dep", _engine=engine)
    run_id = run["data"]["run_id"]
    bad_tasks = [
        {"task_key": "a", "depends_on": ["nonexistent"]},
    ]
    result = create_plan_graph(run_id=run_id, tasks=bad_tasks, _engine=engine)
    assert result["ok"] is False
    assert result["error_code"] == "INVALID_DAG"


def test_create_plan_graph_run_not_found(engine):
    result = create_plan_graph(run_id="no_such_run", tasks=SIMPLE_TASKS, _engine=engine)
    assert result["ok"] is False
    assert result["error_code"] == "NOT_FOUND"


def test_replace_plan_branch(engine):
    from dag_planner_mcp.tools.state import mark_task_completed
    from dag_planner_mcp.tools.query import list_tasks

    run = create_workflow_run(goal="Replace branch test", _engine=engine)
    run_id = run["data"]["run_id"]
    plan = create_plan_graph(run_id=run_id, tasks=SIMPLE_TASKS, activate=True, _engine=engine)
    task_ids = plan["data"]["task_ids"]

    # Complete t1 to activate t2 and t3
    mark_task_completed(task_id=task_ids["t1"], _engine=engine)

    anchor_id = task_ids["t1"]
    new_tasks = [
        {"task_key": "new_a", "title": "New A", "depends_on": []},
        {"task_key": "new_b", "title": "New B", "depends_on": ["new_a"]},
    ]
    result = replace_plan_branch(
        run_id=run_id, anchor_task_id=anchor_id, new_tasks=new_tasks, _engine=engine
    )
    assert result["ok"] is True
    assert len(result["data"]["cancelled_task_ids"]) > 0
    assert "new_a" in result["data"]["new_task_ids"]


def test_replace_plan_branch_anchor_not_found(engine):
    run = create_workflow_run(goal="No anchor", _engine=engine)
    run_id = run["data"]["run_id"]
    result = replace_plan_branch(
        run_id=run_id, anchor_task_id="bad_id", new_tasks=[], _engine=engine
    )
    assert result["ok"] is False
    assert result["error_code"] == "NOT_FOUND"
