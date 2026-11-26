"""Counts for the dashboard's summary widgets (User Story 4.1.3, AB#21).

The widgets show three numbers: overdue, due today, due this week. They are computed from
the same list the dashboard shows (relevant tasks, via store.list_tasks), so the numbers
always match the task list, and they change after every sync because every request reads
the current data.

The rules (one place, so the backend, the tests and the docs agree). All windows are measured
from the moment of the request, not from calendar days:
- Only tasks that are open count: a task marked "done" is in no widget.
- No due date: in no widget. Either the lecturer set no time or it is an old task.
- overdue:        the deadline has passed (due < now), from the very second it passes.
- due_today:      the deadline is within the next 24 hours (now <= due < now + 24h).
- due_this_week:  the deadline is within the next 7 days (now <= due < now + 7 days), so
                  at 09:00 on Wednesday it covers up to 09:00 the next Wednesday. It
                  includes the tasks of due_today.
"""
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field

from .models import LOCAL_TIMEZONE, TaskOut

WEEK_DAYS = 7


class TaskSummary(BaseModel):
    overdue: int = Field(..., description="Open tasks whose deadline has passed")
    due_today: int = Field(..., description="Open tasks due within the next 24 hours")
    due_this_week: int = Field(..., description="Open tasks due within the next 7 days (the 24-hour ones included)")
    as_of: datetime = Field(..., description="The moment the counts were computed")


def summarize(tasks: list[TaskOut], now: datetime | None = None) -> TaskSummary:
    """Count `tasks` for the three widgets. `now` is injectable so tests don't depend on the clock."""
    now = (now or datetime.now(LOCAL_TIMEZONE)).astimezone(LOCAL_TIMEZONE)
    # Absolute time (UTC arithmetic), so a daylight-saving change cannot shift the window by an hour.
    now_utc = now.astimezone(timezone.utc)
    today_end = now_utc + timedelta(hours=24)
    week_end = now_utc + timedelta(days=WEEK_DAYS)

    overdue = due_today = due_this_week = 0
    for task in tasks:
        if task.status != "open" or task.due_date is None:
            continue
        due = task.due_date
        if due.tzinfo is None:  # stores return aware datetimes; be safe anyway
            due = due.replace(tzinfo=LOCAL_TIMEZONE)
        if due < now_utc:
            overdue += 1
        elif due < today_end:
            due_today += 1
            due_this_week += 1
        elif due < week_end:
            due_this_week += 1
    return TaskSummary(overdue=overdue, due_today=due_today, due_this_week=due_this_week, as_of=now)
