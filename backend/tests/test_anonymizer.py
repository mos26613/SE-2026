"""Unit tests for PII Anonymizer (US 5.2.1 AB#39, US 5.2.2 AB#40).

Tests:
  - Masking Israeli ID numbers (Teudat Zehut)
  - Masking email addresses (Hebrew & English contexts)
  - Masking names (Hebrew & English with titles and context)
  - Mixed-language texts with IDs, emails, and names
  - Round-trip restoration
"""
import pytest
from app.anonymizer import (
    Anonymizer,
    EmailRedactor,
    IsraeliIdRedactor,
    NameRedactor,
    is_valid_israeli_id,
)


def test_israeli_id_validation():
    # Valid Israeli IDs
    assert is_valid_israeli_id("123456782")
    assert is_valid_israeli_id("12345678-2")
    assert is_valid_israeli_id("123 456 782")
    assert is_valid_israeli_id("123-456-782")

    # Invalid IDs
    assert not is_valid_israeli_id("123456789")  # wrong checksum
    assert not is_valid_israeli_id("12345")      # too short
    assert not is_valid_israeli_id("abcdefghi")  # non-digits


def test_mask_israeli_id():
    anon = Anonymizer(redactors=[IsraeliIdRedactor()])
    text = "סטודנט ת.ז. 123456782 הגיש ערעור."
    anonymized = anon.anonymize(text)
    assert "123456782" not in anonymized
    assert "[ID_1]" in anonymized

    # Restore roundtrip
    restored = anon.restore(anonymized)
    assert restored == text


def test_mask_emails():
    anon = Anonymizer(redactors=[EmailRedactor()])
    text = "Please contact support@example.com or student.name@mail.jct.ac.il for details."
    anonymized = anon.anonymize(text)

    assert "support@example.com" not in anonymized
    assert "student.name@mail.jct.ac.il" not in anonymized
    assert "[EMAIL_1]" in anonymized
    assert "[EMAIL_2]" in anonymized

    # Same email gets same placeholder
    text_repeated = "Email me at user@test.com, again user@test.com"
    anon2 = Anonymizer(redactors=[EmailRedactor()])
    anon_repeated = anon2.anonymize(text_repeated)
    assert anon_repeated.count("[EMAIL_1]") == 2

    # Restore
    restored = anon.restore(anonymized)
    assert restored == text


def test_mask_english_names():
    anon = Anonymizer(redactors=[NameRedactor(known_names=["John Doe", "Sarah Connor"])])
    text = "Grade appeal submitted by John Doe to Prof. Alan Turing and Dr. Jane Smith."
    anonymized = anon.anonymize(text)

    assert "John Doe" not in anonymized
    assert "Jane Smith" not in anonymized
    assert "[NAME_" in anonymized

    restored = anon.restore(anonymized)
    assert restored == text


def test_mask_hebrew_names():
    anon = Anonymizer(
        redactors=[
            NameRedactor(known_names=["משה כהן", "דוד ישראלי"])
        ]
    )
    text = "ערעור על ציון עבור משה כהן מול המרצה פרופ' אברהם שטרן וד\"ר שרה לוי."
    anonymized = anon.anonymize(text)

    assert "משה כהן" not in anonymized
    assert "שרה לוי" not in anonymized
    assert "[NAME_" in anonymized

    restored = anon.restore(anonymized)
    assert restored == text


def test_mixed_language_pii_anonymization():
    """US 5.2.2 Acceptance Criteria: Names and emails in Hebrew or English text are masked."""
    anon = Anonymizer(
        redactors=[
            IsraeliIdRedactor(),
            EmailRedactor(),
            NameRedactor(known_names=["יוסי כהן", "Alice Brown"]),
        ]
    )
    text = (
        "שלום, שמי יוסי כהן (ת.ז 123456782). "
        "פניתי למתרגלת Alice Brown באימייל yossi.cohen@edu.jct.ac.il "
        "ובנוסף כתבתי לד\"ר שמואל גולדברג בכתובת shmuel@university.ac.il לגבי מטלה 3."
    )
    anonymized = anon.anonymize(text)

    # Ensure all PII is masked
    assert "יוסי כהן" not in anonymized
    assert "123456782" not in anonymized
    assert "Alice Brown" not in anonymized
    assert "yossi.cohen@edu.jct.ac.il" not in anonymized
    assert "shmuel@university.ac.il" not in anonymized

    # Placeholders present
    assert "[ID_1]" in anonymized
    assert "[NAME_1]" in anonymized
    assert "[EMAIL_1]" in anonymized
    assert "[EMAIL_2]" in anonymized

    # Complete lossless restore
    restored = anon.restore(anonymized)
    assert restored == text


def test_empty_and_none_text():
    anon = Anonymizer()
    assert anon.anonymize(None) is None
    assert anon.anonymize("") == ""
    assert anon.restore(None) is None
    assert anon.restore("") == ""
