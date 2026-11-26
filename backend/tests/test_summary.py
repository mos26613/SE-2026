"""Tests for the summary widgets' counts (User Story 4.1.3, AB#21).

Run:  python -m pytest tests/test_summary.py -v
"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import ai_filter, main
from app.config import get_settings
from app.db import MemoryStore
from app.models import LOCAL_TIMEZONE, TaskOut
from app.summary import summarize
from tests.test_api import dev_settings, fake_ai

# Thursday 26 Nov 2026, 12:00 Israel time.
NOW = datetime(2026, 11, 26, 12, 0, tzinfo=LOCAL_TIMEZONE)


def task(due, status="open", moodle_id="1"):
    return TaskOut(moodle_id=moodle_id, title="t", due_date=due, status=status)


def counts(tasks, now=NOW):
    s = summarize(tasks, now)
    return s.overdue, s.due_today, s.due_this_week


def test_empty_list_is_all_zeros():
    assert counts([]) == (0, 0, 0)


def test_overdue_starts_the_second_the_deadline_passes():
    assert counts([task(NOW - timedelta(seconds=1))]) == (1, 0, 0)
    assert counts([task(NOW - timedelta(days=30))]) == (1, 0, 0)


def test_a_deadline_exactly_now_is_not_yet_overdue():
    assert counts([task(NOW)]) == (0, 1, 1)


def test_today_is_the_next_24_hours_and_counts_in_this_week_too():
    assert counts([task(NOW + timedelta(minutes=1))]) == (0, 1, 1)
    assert counts([task(NOW + timedelta(hours=23, minutes=59))]) == (0, 1, 1)


def test_24_hours_from_now_is_this_week_not_today():
    assert counts([task(NOW + timedelta(hours=24))]) == (0, 0, 1)


def test_tomorrow_morning_is_not_today_when_it_is_more_than_24_hours_away():
    # NOW is Thu 12:00. Friday 11:00 is 23h away (today); Friday 13:00 is 25h away (not today).
    assert counts([task(NOW + timedelta(hours=23))]) == (0, 1, 1)
    assert counts([task(NOW + timedelta(hours=25))]) == (0, 0, 1)


def test_this_week_is_seven_days_from_now_to_the_same_time():
    # Wednesday 09:00 -> up to, not including, next Wednesday 09:00.
    wed = datetime(2026, 11, 25, 9, 0, tzinfo=LOCAL_TIMEZONE)
    just_inside = wed + timedelta(days=7) - timedelta(minutes=1)
    exactly_next_wed = wed + timedelta(days=7)
    assert counts([task(just_inside)], wed) == (0, 0, 1)
    assert counts([task(exactly_next_wed)], wed) == (0, 0, 0)


def test_done_tasks_and_tasks_without_a_date_are_not_counted():
    tasks = [task(NOW - timedelta(days=1), status="done"), task(None), task(NOW + timedelta(hours=1), status="done")]
    assert counts(tasks) == (0, 0, 0)


def test_a_due_date_in_another_offset_is_compared_correctly():
    due = datetime(2026, 11, 26, 11, 0, tzinfo=timezone.utc)  # 13:00 Israel: an hour from NOW
    assert counts([task(due)]) == (0, 1, 1)


def test_the_windows_do_not_depend_on_the_time_zone_of_now():
    now_utc = NOW.astimezone(timezone.utc)
    assert counts([task(NOW + timedelta(hours=2))], now_utc) == (0, 1, 1)


def test_the_week_is_exactly_seven_days_across_a_daylight_saving_change():
    # Israel moves to summer time on Fri 27 Mar 2026. Seven days of absolute time still holds.
    before = datetime(2026, 3, 25, 9, 0, tzinfo=LOCAL_TIMEZONE)
    seven_days = before.astimezone(timezone.utc) + timedelta(days=7)  # 168 hours later, in absolute time
    assert counts([task(seven_days - timedelta(minutes=1))], before) == (0, 0, 1)
    assert counts([task(seven_days)], before) == (0, 0, 0)


def test_mixed_list():
    tasks = [
        task(NOW - timedelta(days=2), moodle_id="a"),
        task(NOW + timedelta(hours=3), moodle_id="b"),
        task(NOW + timedelta(days=3), moodle_id="c"),
        task(NOW + timedelta(days=20), moodle_id="d"),
        task(None, moodle_id="e"),
    ]
    assert counts(tasks) == (1, 1, 2)


# --- the endpoint ---

@pytest.fixture
def client(monkeypatch):
    main.app.dependency_overrides[get_settings] = lambda: dev_settings()
    monkeypatch.setattr(main, "_memory_store", MemoryStore())
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def iso(delta):
    return (datetime.now(LOCAL_TIMEZONE) + delta).isoformat()


def test_summary_of_a_new_student_is_zero(client):
    body = client.get("/api/tasks/summary").json()
    assert (body["overdue"], body["due_today"], body["due_this_week"]) == (0, 0, 0)
    assert "as_of" in body


def test_summary_matches_the_task_list_and_updates_after_a_sync(client, monkeypatch):
    # Acceptance criterion: the counts match the task list and update after each sync.
    monkeypatch.setattr(ai_filter, "classify_tasks", fake_ai({"hidden": False}))
    client.post("/api/tasks/sync", json={"tasks": [
        {"moodle_id": "late", "title": "Late", "due_date": iso(timedelta(days=-2))},
        {"moodle_id": "soon", "title": "Soon", "due_date": iso(timedelta(days=3))},
        {"moodle_id": "far", "title": "Far", "due_date": iso(timedelta(days=30))},
        {"moodle_id": "hidden", "title": "Not a task", "due_date": iso(timedelta(days=-1))},
    ]})

    listed = client.get("/api/tasks").json()
    assert {t["moodle_id"] for t in listed} == {"late", "soon", "far"}  # the hidden one is not listed ...
    summary = client.get("/api/tasks/summary").json()
    assert (summary["overdue"], summary["due_this_week"]) == (1, 1)    # ... and not counted

    # A second sync moves "far" into this week: the next summary reflects it.
    client.post("/api/tasks/sync", json={"tasks": [
        {"moodle_id": "far", "title": "Far", "due_date": iso(timedelta(days=2))},
    ]})
    assert client.get("/api/tasks/summary").json()["due_this_week"] == 2


def test_summary_does_not_clash_with_the_task_list_route(client):
    assert client.get("/api/tasks").status_code == 200
    assert client.get("/api/tasks/summary").status_code == 200


def test_summary_database_failure_is_a_502(client, monkeypatch):
    def boom(self, user_id, include_filtered):
        raise RuntimeError("db down")

    monkeypatch.setattr(MemoryStore, "list_tasks", boom)
    assert client.get("/api/tasks/summary").status_code == 502
