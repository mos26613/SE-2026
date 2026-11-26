"""Remove personal data from text before it is sent to the AI (ADR 0003, Feature 5.2).

User Story 5.2.1 (AB#39): Israeli ID numbers (Teudat Zehut)
User Story 5.2.2 (AB#40): Remove names and email addresses (Hebrew & English)

How it works:
  1. An `Anonymizer` runs a list of *redactors* over the text. Each redactor finds one
     kind of personal data (ID numbers, names, emails...) and returns where it is.
  2. Every value found is replaced with a placeholder such as `[ID_1]`, `[EMAIL_1]`, `[NAME_1]`.
     The same value always gets the same placeholder, so the AI can still see that two mentions match.
  3. The Anonymizer remembers which placeholder stands for which value, so `restore()`
     can put the real values back into the AI's answer on our server.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional, Protocol, Sequence

Span = tuple[int, int]  # (start, end) of a match, like re.Match.span()


class AnonymizationError(RuntimeError):
    """Anonymization could not be completed, so the text must NOT be sent to the AI."""


class Redactor(Protocol):
    """One kind of personal data.

    label:      used in the placeholder, e.g. "ID" -> "[ID_1]".
    find(text): where this kind of data appears in the text.
    key(value): what counts as "the same value".
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
    """Finds valid Israeli ID numbers written as 123456782, 12345678-2, 123 456 782 or 123-456-782."""

    label = "ID"

    _pattern = re.compile(r"(?<!\d)(?<!\d-)(?:\d{9}|\d{8}-\d)(?!-?\d)")
    _grouped = re.compile(r"(?<!\d)(?<!\d[ -])\d{3}([ -])\d{3}\1\d{3}(?![ -]?\d)")

    def find(self, text: str) -> Iterable[Span]:
        for pattern in (self._pattern, self._grouped):
            for match in pattern.finditer(text):
                if is_valid_israeli_id(match.group()):
                    yield match.span()

    def key(self, value: str) -> str:
        return value.replace("-", "").replace(" ", "")


# ---------------------------------------------------------------------------
# User Story 5.2.2: Email addresses
# ---------------------------------------------------------------------------


class EmailRedactor:
    """Finds and masks email addresses (RFC 5322 compatible common subsets).

    Example matches:
      student@jct.ac.il, first.last@mail.huji.ac.il, user+tag@example.org
    """

    label = "EMAIL"

    _pattern = re.compile(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        re.IGNORECASE,
    )

    def find(self, text: str) -> Iterable[Span]:
        for match in self._pattern.finditer(text):
            yield match.span()

    def key(self, value: str) -> str:
        return value.strip().lower()


# ---------------------------------------------------------------------------
# User Story 5.2.2: Names (Hebrew and English)
# ---------------------------------------------------------------------------


class NameRedactor:
    """Finds and masks personal names in English and Hebrew.

    Supports:
      1. Known names passed explicitly (e.g. from student/lecturer profile).
      2. Title-prefixed names:
         - Hebrew: פרופ', פרופסור, ד"ר, דר', מר, גב', גברת, המרצה followed by name parts.
         - English: Prof., Professor, Dr., Mr., Ms., Mrs. followed by capitalized names.
      3. Typical English Full Names (Capitalized First + Capitalized Last).
      4. Hebrew Name pairs (e.g. 'משה כהן', 'שרה לוי', 'דוד ישראלי') based on pattern matching.
    """

    label = "NAME"

    # Hebrew titles (with optional prefixes like ו/ה/ב/ל/מ/ש/כ)
    _HEBREW_TITLES = r'(?:[והמכלש])?(?:פרופ(?:\'|סור)|ד(?:"|״|\')ר|מר|גב(?:\'|רת)|המרצה|המתרגל(?:ת)?|סטודנט(?:ית)?)\s+'
    # English titles
    _ENGLISH_TITLES = r'(?:Prof(?:essor)?\.?|Dr\.?|Mr\.?|Ms\.?|Mrs\.?)\s+'

    # Hebrew name word (excludes conjunctions and title prefixes)
    _HEB_NAME_WORD = r'(?!(?:ו|או|עם|של|אל|על|מול|את|כי|אם)\b|וד["\'״]|ופרופ)[\u0590-\u05fe]{2,}'

    # Title + Hebrew name (1 to 2 words)
    _heb_title_name = re.compile(
        rf"(?<![\u0590-\u05fe]){_HEBREW_TITLES}({_HEB_NAME_WORD}(?:\s+{_HEB_NAME_WORD}){{0,2}})(?![\u0590-\u05fe])",
        re.UNICODE,
    )

    # Title + English name
    _eng_title_name = re.compile(
        rf"\b{_ENGLISH_TITLES}([A-Z][a-z]+(?:\s+[A-Z][a-z]+){{0,2}})\b"
    )

    # Standalone Capitalized English full names: e.g. "John Doe", "Sarah Connor", "Moshe Cohen"
    # Negative lookbehind and lookahead to avoid matching mid-sentence acronyms
    _eng_full_name = re.compile(
        r"\b([A-Z][a-z]{1,20}\s+(?:[A-Z][a-z]{1,20}\s+)?[A-Z][a-z]{1,20})\b"
    )

    # Hebrew 2-word names following common indicator keywords or standalone
    # E.g. שם: משה כהן, שלום דוד לוי, מאת: רחל אברהם
    _heb_indicated_name = re.compile(
        rf"(?:שם(?:\s*הסטודנט|\s*המרצה|\s*המגיש)?(?:\s*:|\s+-)?\s*|מאת:\s*|מרצה:\s*|סטודנט:\s*)({_HEB_NAME_WORD}\s+{_HEB_NAME_WORD})",
        re.UNICODE,
    )

    def __init__(self, known_names: Optional[Sequence[str]] = None) -> None:
        self.known_names: list[str] = [n.strip() for n in known_names] if known_names else []

    def find(self, text: str) -> Iterable[Span]:
        found_spans: list[Span] = []

        # 1. Known names (highest priority)
        for name in self.known_names:
            if not name or len(name) < 2:
                continue
            # Escape and match word boundaries or Unicode boundaries
            pattern = re.compile(rf"(?<![a-zA-Z\u0590-\u05fe]){re.escape(name)}(?![a-zA-Z\u0590-\u05fe])", re.IGNORECASE)
            for m in pattern.finditer(text):
                found_spans.append(m.span())

        # 2. Indicated Hebrew names (e.g. שם: משה כהן)
        for m in self._heb_indicated_name.finditer(text):
            found_spans.append(m.span(1))

        # 3. Title-prefixed Hebrew names (mask the name portion or title+name)
        for m in self._heb_title_name.finditer(text):
            found_spans.append(m.span())

        # 4. Title-prefixed English names
        for m in self._eng_title_name.finditer(text):
            found_spans.append(m.span())

        # 5. Standalone English full names
        # Avoid common words that are capitalized at the start of sentences
        common_words = {
            "United States", "Smart Student", "Task Hub", "Moodle Portal", "Google Chrome",
            "Manifest V3", "Computer Science", "Information Systems", "Final Exam",
            "Spring Semester", "Fall Semester", "Academic Year", "Linear Algebra"
        }
        for m in self._eng_full_name.finditer(text):
            val = m.group(1)
            if val not in common_words:
                found_spans.append(m.span(1))

        # Filter overlapping spans (keep longest / earlier)
        sorted_spans = sorted(found_spans, key=lambda s: (s[0], -(s[1] - s[0])))
        last_end = -1
        for start, end in sorted_spans:
            if start >= last_end:
                yield (start, end)
                last_end = end

    def key(self, value: str) -> str:
        return re.sub(r"\s+", " ", value).strip().lower()


# Order: IsraeliIdRedactor, EmailRedactor, NameRedactor
DEFAULT_REDACTORS: list[Redactor] = [
    IsraeliIdRedactor(),
    EmailRedactor(),
    NameRedactor(),
]


class Anonymizer:
    """Replaces personal data with placeholders and restores it afterwards."""

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
        """Return the text with all personal data replaced. None and '' pass through."""
        if not text:
            return text
        for redactor in self.redactors:
            try:
                spans = sorted(redactor.find(text))
            except Exception as e:
                raise AnonymizationError(f"{type(redactor).__name__} failed: {e}") from e

            # Collect replacements and replace from the back so indexes don't shift
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
