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
from app.change_detection import changed_fields, compare_with_stored, refreshed_fields
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


def test_an_empty_description_is_unknown_not_a_change():
    """The calendar page sends no description; the assignment page sends the instructions."""
    for empty in (None, "", "   "):
        assert changed_fields(HW, {**HW, "description": empty}) == []  # saved text, nothing sent
        assert changed_fields({**HW, "description": empty}, {**HW, "description": None}) == []  # empty both sides


def test_a_first_description_is_filled_in_without_flagging_the_task():
    stored = {**HW, "description": None}
    assert changed_fields(stored, HW) == []
    assert refreshed_fields(stored, HW) == ["description"]


def test_a_really_different_description_is_still_a_change():
    assert changed_fields(HW, {**HW, "description": "Chapter 9"}) == ["description"]


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


def test_a_new_link_or_course_is_saved_quietly_and_a_missing_one_is_ignored():
    stored = {**HW, "moodle_url": "https://moodle.example/a", "moodle_course_id": 7, "course_name": "Algo"}
    assert refreshed_fields(stored, dict(stored)) == []
    assert refreshed_fields(stored, {**stored, "course_name": "Algorithms"}) == ["course_name"]
    assert refreshed_fields(stored, {**stored, "moodle_url": "https://moodle.example/b"}) == ["moodle_url"]
    assert refreshed_fields(stored, {**stored, "moodle_course_id": 8}) == ["moodle_course_id"]
    for name in ("moodle_url", "moodle_course_id", "course_name"):
        assert refreshed_fields(stored, {k: v for k, v in stored.items() if k != name}) == []  # not sent: keep ours
        assert changed_fields(stored, {**stored, name: "something else"}) == []  # never flags the task


def test_batch_comparison_lists_the_unchanged_tasks_that_still_need_saving():
    stored = {"1": {**HW, "moodle_id": "1"}, "2": {**HW, "moodle_id": "2", "description": None}}
    incoming = [{**HW, "moodle_id": "1"}, {**HW, "moodle_id": "2"}]
    diff = compare_with_stored(stored, incoming)
    assert (diff.modified, diff.unchanged, diff.refresh) == ([], ["1", "2"], ["2"])


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


PAGE = {**HW, "moodle_url": "https://moodle.example/mod/assign/view.php?id=101", "moodle_course_id": 7, "course_name": "Algo"}
CALENDAR = {"moodle_id": "101", "title": "Homework 3", "description": "", "due_date": "2026-12-05T23:59:00+02:00"}


def test_syncing_from_the_calendar_and_the_assignment_page_is_not_a_change(client, store):
    """The extension reads both pages. Going back and forth must not flag the task or erase anything."""
    sync(client, PAGE)  # assignment page: has the instructions, link and course
    store.upserts.clear()

    for page in (CALENDAR, PAGE, CALENDAR, CALENDAR, PAGE):
        body = sync(client, page)
        assert (body["updated"], body["unchanged"]) == (0, 1)
        task = tasks_by_id(client)["101"]
        assert task["is_modified"] is False
        assert task["description"] == "Chapter 4"
        assert task["moodle_url"] == PAGE["moodle_url"]
        assert task["course_name"] == "Algo"
    assert store.upserts == [[], [], [], [], []]  # not one row was rewritten


def test_a_description_that_really_changed_is_flagged_even_after_a_calendar_sync(client):
    sync(client, PAGE)
    sync(client, CALENDAR)
    body = sync(client, {**PAGE, "description": "Chapter 9"})
    assert body["updated"] == 1
    task = tasks_by_id(client)["101"]
    assert (task["is_modified"], task["description"]) == (True, "Chapter 9")


def test_a_modified_sync_without_description_keeps_the_saved_one(client):
    sync(client, PAGE)
    sync(client, {**CALENDAR, "due_date": "2026-12-12T23:59:00+02:00"})  # only the date changed
    task = tasks_by_id(client)["101"]
    assert task["is_modified"] is True
    assert task["description"] == "Chapter 4"  # not erased by the calendar's empty description
    assert task["moodle_url"] == PAGE["moodle_url"]


def test_a_description_found_later_is_saved_without_flagging_the_task(client, store):
    sync(client, CALENDAR)  # first seen on the calendar: no description yet
    store.upserts.clear()

    body = sync(client, PAGE)
    assert (body["updated"], body["unchanged"]) == (0, 1)
    task = tasks_by_id(client)["101"]
    assert (task["is_modified"], task["description"]) == (False, "Chapter 4")
    assert len(store.upserts[0]) == 1  # saved once


def test_a_renamed_course_or_a_new_link_is_saved_but_does_not_flag_the_task(client):
    sync(client, PAGE)
    body = sync(client, {**PAGE, "course_name": "Algorithms", "moodle_url": "https://moodle.example/new"})
    assert (body["updated"], body["unchanged"]) == (0, 1)
    task = tasks_by_id(client)["101"]
    assert (task["course_name"], task["moodle_url"]) == ("Algorithms", "https://moodle.example/new")
    assert task["is_modified"] is False


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
    assert task_calls(db, "select") == [("tasks", "select", f"{COMPARE_COLUMNS},courses(name)")]  # one query, with the course name
    assert len(task_calls(db, "in_")) == 1
    for needed in ("title", "description", "due_date", "moodle_url", "moodle_course_id"):
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


def test_supabase_store_returns_the_course_name_next_to_the_task():
    store, db = make_supabase_store()
    db.rows[("u1", "1")] = {"user_id": "u1", "moodle_id": "1", "title": "a", "courses": {"name": "Algo"}}
    db.rows[("u1", "2")] = {"user_id": "u1", "moodle_id": "2", "title": "b", "courses": None}  # no course
    found = store.existing_tasks("u1", ["1", "2"])
    assert found["1"]["course_name"] == "Algo"
    assert found["2"]["course_name"] is None
    assert "courses" not in found["1"]


def test_a_renamed_course_updates_the_course_and_the_task_without_flagging_it(supabase_client):
    client, db = supabase_client
    uid = "00000000-0000-0000-0000-000000000001"
    db.rows[(uid, "1")] = {"user_id": uid, "moodle_id": "1", "title": "Task", "moodle_course_id": 7, "courses": {"name": "Algo"}}
    db.calls.clear()

    body = client.post(
        "/api/tasks/sync",
        json={"tasks": [{"moodle_id": "1", "title": "Task", "moodle_course_id": 7, "course_name": "Algorithms"}]},
    ).json()
    assert (body["updated"], body["unchanged"]) == (0, 1)

    course_writes = [c for c in db.calls if c[0] == "courses" and c[1] == "upsert"]
    assert [row["name"] for row in course_writes[0][2]] == ["Algorithms"]
    payload = task_calls(db, "upsert")[0][2]
    assert [row["moodle_id"] for row in payload] == ["1"]
    assert "is_modified" not in payload[0]  # nothing the student needs to be told about
    assert "description" not in payload[0]  # not sent, so not overwritten
