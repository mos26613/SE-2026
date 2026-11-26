"""Did the assignment change on Moodle since we last saved it? (US 3.3.1)

Every sync sends all the assignments the extension found. Most of them are exactly what
we already have. This module compares each incoming task with the stored one, so the
sync can:
  - flag the tasks whose details changed (tasks.is_modified, the "Recently Modified" badge),
  - skip the ones that did not change, instead of rewriting them in the database.

What counts as a change: the title, the description or the due date.
The comparison ignores differences that are only formatting:
  - extra spaces or line breaks in the text ("Exam 1" == "Exam   1\\n"),
  - an empty description and no description are the same,
  - the same moment written in two time zones ("10:00+02:00" == "08:00Z").
A date without a time zone is read as Israel time, like everywhere else in the API.
"""
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from .models import LOCAL_TIMEZONE

# The fields that make a task "modified" when they differ.
COMPARED_FIELDS = ("title", "description", "due_date")

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


def changed_fields(stored: dict, incoming: dict) -> list[str]:
    """The names of the fields that differ between the stored task and the incoming one."""
    return [f for f in COMPARED_FIELDS if _normalized(stored, f) != _normalized(incoming, f)]


@dataclass
class SyncDiff:
    """How the incoming tasks of one sync relate to what is already stored."""

    new: list[str] = field(default_factory=list)  # moodle_ids we have never saved
    modified: list[str] = field(default_factory=list)  # saved before, and the details changed
    unchanged: list[str] = field(default_factory=list)  # saved before, identical


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
    return diff
