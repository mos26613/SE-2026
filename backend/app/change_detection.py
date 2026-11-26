"""Did the assignment change on Moodle since we last saved it? (US 3.3.1)

Every sync sends all the assignments the extension found. Most of them are exactly what
we already have. This module compares each incoming task with the stored one, so the
sync can:
  - flag the tasks whose details changed (tasks.is_modified, the "Recently Modified" badge),
  - skip the ones that did not change, instead of rewriting them in the database.

What counts as a change: the title, the description or the due date.
The comparison ignores differences that are only formatting:
  - extra spaces or line breaks in the text ("Exam 1" == "Exam   1\\n"),
  - the same moment written in two time zones ("10:00+02:00" == "08:00Z").
A date without a time zone is read as Israel time, like everywhere else in the API.

An empty description means "unknown", not "the lecturer deleted it":
  the extension reads the calendar page (no description) and the assignment page (with the
  instructions), so the same task arrives both ways. An empty incoming description is never
  compared and never replaces a saved one. A description that appears for a task that had
  none is filled in quietly, without the "modified" flag.

Details that are not part of the badge (the Moodle link, the course) are kept up to date
quietly too: a change is saved, but the task is not flagged. A missing value is ignored.
"""
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from .models import LOCAL_TIMEZONE

# The fields that make a task "modified" when they differ.
COMPARED_FIELDS = ("title", "description", "due_date")

# Fields that are refreshed without flagging the task. Only compared when the sync sends a value.
DETAIL_FIELDS = ("moodle_url", "moodle_course_id", "course_name")

_WHITESPACE = re.compile(r"\s+")


def _normalize_text(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = _WHITESPACE.sub(" ", value).strip()
    return cleaned or None


def _normalize_date(value: Any) -> Optional[datetime]:
    """Turn a date (ISO text from the database, or a datetime) into one comparable moment, in UTC."""
    if value is None or value == "":
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=LOCAL_TIMEZONE)
    return value.astimezone(timezone.utc)


def _normalized(row: dict, field_name: str):
    if field_name == "due_date":
        return _normalize_date(row.get(field_name))
    return _normalize_text(row.get(field_name))


def _description_changed(stored: dict, incoming: dict) -> bool:
    new = _normalize_text(incoming.get("description"))
    old = _normalize_text(stored.get("description"))
    if new is None or old is None:
        return False  # unknown on one side: nothing to compare (a first description is only filled in)
    return new != old


def changed_fields(stored: dict, incoming: dict) -> list[str]:
    """The names of the fields that really changed on Moodle (this is what flags the task)."""
    changed = []
    for name in COMPARED_FIELDS:
        if name == "description":
            if _description_changed(stored, incoming):
                changed.append(name)
        elif _normalized(stored, name) != _normalized(incoming, name):
            changed.append(name)
    return changed


def refreshed_fields(stored: dict, incoming: dict) -> list[str]:
    """Fields to save quietly, without flagging the task: a first description, a new link or course."""
    refreshed = []
    if _normalize_text(incoming.get("description")) is not None and _normalize_text(stored.get("description")) is None:
        refreshed.append("description")
    for name in DETAIL_FIELDS:
        value = incoming.get(name)
        if value is None or value == "":
            continue  # not sent: keep what we have
        if value != stored.get(name):
            refreshed.append(name)
    return refreshed


@dataclass
class SyncDiff:
    """How the incoming tasks of one sync relate to what is already stored."""

    new: list[str] = field(default_factory=list)  # moodle_ids we have never saved
    modified: list[str] = field(default_factory=list)  # saved before, and the details changed
    unchanged: list[str] = field(default_factory=list)  # saved before, identical
    refresh: list[str] = field(default_factory=list)  # unchanged, but a link/course/first description needs saving


def compare_with_stored(stored: dict[str, dict], incoming: list[dict]) -> SyncDiff:
    """Compare a whole batch with one dictionary lookup per task (no database call per task).

    `stored` maps moodle_id -> the stored row, `incoming` is the list of rows about to be saved.
    """
    diff = SyncDiff()
    for row in incoming:
        moodle_id = row["moodle_id"]
        old = stored.get(moodle_id)
        if old is None:
            diff.new.append(moodle_id)
        elif changed_fields(old, row):
            diff.modified.append(moodle_id)
        else:
            diff.unchanged.append(moodle_id)
            if refreshed_fields(old, row):
                diff.refresh.append(moodle_id)
    return diff
