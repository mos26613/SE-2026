"""Who is calling?

The extension and the dashboard log the student in with Supabase Auth and send the
token in every request:  Authorization: Bearer <access_token>
We ask Supabase who that token belongs to. No valid token -> 401.

In dev mode (no SUPABASE_URL) everyone is the same test user, so you can try the
API from /docs without logging in.
"""
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import Settings, get_settings

DEV_USER_ID = "00000000-0000-0000-0000-000000000001"

_bearer = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    id: str
    access_token: str


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    settings: Settings = Depends(get_settings),
) -> CurrentUser:
    if settings.dev_mode:
        return CurrentUser(id=DEV_USER_ID, access_token="dev")

    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing Authorization: Bearer <token> header")

    token = credentials.credentials
    try:
        from supabase import create_client

        client = create_client(settings.supabase_url, settings.supabase_key)
        result = client.auth.get_user(token)
        user = result.user if result else None
    except Exception:
        user = None

    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    return CurrentUser(id=user.id, access_token=token)
