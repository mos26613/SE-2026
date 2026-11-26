"""Tests for US 3.3.1: detect assignments that changed on Moodle.

Three layers:
  1. the comparison itself (app/change_detection.py), with plain dictionaries;
  2. the whole sync through the API, on the in-memory store;
  3. the Supabase store, with a fake client that counts every database call.

Run:  python -m pytest -v
"""
import time

import pytest
from fastapi.testclient import TestClient

from app import ai_filter, main
from app.change_detection import changed_fields, compare_with_stored
from app.config import get_settings
from app.db import COMPARE_COLUMNS, MemoryStore, SupabaseStore

from .test_api import dev_settings, fake_ai

HW = {"moodle_id": "101", "title": "Homework 3", "description": "Chapter 4", "due_date": "2026-12-05T23:59:00+02:00"}


# ---------------------------------------------------------------- 1. the comparison


def test_identical_task_has_no_changes():
    assert changed_fields(HW, dict(HW)) == []


@pytest.mark.parametrize(
    "field, value",
    [
        ("title", "Homework 3 (extended)"),
        ("description", "Chapter 5"),
        ("due_date", "2026-12-10T23:59:00+02:00"),
    ],
)
def test_a_changed_title_description_or_due_date_is_detected(field, value):
    assert changed_fields(HW, {**HW, field: value}) == [field]


def test_several_changed_fields_are_all_reported():
    assert changed_fields(HW, {**HW, "title": "New", "due_date": None}) == ["title", "due_date"]


def test_extra_spaces_and_line_breaks_are_not_a_change():
    noisy = {**HW, "title": "  Homework   3 ", "description": "Chapter\n 4\t"}
    assert changed_fields(HW, noisy) == []


def test_empty_description_and_missing_description_are_the_same():
    assert changed_fields({**HW, "description": None}, {**HW, "description": ""}) == []
    assert changed_fields({**HW, "description": None}, {**HW, "description": "   "}) == []
    assert changed_fields({**HW, "description": None}, {**HW, "description": "now has text"}) == ["description"]


def test_the_same_moment_in_another_time_zone_is_not_a_change():
    stored = {**HW, "due_date": "2026-12-05T21:59:00+00:00"}  # how the database returns it
    assert changed_fields(stored, HW) == []  # 23:59+02:00 is the same moment
    assert changed_fields({**HW, "due_date": "2026-12-05T21:59:00Z"}, HW) == []


def test_a_date_without_time_zone_is_read_as_israel_time():
    assert changed_fields({**HW, "due_date": "2026-12-05T23:59:00"}, HW) == []  # winter: Israel is UTC+2
    assert changed_fields({**HW, "due_date": "2026-12-05T23:59:00"}, {**HW, "due_date": "2026-12-05T23:59:00Z"}) == ["due_date"]


@pytest.fixture
def machine_in_utc(monkeypatch):
    """Pretend the computer's own clock is on UTC (not possible on Windows, where the test is skipped)."""
    if not hasattr(time, "tzset"):
        pytest.skip("time.tzset is not available on this system")
    monkeypatch.setenv("TZ", "UTC")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def test_a_date_without_time_zone_is_israel_time_whatever_the_computer_clock_says(machine_in_utc):
    """The comparison must not depend on where the server runs (a laptop in Israel, a Docker host on UTC)."""
    assert changed_fields({**HW, "due_date": "2026-12-05T23:59:00"}, HW) == []


def test_adding_or_removing_a_due_date_is_a_change():
    assert changed_fields({**HW, "due_date": None}, HW) == ["due_date"]
    assert changed_fields(HW, {**HW, "due_date": None}) == ["due_date"]
    assert changed_fields({**HW, "due_date": None}, {**HW, "due_date": None}) == []


def test_other_fields_do_not_count_as_a_change():
    other = {**HW, "moodle_url": "https://moodle.example/x", "ai_category": "exam", "is_relevant": False}
    assert changed_fields(HW, other) == []


def test_batch_comparison_sorts_tasks_into_new_modified_unchanged():
    stored = {"1": {**HW, "moodle_id": "1"}, "2": {**HW, "moodle_id": "2"}}
    incoming = [
        {**HW, "moodle_id": "1"},  # identical
        {**HW, "moodle_id": "2", "title": "Renamed"},  # changed
        {**HW, "moodle_id": "3"},  # never saved
    ]
    diff = compare_with_stored(stored, incoming)
    assert (diff.new, diff.modified, diff.unchanged) == (["3"], ["2"], ["1"])


def test_comparing_a_big_batch_is_fast():
    """Dictionary lookups, no database call per task: 10,000 tasks take a fraction of a second."""
    stored = {str(i): {"moodle_id": str(i), "title": f"T{i}", "description": "d", "due_date": "2026-12-05T21:59:00+00:00"} for i in range(10_000)}
    incoming = [{**row, "due_date": "2026-12-05T23:59:00+02:00"} for row in stored.values()]
    incoming[5_000] = {**incoming[5_000], "title": "changed"}
    started = time.perf_counter()
    diff = compare_with_stored(stored, incoming)
    assert time.perf_counter() - started < 2.0
    assert diff.modified == ["5000"]
    assert len(diff.unchanged) == 9_999


# ---------------------------------------------------------------- 2. the whole sync (dev mode)


class SpyStore(MemoryStore):
    """The in-memory store, remembering which rows each upsert received."""

    def __init__(self):
        super().__init__()
        self.upserts: list[list[dict]] = []

    def upsert(self, user_id, rows):
        self.upserts.append(list(rows))
        super().upsert(user_id, rows)


@pytest.fixture
def store(monkeypatch):
    spy = SpyStore()
    monkeypatch.setattr(main, "_memory_store", spy)
    return spy


@pytest.fixture
def client(store):
    main.app.dependency_overrides[get_settings] = lambda: dev_settings()
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def tasks_by_id(client):
    return {t["moodle_id"]: t for t in client.get("/api/tasks", params={"include_filtered": True}).json()}


def sync(client, *tasks):
    r = client.post("/api/tasks/sync", json={"tasks": list(tasks)})
    assert r.status_code == 200
    return r.json()


def test_a_new_task_is_saved_and_not_flagged_as_modified(client):
    body = sync(client, HW)
    assert (body["created"], body["updated"], body["unchanged"]) == (1, 0, 0)
    assert tasks_by_id(client)["101"]["is_modified"] is False


def test_changed_due_date_flags_the_task_as_modified(client):
    sync(client, HW, {**HW, "moodle_id": "102", "title": "Quiz"})
    body = sync(client, {**HW, "due_date": "2026-12-12T23:59:00+02:00"}, {**HW, "moodle_id": "102", "title": "Quiz"})
    assert (body["created"], body["updated"], body["unchanged"]) == (0, 1, 1)

    tasks = tasks_by_id(client)
    assert tasks["101"]["is_modified"] is True
    assert tasks["101"]["due_date"].startswith("2026-12-12")  # the new date is saved
    assert tasks["102"]["is_modified"] is False  # the other task is untouched


@pytest.mark.parametrize("field, value", [("title", "Homework 3 v2"), ("description", "Chapter 9")])
def test_changed_title_or_description_flags_the_task(client, field, value):
    sync(client, HW)
    body = sync(client, {**HW, field: value})
    assert body["updated"] == 1
    task = tasks_by_id(client)["101"]
    assert task["is_modified"] is True
    assert task[field] == value


def test_identical_resync_changes_nothing_and_writes_nothing(client, store):
    sync(client, HW)
    store.upserts.clear()

    body = sync(client, HW)
    assert (body["created"], body["updated"], body["unchanged"]) == (0, 0, 1)
    assert store.upserts == [[]]  # the store was asked to save no rows at all
    assert tasks_by_id(client)["101"]["is_modified"] is False


def test_same_moment_in_another_format_is_not_reported_as_a_change(client):
    sync(client, HW)  # 23:59+02:00
    body = sync(client, {**HW, "due_date": "2026-12-05T21:59:00Z"})  # the same moment
    assert (body["updated"], body["unchanged"]) == (0, 1)
    assert tasks_by_id(client)["101"]["is_modified"] is False


def test_the_modified_flag_stays_until_something_clears_it(client):
    sync(client, HW)
    changed = {**HW, "due_date": "2026-12-12T23:59:00+02:00"}
    sync(client, changed)
    sync(client, changed)  # an identical sync after the change must not clear the flag
    assert tasks_by_id(client)["101"]["is_modified"] is True


def test_only_changed_and_new_rows_reach_the_store(client, store):
    sync(client, HW, {**HW, "moodle_id": "102"})
    store.upserts.clear()

    sync(client, {**HW, "title": "Renamed"}, {**HW, "moodle_id": "102"}, {**HW, "moodle_id": "103"})
    sent = {row["moodle_id"]: row for row in store.upserts[0]}
    assert set(sent) == {"101", "103"}  # 102 was identical
    assert sent["101"]["is_modified"] is True
    assert "is_modified" not in sent["103"]  # new: the database default (false) applies


def test_an_unchanged_task_is_saved_once_to_add_the_ai_verdict_it_was_missing(client, store, monkeypatch):
    sync(client, HW)  # no AI key: saved without AI fields
    store.upserts.clear()

    monkeypatch.setattr(ai_filter, "classify_tasks", fake_ai({}))
    body = sync(client, HW)
    assert (body["updated"], body["unchanged"]) == (0, 1)  # nothing changed on Moodle
    task = tasks_by_id(client)["101"]
    assert task["ai_category"] == "homework"
    assert task["is_modified"] is False  # adding the AI verdict is not a Moodle change

    store.upserts.clear()
    sync(client, HW)  # the AI verdict is saved now: no more writes
    assert store.upserts == [[]]


def test_a_failure_while_reading_saved_tasks_returns_502_before_calling_the_ai(client, store, monkeypatch):
    def boom(user_id, ids):
        raise RuntimeError("database is down")

    ai_calls = []
    monkeypatch.setattr(store, "existing_tasks", boom)
    monkeypatch.setattr(ai_filter, "classify_tasks", lambda tasks, settings: ai_calls.append(1) or {})

    r = client.post("/api/tasks/sync", json={"tasks": [HW]})
    assert r.status_code == 502
    assert "database is down" not in r.text  # no internal details
    assert ai_calls == []  # no Gemini quota spent
    assert store.upserts == []


# ---------------------------------------------------------------- 3. Supabase store, counting calls


class FakeSupabase:
    """A tiny stand-in for the Supabase client that keeps rows in memory and records every call."""

    def __init__(self):
        self.rows: dict[tuple, dict] = {}
        self.calls: list[tuple] = []

    def table(self, name):
        return FakeQuery(self, name)


class FakeQuery:
    def __init__(self, db, table):
        self.db, self.table = db, table
        self._filters, self._columns = {}, None

    def select(self, columns):
        self._columns = columns
        self.db.calls.append((self.table, "select", columns))
        return self

    def eq(self, column, value):
        self._filters[column] = value
        return self

    def in_(self, column, values):
        self.db.calls.append((self.table, "in_", column, list(values)))
        self._filters[column] = set(values)
        return self

    def upsert(self, payload, **kw):
        self.db.calls.append((self.table, "upsert", payload, kw))
        if self.table == "tasks":
            for row in payload:
                key = (row["user_id"], row["moodle_id"])
                self.db.rows[key] = {**self.db.rows.get(key, {}), **row}
        return self

    def execute(self):
        data = []
        if self._columns is not None and self.table == "tasks":
            for row in self.db.rows.values():
                if all(row.get(c) in v if isinstance(v, set) else row.get(c) == v for c, v in self._filters.items()):
                    data.append(row)
        return type("Res", (), {"data": data})()


def make_supabase_store():
    db = FakeSupabase()
    store = SupabaseStore.__new__(SupabaseStore)
    store._table, store._courses, store._client = "tasks", "courses", db
    return store, db


def task_calls(db, kind):
    return [c for c in db.calls if c[0] == "tasks" and c[1] == kind]


def test_supabase_store_reads_what_it_needs_to_compare_in_one_query():
    store, db = make_supabase_store()
    store.upsert("u1", [{"moodle_id": "1", "title": "a"}])
    db.calls.clear()

    found = store.existing_tasks("u1", ["1", "2"])
    assert list(found) == ["1"]
    assert task_calls(db, "select") == [("tasks", "select", COMPARE_COLUMNS)]
    assert len(task_calls(db, "in_")) == 1
    for needed in ("title", "description", "due_date"):
        assert needed in COMPARE_COLUMNS


def test_supabase_store_does_not_query_for_an_empty_batch():
    store, db = make_supabase_store()
    assert store.existing_tasks("u1", []) == {}
    assert db.calls == []


@pytest.fixture
def supabase_client(monkeypatch):
    store, db = make_supabase_store()
    main.app.dependency_overrides[get_settings] = lambda: dev_settings()
    main.app.dependency_overrides[main.get_store] = lambda: store
    yield TestClient(main.app), db
    main.app.dependency_overrides.clear()


def test_a_sync_of_200_tasks_uses_one_read_and_a_resync_uses_no_writes(supabase_client):
    """The batch limit is 200 tasks. Reads and writes do not grow with the number of tasks."""
    client, db = supabase_client
    batch = [{"moodle_id": str(i), "title": f"Task {i}", "description": "d", "due_date": "2026-12-05T23:59:00+02:00"} for i in range(200)]

    first = client.post("/api/tasks/sync", json={"tasks": batch}).json()
    assert (first["created"], first["updated"], first["unchanged"]) == (200, 0, 0)
    assert len(task_calls(db, "select")) == 1
    assert len(task_calls(db, "upsert")) == 1  # all 200 new rows in one write

    db.calls.clear()
    second = client.post("/api/tasks/sync", json={"tasks": batch}).json()
    assert (second["created"], second["updated"], second["unchanged"]) == (0, 0, 200)
    assert len(task_calls(db, "select")) == 1
    assert task_calls(db, "upsert") == []  # nothing changed: no write at all


def test_a_changed_task_is_sent_to_supabase_with_the_modified_flag(supabase_client):
    client, db = supabase_client
    batch = [{"moodle_id": str(i), "title": f"Task {i}", "due_date": "2026-12-05T23:59:00+02:00"} for i in range(3)]
    client.post("/api/tasks/sync", json={"tasks": batch})
    db.calls.clear()

    batch[1] = {**batch[1], "due_date": "2026-12-20T10:00:00+02:00"}
    body = client.post("/api/tasks/sync", json={"tasks": batch}).json()
    assert (body["updated"], body["unchanged"]) == (1, 2)

    writes = task_calls(db, "upsert")
    assert len(writes) == 1
    payload = writes[0][2]
    assert [row["moodle_id"] for row in payload] == ["1"]  # only the changed task
    assert payload[0]["is_modified"] is True
    assert payload[0]["user_id"] == "00000000-0000-0000-0000-000000000001"
