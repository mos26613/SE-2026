"""The AI step: send the scraped tasks to the AI Gateway and get back a verdict for each one."""
import json
import logging

from pydantic import TypeAdapter, ValidationError

from . import ai_gateway
from .config import Settings
from .models import AIResult, TaskIn

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You help university students organize their Moodle assignments.
You get a JSON list of items scraped from Moodle. For EACH item return an object with:
- moodle_id: copied exactly from the input
- is_relevant: true if it is something the student must do or prepare for
  (assignment, exam, quiz, project, required reading); false for announcements,
  forum posts, general course info, or duplicates of another item in the list
- category: one of homework, exam, project, quiz, reading, other
- priority: 1 (low) to 5 (urgent), based on how soon it is due and how important it sounds
  (exams and final projects are usually 4-5)
- summary: one short sentence describing what to do, in the same language as the title
Items may be in Hebrew or English. Return ONLY a JSON array, one object per input item."""

_results_adapter = TypeAdapter(list[AIResult])


def _task_for_prompt(task: TaskIn) -> dict:
    return {
        "moodle_id": task.moodle_id,
        "title": task.title,
        "course_name": task.course_name,
        "description": (task.description or "")[:1500],
        "due_date": task.due_date.isoformat() if task.due_date else None,
    }


def classify_tasks(tasks: list[TaskIn], settings: Settings) -> dict[str, AIResult]:
    """Return {moodle_id: AIResult}. Empty dict means the AI step was skipped or failed."""
    if not tasks or not settings.gemini_api_key:
        return {}

    try:
        contents = json.dumps([_task_for_prompt(t) for t in tasks], ensure_ascii=False)
        raw_text = ai_gateway.generate_text(
            prompt=contents,
            system_instruction=SYSTEM_PROMPT,
            settings=settings,
        )
        results = _results_adapter.validate_json(raw_text or "[]")
    except ValidationError as e:
        log.warning("Gemini returned data in an unexpected shape: %s", e)
        return {}
    except Exception as e:
        log.warning("Gemini call failed, saving tasks without AI fields: %s", e)
        return {}

    known_ids = {t.moodle_id for t in tasks}
    return {r.moodle_id: r for r in results if r.moodle_id in known_ids}
