"""Centralized AI Gateway for Gemini calls in the backend."""
import logging
import time

from .config import Settings

log = logging.getLogger(__name__)

# Errors that usually mean "Google is busy right now" and are worth one more try.
_TRANSIENT_MARKERS = ("500", "503", "504", "DEADLINE_EXCEEDED", "UNAVAILABLE", "INTERNAL")
RETRY_DELAY_SECONDS = 2.0


def _is_transient(error: Exception) -> bool:
    text = str(error)
    return any(marker in text for marker in _TRANSIENT_MARKERS)


def generate_text(
    *,
    prompt: str,
    system_instruction: str,
    settings: Settings,
    response_mime_type: str = "application/json",
    temperature: float = 0.1,
) -> str:
    """Send a prompt through the single Gemini client entry point and return raw text."""
    if not settings.gemini_api_key:
        return ""

    from google import genai
    from google.genai import types

    client = genai.Client(
        api_key=settings.gemini_api_key,
        http_options=types.HttpOptions(timeout=int(settings.gemini_timeout_seconds * 1000)),
    )

    def call(thinking_level: str):
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type=response_mime_type,
            temperature=temperature,
        )
        if thinking_level:
            config.thinking_config = types.ThinkingConfig(thinking_level=thinking_level.upper())
        return client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=config,
        )

    def call_with_fallback():
        try:
            return call(settings.gemini_thinking_level)
        except Exception as e:
            if settings.gemini_thinking_level and "thinking" in str(e).lower():
                log.info("Model rejected thinking level, retrying without it")
                return call("")
            raise

    try:
        response = call_with_fallback()
    except Exception as e:
        if not _is_transient(e):
            raise
        log.info("Gemini busy (%s), retrying once in %.0fs", str(e)[:60], RETRY_DELAY_SECONDS)
        time.sleep(RETRY_DELAY_SECONDS)
        response = call_with_fallback()

    return response.text or ""
