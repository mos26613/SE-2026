"""Tests for student registration (User Story 1.1.1, AB#183).

The HTTP tests use the in-memory registrar. The Supabase-specific rules (duplicate
detection, error mapping) are tested with a fake Supabase client, so no internet is needed.

Run:  python -m pytest tests/test_signup.py -v
"""
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import Settings, get_settings
from app.routers import auth as signup_module
from app.routers.auth import (
    DUPLICATE_EMAIL_MESSAGE,
    EmailAlreadyRegistered,
    MemoryRegistrar,
    SignupRejected,
    SupabaseRegistrar,
)

GOOD = {"email": "student@example.com", "password": "Secret123"}


@pytest.fixture
def client(monkeypatch):
    main.app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, supabase_url="")
    monkeypatch.setattr(signup_module, "_memory_registrar", MemoryRegistrar())  # fresh emails per test
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


# --- success -----------------------------------------------------------------

def test_signup_succeeds(client):
    r = client.post("/api/auth/signup", json=GOOD)
    assert r.status_code == 201
    assert r.json()["email"] == "student@example.com"
    assert "verification" in r.json()["message"]


def test_signup_needs_no_login_token(client):
    # Registration is the step before having a token.
    assert client.post("/api/auth/signup", json=GOOD).status_code == 201


def test_email_is_saved_in_lowercase(client):
    r = client.post("/api/auth/signup", json={**GOOD, "email": "Student@Example.COM"})
    assert r.status_code == 201
    assert r.json()["email"] == "student@example.com"


# --- email validation (AC 1) -------------------------------------------------

@pytest.mark.parametrize("email", ["", "plainaddress", "no-at-sign.com", "a@", "@example.com", "a b@example.com"])
def test_invalid_email_is_rejected(client, email):
    r = client.post("/api/auth/signup", json={**GOOD, "email": email})
    assert r.status_code == 422


# --- password strength (AC 2) ------------------------------------------------

@pytest.mark.parametrize(
    "password",
    [
        "Short1A",      # 7 characters
        "alllowercase1",  # no uppercase
        "NoDigitsHere",   # no digit
        "",
        "12345678",       # no uppercase letter
    ],
)
def test_weak_password_is_rejected(client, password):
    r = client.post("/api/auth/signup", json={**GOOD, "password": password})
    assert r.status_code == 422
    assert "at least 8 characters" in str(r.json())


def test_password_with_exactly_8_characters_is_accepted(client):
    assert client.post("/api/auth/signup", json={**GOOD, "password": "Abcdefg1"}).status_code == 201


def test_password_too_long_for_supabase_is_rejected(client):
    r = client.post("/api/auth/signup", json={**GOOD, "password": "Aa1" + "x" * 70})
    assert r.status_code == 422


def test_missing_fields_are_rejected(client):
    assert client.post("/api/auth/signup", json={"email": GOOD["email"]}).status_code == 422
    assert client.post("/api/auth/signup", json={"password": GOOD["password"]}).status_code == 422


# --- duplicate email (AC 4) --------------------------------------------------

def test_duplicate_email_returns_400_with_clear_message(client):
    assert client.post("/api/auth/signup", json=GOOD).status_code == 201
    r = client.post("/api/auth/signup", json=GOOD)
    assert r.status_code == 400
    assert r.json()["detail"] == DUPLICATE_EMAIL_MESSAGE


def test_duplicate_email_ignores_letter_case(client):
    client.post("/api/auth/signup", json=GOOD)
    r = client.post("/api/auth/signup", json={**GOOD, "email": "STUDENT@example.com"})
    assert r.status_code == 400


def test_unexpected_failure_returns_502_without_details(client, monkeypatch):
    class Broken:
        def sign_up(self, email, password):
            raise RuntimeError("secret internal detail")

    main.app.dependency_overrides[signup_module.get_registrar] = lambda: Broken()
    r = client.post("/api/auth/signup", json=GOOD)
    assert r.status_code == 502
    assert "secret" not in r.text


# --- Supabase registrar (AC 3) ----------------------------------------------

class FakeAuth:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, []

    def sign_up(self, credentials):
        self.calls.append(credentials)
        if self.error:
            raise self.error
        return self.result


def registrar_with(fake_auth, redirect_to: str = "") -> SupabaseRegistrar:
    registrar = object.__new__(SupabaseRegistrar)  # skip the real Supabase connection
    registrar._client = SimpleNamespace(auth=fake_auth)
    registrar._redirect_to = redirect_to
    return registrar


class FakeSupabaseError(Exception):
    def __init__(self, code, status=400):
        super().__init__(code)
        self.code, self.status = code, status


def test_supabase_signup_sends_email_and_password():
    auth = FakeAuth(SimpleNamespace(user=SimpleNamespace(identities=[object()])))
    registrar_with(auth).sign_up("a@example.com", "Secret123")
    assert auth.calls == [{"email": "a@example.com", "password": "Secret123"}]


def test_supabase_signup_sends_the_verification_link_to_the_frontend_when_configured():
    auth = FakeAuth(SimpleNamespace(user=SimpleNamespace(identities=[object()])))
    registrar_with(auth, redirect_to="https://app.example/welcome").sign_up("a@example.com", "Secret123")
    assert auth.calls == [
        {"email": "a@example.com", "password": "Secret123", "options": {"email_redirect_to": "https://app.example/welcome"}}
    ]


def test_the_frontend_address_is_empty_by_default():
    assert Settings(_env_file=None).frontend_url == ""
    assert Settings(_env_file=None, frontend_url="https://app.example").frontend_url == "https://app.example"


def test_supabase_hidden_duplicate_is_detected():
    # With "Confirm email" on, Supabase answers a duplicate with a user that has no identities.
    auth = FakeAuth(SimpleNamespace(user=SimpleNamespace(identities=[])))
    with pytest.raises(EmailAlreadyRegistered):
        registrar_with(auth).sign_up("a@example.com", "Secret123")


@pytest.mark.parametrize("code", ["user_already_exists", "email_exists"])
def test_supabase_duplicate_error_codes(code):
    with pytest.raises(EmailAlreadyRegistered):
        registrar_with(FakeAuth(error=FakeSupabaseError(code))).sign_up("a@example.com", "Secret123")


def test_supabase_weak_password_is_a_400():
    with pytest.raises(SignupRejected) as err:
        registrar_with(FakeAuth(error=FakeSupabaseError("weak_password"))).sign_up("a@example.com", "Secret123")
    assert err.value.status_code == 400


def test_supabase_rate_limit_is_a_429():
    error = FakeSupabaseError("over_email_send_rate_limit", status=429)
    with pytest.raises(SignupRejected) as err:
        registrar_with(FakeAuth(error=error)).sign_up("a@example.com", "Secret123")
    assert err.value.status_code == 429


def test_supabase_unknown_error_is_passed_up():
    with pytest.raises(RuntimeError):
        registrar_with(FakeAuth(error=RuntimeError("boom"))).sign_up("a@example.com", "Secret123")
