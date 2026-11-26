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

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware

from . import ai_filter
from .auth import CurrentUser, get_current_user
from .change_detection import compare_with_stored
from .config import Settings, get_settings
from .db import MemoryStore, SupabaseStore, TaskStore
from .models import AIResult, SyncRequest, SyncResponse, TaskIn, TaskOut
from .routers import auth as auth_router
from .summary import TaskSummary, summarize

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("task-api")

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


@app.post("/api/tasks/sync", response_model=SyncResponse, tags=["tasks"])
def sync_tasks(
    body: SyncRequest,
    user: CurrentUser = Depends(get_current_user),
    store: TaskStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
):
    """Called by the Chrome extension with every assignment it found on Moodle."""
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
    except Exception:
        log.exception("Reading saved tasks failed")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Could not read saved tasks from the database")

    ai_results = ai_filter.classify_tasks(unique, settings)
    rows = [_to_row(t, ai_results.get(t.moodle_id)) for t in unique]

    # Which tasks are new, which changed on Moodle, and which came back identical (US 3.3.1).
    diff = compare_with_stored(stored, rows)
    new_ids, modified_ids, refresh_ids = set(diff.new), set(diff.modified), set(diff.refresh)

    to_save = []
    for row in rows:
        moodle_id = row["moodle_id"]
        if moodle_id in modified_ids:
            to_save.append({**row, "is_modified": True})  # the "Recently Modified" flag
        elif moodle_id in new_ids:
            to_save.append(row)
        elif moodle_id in refresh_ids:
            # Identical on Moodle, but a link, the course or a first description has to be saved.
            # Not flagged: nothing changed that the student needs to be told about.
            to_save.append(row)
        elif "ai_category" in row and stored[moodle_id].get("ai_category") is None:
            # Identical on Moodle, but the AI has not looked at it before: save only to add its verdict.
            to_save.append(row)
        # Otherwise the task is identical to what we have: no database write.

    try:
        store.upsert(user.id, to_save)
    except Exception:
        log.exception("Saving tasks failed")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Could not save tasks to the database")

    return SyncResponse(
        received=len(body.tasks),
        created=len(diff.new),
        updated=len(diff.modified),
        unchanged=len(diff.unchanged),
        filtered_out=sum(1 for r in ai_results.values() if not r.is_relevant),
        ai_applied=bool(ai_results),
    )


@app.get("/api/tasks", response_model=list[TaskOut], tags=["tasks"])
def list_tasks(
    include_filtered: bool = Query(False, description="Also return items Gemini marked as not relevant"),
    user: CurrentUser = Depends(get_current_user),
    store: TaskStore = Depends(get_store),
):
    """Called by the dashboard. Returns the student's tasks, soonest deadline first."""
    try:
        return store.list_tasks(user.id, include_filtered)
    except Exception:
        log.exception("Reading tasks failed")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Could not read tasks from the database")


# Declared after GET /api/tasks but with a longer path, so the two never clash.
@app.get("/api/tasks/summary", response_model=TaskSummary, tags=["tasks"])
def tasks_summary(
    user: CurrentUser = Depends(get_current_user),
    store: TaskStore = Depends(get_store),
):
    """Called by the dashboard's summary widgets: how many tasks are overdue, due today, due this week.

    Counted from the same tasks as GET /api/tasks (filtered-out items are not counted),
    so the widgets always agree with the list.
    """
    try:
        tasks = store.list_tasks(user.id, include_filtered=False)
    except Exception:
        log.exception("Reading tasks for the summary failed")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Could not read tasks from the database")
    return summarize(tasks)
