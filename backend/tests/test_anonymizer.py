"""Tests for removing personal data before the AI (User Story 5.2.1, ADR 0003).

Acceptance criterion: valid Israeli ID numbers are always replaced with placeholders.

The ID numbers below are made up; they only pass the check-digit test.
"""
import pytest

from app.anonymizer import AnonymizationError, Anonymizer, IsraeliIdRedactor, is_valid_israeli_id

VALID_ID = "123456782"
OTHER_VALID_ID = "039337423"
INVALID_ID = "123456789"  # wrong check digit


@pytest.mark.parametrize("value", ["123456782", "039337423", "000000018", "12345678-2"])
def test_check_digit_accepts_valid_ids(value):
    assert is_valid_israeli_id(value)


@pytest.mark.parametrize("value", ["123456789", "12345678", "1234567890", "12345678-9", "abcdefghi", ""])
def test_check_digit_rejects_invalid_ids(value):
    assert not is_valid_israeli_id(value)


@pytest.mark.parametrize(
    "text, expected",
    [
        (f"My ID is {VALID_ID}.", "My ID is [ID_1]."),
        (f"ת.ז. {VALID_ID} - ערעור על ציון", "ת.ז. [ID_1] - ערעור על ציון"),
        (f"ת\"ז:{VALID_ID}", "ת\"ז:[ID_1]"),
        ("ID 12345678-2 please", "ID [ID_1] please"),
        (f"({VALID_ID})", "([ID_1])"),
        (f"{VALID_ID}\n{OTHER_VALID_ID}", "[ID_1]\n[ID_2]"),
        (f"student_{VALID_ID}_hw3.pdf", "student_[ID_1]_hw3.pdf"),
    ],
)
def test_valid_ids_are_replaced(text, expected):
    assert Anonymizer().anonymize(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        f"Reference {INVALID_ID}",  # 9 digits but the check digit is wrong
        f"Phone +972{VALID_ID}",  # part of a longer number
        f"Order 1{VALID_ID}",
        f"{VALID_ID}0 bytes",
        "Course 20417, grade 95, room 1234",  # short numbers are never touched
        "Due 2026-12-01T23:59:00+02:00",
        "",
    ],
)
def test_other_numbers_are_left_alone(text):
    assert Anonymizer().anonymize(text) == text


def test_none_passes_through():
    assert Anonymizer().anonymize(None) is None


def test_same_id_gets_same_placeholder_across_texts():
    anon = Anonymizer()
    assert anon.anonymize(f"{VALID_ID} and {OTHER_VALID_ID}") == "[ID_1] and [ID_2]"
    # Another field in the same request, and the dashed spelling of the same ID.
    assert anon.anonymize("again 12345678-2") == "again [ID_1]"
    assert anon.mapping == {"[ID_1]": VALID_ID, "[ID_2]": OTHER_VALID_ID}


def test_restore_round_trip():
    anon = Anonymizer()
    original = f"Appeal for student {VALID_ID} (also {OTHER_VALID_ID}), regarding {VALID_ID}"
    safe = anon.anonymize(original)
    assert VALID_ID not in safe and OTHER_VALID_ID not in safe
    assert anon.restore(safe) == original


def test_restore_without_placeholders_changes_nothing():
    anon = Anonymizer()
    assert anon.restore("Study for the exam") == "Study for the exam"
    anon.anonymize(VALID_ID)
    assert anon.restore("Nothing to restore [ID_9]") == "Nothing to restore [ID_9]"
    assert anon.restore(None) is None


def test_many_ids_get_distinct_placeholders():
    ids = [f"{n:08d}" for n in range(1, 12)]
    ids = [i + next(str(d) for d in range(10) if is_valid_israeli_id(i + str(d))) for i in ids]
    anon = Anonymizer()
    safe = anon.anonymize(" ".join(ids))
    assert safe == " ".join(f"[ID_{n}]" for n in range(1, 12))
    assert anon.restore(safe) == " ".join(ids)  # [ID_1] must not eat the start of [ID_10]


def test_extra_redactors_plug_in():
    """How User Story 5.2.2 adds names and emails: a class with label, find and key."""

    class FakeEmailRedactor:
        label = "EMAIL"

        def find(self, text):
            start = text.find("dana@example.com")
            return [] if start < 0 else [(start, start + len("dana@example.com"))]

        def key(self, value):
            return value.lower()

    anon = Anonymizer([IsraeliIdRedactor(), FakeEmailRedactor()])
    safe = anon.anonymize(f"dana@example.com, ID {VALID_ID}")
    assert safe == "[EMAIL_1], ID [ID_1]"
    assert anon.restore(safe) == f"dana@example.com, ID {VALID_ID}"


def test_a_failing_redactor_raises_instead_of_leaking():
    class BrokenRedactor:
        label = "NAME"

        def find(self, text):
            raise ValueError("model not loaded")

        def key(self, value):
            return value

    with pytest.raises(AnonymizationError):
        Anonymizer([IsraeliIdRedactor(), BrokenRedactor()]).anonymize(f"ID {VALID_ID}")
