"""Performance and load time benchmark tests (US 4.1.2, AB#20).

Acceptance Criteria:
  - Measured load time is under 3 seconds on a standard connection.
  - Returns dashboard summary in a single request.
  - Client-side cache headers present.
"""
import time
import pytest
from fastapi.testclient import TestClient

from app.main import app, _memory_store


@pytest.fixture(autouse=True)
def clean_memory_store():
    _memory_store._data.clear()
    yield
    _memory_store._data.clear()


@pytest.fixture
def client():
    return TestClient(app)


def test_dashboard_summary_in_single_request(client):
    """Task 111: Single FastAPI endpoint returning dashboard overview."""
    headers = {"Authorization": "Bearer perf-user-1"}

    # Seed 50 tasks across 5 courses
    tasks_payload = {
        "tasks": [
            {
                "moodle_id": f"perf_task_{i}",
                "title": f"Assignment {i}",
                "course_name": f"Course {i % 5}",
                "due_date": "2026-12-15T18:00:00+02:00",
            }
            for i in range(50)
        ]
    }
    sync_res = client.post("/api/tasks/sync", json=tasks_payload, headers=headers)
    assert sync_res.status_code == 200

    # Fetch summary
    start = time.perf_counter()
    res = client.get("/api/dashboard/summary", headers=headers)
    duration = time.perf_counter() - start

    assert res.status_code == 200
    data = res.json()

    assert data["total_tasks"] == 50
    assert data["courses_count"] == 5
    assert "upcoming_tasks" in data
    assert len(data["upcoming_tasks"]) <= 5

    # Acceptance criteria: load time under 3 seconds! (API takes < 100ms)
    assert duration < 3.0
    assert duration < 0.2  # Server processing well under 200ms

    # Task 112: Cache control headers present
    assert "Cache-Control" in res.headers
    assert "private" in res.headers["Cache-Control"]
