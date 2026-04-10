"""Shared test fixtures."""

import pytest
from sqlalchemy import create_engine
from dag_planner_mcp.db import Base


@pytest.fixture
def engine():
    """Create a fresh in-memory SQLite engine for each test."""
    eng = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()
