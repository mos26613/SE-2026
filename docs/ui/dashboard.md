# Dashboard: wireframe and components

User Story 4.1.1 (AB#19), task 4.1.1.1 (AB#107). Flow: `uml-sprint1/e_dashboard` (process e).

## Wireframe

```
┌──────────────────────────────────────────────────────────┐
│ My tasks                                       Sign out  │  header
├──────────────────────────────────────────────────────────┤
│ [ Due today ] [ This week ] [ Overdue ]                  │  widgets: US 4.1.3 (AB#21), later
├──────────────────────────────────────────────────────────┤
│ 12 tasks from 4 courses                                  │
│ ┌──────────────────────────────────────────────┐         │
│ │ Midterm exam                            Open │         │  task card (AB#109)
│ │ Calculus 1                                   │         │
│ │ Tue, 1 Dec 2026, 09:00                       │         │
│ │ Study chapters 1-5          (AI summary)     │         │
│ └──────────────────────────────────────────────┘         │
│ ┌──────────────────────────────────────────────┐         │
│ │ ...                                          │         │  soonest deadline first;
│ └──────────────────────────────────────────────┘         │  date sections: US 4.2.1 (AB#23)
└──────────────────────────────────────────────────────────┘
```

Other states replace the list (AB#110):

| State | When | Shows |
|---|---|---|
| Loading | While `GET /api/tasks` runs | "Loading your tasks…" |
| Empty | The API returns no tasks | "No tasks yet" + how to sync with the extension |
| Error | Network error or 5xx | The error + **Retry** |
| Signed out | No session, or the API answers 401 | Redirect to `/login` |

## Components

```
App (routes, session)
├── /login → LoginPage            placeholder until US 1.1.2 (AB#188)
└── /      → DashboardPage        loads tasks, picks the state
             ├── (SummaryWidgets)  US 4.1.3, later
             └── TaskCard × n      title, course, deadline, status, AI summary
```

## Decisions

- **The backend is the only data source.** The dashboard sends the Supabase session token to `GET /api/tasks`; it never queries tables directly. The same rules (validation, AI filter, RLS) apply to every client.
- **Order comes from the backend** (`due_date` ascending, no date last), which the `idx_tasks_user_due` index returns without sorting (docs/performance/indexing.md).
- **Deadlines are shown in Israel time** (`Asia/Jerusalem`), matching Moodle, whatever the browser's time zone.
- **Hidden tasks:** items Gemini marked "not relevant" are not shown (`include_filtered` is off).
- **Hebrew:** titles, course names and summaries use `dir="auto"`, so Hebrew text is right-aligned.
