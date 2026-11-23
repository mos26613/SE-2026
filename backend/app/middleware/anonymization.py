import json
import logging
import re
from starlette.responses import JSONResponse

log = logging.getLogger("anonymization-middleware")

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?:\+972|0)[\s-]?5\d[\s-]?\d{3}[\s-]?\d{4}")
_ID_RE = re.compile(r"\b\d{9}\b")


class AnonymizationError(Exception):
    """Raised when mandatory PII anonymization cannot safely complete."""


def anonymize_text(value: str) -> str:
    if not isinstance(value, str):
        raise AnonymizationError("Value must be a string")
    cleaned = _EMAIL_RE.sub("[REDACTED_EMAIL]", value)
    cleaned = _PHONE_RE.sub("[REDACTED_PHONE]", cleaned)
    cleaned = _ID_RE.sub("[REDACTED_ID]", cleaned)
    return cleaned


def anonymize_payload(payload):
    if isinstance(payload, dict):
        return {k: anonymize_payload(v) for k, v in payload.items()}
    if isinstance(payload, list):
        return [anonymize_payload(item) for item in payload]
    if isinstance(payload, str):
        return anonymize_text(payload)
    return payload


class MandatoryAnonymizationMiddleware:
    """ASGI middleware enforcing mandatory PII anonymization on protected paths."""

    def __init__(self, app, protected_paths: tuple[str, ...] = ("/api/tasks/sync",)):
        self.app = app
        self.protected_paths = protected_paths

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and scope.get("method") in {"POST", "PUT", "PATCH"}:
            path = scope.get("path", "")
            if path.startswith(self.protected_paths):
                chunks = []
                more_body = True
                while more_body:
                    message = await receive()
                    if message.get("type") == "http.request":
                        body_part = message.get("body", b"")
                        if body_part:
                            chunks.append(body_part)
                        more_body = message.get("more_body", False)
                    else:
                        more_body = False

                raw_body = b"".join(chunks)
                if raw_body:
                    try:
                        parsed = json.loads(raw_body.decode("utf-8"))
                        sanitized = anonymize_payload(parsed)
                        sanitized_bytes = json.dumps(sanitized, ensure_ascii=False).encode("utf-8")
                    except Exception:
                        log.warning("Mandatory anonymization failed; blocking request on %s", path)
                        response = JSONResponse(
                            status_code=422,
                            content={"detail": "Request blocked: mandatory anonymization failed"},
                        )
                        await response(scope, receive, send)
                        return

                    sent = False

                    async def sanitized_receive():
                        nonlocal sent
                        if not sent:
                            sent = True
                            return {"type": "http.request", "body": sanitized_bytes, "more_body": False}
                        return {"type": "http.request", "body": b"", "more_body": False}

                    await self.app(scope, sanitized_receive, send)
                    return

        await self.app(scope, receive, send)
