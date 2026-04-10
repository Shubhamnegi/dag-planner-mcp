"""Tests for IO tools."""

import pytest
from dag_planner_mcp.tools.planning import create_workflow_run, create_plan_graph
from dag_planner_mcp.tools.io import put_task_output, put_task_checkpoint, get_task_payload_refs


def _setup(engine):
    run = create_workflow_run(goal="IO test", _engine=engine)
    run_id = run["data"]["run_id"]
    plan = create_plan_graph(
        run_id=run_id,
        tasks=[{"task_key": "t1", "depends_on": [], "input_json": {"x": 1}}],
        _engine=engine,
    )
    task_id = plan["data"]["task_ids"]["t1"]
    return run_id, task_id


def test_put_task_output_working(engine):
    _, task_id = _setup(engine)
    result = put_task_output(task_id=task_id, output={"progress": 50}, is_final=False, _engine=engine)
    assert result["ok"] is True
    assert result["data"]["is_final"] is False


def test_put_task_output_final(engine):
    _, task_id = _setup(engine)
    result = put_task_output(task_id=task_id, output={"result": "done"}, is_final=True, _engine=engine)
    assert result["ok"] is True
    assert result["data"]["is_final"] is True


def test_put_task_checkpoint(engine):
    _, task_id = _setup(engine)
    result = put_task_checkpoint(task_id=task_id, checkpoint={"step": 3, "state": "partial"}, _engine=engine)
    assert result["ok"] is True
    assert result["data"]["checkpointed"] is True


def test_get_task_payload_refs(engine):
    _, task_id = _setup(engine)
    put_task_output(task_id=task_id, output={"progress": 25}, _engine=engine)
    put_task_checkpoint(task_id=task_id, checkpoint={"step": 1}, _engine=engine)

    result = get_task_payload_refs(task_id=task_id, _engine=engine)
    assert result["ok"] is True
    data = result["data"]
    assert data["input_json"] == {"x": 1}
    assert data["working_output_json"] == {"progress": 25}
    assert data["checkpoint_json"] == {"step": 1}


def test_put_task_output_not_found(engine):
    result = put_task_output(task_id="no_task", output={}, _engine=engine)
    assert result["ok"] is False
    assert result["error_code"] == "NOT_FOUND"


def test_put_task_checkpoint_not_found(engine):
    result = put_task_checkpoint(task_id="no_task", checkpoint={}, _engine=engine)
    assert result["ok"] is False
    assert result["error_code"] == "NOT_FOUND"


def test_get_payload_refs_not_found(engine):
    result = get_task_payload_refs(task_id="no_task", _engine=engine)
    assert result["ok"] is False
    assert result["error_code"] == "NOT_FOUND"


def test_final_output_persists(engine):
    _, task_id = _setup(engine)
    put_task_output(task_id=task_id, output={"result": "final"}, is_final=True, _engine=engine)
    refs = get_task_payload_refs(task_id=task_id, _engine=engine)
    assert refs["data"]["final_output_json"] == {"result": "final"}
