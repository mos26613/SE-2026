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


def _fake_supabase_store(calls: list, select_rows=None):
    """A SupabaseStore whose client records every upsert/select instead of calling Supabase."""
    from app.db import SupabaseStore

    class FakeQuery:
        def __init__(self, table):
            self.table = table

        def upsert(self, payload, **kw):
            calls.append((self.table, payload, kw))
            return self

        def select(self, columns):
            calls.append((self.table, "select", columns))
            return self

        def eq(self, *a):
            return self

        def order(self, *a, **kw):
            return self

        def execute(self):
            return type("Res", (), {"data": select_rows or []})()

    store = SupabaseStore.__new__(SupabaseStore)
    store._table = "tasks"
    store._courses = "courses"
    store._client = type("C", (), {"table": lambda self, name: FakeQuery(name)})()
    return store


def test_supabase_store_keeps_old_ai_fields_when_ai_missing():
    """SupabaseStore sends rows with and without AI fields as separate upserts."""
    calls = []
    store = _fake_supabase_store(calls)
    store.upsert("u1", [
        {"moodle_id": "1", "title": "a", "is_relevant": True, "ai_category": "exam", "ai_priority": 5, "ai_summary": "s"},
        {"moodle_id": "2", "title": "b"},
    ])
    task_calls = [c for c in calls if c[0] == "tasks"]
    assert len(task_calls) == 2
    for _, payload, kw in task_calls:
        assert kw == {"on_conflict": "user_id,moodle_id", "default_to_null": False}
        assert all(row["user_id"] == "u1" for row in payload)
    no_ai = next(p for _, p, _ in task_calls if p[0]["moodle_id"] == "2")
    assert "is_relevant" not in no_ai[0]


def test_supabase_store_saves_courses_and_keeps_name_out_of_tasks():
    """Course names go to the courses table; tasks only get moodle_course_id."""
    calls = []
    store = _fake_supabase_store(calls)
    store.upsert("u1", [
        {"moodle_id": "1", "title": "a", "course_name": "Data Structures", "moodle_course_id": 77},
        {"moodle_id": "2", "title": "b", "course_name": None, "moodle_course_id": 88},
        {"moodle_id": "3", "title": "c", "course_name": "No id", "moodle_course_id": None},
    ])
    course_calls = [c for c in calls if c[0] == "courses"]
    named = next(c for c in course_calls if "ignore_duplicates" not in c[2])
    placeholder = next(c for c in course_calls if c[2].get("ignore_duplicates"))
    assert named[1] == [{"user_id": "u1", "moodle_course_id": 77, "name": "Data Structures"}]
    assert placeholder[1] == [{"user_id": "u1", "moodle_course_id": 88, "name": "Course 88"}]
    assert named[2]["on_conflict"] == "user_id,moodle_course_id"

    task_rows = [row for c in calls if c[0] == "tasks" for row in c[1]]
    assert all("course_name" not in row for row in task_rows)
    assert {row["moodle_course_id"] for row in task_rows} == {77, 88, None}


def test_supabase_store_reads_course_name_from_courses():
    calls = []
    store = _fake_supabase_store(calls, select_rows=[
        {"moodle_id": "1", "title": "a", "moodle_course_id": 77, "user_id": "u1", "is_relevant": True,
         "status": "open", "courses": {"name": "Data Structures"}},
        {"moodle_id": "2", "title": "b", "moodle_course_id": None, "user_id": "u1", "is_relevant": True,
         "status": "open", "courses": None},
    ])
    tasks = store.list_tasks("u1", include_filtered=False)
    assert ("tasks", "select", "*, courses(name)") in calls
    assert tasks[0].course_name == "Data Structures"
    assert tasks[0].moodle_course_id == 77
    assert tasks[1].course_name is None


def test_moodle_course_id_round_trips_in_dev_mode(client, monkeypatch):
    monkeypatch.setattr(ai_filter, "classify_tasks", fake_ai({}))
    client.post("/api/tasks/sync", json={"tasks": [
        {"moodle_id": "1", "title": "HW", "course_name": "Logic", "moodle_course_id": 1234}
    ]})
    task = client.get("/api/tasks").json()[0]
    assert task["moodle_course_id"] == 1234
    assert task["course_name"] == "Logic"


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


def _recording_gemini(monkeypatch, response_text: str) -> list:
    """Replace Gemini with a fake that records exactly what would be sent to Google."""
    sent = []

    class FakeResponse:
        text = response_text

    class FakeClient:
        class models:
            @staticmethod
            def generate_content(model, contents, config):
                sent.append(contents)
                return FakeResponse()

    import google.genai

    monkeypatch.setattr(google.genai, "Client", lambda **kwargs: FakeClient())
    return sent


def test_id_numbers_never_reach_gemini_and_come_back_in_the_summary(client, monkeypatch):
    """User Story 5.2.1: valid Israeli ID numbers are replaced before the AI call."""
    sent = _recording_gemini(
        monkeypatch,
        '[{"moodle_id": "301", "is_relevant": true, "category": "other", "summary": "Submit appeal for [ID_1]"}]',
    )
    main.app.dependency_overrides[get_settings] = lambda: dev_settings(gemini_api_key="fake-key")

    task = {
        "moodle_id": "301",
        "title": "ערעור - ת.ז. 123456782",
        "course_name": "Algorithms",
        "description": "Student 123456782 (also 12345678-2) asks to recheck question 3. Ref 123456789.",
    }
    r = client.post("/api/tasks/sync", json={"tasks": [task]})
    assert r.status_code == 200
    assert r.json()["ai_applied"] is True

    assert len(sent) == 1
    assert "123456782" not in sent[0] and "12345678-2" not in sent[0]
    assert "[ID_1]" in sent[0]
    assert "123456789" in sent[0]  # wrong check digit: not an ID, left alone
    assert '"moodle_id": "301"' in sent[0]  # needed to match answers back, never changed

    saved = client.get("/api/tasks").json()[0]
    assert saved["title"] == task["title"]  # our own database keeps the real text
    assert saved["ai_summary"] == "Submit appeal for 123456782"  # restored on our server


def test_if_anonymization_fails_gemini_is_skipped_but_tasks_are_saved(client, monkeypatch):
    from app import anonymizer

    class BrokenRedactor:
        label = "ID"

        def find(self, text):
            raise RuntimeError("bug")

        def key(self, value):
            return value

    sent = _recording_gemini(monkeypatch, "[]")
    monkeypatch.setattr(anonymizer, "DEFAULT_REDACTORS", [BrokenRedactor()])
    main.app.dependency_overrides[get_settings] = lambda: dev_settings(gemini_api_key="fake-key")

    r = client.post("/api/tasks/sync", json={"tasks": [{"moodle_id": "1", "title": "ID 123456782"}]})
    assert r.status_code == 200
    assert r.json()["ai_applied"] is False
    assert sent == []  # nothing was sent to Google
    assert len(client.get("/api/tasks").json()) == 1
