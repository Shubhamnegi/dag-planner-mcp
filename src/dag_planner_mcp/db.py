import os
from sqlalchemy import (
    create_engine, Column, String, Integer, JSON, Text, ForeignKey
)
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


class WorkflowRun(Base):
    __tablename__ = "workflow_run"
    run_id = Column(String, primary_key=True)
    session_id = Column(String)
    user_id = Column(String)
    goal = Column(Text)
    status = Column(String, default="draft")
    plan_version = Column(Integer, default=0)
    metadata_json = Column(JSON)
    created_at = Column(String)
    updated_at = Column(String)
    completed_at = Column(String)


class WorkflowTask(Base):
    __tablename__ = "workflow_task"
    task_id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("workflow_run.run_id"))
    task_key = Column(String)
    title = Column(String)
    description = Column(Text)
    owner_agent = Column(String)
    status = Column(String, default="created")
    priority = Column(Integer, default=0)
    input_json = Column(JSON)
    final_output_json = Column(JSON)
    working_output_json = Column(JSON)
    output_contract_json = Column(JSON)
    checkpoint_json = Column(JSON)
    claimed_by = Column(String)
    claimed_until = Column(String)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    plan_version = Column(Integer, default=1)
    created_at = Column(String)
    updated_at = Column(String)


class WorkflowTaskEdge(Base):
    __tablename__ = "workflow_task_edge"
    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String, ForeignKey("workflow_run.run_id"))
    parent_task_id = Column(String, ForeignKey("workflow_task.task_id"))
    child_task_id = Column(String, ForeignKey("workflow_task.task_id"))
    edge_type = Column(String, default="depends_on")
    created_at = Column(String)


class WorkflowTaskAttempt(Base):
    __tablename__ = "workflow_task_attempt"
    attempt_id = Column(String, primary_key=True)
    task_id = Column(String, ForeignKey("workflow_task.task_id"))
    run_id = Column(String, ForeignKey("workflow_run.run_id"))
    attempt_no = Column(Integer, default=1)
    executor_id = Column(String)
    status = Column(String)
    input_snapshot_ref = Column(String)
    output_snapshot_ref = Column(String)
    error_json = Column(JSON)
    started_at = Column(String)
    ended_at = Column(String)


class WorkflowEvent(Base):
    __tablename__ = "workflow_event"
    event_id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("workflow_run.run_id"))
    task_id = Column(String)
    event_type = Column(String)
    payload_json = Column(JSON)
    created_by = Column(String)
    created_at = Column(String)


class HumanApproval(Base):
    __tablename__ = "human_approval"
    approval_id = Column(String, primary_key=True)
    run_id = Column(String, ForeignKey("workflow_run.run_id"))
    task_id = Column(String, ForeignKey("workflow_task.task_id"))
    status = Column(String, default="pending")
    question = Column(Text)
    options_json = Column(JSON)
    decision_json = Column(JSON)
    requested_by = Column(String)
    decided_by = Column(String)
    requested_at = Column(String)
    decided_at = Column(String)


_engine = None


def get_engine():
    global _engine
    if _engine is None:
        db_url = os.environ.get("DATABASE_URL", "sqlite:///dag_planner.db")
        _engine = create_engine(db_url, echo=False)
        Base.metadata.create_all(_engine)
    return _engine
