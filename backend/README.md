# Backend (FastAPI)

The server in the middle of the system:

```
Chrome extension ──POST /api/tasks/sync──▶ FastAPI ──▶ Gemini (AI filter)
                                              │
                                              ▼
React dashboard  ◀──GET /api/tasks──────── Supabase
```

1. The extension sends every assignment it scraped from Moodle.
2. The API validates the data and asks Gemini which items are real tasks, plus a category, a priority and a one-line summary for each.
3. Everything is saved to Supabase, one row per student per Moodle assignment, so a re-sync updates instead of duplicating.
4. The dashboard reads the student's tasks back, soonest deadline first.

Related work items: US 3.1.1 (AB#366), US 3.1.2 (AB#371), US 5.1.3 (AB#37), US 5.2.1 (AB#39). Partly covers US 3.1.3, 3.2.1, 3.2.2 and 5.1.1 (see "Not done yet").

## Layout

| File | What it does |
|---|---|
| `app/main.py` | The endpoints |
| `app/models.py` | Request/response shapes. Bad data is rejected automatically (422). Dates without a time zone are treated as Israel time |
| `app/anonymizer.py` | Removes personal data (Israeli ID numbers so far) before anything is sent to Gemini, and puts it back in Gemini's answer. See "Anonymization" below |
| `app/ai_filter.py` | The Gemini step. Anonymizes the prompt first. Never blocks saving: if Gemini is missing, busy or fails, tasks are saved without AI fields (one automatic retry on 5xx) |
| `app/db.py` | Saving and reading. `SupabaseStore` for the real database, `MemoryStore` for dev mode and tests. The only file to change if the table's columns differ |
| `app/auth.py` | Checks the student's Supabase login token |
| `app/config.py` | Settings from the root `.env` |
| `tests/test_api.py` | End-to-end API tests with an in-memory store and a fake Gemini |
| `tests/test_anonymizer.py` | Tests for the anonymization rules |

## Endpoints

| Method | Path | Caller | What it does |
|---|---|---|---|
| GET | `/` | anyone | Welcome message |
| GET | `/health` | anyone | Whether Supabase and Gemini are configured |
| POST | `/api/tasks/sync` | Chrome extension | Receives `{"tasks": [...]}`, runs the AI filter, saves. Returns how many were created / updated / filtered out |
| GET | `/api/tasks` | Dashboard | The student's tasks, soonest deadline first. `?include_filtered=true` also returns items Gemini marked as not relevant |

Every `/api` request must send the student's Supabase login token: `Authorization: Bearer <access_token>`.
In **dev mode** (`SUPABASE_URL` empty or still the placeholder) no token is needed and data is kept in memory until the server restarts, so you can try everything from `/docs` right away.

Example sync body:

```json
{
  "tasks": [
    {
      "moodle_id": "48213",
      "title": "תרגיל בית 3",
      "course_name": "מבני נתונים",
      "moodle_course_id": 1234,
      "description": "Submit a PDF...",
      "due_date": "2026-12-05T23:59:00+02:00",
      "moodle_url": "https://moodle.example.ac.il/mod/assign/view.php?id=48213"
    }
  ]
}
```

`moodle_course_id` (Moodle's numeric course ID) is optional but recommended: it links the task to the student's row in the `courses` table, which is where the course name is stored. Without it the task is saved, but its course name isn't.

Dates are ISO 8601. A date without a time zone is treated as Israel time. The dashboard should convert returned dates to local time for display.

## Running it

**With Docker** (from the repo root): `docker compose up --build`, then open http://localhost:8000/docs.

**Without Docker** (Windows):

```
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

The backend reads the `.env` file at the repo root (copy it from `.env.example`).

**Tests:** from `backend/`, run `python -m pytest -v`.

**Techloq users:** if `pip install` or the Gemini/Supabase calls fail with an SSL / certificate error, set up the Techloq certificate as admin, then open a new terminal:

```
setx REQUESTS_CA_BUNDLE "C:\certs\BundledCertificate.crt" /m
setx SSL_CERT_FILE "C:\certs\BundledCertificate.crt" /m
pip config set global.cert "C:\certs\BundledCertificate.crt"
```

## Getting a Gemini API key

1. Go to https://aistudio.google.com/app/apikey and sign in with a Google account.
2. Click **Create API key**, then **Create API key in new project** (or pick the team's project).
3. Copy the key (it starts with `AIza...`) into the root `.env`: `GEMINI_API_KEY=AIza...`
4. Restart the server. `GET /health` should show `"ai": "on"`.

Notes:

- **Keep the key secret.** Only in `.env`, which git ignores. Never commit it, paste it in a chat, or put it in the extension. Each teammate can create their own key.
- **Free tier:** no credit card, but rate-limited, and on the free tier Google may use prompts to improve its products.
- **Model:** `GEMINI_MODEL` picks the model (default `gemini-3.5-flash-lite`). `gemini-2.5-flash` is no longer available to new users, and `gemini-3.8-flash` kept timing out on the free tier. If you get "model not found", pick a current Flash model from https://ai.google.dev/gemini-api/docs/models.
- `504 DEADLINE_EXCEEDED` / `503 UNAVAILABLE`: Gemini was busy; the API retries once. `429 RESOURCE_EXHAUSTED`: free-tier limit, wait a minute. In all cases tasks are still saved, just without AI fields.

## Anonymization (before Gemini)

ADR 0003 says no personal data may reach the AI provider. `app/anonymizer.py` does this on our server:

1. Before the Gemini call, every free-text field (title, course name, description) goes through one `Anonymizer`. Each piece of personal data is replaced with a placeholder such as `[ID_1]`. The same value gets the same placeholder everywhere in the request.
2. Gemini only ever sees the placeholders. `moodle_id` is not changed, because it is Moodle's own number and we need it to match answers back.
3. When the answer comes back, the placeholders in Gemini's summary are replaced with the real values. The database always keeps the original text.
4. If anonymization fails for any reason, Gemini is **not called**. The sync still saves the tasks, just without AI fields (`ai_applied: false`), like any other AI failure.

What is removed so far:

| Kind | Placeholder | Rule | Story |
|---|---|---|---|
| Israeli ID number | `[ID_n]` | 9 digits (`123456782`) or `12345678-2`, standalone, with a valid check digit. Numbers with a wrong check digit, digits inside longer numbers (phones, timestamps) and short numbers (grades, course codes) are left alone | US 5.2.1 (AB#39) |
| Names, emails | | Not yet | US 5.2.2 (AB#40) |

**Adding a new kind (US 5.2.2):** write a class with a `label` (e.g. `"EMAIL"`), a `find(text)` method that returns the `(start, end)` positions it found, and a `key(value)` method that says when two values are the same (e.g. `value.lower()` for emails). Add it to `DEFAULT_REDACTORS` in `app/anonymizer.py`. Placeholders, the same-value-same-placeholder rule and restoring come for free. If `find` raises, the whole text is refused (`AnonymizationError`) rather than sent half-cleaned.

**The mandatory middleware (US 5.2.3, AB#41)** can wrap any AI call the same way `ai_filter.py` does: create an `Anonymizer`, call `anonymize()` on everything sent, `restore()` on what comes back, and refuse the call on `AnonymizationError`.

## Connecting to Supabase

1. In the Supabase dashboard open **Settings → API** and copy the **Project URL** and the **anon public** key into the root `.env` (`SUPABASE_URL`, `SUPABASE_KEY`). Never the `service_role` key.
2. Restart. `GET /health` should show `"mode": "supabase"`.

The schema is owned by Epic 1 (project `dsclfcysdrjchhyynggt`). What the backend relies on:

- `tasks`: the columns in `app/db.py` (`COLUMNS`) plus `user_id`, a unique constraint on `(user_id, moodle_id)`, and a foreign key `(user_id, moodle_course_id)` → `courses`.
- `courses`: `user_id`, `moodle_course_id`, `name`, unique on `(user_id, moodle_course_id)`. The backend creates or renames a course when a task arrives with a `moodle_course_id`.
- `users`: one row per student, created automatically on sign-up by the `on_auth_user_created` trigger (`tasks.user_id` references it).
- Row-level security on all three, and `grant ... to authenticated` so the Data API can reach them (the project doesn't expose new tables automatically).

## Not done yet

- **PII anonymization (US 5.2.2, 5.2.3, ADR 0003):** ID numbers are now removed before Gemini (see "Anonymization"). Names and email addresses are still sent as they are, so US 5.2.2 must be done before this goes to production.
- **Real Supabase test (US 3.1.3, 3.2.1, 3.2.2):** the Supabase code matches Epic 1's schema and is unit-tested with fakes, but hasn't run against the real project yet.
- **`is_modified` ("Recently Modified" badge, Epic 3):** the column exists but the backend doesn't set it yet when a deadline changes.
- **Large syncs:** all tasks go to Gemini in one request, and Gemini is called again on every re-sync. Fine for tens of tasks; batching and skipping unchanged tasks would help once real extension data arrives.
- **Rate limiting (US 3.1.4)**.
