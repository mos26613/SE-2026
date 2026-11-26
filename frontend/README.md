# Frontend (React dashboard)

The student's dashboard: all upcoming tasks from all synced Moodle courses on one screen (User Story 4.1.1, AB#19). Built with React + Vite.

```
Browser ──sign in──▶ Supabase Auth (session token)
        ──GET /api/tasks (Bearer token)──▶ FastAPI backend ──▶ Supabase (RLS)
```

The dashboard never reads the database directly: it only calls our backend, with the student's token.

## Layout

| Path | What it does |
|---|---|
| `src/App.jsx` | Routes: `/` dashboard (signed-in only), `/login` sign-in |
| `src/pages/DashboardPage.jsx` | Loads the tasks and shows the loading, error, empty or list state |
| `src/components/TaskCard.jsx` | One task: title (links to Moodle), course, deadline in Israel time, status |
| `src/pages/LoginPage.jsx` | **Placeholder** email/password sign-in until US 1.1.2 (AB#188) |
| `src/api.js` | Calls the backend |
| `src/supabase.js` | Supabase client, used only for sign-in |
| `src/config.js` | Settings from the root `.env` |
| `src/test/` | Tests (Vitest + React Testing Library) |

Design notes and the wireframe: [docs/ui/dashboard.md](../docs/ui/dashboard.md).

## Setup

Needs Node.js 20 or newer.

1. Add the dashboard settings to the **root** `.env` (see `.env.example`). Use the same values as `SUPABASE_URL` and `SUPABASE_KEY`:
   ```
   VITE_API_URL=http://localhost:8000
   VITE_SUPABASE_URL=https://<project>.supabase.co
   VITE_SUPABASE_ANON_KEY=<the anon public key>
   ```
   Only `VITE_*` values reach the browser, and they end up in the JavaScript anyone can read. That's fine for the anon key (Row Level Security protects the data), but **never** put the `service_role` key or `GEMINI_API_KEY` in a `VITE_` variable.
2. Install: `npm install` (in `frontend/`).

## Running it

Start the backend first (see `backend/README.md`), then in `frontend/`:

```
npm run dev
```

Open http://localhost:5173 and sign in with a Supabase test user. The backend already allows this origin (`CORS_ORIGINS`).

With Docker, `docker compose up --build` from the repo root builds the app and serves it on http://localhost:3000. The `VITE_*` values are read from the root `.env` at build time, so rebuild after changing them.

## Tests

```
npm test
```

| Test | Covers |
|---|---|
| `dashboard.test.jsx` | Tasks from all courses shown in API order (AC 1), empty state (AC 2), loading, error + Retry, unreachable server, 401 → sign-in page, token sent to the API |
| `taskCard.test.jsx` | Card fields, Israel-time deadline, Moodle link, missing course/deadline, done status, Hebrew titles |
| `app.test.jsx` | Signed-out → sign-in page, signed-in → dashboard |

## Not done yet (other stories)

- Summary widgets: today / this week / overdue (US 4.1.3, AB#21). The slot is marked in `DashboardPage.jsx`.
- Date sections (US 4.2.1, AB#23). The list already comes sorted by deadline from the backend.
- Load time under 3 s (US 4.1.2, AB#20).
- Real sign-in, sign-up and password reset (US 1.1.2, AB#188).
