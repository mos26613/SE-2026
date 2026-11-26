"""Row Level Security tests against the REAL Supabase project (User Story 1.3.1, AB#226).

They prove that student B can't read or change student A's data, through the Data API
directly and through our FastAPI backend (task 1.3.1.3).

These tests are SKIPPED unless two test accounts are configured, so a normal
`python -m pytest` stays offline. To run them, add to the root .env (or `set` in cmd):

    RLS_TEST_EMAIL_A=test1@example.com
    RLS_TEST_PASSWORD_A=...
    RLS_TEST_EMAIL_B=test2@example.com
    RLS_TEST_PASSWORD_B=...

plus the usual SUPABASE_URL and SUPABASE_KEY (the anon key), then:

    python -m pytest tests/test_rls.py -v

They only create rows whose moodle_id starts with "rls-test-" and courses with
moodle_course_id 999999001-999999002, and delete them again at the end.
See docs/security/rls.md.
"""
import pytest
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config import Settings


class RlsTestSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), env_file_encoding="utf-8", extra="ignore")

    rls_test_email_a: str = ""
    rls_test_password_a: str = ""
    rls_test_email_b: str = ""
    rls_test_password_b: str = ""


_rls = RlsTestSettings()
_app = Settings()

pytestmark = pytest.mark.skipif(
    _app.dev_mode or not all([_rls.rls_test_email_a, _rls.rls_test_password_a, _rls.rls_test_email_b, _rls.rls_test_password_b]),
    reason="RLS integration tests need SUPABASE_URL and RLS_TEST_EMAIL/PASSWORD_A/B (see docstring)",
)

TASK_ID = "rls-test-1"
COURSE_ID = 999999001
OTHER_COURSE_ID = 999999002


def _client(email: str | None = None, password: str | None = None):
    """A Supabase client with the anon key, signed in as a student (or signed out)."""
    from supabase import create_client

    client = create_client(_app.supabase_url, _app.supabase_key)
    if email:
        session = client.auth.sign_in_with_password({"email": email, "password": password}).session
        client.postgrest.auth(session.access_token)
        client.user_id = session.user.id
        client.access_token = session.access_token
    return client


def _cleanup(client):
    client.table("tasks").delete().like("moodle_id", "rls-test-%").execute()
    client.table("courses").delete().in_("moodle_course_id", [COURSE_ID, OTHER_COURSE_ID]).execute()


@pytest.fixture(scope="module")
def students():
    """Student A owns one course and one task. Student B owns nothing (yet)."""
    a = _client(_rls.rls_test_email_a, _rls.rls_test_password_a)
    b = _client(_rls.rls_test_email_b, _rls.rls_test_password_b)
    assert a.user_id != b.user_id, "A and B must be two different accounts"
    for c in (a, b):
        _cleanup(c)

    a.table("courses").insert({"user_id": a.user_id, "moodle_course_id": COURSE_ID, "name": "RLS test course"}).execute()
    a.table("tasks").insert(
        {"user_id": a.user_id, "moodle_id": TASK_ID, "title": "A's secret task", "moodle_course_id": COURSE_ID}
    ).execute()

    yield a, b

    for c in (a, b):
        _cleanup(c)


def _a_task_is_intact(a):
    rows = a.table("tasks").select("title").eq("moodle_id", TASK_ID).execute().data
    assert rows == [{"title": "A's secret task"}]


def _rejected(call) -> str:
    """Run a call that RLS must refuse; return the Postgres error code."""
    from postgrest.exceptions import APIError

    with pytest.raises(APIError) as err:
        call()
    return err.value.code


# --- Read ------------------------------------------------------------------


def test_owner_can_read_own_rows(students):
    a, _ = students
    assert len(a.table("tasks").select("*").eq("moodle_id", TASK_ID).execute().data) == 1
    assert len(a.table("courses").select("*").eq("moodle_course_id", COURSE_ID).execute().data) == 1


@pytest.mark.parametrize("table, column, value", [("tasks", "moodle_id", TASK_ID), ("courses", "moodle_course_id", COURSE_ID)])
def test_other_student_reads_nothing(students, table, column, value):
    a, b = students
    assert b.table(table).select("*").eq(column, value).execute().data == []
    assert b.table(table).select("*").eq("user_id", a.user_id).execute().data == []


def test_other_student_cannot_read_profile(students):
    a, b = students
    assert b.table("users").select("*").eq("id", a.user_id).execute().data == []


def test_signed_out_request_gets_nothing(students):
    from postgrest.exceptions import APIError

    anon = _client()
    for table in ("tasks", "courses", "users"):
        try:
            assert anon.table(table).select("*").execute().data == []
        except APIError as e:
            assert e.code == "42501"  # permission denied: also acceptable


# --- Write -----------------------------------------------------------------


def test_other_student_cannot_update(students):
    a, b = students
    assert b.table("tasks").update({"title": "hacked"}).eq("moodle_id", TASK_ID).execute().data == []
    assert b.table("courses").update({"name": "hacked"}).eq("moodle_course_id", COURSE_ID).execute().data == []
    _a_task_is_intact(a)


def test_other_student_cannot_take_over_a_row(students):
    """Changing user_id to steal a row is blocked too (no row matches B's USING clause)."""
    a, b = students
    assert b.table("tasks").update({"user_id": b.user_id}).eq("user_id", a.user_id).execute().data == []
    _a_task_is_intact(a)


def test_other_student_cannot_delete(students):
    a, b = students
    assert b.table("tasks").delete().eq("moodle_id", TASK_ID).execute().data == []
    assert b.table("courses").delete().eq("moodle_course_id", COURSE_ID).execute().data == []
    _a_task_is_intact(a)


def test_other_student_cannot_insert_rows_for_someone_else(students):
    a, b = students
    code = _rejected(
        lambda: b.table("tasks").insert({"user_id": a.user_id, "moodle_id": "rls-test-planted", "title": "x"}).execute()
    )
    assert code == "42501"  # new row violates row-level security policy
    code = _rejected(
        lambda: b.table("courses").insert({"user_id": a.user_id, "moodle_course_id": OTHER_COURSE_ID, "name": "x"}).execute()
    )
    assert code == "42501"
    assert a.table("tasks").select("*").eq("moodle_id", "rls-test-planted").execute().data == []


def test_own_task_cannot_point_at_someone_elses_course(students):
    """tasks -> courses is keyed on (user_id, moodle_course_id), so B can't attach to A's course."""
    _, b = students
    _rejected(
        lambda: b.table("tasks").insert(
            {"user_id": b.user_id, "moodle_id": "rls-test-link", "title": "x", "moodle_course_id": COURSE_ID}
        ).execute()
    )


# --- Through the FastAPI backend (task 1.3.1.3) ------------------------------


def test_backend_store_with_wrong_user_id_still_sees_only_own_rows(students):
    """Even if the backend had a bug and asked for A's user_id with B's token, RLS returns nothing."""
    from app.db import SupabaseStore

    a, b = students
    store_as_b = SupabaseStore(_app, b.access_token)
    assert store_as_b.list_tasks(a.user_id, include_filtered=True) == []
    assert store_as_b.existing_tasks(a.user_id, [TASK_ID]) == {}


def test_api_as_other_student(students):
    """GET /api/tasks with B's token hides A's task; syncing A's moodle_id creates B's own row."""
    from fastapi.testclient import TestClient

    from app import main
    from app.config import get_settings

    a, b = students
    main.app.dependency_overrides[get_settings] = lambda: Settings(gemini_api_key="")  # no AI calls
    try:
        api = TestClient(main.app)
        headers = {"Authorization": f"Bearer {b.access_token}"}

        tasks = api.get("/api/tasks", params={"include_filtered": True}, headers=headers).json()
        assert all(t["moodle_id"] != TASK_ID for t in tasks)

        r = api.post("/api/tasks/sync", json={"tasks": [{"moodle_id": TASK_ID, "title": "B's own copy"}]}, headers=headers)
        assert r.status_code == 200
        assert r.json()["created"] == 1  # a new row for B, not an update of A's
    finally:
        main.app.dependency_overrides.clear()

    _a_task_is_intact(a)
    assert b.table("tasks").select("title").eq("moodle_id", TASK_ID).execute().data == [{"title": "B's own copy"}]
