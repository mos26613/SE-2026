"""Saving and reading tasks.

Two stores with the same methods:
- SupabaseStore: the real database. Each request acts as the logged-in student,
  so Supabase's Row Level Security makes sure they only touch their own rows.
- MemoryStore: used in dev mode (no SUPABASE_URL) and in tests. Data disappears
  when the server restarts.

If the team's real tables use different column names, this is the only file to change.

Database layout (Epic 1): tasks.moodle_course_id links to courses(user_id, moodle_course_id),
and the course name lives in courses.name, not in tasks.
"""
from datetime import datetime
from typing import Protocol

from .config import Settings
from .models import TaskOut

# The tasks columns we write. Must match the Supabase table.
COLUMNS = [
    "moodle_id", "title", "moodle_course_id", "description", "due_date", "moodle_url",
    "is_relevant", "ai_category", "ai_priority", "ai_summary", "is_modified",
    "user_notes", "custom_priority", "conflict_detected", "conflict_message",
]

# What we read back to tell whether an incoming task changed (see change_detection.py).
# ai_category tells us whether the AI has already looked at the task. The course name comes
# from the courses table (added in existing_tasks), like in list_tasks.
COMPARE_COLUMNS = "moodle_id,title,description,due_date,moodle_url,moodle_course_id,ai_category,user_notes,custom_priority,conflict_detected,conflict_message"


class TaskStore(Protocol):
    def existing_tasks(self, user_id: str, moodle_ids: list[str]) -> dict[str, dict]: ...
    def upsert(self, user_id: str, rows: list[dict]) -> None: ...
    def list_tasks(self, user_id: str, include_filtered: bool) -> list[TaskOut]: ...
    def update_user_task(self, user_id: str, moodle_id: str, updates: dict) -> Optional[TaskOut]: ...


def _sort_key(task: TaskOut):
    # Tasks with a due date first (soonest first), then tasks without one.
    return (task.due_date is None, task.due_date or datetime.max)


class MemoryStore:
    def __init__(self) -> None:
        self._data: dict[str, dict[str, dict]] = {}  # user_id -> moodle_id -> row

    def existing_tasks(self, user_id: str, moodle_ids: list[str]) -> dict[str, dict]:
        mine = self._data.get(user_id, {})
        return {m: dict(mine[m]) for m in moodle_ids if m in mine}

    def upsert(self, user_id: str, rows: list[dict]) -> None:
        mine = self._data.setdefault(user_id, {})
        for row in rows:
            old = mine.get(row["moodle_id"], {})
            # Preserve user notes, custom priority, and status across syncs
            merged = {**old, **row}
            if "user_notes" not in row and "user_notes" in old:
                merged["user_notes"] = old["user_notes"]
            if "custom_priority" not in row and "custom_priority" in old:
                merged["custom_priority"] = old["custom_priority"]
            merged["status"] = old.get("status", "open")
            mine[row["moodle_id"]] = merged

    def update_user_task(self, user_id: str, moodle_id: str, updates: dict) -> Optional[TaskOut]:
        mine = self._data.get(user_id, {})
        if moodle_id not in mine:
            return None
        task = mine[moodle_id]
        if "user_notes" in updates:
            task["user_notes"] = updates["user_notes"]
        if "custom_priority" in updates:
            task["custom_priority"] = updates["custom_priority"]
        if updates.get("resolve_conflict"):
            task["conflict_detected"] = False
            task["conflict_message"] = None
        return TaskOut(**task)

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
        self._courses = settings.courses_table

    def existing_tasks(self, user_id: str, moodle_ids: list[str]) -> dict[str, dict]:
        """The stored version of the given tasks, in ONE query, keyed by moodle_id."""
        if not moodle_ids:
            return {}
        res = (
            self._client.table(self._table)
            .select(f"{COMPARE_COLUMNS},{self._courses}(name)")
            .eq("user_id", user_id)
            .in_("moodle_id", moodle_ids)
            .execute()
        )
        found = {}
        for row in res.data:
            course = row.pop(self._courses, None) or {}
            found[row["moodle_id"]] = {**row, "course_name": course.get("name")}
        return found

    def _save_courses(self, user_id: str, rows: list[dict]) -> None:
        """Make sure every course a task points to exists, so the tasks -> courses foreign key holds."""
        named: dict[int, str] = {}
        unnamed: set[int] = set()
        for r in rows:
            course_id = r.get("moodle_course_id")
            if course_id is None:
                continue
            if r.get("course_name"):
                named[course_id] = r["course_name"]
            else:
                unnamed.add(course_id)
        unnamed -= set(named)

        if named:
            # Insert new courses and refresh the names of existing ones.
            self._client.table(self._courses).upsert(
                [{"user_id": user_id, "moodle_course_id": cid, "name": name} for cid, name in named.items()],
                on_conflict="user_id,moodle_course_id",
            ).execute()
        if unnamed:
            # No name was sent: create a placeholder only if the course doesn't exist yet.
            self._client.table(self._courses).upsert(
                [{"user_id": user_id, "moodle_course_id": cid, "name": f"Course {cid}"} for cid in unnamed],
                on_conflict="user_id,moodle_course_id",
                ignore_duplicates=True,
            ).execute()

    def upsert(self, user_id: str, rows: list[dict]) -> None:
        if not rows:
            return
        self._save_courses(user_id, rows)

        # Rows with AI fields and rows without them are sent separately, so a sync where
        # Gemini was unavailable never wipes the AI fields saved by an earlier sync.
        groups: dict[tuple, list[dict]] = {}
        for r in rows:
            task = {k: v for k, v in r.items() if k != "course_name"}  # the name lives in courses
            groups.setdefault(tuple(sorted(task)), []).append({**task, "user_id": user_id})
        for payload in groups.values():
            # One row per (student, Moodle assignment): a re-sync updates instead of duplicating.
            self._client.table(self._table).upsert(
                payload, on_conflict="user_id,moodle_id", default_to_null=False
            ).execute()

    def list_tasks(self, user_id: str, include_filtered: bool) -> list[TaskOut]:
        # courses(name) pulls the course name through the tasks -> courses foreign key.
        query = self._client.table(self._table).select(f"*, {self._courses}(name)").eq("user_id", user_id)
        if not include_filtered:
            query = query.eq("is_relevant", True)
        res = query.order("due_date", desc=False, nullsfirst=False).execute()
        tasks = []
        for row in res.data:
            course = row.pop(self._courses, None) or {}
            tasks.append(TaskOut(**row, course_name=course.get("name")))
        return tasks

    def update_user_task(self, user_id: str, moodle_id: str, updates: dict) -> Optional[TaskOut]:
        patch = {}
        if "user_notes" in updates:
            patch["user_notes"] = updates["user_notes"]
        if "custom_priority" in updates:
            patch["custom_priority"] = updates["custom_priority"]
        if updates.get("resolve_conflict"):
            patch["conflict_detected"] = False
            patch["conflict_message"] = None
        if not patch:
            return None
        res = (
            self._client.table(self._table)
            .update(patch)
            .eq("user_id", user_id)
            .eq("moodle_id", moodle_id)
            .execute()
        )
        if not res.data:
            return None
        return TaskOut(**res.data[0])
