"""Unit tests for Sync Transaction Logging and Security (US 3.2.4, AB#402).

Acceptance Criteria:
  1. Given a successful synchronization batch, summary logs record the exact timestamp
     and processed task count.
  2. Given a database exception, detailed stack traces and error metadata are recorded.
  3. Given log output configurations, sensitive user credentials or tokens are strictly
     masked or excluded from logs.
"""
import logging
import pytest
from unittest.mock import MagicMock

from app.logging_config import (
    SensitiveDataFilter,
    log_sync_error,
    log_sync_transaction,
    scrub_sensitive_data,
)


def test_scrub_sensitive_data():
    """AC 3: Sensitive user credentials or tokens are strictly masked."""
    # Bearer tokens
    raw = "Header Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xyz.123"
    cleaned = scrub_sensitive_data(raw)
    assert "Bearer [MASKED_TOKEN]" in cleaned
    assert "eyJhbGciOiJIUzI1Ni" not in cleaned

    # JSON password / access token keys
    raw_json = '{"user": "student", "password": "supersecret123", "access_token": "secret_abc"}'
    cleaned_json = scrub_sensitive_data(raw_json)
    assert "supersecret123" not in cleaned_json
    assert "secret_abc" not in cleaned_json
    assert "[MASKED]" in cleaned_json


def test_sensitive_data_logging_filter():
    """AC 3: Logger filter scrubs messages automatically."""
    filt = SensitiveDataFilter()
    record = logging.LogRecord(
        name="test-logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Student token: Bearer secret_token_value_12345",
        args=(),
        exc_info=None,
    )
    assert filt.filter(record) is True
    assert "secret_token_value_12345" not in record.msg
    assert "[MASKED_TOKEN]" in record.msg


def test_log_sync_transaction():
    """AC 1: Successful sync records exact timestamp and processed task count."""
    mock_logger = MagicMock(spec=logging.Logger)
    log_sync_transaction(
        mock_logger,
        user_id="usr-789",
        received=10,
        created=4,
        updated=2,
        unchanged=4,
        conflicts=1,
        duration_ms=45.2,
    )

    mock_logger.info.assert_called_once()
    msg, *args = mock_logger.info.call_args[0]
    extra = mock_logger.info.call_args[1].get("extra", {})

    metadata = extra.get("metadata", {})
    assert metadata["event"] == "sync_transaction"
    assert metadata["user_id"] == "usr-789"
    assert metadata["received_count"] == 10
    assert metadata["created_count"] == 4
    assert metadata["updated_count"] == 2
    assert "timestamp" in metadata


def test_log_sync_error():
    """AC 2: Database exception records detailed stack trace and error metadata."""
    mock_logger = MagicMock(spec=logging.Logger)
    try:
        raise ConnectionError("Supabase connection timeout")
    except ConnectionError as exc:
        log_sync_error(
            mock_logger,
            operation="upsert_tasks",
            user_id="usr-456",
            error=exc,
            metadata={"batch_size": 5},
        )

    mock_logger.error.assert_called_once()
    kwargs = mock_logger.error.call_args[1]
    assert kwargs.get("exc_info") is True
    metadata = kwargs.get("extra", {}).get("metadata", {})
    assert metadata["operation"] == "upsert_tasks"
    assert metadata["user_id"] == "usr-456"
    assert metadata["error_type"] == "ConnectionError"
