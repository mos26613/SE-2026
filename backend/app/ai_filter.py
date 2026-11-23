"""The AI step: send the scraped tasks to Gemini and get back a verdict for each one.

Gemini decides whether each item is a real task for the student, sorts it into a
category, rates its priority and writes a one-line summary.

Privacy rule (ADR 0003): personal data such as ID numbers is replaced with
placeholders before anything is sent, and put back in Gemini's answer here on the
server. If anonymization fails, Gemini is not called at all.

Design rule: the AI never blocks saving. If there is no key, Gemini is down,
or it answers with something we can't parse, we return an empty result and the
tasks are saved without AI fields.
"""
import json
import logging
import time

from pydantic import TypeAdapter, ValidationError

from .anonymizer import Anonymizer
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

# Errors that usually mean "Google is busy right now" and are worth one more try.
_TRANSIENT_MARKERS = ("500", "503", "504", "DEADLINE_EXCEEDED", "UNAVAILABLE", "INTERNAL")
RETRY_DELAY_SECONDS = 2.0


def _is_transient(error: Exception) -> bool:
    text = str(error)
    return any(marker in text for marker in _TRANSIENT_MARKERS)


def _task_for_prompt(task: TaskIn, anon: Anonymizer) -> dict:
    # moodle_id is Moodle's own number, not personal data, and we need it unchanged to
    # match Gemini's answers back to the tasks. Every free-text field is anonymized.
    return {
        "moodle_id": task.moodle_id,
        "title": anon.anonymize(task.title),
        "course_name": anon.anonymize(task.course_name),
        "description": anon.anonymize((task.description or "")[:1500]),  # keep the prompt small
        "due_date": task.due_date.isoformat() if task.due_date else None,
    }


def classify_tasks(tasks: list[TaskIn], settings: Settings) -> dict[str, AIResult]:
    """Return {moodle_id: AIResult}. Empty dict means the AI step was skipped or failed."""
    if not tasks or not settings.gemini_api_key:
        return {}

    # Anonymize first, outside the Gemini error handling: if this fails we must not
    # send anything, and the tasks are still saved without AI fields.
    anon = Anonymizer()
    try:
        contents = json.dumps([_task_for_prompt(t, anon) for t in tasks], ensure_ascii=False)
    except Exception as e:  # AnonymizationError, or any other bug while building the prompt
        log.error("Anonymization failed, not calling Gemini: %s", e)
        return {}

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(
            api_key=settings.gemini_api_key,
            http_options=types.HttpOptions(timeout=int(settings.gemini_timeout_seconds * 1000)),
        )
        def call(thinking_level: str):
            config = types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                temperature=0.1,
            )
            if thinking_level:
                config.thinking_config = types.ThinkingConfig(thinking_level=thinking_level.upper())
            return client.models.generate_content(model=settings.gemini_model, contents=contents, config=config)

        def call_with_fallback():
            try:
                return call(settings.gemini_thinking_level)
            except Exception as e:
                # Some models don't accept a thinking level; retry once with the model's default.
                if settings.gemini_thinking_level and "thinking" in str(e).lower():
                    log.info("Model rejected thinking level, retrying without it")
                    return call("")
                raise

        try:
            response = call_with_fallback()
        except Exception as e:
            if not _is_transient(e):
                raise
            # Google was busy or slow; wait a moment and try once more.
            log.info("Gemini busy (%s), retrying once in %.0fs", str(e)[:60], RETRY_DELAY_SECONDS)
            time.sleep(RETRY_DELAY_SECONDS)
            response = call_with_fallback()
        results = _results_adapter.validate_json(response.text or "[]")
    except ValidationError as e:
        log.warning("Gemini returned data in an unexpected shape: %s", e)
        return {}
    except Exception as e:  # network error, bad key, quota, timeout...
        log.warning("Gemini call failed, saving tasks without AI fields: %s", e)
        return {}

    known_ids = {t.moodle_id for t in tasks}
    return {
        r.moodle_id: r.model_copy(update={"summary": anon.restore(r.summary)})
        for r in results
        if r.moodle_id in known_ids
    }
