"""Test fixtures.

Points the whole app at a throwaway SQLite file for the test run (set via
DATABASE_URL before anything imports app.*), so tests never touch the real
MySQL database from .env and don't need a live DB server.
"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_run.db"

import pytest
from fastapi.testclient import TestClient

from app.db.connection import Base, engine
from app.main import app


@pytest.fixture()
def client():
    # TestClient triggers FastAPI's startup event (init_db + seed_products).
    with TestClient(app) as c:
        yield c
    # Wipe all rows between tests so each test starts from a clean slate,
    # without paying the cost of dropping/recreating the schema every time.
    with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture()
def auth_headers(client):
    """Registers a user, logs in, and returns ready-to-use auth headers."""
    client.post(
        "/auth/register",
        json={"email": "user@example.com", "password": "secret123", "full_name": "Test User"},
    )
    resp = client.post("/auth/login", json={"email": "user@example.com", "password": "secret123"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
