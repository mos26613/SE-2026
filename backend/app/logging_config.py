"""Structured logging configuration and sensitive data scrubbing (US 3.2.4, AB#402).

Acceptance Criteria:
  1. Given a successful synchronization batch, summary logs record the exact timestamp
     and processed task count.
  2. Given a database exception, detailed stack traces and error metadata are recorded
     in the server logs.
  3. Sensitive user credentials, passwords, or tokens (JWT/Bearer) are strictly masked
     or excluded from logs.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

# Patterns to scrub sensitive values (Bearer tokens, JWTs, passwords, secrets)
_SENSITIVE_PATTERNS = [
    (re.compile(r"(Bearer\s+)[A-Za-z0-9\-_\.]+", re.IGNORECASE), r"\1[MASKED_TOKEN]"),
    (re.compile(r"(eyJ[A-Za-z0-9\-_]{10,}\.[A-Za-z0-9\-_]{10,}\.[A-Za-z0-9\-_]+)"), r"[MASKED_JWT]"),
    (re.compile(r"(['\"]?(?:access_token|token|password|secret|jwt_token|api_key)['\"]?\s*[:=]\s*['\"])[^'\"]+(['\"])", re.IGNORECASE), r"\1[MASKED]\2"),
]


def scrub_sensitive_data(message: str) -> str:
    """Mask credentials, tokens and passwords in log messages."""
    if not isinstance(message, str):
        return str(message)
    for pattern, replacement in _SENSITIVE_PATTERNS:
        message = pattern.sub(replacement, message)
    return message


class SensitiveDataFilter(logging.Filter):
    """Logging filter that scrubs sensitive information from record messages and arguments."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = scrub_sensitive_data(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: scrub_sensitive_data(v) if isinstance(v, str) else v for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(scrub_sensitive_data(a) if isinstance(a, str) else a for a in record.args)
        return True


class JsonLogFormatter(logging.Formatter):
    """Structured JSON formatter with ISO timestamps and event metadata."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_entry["stack_trace"] = self.formatException(record.exc_info)
        if hasattr(record, "metadata") and isinstance(record.metadata, dict):
            # Mask sensitive metadata items
            log_entry["metadata"] = {
                k: scrub_sensitive_data(str(v)) if any(s in k.lower() for s in ("token", "key", "secret", "password")) else v
                for k, v in record.metadata.items()
            }
        return json.dumps(log_entry, default=str)


def setup_structured_logging(level: int = logging.INFO) -> logging.Logger:
    """Set up structured logging with sensitive data filtering."""
    logger = logging.getLogger("task-api")
    logger.setLevel(level)
    logger.addFilter(SensitiveDataFilter())
    return logger


def log_sync_transaction(
    logger: logging.Logger,
    user_id: str,
    received: int,
    created: int,
    updated: int,
    unchanged: int,
    conflicts: int,
    duration_ms: float,
) -> None:
    """Log successful sync payload metrics and exact timestamp (AC 1)."""
    now = datetime.now(timezone.utc).isoformat()
    logger.info(
        "Sync transaction completed successfully: timestamp=%s user_id=%s received=%d created=%d updated=%d unchanged=%d conflicts=%d duration_ms=%.2f",
        now,
        user_id,
        received,
        created,
        updated,
        unchanged,
        conflicts,
        duration_ms,
        extra={
            "metadata": {
                "event": "sync_transaction",
                "timestamp": now,
                "user_id": user_id,
                "received_count": received,
                "created_count": created,
                "updated_count": updated,
                "unchanged_count": unchanged,
                "conflicts_count": conflicts,
                "duration_ms": duration_ms,
            }
        },
    )


def log_sync_error(
    logger: logging.Logger,
    operation: str,
    user_id: str,
    error: Exception,
    metadata: Optional[dict] = None,
) -> None:
    """Log full stack traces and context on database exception events (AC 2)."""
    clean_metadata = dict(metadata or {})
    clean_metadata.update({"operation": operation, "user_id": user_id, "error_type": type(error).__name__})
    logger.error(
        "Database exception during %s for user %s: %s",
        operation,
        user_id,
        str(error),
        exc_info=True,
        extra={"metadata": clean_metadata},
    )
