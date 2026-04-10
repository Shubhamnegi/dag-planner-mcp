"""Tests for validation tools."""

import pytest
from dag_planner_mcp.tools.planning import create_workflow_run, create_plan_graph
from dag_planner_mcp.tools.state import mark_task_completed
from dag_planner_mcp.tools.validation import validate_task_output, validate_dag_acyclic


JSON_SCHEMA_CONTRACT = {
    "type": "object",
    "properties": {
        "result": {"type": "string"},
        "score": {"type": "number"},
    },
    "required": ["result"],
}

TASKS_WITH_CONTRACT = [
    {
        "task_key": "t1",
        "depends_on": [],
        "output_contract_json": JSON_SCHEMA_CONTRACT,
    }
]


def _setup(engine):
    run = create_workflow_run(goal="Validation test", _engine=engine)
    run_id = run["data"]["run_id"]
    plan = create_plan_graph(run_id=run_id, tasks=TASKS_WITH_CONTRACT, _engine=engine)
    task_id = plan["data"]["task_ids"]["t1"]
    return run_id, task_id


def test_validate_task_output_valid(engine):
    _, task_id = _setup(engine)
    result = validate_task_output(
        task_id=task_id,
        output={"result": "success", "score": 0.95},
        _engine=engine,
    )
    assert result["ok"] is True
    assert result["data"]["valid"] is True


def test_validate_task_output_invalid(engine):
    _, task_id = _setup(engine)
    result = validate_task_output(
        task_id=task_id,
        output={"score": 0.5},  # missing required 'result'
        _engine=engine,
    )
    assert result["ok"] is True
    assert result["data"]["valid"] is False
    assert len(result["data"]["errors"]) > 0


def test_validate_task_output_wrong_type(engine):
    _, task_id = _setup(engine)
    result = validate_task_output(
        task_id=task_id,
        output={"result": 123},  # result should be string
        _engine=engine,
    )
    assert result["ok"] is True
    assert result["data"]["valid"] is False


def test_validate_task_output_uses_final_output(engine):
    _, task_id = _setup(engine)
    mark_task_completed(task_id=task_id, final_output={"result": "done"}, _engine=engine)

    result = validate_task_output(task_id=task_id, _engine=engine)
    assert result["ok"] is True
    assert result["data"]["valid"] is True


def test_validate_task_output_no_output(engine):
    _, task_id = _setup(engine)
    result = validate_task_output(task_id=task_id, _engine=engine)
    assert result["ok"] is True
    assert result["data"]["valid"] is False
    assert "errors" in result["data"]


def test_validate_task_no_contract(engine):
    run = create_workflow_run(goal="No contract", _engine=engine)
    run_id = run["data"]["run_id"]
    plan = create_plan_graph(
        run_id=run_id,
        tasks=[{"task_key": "t1", "depends_on": []}],
        _engine=engine,
    )
    task_id = plan["data"]["task_ids"]["t1"]
    result = validate_task_output(task_id=task_id, output={"anything": True}, _engine=engine)
    assert result["ok"] is True
    assert result["data"]["valid"] is True


def test_validate_task_not_found(engine):
    result = validate_task_output(task_id="no_task", output={}, _engine=engine)
    assert result["ok"] is False
    assert result["error_code"] == "NOT_FOUND"


def test_validate_dag_acyclic_valid():
    tasks = [
        {"task_key": "a", "depends_on": []},
        {"task_key": "b", "depends_on": ["a"]},
        {"task_key": "c", "depends_on": ["a", "b"]},
    ]
    result = validate_dag_acyclic(tasks=tasks)
    assert result["ok"] is True
    assert result["data"]["valid"] is True
    assert "topological_order" in result["data"]


def test_validate_dag_acyclic_cycle():
    tasks = [
        {"task_key": "x", "depends_on": ["y"]},
        {"task_key": "y", "depends_on": ["x"]},
    ]
    result = validate_dag_acyclic(tasks=tasks)
    assert result["ok"] is True
    assert result["data"]["valid"] is False
    assert len(result["data"]["errors"]) > 0


def test_validate_dag_acyclic_unknown_dep():
    tasks = [
        {"task_key": "a", "depends_on": ["ghost"]},
    ]
    result = validate_dag_acyclic(tasks=tasks)
    assert result["ok"] is True
    assert result["data"]["valid"] is False
