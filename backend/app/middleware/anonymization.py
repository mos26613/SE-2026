import json
import logging
import re
from dataclasses import dataclass
from starlette.responses import JSONResponse

log = logging.getLogger("anonymization-middleware")

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?:\+972|0)[\s-]?5\d[\s-]?\d{3}[\s-]?\d{4}")
_ID_RE = re.compile(r"\b\d{9}\b")


class AnonymizationError(Exception):
    """Raised when mandatory PII anonymization cannot safely complete."""


@dataclass(frozen=True)
class AnonymizationResult:
    payload: object
    ok: bool
    reason: str | None = None


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
    if payload is None or isinstance(payload, (int, float, bool)):
        return payload
    raise AnonymizationError(f"Unsupported payload type: {type(payload).__name__}")


def run_anonymization(payload) -> AnonymizationResult:
    """Run PII anonymization (#39, #40, #41) and report whether AI calls are safe."""
    try:
        sanitized = anonymize_payload(payload)
        return AnonymizationResult(payload=sanitized, ok=True)
    except Exception as exc:
        log.warning("Anonymization failed; blocking AI call and continuing without AI fields: %s", exc)
        return AnonymizationResult(payload=payload, ok=False, reason=str(exc))


class MandatoryAnonymizationMiddleware:
    """ASGI middleware enforcing PII anonymization (#39, #40, #41) on /api/tasks/sync."""

    def __init__(self, app, protected_paths: tuple[str, ...] = ("/api/tasks/sync",)):
        self.app = app
        self.protected_paths = protected_paths

    async def __call__(self, scope, receive, send):
        state = scope.setdefault("state", {})
        state.setdefault("anonymization_ok", True)

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
                    except Exception as exc:
                        log.warning("Invalid JSON payload on %s; blocking request: %s", path, exc)
                        response = JSONResponse(
                            status_code=422,
                            content={"detail": "Request blocked: invalid JSON payload"},
                        )
                        await response(scope, receive, send)
                        return

                    result = run_anonymization(parsed)
                    state["anonymization_ok"] = result.ok
                    if not result.ok:
                        state["anonymization_reason"] = result.reason

                    body_to_forward = (
                        json.dumps(result.payload, ensure_ascii=False).encode("utf-8")
                        if result.ok
                        else raw_body
                    )
                    sent = False

                    async def forwarded_receive():
                        nonlocal sent
                        if not sent:
                            sent = True
                            return {"type": "http.request", "body": body_to_forward, "more_body": False}
                        return {"type": "http.request", "body": b"", "more_body": False}

                    await self.app(scope, forwarded_receive, send)
                    return

        await self.app(scope, receive, send)
