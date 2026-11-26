"""Student registration (User Story 1.1.1, AB#183).

POST /api/auth/signup creates the student in Supabase Auth. Supabase then sends the
verification email (the "Confirm email" setting in the Supabase dashboard must be on).
The `users` profile row is created by the on_auth_user_created trigger in the database.

In dev mode (no SUPABASE_URL) emails are kept in memory so the endpoint can be tried
from /docs and tested without a database or an email provider.
"""
import logging
import re
from typing import Protocol

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, field_validator

from ..config import Settings, get_settings

log = logging.getLogger("task-api")

router = APIRouter(prefix="/api/auth", tags=["auth"])

PASSWORD_RULES = "Password must be at least 8 characters and contain at least one uppercase letter and one digit"
DUPLICATE_EMAIL_MESSAGE = "An account with this email already exists. Try logging in instead."


class SignupRequest(BaseModel):
    email: EmailStr
    password: str  # at most 72 bytes: the longest password Supabase Auth accepts

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, value: str) -> str:
        return value.lower()

    @field_validator("password")
    @classmethod
    def check_strength(cls, value: str) -> str:
        if len(value) < 8 or not re.search(r"[A-Z]", value) or not re.search(r"\d", value):
            raise ValueError(PASSWORD_RULES)
        if len(value.encode()) > 72:
            raise ValueError("Password must be at most 72 bytes long")
        return value


class SignupResponse(BaseModel):
    message: str
    email: EmailStr


class EmailAlreadyRegistered(Exception):
    pass


class SignupRejected(Exception):
    """Supabase refused the signup for a reason the student can act on."""

    def __init__(self, message: str, status_code: int = status.HTTP_400_BAD_REQUEST) -> None:
        super().__init__(message)
        self.status_code = status_code


class Registrar(Protocol):
    def sign_up(self, email: str, password: str) -> None: ...


class MemoryRegistrar:
    """Dev mode and tests: remembers emails until the server restarts."""

    def __init__(self) -> None:
        self.emails: set[str] = set()

    def sign_up(self, email: str, password: str) -> None:
        if email in self.emails:
            raise EmailAlreadyRegistered(email)
        self.emails.add(email)


class SupabaseRegistrar:
    def __init__(self, settings: Settings) -> None:
        from supabase import create_client

        # The anon key is enough: Supabase Auth sends the verification email itself.
        self._client = create_client(settings.supabase_url, settings.supabase_key)
        # Where the link in the verification email sends the student. Empty = the "Site URL" set in
        # the Supabase dashboard. Supabase only accepts addresses listed under Redirect URLs there.
        self._redirect_to = settings.frontend_url

    def sign_up(self, email: str, password: str) -> None:
        credentials = {"email": email, "password": password}
        if self._redirect_to:
            credentials["options"] = {"email_redirect_to": self._redirect_to}
        try:
            result = self._client.auth.sign_up(credentials)
        except Exception as exc:  # the Supabase client raises its own error types
            code = getattr(exc, "code", None)
            http_status = getattr(exc, "status", None)
            if code in ("user_already_exists", "email_exists"):
                raise EmailAlreadyRegistered(email) from exc
            if code == "weak_password":
                raise SignupRejected(PASSWORD_RULES) from exc
            if http_status == 429 or code in ("over_email_send_rate_limit", "over_request_rate_limit"):
                raise SignupRejected("Too many attempts. Please wait a minute and try again.", 429) from exc
            raise

        # When "Confirm email" is on, Supabase hides duplicates: it returns a user with no
        # identities instead of an error, so an existing account is detected here.
        user = result.user if result else None
        if user is not None and user.identities is not None and len(user.identities) == 0:
            raise EmailAlreadyRegistered(email)


# One shared in-memory registrar for dev mode.
_memory_registrar = MemoryRegistrar()


def get_registrar(settings: Settings = Depends(get_settings)) -> Registrar:
    if settings.dev_mode:
        return _memory_registrar
    return SupabaseRegistrar(settings)


@router.post("/signup", response_model=SignupResponse, status_code=status.HTTP_201_CREATED)
def signup(body: SignupRequest, registrar: Registrar = Depends(get_registrar)):
    """Register a new student. A verification link is sent to the email address."""
    try:
        registrar.sign_up(body.email, body.password)
    except EmailAlreadyRegistered:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, DUPLICATE_EMAIL_MESSAGE)
    except SignupRejected as exc:
        raise HTTPException(exc.status_code, str(exc))
    except Exception:
        log.exception("Signup failed")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Could not create the account. Please try again later.")

    return SignupResponse(
        message="Account created. Check your email and click the verification link to finish.",
        email=body.email,
    )
