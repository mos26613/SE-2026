# Row Level Security (multi-tenant isolation)

User Story 1.3.1 (AB#226), tasks 1.3.1.1 to 1.3.1.4. Supabase project `dsclfcysdrjchhyynggt`.

Every student shares the same `users`, `courses` and `tasks` tables. PostgreSQL Row Level Security (RLS) makes sure each student can only see and change their own rows, even if a request comes straight to the Supabase Data API with a valid login, and even if our backend has a bug.

## How requests reach the database

- The extension and the dashboard log in with Supabase Auth and get a JWT (access token).
- The FastAPI backend uses the **anon key plus the student's token** (`SupabaseStore` in `backend/app/db.py`), never the `service_role` key. So every query runs as the Postgres role `authenticated`, and `auth.uid()` is the student's id.
- Requests without a login run as the role `anon`.

## Policies

RLS is **enabled** on all three tables. Each table has one policy:

| Table | Policy | Role | Commands | USING (which rows are visible / can be changed) | WITH CHECK (which rows may be written) |
|---|---|---|---|---|---|
| `users` | Users can view and edit their own profile | `authenticated` | ALL | `(select auth.uid()) = id` | `(select auth.uid()) = id` |
| `courses` | Users can manage their own courses | `authenticated` | ALL | `(select auth.uid()) = user_id` | `(select auth.uid()) = user_id` |
| `tasks` | Users can manage their own tasks | `authenticated` | ALL | `(select auth.uid()) = user_id` | `(select auth.uid()) = user_id` |

- `ALL` means the same rule applies to SELECT, INSERT, UPDATE and DELETE. USING filters the rows a student can read, update or delete. WITH CHECK rejects any inserted or updated row that doesn't belong to the student, so a row can't be planted for, or handed over to, someone else.
- `auth.uid()` is wrapped in `(select ...)` so Postgres evaluates it once per query instead of once per row (Supabase's recommended form).
- There is no policy for `anon`, so signed-out requests see nothing.
- `user_id` is `NOT NULL` on `courses` and `tasks`.
- The foreign key from `tasks` to `courses` is on `(user_id, moodle_course_id)`, so a student can't attach a task to someone else's course.
- `service_role` and the `postgres` owner bypass RLS by design. Their keys must never leave the server (and our backend doesn't use them at all).

## Privileges

RLS only filters rows. Table privileges decide which commands are allowed at all:

| Role | users | courses | tasks |
|---|---|---|---|
| `authenticated` | SELECT, INSERT, UPDATE, DELETE | SELECT, INSERT, UPDATE, DELETE | SELECT, INSERT, UPDATE, DELETE |
| `anon` | none | none | none |

`TRUNCATE` ignores RLS completely, so it was revoked from `anon` and `authenticated` together with the unused `TRIGGER` and `REFERENCES` (migration `supabase/migrations/20261123173000_rls_hardening.sql`). The same migration stops anyone calling the event-trigger function `rls_auto_enable()` through the API; Postgres still runs it automatically to turn RLS on for every new table in `public`. That function is created by Supabase (automatic RLS, chosen when the project was set up), not by our migrations, so the migration revokes it only where it exists. A local or CI database built from the migrations alone doesn't have it.

**Adding a table:** RLS turns on automatically (`ensure_rls` event trigger), which blocks everything until you add a policy. Add an owner policy like the ones above and `grant select, insert, update, delete on <table> to authenticated`. Never grant `truncate`.

## Acceptance criteria

| Criterion | How it is met | Proof |
|---|---|---|
| RLS enabled on `courses` and `tasks` | Enabled on `courses`, `tasks` and `users` | `supabase/tests/rls_check.sql` checks `pg_class.relrowsecurity` directly (see below) |
| Policies verify `auth.uid() = user_id` for SELECT, INSERT, UPDATE and DELETE | One `FOR ALL` policy per table with the check in both USING and WITH CHECK | `supabase/tests/rls_check.sql` (policy exists); `backend/tests/test_rls.py` tests each command |
| Cross-tenant attempts return empty results or access errors | Reads, updates and deletes of another student's rows match 0 rows; inserts for another student fail with `42501`; signed-out requests get nothing | `backend/tests/test_rls.py` |

## Configuration check

`supabase/tests/rls_check.sql` checks the configuration itself, without test accounts. Paste it into the Supabase SQL Editor and run it; it only reads. It checks, for `users`, `courses` and `tasks`:

1. RLS is enabled (`pg_class.relrowsecurity`).
2. A `FOR ALL` policy for `authenticated` compares `auth.uid()` in both USING and WITH CHECK.
3. There is no policy for `anon` or `public`.
4. Neither `anon` nor `authenticated` can `TRUNCATE`.
5. `rls_auto_enable()`, if present, can't be called by `anon` or `authenticated`.

A successful run ends with the notice `rls check passed`; a problem stops it with an error naming the check. Tested on Postgres 17: it passes after the migrations and fails when RLS is turned off on a table, when a policy for `anon` is added, or when the hardening migration is missing.

## Automated tests

`backend/tests/test_rls.py` signs in as two real test students, A and B, against the real project. A creates a course and a task, then the tests check that B:

- reads nothing of A's from `tasks`, `courses` or `users`;
- updates or deletes 0 of A's rows, and can't take a row over by changing `user_id` (A's data is checked afterwards);
- can't insert a task or course with A's `user_id` (error `42501`);
- can't link a task to A's course (foreign key);
- through the backend: `SupabaseStore` asked for A's `user_id` with B's token returns nothing, `GET /api/tasks` with B's token doesn't include A's task, and syncing A's `moodle_id` as B creates B's own row.

A signed-out request gets an empty list or `42501`.

The tests only create rows with `moodle_id` starting `rls-test-` and courses `999999001` to `999999002`, and delete them at the end. They are skipped unless the test accounts are configured, so the normal test run needs no internet. To run them, add to the root `.env`:

```
RLS_TEST_EMAIL_A=test1@example.com
RLS_TEST_PASSWORD_A=...
RLS_TEST_EMAIL_B=test2@example.com
RLS_TEST_PASSWORD_B=...
```

then, in `backend/` with the venv active:

```
python -m pytest tests/test_rls.py -v
```

Both accounts must exist in Supabase (Authentication → Users, with the email confirmed).
