"""Pytest fixtures: isolated SQLite database per test run."""

from __future__ import annotations

import os
import pathlib
import tempfile

# Must happen before any app import: bind the engine to a scratch database.
_TMP_DIR = pathlib.Path(tempfile.mkdtemp(prefix="sentinelx-test-"))
os.environ["SENTINEL_DB_PATH"] = str(_TMP_DIR / "sentinel_test.db")
os.environ.setdefault("SENTINEL_TICKET_SECRET", "test-secret-not-a-real-key")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, SessionLocal, engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.tools import reset_simulated_state  # noqa: E402


@pytest.fixture(autouse=True)
def clean_state():
    """Fresh database, seed data and simulated environment for every test."""
    Base.metadata.drop_all(bind=engine)
    init_db()
    reset_simulated_state()
    yield


@pytest.fixture()
def client(clean_state):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db(clean_state):
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
