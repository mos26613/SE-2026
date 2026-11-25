"""Remove personal data from text before it is sent to the AI (ADR 0003, Feature 5.2).

How it works:
  1. An `Anonymizer` runs a list of *redactors* over the text. Each redactor finds one
     kind of personal data (ID numbers, names, emails...) and returns where it is.
  2. Every value found is replaced with a placeholder such as `[ID_1]`. The same value
     always gets the same placeholder, so the AI can still see that two mentions match.
  3. The Anonymizer remembers which placeholder stands for which value, so `restore()`
     can put the real values back into the AI's answer on our server.

Use one Anonymizer per AI request, so that all the texts in the request share the same
placeholders:

    anon = Anonymizer()
    safe_title = anon.anonymize(task.title)      # "Appeal for [ID_1]"
    ...send safe text to Gemini...
    summary = anon.restore(ai_answer)            # "Appeal for 123456782"

Adding a new kind of personal data (e.g. User Story 5.2.2, names and emails): write a
class with a `label` and a `find(text)` method (see `Redactor`) and add it to
`DEFAULT_REDACTORS`. Nothing else needs to change.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional, Protocol

Span = tuple[int, int]  # (start, end) of a match, like re.Match.span()


class AnonymizationError(RuntimeError):
    """Anonymization could not be completed, so the text must NOT be sent to the AI."""


class Redactor(Protocol):
    """One kind of personal data.

    label:      used in the placeholder, e.g. "ID" -> "[ID_1]". Letters only.
    find(text): where this kind of data appears in the text.
    key(value): what counts as "the same value" (e.g. ignore a dash in an ID number).
    """

    label: str

    def find(self, text: str) -> Iterable[Span]: ...

    def key(self, value: str) -> str: ...


# ---------------------------------------------------------------------------
# User Story 5.2.1: Israeli ID numbers (Teudat Zehut)
# ---------------------------------------------------------------------------


def is_valid_israeli_id(value: str) -> bool:
    """Check an Israeli ID number with its check digit (the official algorithm).

    Digits are multiplied alternately by 1 and 2. When a product has two digits its
    digits are added (14 -> 1 + 4 = 5). The ID is valid if the total divides by 10.
    Accepts 9 digits, optionally written as 12345678-9, 123 456 789 or 123-456-789.
    """
    digits = value.replace("-", "").replace(" ", "")
    if len(digits) != 9 or not digits.isdigit():
        return False
    total = 0
    for i, ch in enumerate(digits):
        product = int(ch) * (1 if i % 2 == 0 else 2)
        total += product - 9 if product > 9 else product
    return total % 10 == 0


class IsraeliIdRedactor:
    """Finds valid Israeli ID numbers written as 123456782, 12345678-2, 123 456 782 or 123-456-782.

    Only standalone numbers count: digits that are part of a longer number (a phone
    number, a timestamp, another ID) are left alone, and so are numbers whose check
    digit is wrong. Shorter numbers padded with zeros (old 8-digit IDs) are not matched
    on purpose: about 1 in 10 random numbers would pass the check, so grades and course
    codes would be masked. Groups of three must use the same separator throughout, so
    phone numbers such as 050 123 4567 or 052-123-4567 are not matched either.
    """

    label = "ID"

    # Not preceded by a digit (or "digit-"), not followed by a digit (or "-digit").
    _pattern = re.compile(r"(?<!\d)(?<!\d-)(?:\d{9}|\d{8}-\d)(?!-?\d)")
    # 123 456 782 or 123-456-782: three groups of three with the same separator, and no
    # digit group directly before or after (so it is not part of a longer number).
    _grouped = re.compile(r"(?<!\d)(?<!\d[ -])\d{3}([ -])\d{3}\1\d{3}(?![ -]?\d)")

    def find(self, text: str) -> Iterable[Span]:
        for pattern in (self._pattern, self._grouped):
            for match in pattern.finditer(text):
                if is_valid_israeli_id(match.group()):
                    yield match.span()

    def key(self, value: str) -> str:
        return value.replace("-", "").replace(" ", "")


# Order matters only when two kinds could overlap; earlier redactors win.
# User Story 5.2.2 adds its name and email redactors here.
DEFAULT_REDACTORS: list[Redactor] = [IsraeliIdRedactor()]


class Anonymizer:
    """Replaces personal data with placeholders and can put it back afterwards."""

    def __init__(self, redactors: Optional[Iterable[Redactor]] = None):
        self.redactors: list[Redactor] = list(DEFAULT_REDACTORS if redactors is None else redactors)
        self._placeholder_for: dict[tuple[str, str], str] = {}  # (label, key) -> "[ID_1]"
        self._original_for: dict[str, str] = {}  # "[ID_1]" -> the value as first written
        self._counts: dict[str, int] = {}

    @property
    def mapping(self) -> dict[str, str]:
        """Placeholder -> original value. Never send this to the AI."""
        return dict(self._original_for)

    def _placeholder(self, redactor: Redactor, value: str) -> str:
        lookup = (redactor.label, redactor.key(value))
        if lookup not in self._placeholder_for:
            self._counts[redactor.label] = self._counts.get(redactor.label, 0) + 1
            placeholder = f"[{redactor.label}_{self._counts[redactor.label]}]"
            self._placeholder_for[lookup] = placeholder
            self._original_for[placeholder] = value
        return self._placeholder_for[lookup]

    def anonymize(self, text: Optional[str]) -> Optional[str]:
        """Return the text with all personal data replaced. None and "" pass through.

        Raises AnonymizationError if any redactor fails, so the caller can refuse to
        send the text instead of sending it half-cleaned.
        """
        if not text:
            return text
        for redactor in self.redactors:
            try:
                spans = sorted(redactor.find(text))
            except Exception as e:  # a bug in one redactor must never leak data
                raise AnonymizationError(f"{type(redactor).__name__} failed: {e}") from e
            # Number placeholders in reading order, then replace from the end so
            # earlier positions stay correct.
            replacements = [(start, end, self._placeholder(redactor, text[start:end])) for start, end in spans]
            for start, end, placeholder in reversed(replacements):
                text = text[:start] + placeholder + text[end:]
        return text

    def restore(self, text: Optional[str]) -> Optional[str]:
        """Put the original values back in place of any placeholders in the text."""
        if not text or not self._original_for:
            return text
        pattern = re.compile("|".join(re.escape(p) for p in self._original_for))
        return pattern.sub(lambda m: self._original_for[m.group()], text)
