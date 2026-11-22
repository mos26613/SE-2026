"""The shape of the data going in and out of the API.

FastAPI uses these classes to check every request automatically:
anything that doesn't match (missing title, bad date, ...) is rejected with a 422 error
before our code even runs.
"""
from datetime import datetime
from typing import Literal, Optional
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, HttpUrl, field_validator

# Moodle shows deadlines in local time. A date sent without a time zone is treated as Israel time.
LOCAL_TIMEZONE = ZoneInfo("Asia/Jerusalem")


class TaskIn(BaseModel):
    """One assignment as the Chrome extension scrapes it from Moodle."""

    moodle_id: str = Field(..., min_length=1, max_length=100, description="Moodle's own ID for the assignment")
    title: str = Field(..., min_length=1, max_length=500)
    course_name: Optional[str] = Field(None, max_length=300)
    moodle_course_id: Optional[int] = Field(None, ge=0, description="Moodle's own ID for the course (links the task to the courses table)")
    description: Optional[str] = Field(None, max_length=10_000)
    due_date: Optional[datetime] = Field(None, description="ISO 8601, e.g. 2026-12-01T23:59:00+02:00")
    moodle_url: Optional[HttpUrl] = None

    @field_validator("due_date")
    @classmethod
    def _assume_local_time(cls, value: Optional[datetime]) -> Optional[datetime]:
        # Without this, "2026-12-06T10:00:00" and "2026-12-06T10:00:00+02:00" can't be
        # compared or sorted, and the database would store the first one 2 hours off (as UTC).
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=LOCAL_TIMEZONE)
        return value


class SyncRequest(BaseModel):
    tasks: list[TaskIn] = Field(..., description="All assignments the extension found in this scan")


class AIResult(BaseModel):
    """What Gemini adds to each task."""

    moodle_id: str
    is_relevant: bool = Field(..., description="False if this is not a real task for the student (e.g. an announcement)")
    category: Literal["homework", "exam", "project", "quiz", "reading", "other"] = "other"
    priority: int = Field(3, ge=1, le=5, description="1 = low, 5 = urgent/important")
    summary: str = Field("", max_length=300)


class TaskOut(BaseModel):
    """A task as stored and returned to the dashboard."""

    moodle_id: str
    title: str
    course_name: Optional[str] = None
    moodle_course_id: Optional[int] = None
    description: Optional[str] = None
    due_date: Optional[datetime] = None
    moodle_url: Optional[str] = None
    is_relevant: bool = True
    ai_category: Optional[str] = None
    ai_priority: Optional[int] = None
    ai_summary: Optional[str] = None
    status: str = "open"


class SyncResponse(BaseModel):
    received: int
    created: int
    updated: int
    filtered_out: int = Field(..., description="Tasks Gemini marked as not relevant (still saved, hidden by default)")
    ai_applied: bool = Field(..., description="False if Gemini was skipped or failed; tasks were saved anyway")
