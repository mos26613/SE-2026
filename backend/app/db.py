"""Saving and reading tasks.

Two stores with the same methods:
- SupabaseStore: the real database. Each request acts as the logged-in student,
  so Supabase's Row Level Security makes sure they only touch their own rows.
- MemoryStore: used in dev mode (no SUPABASE_URL) and in tests. Data disappears
  when the server restarts.

If the team's real table uses different column names, this is the only file to change.
"""
from datetime import datetime
from typing import Protocol

from .config import Settings
from .models import TaskOut

# The columns we write. Must match the Supabase table.
COLUMNS = [
    "moodle_id", "title", "course_name", "description", "due_date", "moodle_url",
    "is_relevant", "ai_category", "ai_priority", "ai_summary",
]


class TaskStore(Protocol):
    def existing_ids(self, user_id: str, moodle_ids: list[str]) -> set[str]: ...
    def upsert(self, user_id: str, rows: list[dict]) -> None: ...
    def list_tasks(self, user_id: str, include_filtered: bool) -> list[TaskOut]: ...


def _sort_key(task: TaskOut):
    # Tasks with a due date first (soonest first), then tasks without one.
    return (task.due_date is None, task.due_date or datetime.max)


class MemoryStore:
    def __init__(self) -> None:
        self._data: dict[str, dict[str, dict]] = {}  # user_id -> moodle_id -> row

    def existing_ids(self, user_id: str, moodle_ids: list[str]) -> set[str]:
        mine = self._data.get(user_id, {})
        return {m for m in moodle_ids if m in mine}

    def upsert(self, user_id: str, rows: list[dict]) -> None:
        mine = self._data.setdefault(user_id, {})
        for row in rows:
            old = mine.get(row["moodle_id"], {})
            mine[row["moodle_id"]] = {**old, **row, "status": old.get("status", "open")}

    def list_tasks(self, user_id: str, include_filtered: bool) -> list[TaskOut]:
        tasks = [TaskOut(**row) for row in self._data.get(user_id, {}).values()]
        if not include_filtered:
            tasks = [t for t in tasks if t.is_relevant]
        return sorted(tasks, key=_sort_key)


class SupabaseStore:
    def __init__(self, settings: Settings, access_token: str) -> None:
        from supabase import create_client

        self._client = create_client(settings.supabase_url, settings.supabase_key)
        # Act as the student, not as an admin, so Row Level Security applies.
        self._client.postgrest.auth(access_token)
        self._table = settings.tasks_table

    def existing_ids(self, user_id: str, moodle_ids: list[str]) -> set[str]:
        if not moodle_ids:
            return set()
        res = (
            self._client.table(self._table)
            .select("moodle_id")
            .eq("user_id", user_id)
            .in_("moodle_id", moodle_ids)
            .execute()
        )
        return {r["moodle_id"] for r in res.data}

    def upsert(self, user_id: str, rows: list[dict]) -> None:
        if not rows:
            return
        # Rows with AI fields and rows without them are sent separately, so a sync where
        # Gemini was unavailable never wipes the AI fields saved by an earlier sync.
        groups: dict[tuple, list[dict]] = {}
        for r in rows:
            groups.setdefault(tuple(sorted(r)), []).append({**r, "user_id": user_id})
        for payload in groups.values():
            # One row per (student, Moodle assignment): a re-sync updates instead of duplicating.
            self._client.table(self._table).upsert(
                payload, on_conflict="user_id,moodle_id", default_to_null=False
            ).execute()

    def list_tasks(self, user_id: str, include_filtered: bool) -> list[TaskOut]:
        query = self._client.table(self._table).select("*").eq("user_id", user_id)
        if not include_filtered:
            query = query.eq("is_relevant", True)
        res = query.order("due_date", desc=False, nullsfirst=False).execute()
        return [TaskOut(**row) for row in res.data]
