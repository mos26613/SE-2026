"""End-to-end tests for the API (section 4: E2E Test & FastAPI Integration).

They run the whole request flow - validation, AI step, saving, reading back -
against the in-memory store, with Gemini replaced by a fake so the tests are
fast, free and don't need internet or keys.

Run:  python -m pytest -v
"""
import pytest
from fastapi.testclient import TestClient

from app import ai_filter, main
from app.config import Settings, get_settings
from app.db import MemoryStore
from app.models import AIResult


def dev_settings(**overrides) -> Settings:
    values = {"supabase_url": "", "gemini_api_key": "", **overrides}
    return Settings(_env_file=None, **values)


@pytest.fixture
def client(monkeypatch):
    main.app.dependency_overrides[get_settings] = lambda: dev_settings()
    monkeypatch.setattr(main, "_memory_store", MemoryStore())  # fresh data for every test
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def fake_ai(verdicts: dict[str, bool]):
    """Pretend to be Gemini: mark the given moodle_ids relevant or not."""

    def _classify(tasks, settings):
        return {
            t.moodle_id: AIResult(
                moodle_id=t.moodle_id,
                is_relevant=verdicts.get(t.moodle_id, True),
                category="homework",
                priority=4,
                summary=f"Do {t.title}",
            )
            for t in tasks
        }

    return _classify


TASKS = [
    {"moodle_id": "101", "title": "Homework 3", "course_name": "Algorithms", "due_date": "2026-12-05T23:59:00+02:00"},
    {"moodle_id": "102", "title": "Midterm exam", "course_name": "Calculus", "due_date": "2026-12-01T09:00:00+02:00"},
    {"moodle_id": "103", "title": "Welcome to the course forum", "course_name": "Calculus"},
]


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_sync_then_list_full_flow(client, monkeypatch):
    monkeypatch.setattr(ai_filter, "classify_tasks", fake_ai({"103": False}))

    r = client.post("/api/tasks/sync", json={"tasks": TASKS})
    assert r.status_code == 200
    assert r.json() == {"received": 3, "created": 3, "updated": 0, "filtered_out": 1, "ai_applied": True}

    tasks = client.get("/api/tasks").json()
    # The forum post was filtered out, the rest come back soonest deadline first.
    assert [t["moodle_id"] for t in tasks] == ["102", "101"]
    assert tasks[0]["ai_category"] == "homework"
    assert tasks[0]["ai_priority"] == 4

    everything = client.get("/api/tasks", params={"include_filtered": True}).json()
    assert len(everything) == 3


def test_resync_updates_instead_of_duplicating(client, monkeypatch):
    monkeypatch.setattr(ai_filter, "classify_tasks", fake_ai({}))
    client.post("/api/tasks/sync", json={"tasks": TASKS})

    changed = [{**TASKS[0], "due_date": "2026-12-10T23:59:00+02:00"}]
    r = client.post("/api/tasks/sync", json={"tasks": changed})
    assert r.json()["created"] == 0
    assert r.json()["updated"] == 1

    tasks = client.get("/api/tasks").json()
    assert len(tasks) == 3
    hw = next(t for t in tasks if t["moodle_id"] == "101")
    assert hw["due_date"].startswith("2026-12-10")


def test_duplicates_inside_one_batch_are_merged(client, monkeypatch):
    monkeypatch.setattr(ai_filter, "classify_tasks", fake_ai({}))
    r = client.post("/api/tasks/sync", json={"tasks": [TASKS[0], TASKS[0]]})
    assert r.json()["created"] == 1
    assert len(client.get("/api/tasks").json()) == 1


def test_tasks_are_saved_even_when_ai_is_unavailable(client):
    # No GEMINI_API_KEY in dev_settings, so the real classify_tasks skips the AI step.
    r = client.post("/api/tasks/sync", json={"tasks": TASKS})
    assert r.status_code == 200
    assert r.json()["ai_applied"] is False
    assert len(client.get("/api/tasks").json()) == 3


def test_ai_failure_does_not_lose_data(client, monkeypatch):
    # Simulate Gemini crashing inside the real function.
    class Boom:
        class models:
            @staticmethod
            def generate_content(**kwargs):
                raise TimeoutError("Gemini timed out")

    import google.genai

    monkeypatch.setattr(google.genai, "Client", lambda **kwargs: Boom())
    main.app.dependency_overrides[get_settings] = lambda: dev_settings(gemini_api_key="fake-key")

    r = client.post("/api/tasks/sync", json={"tasks": TASKS})
    assert r.status_code == 200
    assert r.json()["ai_applied"] is False
    assert len(client.get("/api/tasks").json()) == 3


def test_invalid_task_is_rejected(client):
    r = client.post("/api/tasks/sync", json={"tasks": [{"moodle_id": "1"}]})  # no title
    assert r.status_code == 422

    r = client.post("/api/tasks/sync", json={"tasks": [{"moodle_id": "1", "title": "x", "due_date": "next week"}]})
    assert r.status_code == 422


def test_too_many_tasks_is_rejected(client):
    main.app.dependency_overrides[get_settings] = lambda: dev_settings(max_tasks_per_sync=2)
    r = client.post("/api/tasks/sync", json={"tasks": TASKS})
    assert r.status_code == 413


def test_hebrew_titles_round_trip(client, monkeypatch):
    monkeypatch.setattr(ai_filter, "classify_tasks", fake_ai({}))
    client.post("/api/tasks/sync", json={"tasks": [{"moodle_id": "201", "title": "תרגיל בית 4", "course_name": "מבני נתונים"}]})
    task = client.get("/api/tasks").json()[0]
    assert task["title"] == "תרגיל בית 4"
    assert task["course_name"] == "מבני נתונים"


def test_ai_parser_ignores_unknown_ids_and_bad_output(monkeypatch):
    """The real classify_tasks with a fake Gemini response."""
    from app.models import TaskIn

    class FakeResponse:
        text = '[{"moodle_id": "101", "is_relevant": true, "category": "exam", "priority": 5, "summary": "Study"},' \
               ' {"moodle_id": "999", "is_relevant": false}]'

    class FakeClient:
        class models:
            @staticmethod
            def generate_content(**kwargs):
                return FakeResponse()

    import google.genai

    monkeypatch.setattr(google.genai, "Client", lambda **kwargs: FakeClient())
    out = ai_filter.classify_tasks([TaskIn(moodle_id="101", title="Exam")], dev_settings(gemini_api_key="k"))
    assert set(out) == {"101"}  # the made-up id 999 is dropped
    assert out["101"].category == "exam"

    FakeResponse.text = "sorry, I can't do that"
    assert ai_filter.classify_tasks([TaskIn(moodle_id="101", title="Exam")], dev_settings(gemini_api_key="k")) == {}


def test_supabase_store_keeps_old_ai_fields_when_ai_missing():
    """SupabaseStore sends rows with and without AI fields as separate upserts."""
    from app.db import SupabaseStore

    calls = []

    class FakeQuery:
        def __init__(self, payload=None, kw=None):
            self.payload, self.kw = payload, kw

        def upsert(self, payload, **kw):
            calls.append((payload, kw))
            return self

        def execute(self):
            return self

    store = SupabaseStore.__new__(SupabaseStore)
    store._table = "tasks"
    store._client = type("C", (), {"table": lambda self, name: FakeQuery()})()

    store.upsert("u1", [
        {"moodle_id": "1", "title": "a", "is_relevant": True, "ai_category": "exam", "ai_priority": 5, "ai_summary": "s"},
        {"moodle_id": "2", "title": "b"},
    ])
    assert len(calls) == 2
    for payload, kw in calls:
        assert kw == {"on_conflict": "user_id,moodle_id", "default_to_null": False}
        assert all(row["user_id"] == "u1" for row in payload)
    no_ai = next(p for p, _ in calls if p[0]["moodle_id"] == "2")
    assert "is_relevant" not in no_ai[0]


def test_ai_sends_thinking_level_and_retries_without_it(monkeypatch):
    """Low thinking level is sent; if the model rejects it, we retry once without it."""
    from app.models import TaskIn

    seen = []

    class FakeResponse:
        text = '[{"moodle_id": "1", "is_relevant": true}]'

    class FakeClient:
        class models:
            @staticmethod
            def generate_content(model, contents, config):
                seen.append(config.thinking_config)
                if config.thinking_config is not None:
                    raise ValueError("400 INVALID_ARGUMENT: thinking_level is not supported")
                return FakeResponse()

    import google.genai

    monkeypatch.setattr(google.genai, "Client", lambda **kwargs: FakeClient())
    out = ai_filter.classify_tasks([TaskIn(moodle_id="1", title="HW")], dev_settings(gemini_api_key="k"))
    assert set(out) == {"1"}
    assert str(seen[0].thinking_level).endswith("MINIMAL")
    assert seen[1] is None


def test_dates_without_time_zone_are_israel_time(client, monkeypatch):
    """Mixed date formats used to crash GET /api/tasks; now a missing zone means Israel time."""
    monkeypatch.setattr(ai_filter, "classify_tasks", fake_ai({}))
    r = client.post("/api/tasks/sync", json={"tasks": [
        {"moodle_id": "a", "title": "With zone", "due_date": "2026-12-06T09:00:00+02:00"},
        {"moodle_id": "b", "title": "No zone", "due_date": "2026-12-06T08:00:00"},
        {"moodle_id": "c", "title": "UTC", "due_date": "2026-12-06T08:30:00Z"},  # = 10:30 Israel time
        {"moodle_id": "d", "title": "No date"},
    ]})
    assert r.status_code == 200

    tasks = client.get("/api/tasks").json()
    assert [t["moodle_id"] for t in tasks] == ["b", "a", "c", "d"]
    no_zone = next(t for t in tasks if t["moodle_id"] == "b")
    assert no_zone["due_date"] == "2026-12-06T08:00:00+02:00"


def test_ai_retries_once_when_gemini_is_busy(monkeypatch):
    """A 504 from Google is retried once; a second failure gives up (tasks still saved)."""
    from app.models import TaskIn

    calls = []
    outcomes = []

    class FakeResponse:
        text = '[{"moodle_id": "1", "is_relevant": true}]'

    class FakeClient:
        class models:
            @staticmethod
            def generate_content(**kwargs):
                calls.append(1)
                outcome = outcomes.pop(0)
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome

    import google.genai

    monkeypatch.setattr(google.genai, "Client", lambda **kwargs: FakeClient())
    monkeypatch.setattr(ai_filter, "RETRY_DELAY_SECONDS", 0)
    settings = dev_settings(gemini_api_key="k")
    task = [TaskIn(moodle_id="1", title="HW")]

    outcomes[:] = [RuntimeError("504 DEADLINE_EXCEEDED"), FakeResponse()]
    assert set(ai_filter.classify_tasks(task, settings)) == {"1"}
    assert len(calls) == 2

    calls.clear()
    outcomes[:] = [RuntimeError("504 DEADLINE_EXCEEDED"), RuntimeError("504 DEADLINE_EXCEEDED")]
    assert ai_filter.classify_tasks(task, settings) == {}
    assert len(calls) == 2

    calls.clear()
    outcomes[:] = [RuntimeError("400 API key not valid")]  # not a "busy" error: no retry
    assert ai_filter.classify_tasks(task, settings) == {}
    assert len(calls) == 1


def test_root_welcome_message(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["status"] == "online"


def test_placeholder_supabase_url_from_env_example_means_dev_mode():
    # A teammate who copies .env.example without filling it in should still get dev mode.
    assert Settings(_env_file=None, supabase_url="your-supabase-url-here").dev_mode
    assert not Settings(_env_file=None, supabase_url="https://abc.supabase.co").dev_mode


def test_supabase_key_accepts_both_env_names(monkeypatch):
    monkeypatch.setenv("SUPABASE_KEY", "from-root-env")
    assert Settings(_env_file=None).supabase_key == "from-root-env"
    monkeypatch.delenv("SUPABASE_KEY")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "old-name")
    assert Settings(_env_file=None).supabase_key == "old-name"
