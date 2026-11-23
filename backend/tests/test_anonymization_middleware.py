from fastapi.testclient import TestClient

from app import ai_filter
from app.auth import CurrentUser, get_current_user
from app.main import app
from app.middleware import anonymization as anonymization_mod
from app.middleware.anonymization import AnonymizationResult


def _override_user():
    return CurrentUser(id="user-1", access_token="test-token")


def test_raw_pii_is_anonymized_before_ai_gateway(monkeypatch):
    app.dependency_overrides[get_current_user] = _override_user
    seen_titles = []
    seen_descriptions = []

    def fake_classify(tasks, settings):
        for t in tasks:
            seen_titles.append(t.title)
            seen_descriptions.append(t.description or "")
        return {}

    monkeypatch.setattr(ai_filter, "classify_tasks", fake_classify)

    client = TestClient(app)
    payload = {
        "tasks": [
            {
                "moodle_id": "m-1",
                "title": "Submit lab to student@example.com",
                "course_name": "SE-2026",
                "description": "Call 050-1234567 or ID 123456789",
            }
        ]
    }

    try:
        resp = client.post(
            "/api/tasks/sync",
            json=payload,
            headers={"Authorization": "Bearer test-token"},
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert seen_titles == ["Submit lab to [REDACTED_EMAIL]"]
    assert "050-1234567" not in seen_descriptions[0]
    assert "123456789" not in seen_descriptions[0]
    assert "[REDACTED_PHONE]" in seen_descriptions[0]
    assert "[REDACTED_ID]" in seen_descriptions[0]


def test_invalid_json_is_blocked_by_anonymization_middleware():
    app.dependency_overrides[get_current_user] = _override_user
    client = TestClient(app)

    try:
        resp = client.post(
            "/api/tasks/sync",
            content="{not-valid-json",
            headers={
                "Authorization": "Bearer test-token",
                "Content-Type": "application/json",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 422
    assert "blocked" in resp.json()["detail"].lower()


def test_anonymization_failure_blocks_ai_and_saves_without_ai_fields(monkeypatch):
    app.dependency_overrides[get_current_user] = _override_user
    ai_called = False

    def fake_run_anonymization(payload):
        return AnonymizationResult(payload=payload, ok=False, reason="forced failure")

    def fake_classify(tasks, settings):
        nonlocal ai_called
        ai_called = True
        return {}

    monkeypatch.setattr(anonymization_mod, "run_anonymization", fake_run_anonymization)
    monkeypatch.setattr(ai_filter, "classify_tasks", fake_classify)

    client = TestClient(app)
    payload = {
        "tasks": [
            {
                "moodle_id": "m-2",
                "title": "Assignment without AI",
                "course_name": "SE-2026",
            }
        ]
    }

    try:
        resp = client.post(
            "/api/tasks/sync",
            json=payload,
            headers={"Authorization": "Bearer test-token"},
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["ai_applied"] is False
    assert ai_called is False
