"""Smart Student Task Hub API.

Flow for every sync:
  Chrome extension --POST /api/tasks/sync--> validate (models.py)
                                           -> Gemini filter (ai_filter.py)
                                           -> save to Supabase (db.py)
  React dashboard  --GET /api/tasks------> read from Supabase

Run locally:   python -m uvicorn app.main:app --reload
Then open:     http://localhost:8000/docs
"""
import logging

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware

from . import ai_filter
from .auth import CurrentUser, get_current_user
from .config import Settings, get_settings
from .db import MemoryStore, SupabaseStore, TaskStore
from .models import AIResult, SyncRequest, SyncResponse, TaskIn, TaskOut

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

# One shared in-memory store for dev mode.
_memory_store = MemoryStore()


def get_store(
    user: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> TaskStore:
    if settings.dev_mode:
        return _memory_store
    return SupabaseStore(settings, user.access_token)


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

    ai_results = ai_filter.classify_tasks(unique, settings)
    rows = [_to_row(t, ai_results.get(t.moodle_id)) for t in unique]

    try:
        already_there = store.existing_ids(user.id, [t.moodle_id for t in unique])
        store.upsert(user.id, rows)
    except Exception:
        log.exception("Saving tasks failed")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Could not save tasks to the database")

    return SyncResponse(
        received=len(body.tasks),
        created=len(unique) - len(already_there),
        updated=len(already_there),
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
