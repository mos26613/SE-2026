"""The task queries must keep the shape the indexes are built for (User Story 1.2.2, AB#211).

idx_tasks_user_due is (user_id, due_date) and returns rows in due_date ASC NULLS LAST
order. If someone changes the query to sort differently or stop filtering by user_id,
Postgres can no longer use the index the same way. See docs/performance/indexing.md.
"""
from app.db import SupabaseStore


class RecordingQuery:
    def __init__(self, log):
        self.log = log

    def __getattr__(self, name):
        def call(*args, **kwargs):
            self.log.append((name, args, kwargs))
            return self

        return call

    def execute(self):
        return type("Res", (), {"data": []})()


def _store(log):
    store = SupabaseStore.__new__(SupabaseStore)
    store._table = "tasks"
    store._courses = "courses"
    store._client = type("C", (), {"table": lambda self, name: (log.append(("table", (name,), {})), RecordingQuery(log))[1]})()
    return store


def test_dashboard_query_matches_idx_tasks_user_due():
    log = []
    _store(log).list_tasks("u1", include_filtered=False)
    assert ("eq", ("user_id", "u1"), {}) in log
    assert ("order", ("due_date",), {"desc": False, "nullsfirst": False}) in log  # = the B-tree's own order


def test_existing_ids_query_is_limited_to_one_student():
    log = []
    _store(log).existing_ids("u1", ["a", "b"])
    assert ("eq", ("user_id", "u1"), {}) in log
    assert ("in_", ("moodle_id", ["a", "b"]), {}) in log
