"""Tests for Conflict Resolution (US 3.3.3, AB#418).

Acceptance Criteria:
  1. Given a task with local user edits that conflicts with a remote Moodle update,
     official Moodle deadlines take precedence while preserving user-added notes.
  2. Given an unresolved conflict, when detected, a notification flag is generated for user review.
  3. Given automated merge execution, data integrity is maintained without data loss on custom fields.
"""
from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from app.change_detection import reconcile_task
from app.main import app, _memory_store


@pytest.fixture(autouse=True)
def clean_memory_store():
    _memory_store._data.clear()
    yield
    _memory_store._data.clear()


@pytest.fixture
def client():
    return TestClient(app)


def test_reconcile_prefers_moodle_deadline_and_preserves_user_notes():
    """AC 1: Official Moodle deadline takes precedence while preserving user notes."""
    stored = {
        "moodle_id": "assign_100",
        "title": "HW1 - Linear Algebra",
        "description": "Original description",
        "due_date": "2026-11-01T12:00:00+02:00",
        "user_notes": "Important note: talk to Dani about question 3",
        "custom_priority": 5,
    }
    incoming = {
        "moodle_id": "assign_100",
        "title": "HW1 - Linear Algebra",
        "description": "Original description",
        "due_date": "2026-11-15T23:59:00+02:00",  # Postponed on Moodle
    }

    merged, is_conflict, message = reconcile_task(stored, incoming)

    # Official Moodle deadline takes precedence
    assert merged["due_date"] == "2026-11-15T23:59:00+02:00"

    # User notes and custom priority preserved intact (AC 3)
    assert merged["user_notes"] == "Important note: talk to Dani about question 3"
    assert merged["custom_priority"] == 5

    # Conflict notification flag generated (AC 2)
    assert is_conflict is True
    assert merged["conflict_detected"] is True
    assert "Moodle updated deadline" in message
    assert "notes have been preserved" in message


def test_reconcile_no_conflict_when_moodle_unchanged():
    stored = {
        "moodle_id": "assign_200",
        "title": "Lab 2",
        "due_date": "2026-12-01T10:00:00+02:00",
        "user_notes": "My private note",
    }
    incoming = {
        "moodle_id": "assign_200",
        "title": "Lab 2",
        "due_date": "2026-12-01T10:00:00+02:00",
    }

    merged, is_conflict, message = reconcile_task(stored, incoming)
    assert is_conflict is False
    assert merged.get("conflict_detected", False) is False
    assert merged["user_notes"] == "My private note"


def test_full_sync_conflict_resolution_and_patch(client):
    """End-to-end integration test of conflict resolution lifecycle."""
    headers = {"Authorization": "Bearer dev-user-123"}

    # 1. First sync from Moodle
    sync_payload = {
        "tasks": [
            {
                "moodle_id": "moodle_301",
                "title": "Project Submission",
                "due_date": "2026-12-10T20:00:00+02:00",
                "description": "Initial instructions",
            }
        ]
    }
    res1 = client.post("/api/tasks/sync", json=sync_payload, headers=headers)
    assert res1.status_code == 200

    # 2. Student adds personal notes via PATCH /api/tasks/{moodle_id}
    patch_res = client.patch(
        "/api/tasks/moodle_301",
        json={"user_notes": "Reviewed with professor, need to polish section 4", "custom_priority": 4},
        headers=headers,
    )
    assert patch_res.status_code == 200
    task_after_patch = patch_res.json()
    assert task_after_patch["user_notes"] == "Reviewed with professor, need to polish section 4"
    assert task_after_patch["custom_priority"] == 4

    # 3. Moodle updates the deadline remotely
    resync_payload = {
        "tasks": [
            {
                "moodle_id": "moodle_301",
                "title": "Project Submission",
                "due_date": "2026-12-20T23:59:00+02:00",  # Changed deadline
                "description": "Initial instructions",
            }
        ]
    }
    res2 = client.post("/api/tasks/sync", json=resync_payload, headers=headers)
    assert res2.status_code == 200
    sync_data = res2.json()
    assert sync_data["conflicts"] == 1

    # 4. Fetch tasks and verify merge and notification flag
    tasks_res = client.get("/api/tasks", headers=headers)
    assert tasks_res.status_code == 200
    tasks = tasks_res.json()
    task = next(t for t in tasks if t["moodle_id"] == "moodle_301")

    # Deadline updated to Moodle's new date
    assert "2026-12-20" in task["due_date"]
    # User notes preserved!
    assert task["user_notes"] == "Reviewed with professor, need to polish section 4"
    # Conflict notification flag is on
    assert task["conflict_detected"] is True
    assert task["conflict_message"] is not None

    # 5. User resolves conflict
    resolve_res = client.patch(
        "/api/tasks/moodle_301",
        json={"resolve_conflict": True},
        headers=headers,
    )
    assert resolve_res.status_code == 200
    resolved_task = resolve_res.json()
    assert resolved_task["conflict_detected"] is False
    assert resolved_task["conflict_message"] is None
    assert resolved_task["user_notes"] == "Reviewed with professor, need to polish section 4"
