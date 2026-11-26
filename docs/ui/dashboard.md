# Dashboard: wireframe and components

User Story 4.1.1 (AB#19), task 4.1.1.1 (AB#107); summary widgets: User Story 4.1.3 (AB#21), task AB#53. Flow: `uml-sprint1/e_dashboard` (process e).

## Wireframe

```
┌──────────────────────────────────────────────────────────┐
│ My tasks                                       Sign out  │  header
├──────────────────────────────────────────────────────────┤
│ [ Overdue ] [ Due today ] [ This week ]                  │  summary widgets: US 4.1.3 (AB#21)
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
             ├── SummaryWidgets    US 4.1.3: overdue / due today / this week
             └── TaskCard × n      title, course, deadline, status, AI summary
```

## Summary widgets (US 4.1.3, AB#21)

| Widget | Counts | Backend rule (`GET /api/tasks/summary`) |
|---|---|---|
| Overdue | open tasks whose deadline has passed | `due < now` |
| Due today | open tasks due within 24 hours | `now <= due < now + 24 h` |
| This week | open tasks due within 7 days (the 24-hour ones included) | `now <= due < now + 7 days` |

- The windows run from the moment of the request, not from calendar days.
- Tasks without a due date, tasks marked done and tasks Gemini filtered out are not counted, so the numbers match the list below.
- The dashboard loads the summary together with the list. If the summary fails, the widgets show a dash and the list still works; **Retry** reloads both. The numbers are read again on every load, so they change after the next sync.

## Decisions

- **The backend is the only data source.** The dashboard sends the Supabase session token to `GET /api/tasks`; it never queries tables directly. The same rules (validation, AI filter, RLS) apply to every client.
- **Order comes from the backend** (`due_date` ascending, no date last), which the `idx_tasks_user_due` index returns without sorting (docs/performance/indexing.md).
- **Deadlines are shown in Israel time** (`Asia/Jerusalem`), matching Moodle, whatever the browser's time zone.
- **Hidden tasks:** items Gemini marked "not relevant" are not shown (`include_filtered` is off).
- **Hebrew:** titles, course names and summaries use `dir="auto"`, so Hebrew text is right-aligned.
