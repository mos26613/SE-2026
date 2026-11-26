"""Smart Student Task Hub API.

Flow for every sync:
  Chrome extension --POST /api/tasks/sync--> validate (models.py)
                                           -> compare with saved tasks (change_detection.py)
                                           -> Gemini filter (ai_filter.py)
                                           -> save new and changed tasks to Supabase (db.py)
  React dashboard  --GET /api/tasks------> read from Supabase

Run locally:   python -m uvicorn app.main:app --reload
Then open:     http://localhost:8000/docs
"""
import logging
import time
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware

from . import ai_filter
from .auth import CurrentUser, get_current_user
from .change_detection import compare_with_stored, reconcile_task
from .config import Settings, get_settings
from .db import MemoryStore, SupabaseStore, TaskStore
from .logging_config import log_sync_error, log_sync_transaction, setup_structured_logging
from .models import AIResult, SyncRequest, SyncResponse, TaskIn, TaskOut, TaskUpdateIn
from .routers import auth as auth_router

log = setup_structured_logging(logging.INFO)

app = FastAPI(
    title="Smart Student Task Hub API",
    description="Receives Moodle assignments from the Chrome extension, filters them with Gemini, "
    "stores them in Supabase and serves them to the dashboard.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_origin_regex=r"chrome-extension://.*",
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth_router.router)

# One shared in-memory store for dev mode.
_memory_store = MemoryStore()


def get_store(
    user: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> TaskStore:
    if settings.dev_mode:
        return _memory_store
    return SupabaseStore(settings, user.access_token)


# Fields that only some pages of Moodle give us. When missing, the saved value is kept.
OPTIONAL_FIELDS = ("course_name", "moodle_course_id", "description", "moodle_url")


def _to_row(task: TaskIn, ai: AIResult | None) -> dict:
    row = {
        "moodle_id": task.moodle_id,
        "title": task.title,
        "course_name": task.course_name,
        "moodle_course_id": task.moodle_course_id,
        "description": task.description,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "moodle_url": str(task.moodle_url) if task.moodle_url else None,
    }
    # A value the extension did not send is "unknown", not "erase it": leave it out of the row, so a
    # sync from the calendar page (no description, no link) never wipes what the assignment page gave us.
    for name in OPTIONAL_FIELDS:
        if row[name] is None or row[name] == "":
            del row[name]
    if ai is not None:
        row.update(
            is_relevant=ai.is_relevant,
            ai_category=ai.category,
            ai_priority=ai.priority,
            ai_summary=ai.summary,
        )
    return row


@app.get("/", tags=["system"])
def read_root():
    return {
        "message": "Welcome to Smart Student Task Hub API",
        "status": "online",
    }


@app.get("/health", tags=["system"])
def health(settings: Settings = Depends(get_settings)):
    return {
        "status": "ok",
        "mode": "dev (in-memory)" if settings.dev_mode else "supabase",
        "ai": "on" if settings.gemini_api_key else "off (no GEMINI_API_KEY)",
    }


@app.post("/api/tasks/sync", response_model=SyncResponse, response_model_exclude_none=True, tags=["tasks"])
def sync_tasks(
    body: SyncRequest,
    user: CurrentUser = Depends(get_current_user),
    store: TaskStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
):
    """Called by the Chrome extension with every assignment it found on Moodle."""
    start_time = time.perf_counter()

    if len(body.tasks) > settings.max_tasks_per_sync:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"Too many tasks in one sync (max {settings.max_tasks_per_sync})",
        )

    # The same assignment twice in one batch: keep the last copy.
    unique = list({t.moodle_id: t for t in body.tasks}.values())

    # What we already have for these tasks: one query for the whole batch.
    try:
        stored = store.existing_tasks(user.id, [t.moodle_id for t in unique])
    except Exception as exc:
        log_sync_error(log, "read_existing_tasks", user.id, exc, {"batch_size": len(unique)})
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Could not read saved tasks from the database")

    ai_results = ai_filter.classify_tasks(unique, settings)
    rows = [_to_row(t, ai_results.get(t.moodle_id)) for t in unique]

    # Which tasks are new, which changed on Moodle, and which came back identical (US 3.3.1 & 3.3.3).
    diff = compare_with_stored(stored, rows)
    new_ids, modified_ids, refresh_ids = set(diff.new), set(diff.modified), set(diff.refresh)

    to_save = []
    conflict_count = len(diff.conflicts)

    for row in rows:
        moodle_id = row["moodle_id"]
        old = stored.get(moodle_id)

        if moodle_id in modified_ids:
            if old:
                row, _, _ = reconcile_task(old, row)
            to_save.append({**row, "is_modified": True})  # the "Recently Modified" flag
        elif moodle_id in new_ids:
            to_save.append(row)
        elif moodle_id in refresh_ids:
            # Identical on Moodle, but a link, the course or a first description has to be saved.
            to_save.append(row)
        elif "ai_category" in row and stored[moodle_id].get("ai_category") is None:
            # Identical on Moodle, but the AI has not looked at it before: save only to add its verdict.
            to_save.append(row)
        # Otherwise the task is identical to what we have: no database write.

    try:
        store.upsert(user.id, to_save)
    except Exception as exc:
        log_sync_error(log, "save_tasks", user.id, exc, {"tasks_to_save": len(to_save)})
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Could not save tasks to the database")

    duration_ms = (time.perf_counter() - start_time) * 1000

    # Structured logging of sync transaction (US 3.2.4 AB#402)
    log_sync_transaction(
        log,
        user_id=user.id,
        received=len(body.tasks),
        created=len(diff.new),
        updated=len(diff.modified),
        unchanged=len(diff.unchanged),
        conflicts=conflict_count,
        duration_ms=duration_ms,
    )

    return SyncResponse(
        received=len(body.tasks),
        created=len(diff.new),
        updated=len(diff.modified),
        unchanged=len(diff.unchanged),
        conflicts=conflict_count if conflict_count > 0 else None,
        filtered_out=sum(1 for r in ai_results.values() if not r.is_relevant),
        ai_applied=bool(ai_results),
    )


@app.patch("/api/tasks/{moodle_id}", response_model=TaskOut, tags=["tasks"])
def update_task_user_fields(
    moodle_id: str,
    body: TaskUpdateIn,
    user: CurrentUser = Depends(get_current_user),
    store: TaskStore = Depends(get_store),
):
    """Update user notes or resolve conflicts on a task (US 3.3.3)."""
    updates = body.model_dump(exclude_unset=True)
    updated = store.update_user_task(user.id, moodle_id, updates)
    if not updated:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Task {moodle_id} not found")
    return updated


@app.get("/api/tasks", response_model=list[TaskOut], tags=["tasks"])
def list_tasks(
    response: Response,
    include_filtered: bool = Query(False, description="Also return items Gemini marked as not relevant"),
    user: CurrentUser = Depends(get_current_user),
    store: TaskStore = Depends(get_store),
):
    """Called by the dashboard. Returns the student's tasks, soonest deadline first."""
    response.headers["Cache-Control"] = "private, max-age=5, stale-while-revalidate=15"
    try:
        return store.list_tasks(user.id, include_filtered)
    except Exception as exc:
        log_sync_error(log, "list_tasks", user.id, exc)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Could not read tasks from the database")


@app.get("/api/dashboard/summary", tags=["dashboard"])
@app.get("/api/tasks/summary", tags=["dashboard"])
def get_dashboard_summary(
    response: Response,
    user: CurrentUser = Depends(get_current_user),
    store: TaskStore = Depends(get_store),
):
    """Single request summary endpoint optimizing dashboard load to < 3s (US 4.1.2 AB#20)."""
    response.headers["Cache-Control"] = "private, max-age=5, stale-while-revalidate=15"
    try:
        tasks = store.list_tasks(user.id, include_filtered=False)
    except Exception as exc:
        log_sync_error(log, "dashboard_summary", user.id, exc)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Could not load dashboard data")

    now = datetime.now(timezone.utc)
    courses = {t.course_name for t in tasks if t.course_name}
    conflicts = [t for t in tasks if t.conflict_detected]
    recently_modified = [t for t in tasks if t.is_modified]

    overdue = [t for t in tasks if t.due_date and t.due_date < now]
    upcoming = [t for t in tasks if t.due_date and t.due_date >= now]
    urgent = [t for t in tasks if (t.ai_priority and t.ai_priority >= 4) or (t.due_date and 0 <= (t.due_date - now).total_seconds() <= 172800)]

    return {
        "status": "ok",
        "timestamp": now.isoformat(),
        "total_tasks": len(tasks),
        "courses_count": len(courses),
        "conflicts_count": len(conflicts),
        "recently_modified_count": len(recently_modified),
        "overdue_count": len(overdue),
        "urgent_count": len(urgent),
        "upcoming_tasks": upcoming[:5],
        "conflicted_tasks": conflicts,
    }
