"""Mandatory PII anonymization middleware for AI Gateway requests (AB#41)."""
import re

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d{1,3}[\s-]?)?(?:\(?\d{2,3}\)?[\s-]?)?\d{3}[\s-]?\d{4}(?!\w)")
_ID_NUMBER_RE = re.compile(r"(?<!\d)\d{9}(?!\d)")


class AnonymizationError(Exception):
    """Raised when mandatory PII anonymization cannot be completed safely."""


def anonymize_text(text: str) -> str:
    """Redact common PII patterns from outgoing AI text."""
    if not isinstance(text, str):
        raise AnonymizationError("Input text must be a string.")

    cleaned = _EMAIL_RE.sub("[REDACTED_EMAIL]", text)
    cleaned = _PHONE_RE.sub("[REDACTED_PHONE]", cleaned)
    cleaned = _ID_NUMBER_RE.sub("[REDACTED_ID]", cleaned)
    return cleaned


def apply_mandatory_anonymization(*, prompt: str, system_instruction: str) -> tuple[str, str]:
    """Enforce anonymization on both system instruction and prompt; block on any failure."""
    try:
        safe_system = anonymize_text(system_instruction)
        safe_prompt = anonymize_text(prompt)
    except AnonymizationError:
        raise
    except Exception as exc:
        raise AnonymizationError("Anonymization middleware failed.") from exc

    return safe_prompt, safe_system