# Architecture

> **Status:** design (Phase A). Based on the Project Initiation Document and the context diagram in the Azure DevOps wiki. Update it as the implementation makes things concrete, and record significant decisions as [ADRs](adr/).

## 1. Overview

Smart Student Task Hub uses a **client-server architecture made of containerized services**:

1. A **Chrome extension** collects assignment data from Moodle pages in the student's browser.
2. A **FastAPI backend** in Docker validates, stores and processes that data, and is the only component that talks to the AI and Google Calendar.
3. **Supabase** provides authentication (JWT) and a PostgreSQL database protected by row-level security.
4. A **React dashboard** shows the student's tasks and hosts the AI chat and the Appeal Assistant.
5. **Google Gemini** receives only anonymized data.

## 2. Context diagram

```mermaid
flowchart TB
    Moodle[("Institutional Moodle portal")]
    subgraph Hub["Smart Student Task Hub"]
        Ext["Chrome extension<br/>(Manifest V3)"]
        UI["React dashboard"]
        API["FastAPI backend<br/>(Docker)"]
    end
    DB[("Supabase<br/>PostgreSQL + Auth")]
    AI["Google AI Studio<br/>(Gemini API)"]
    Cal["Google Calendar API"]

    Moodle -- "page data<br/>(passive scraping)" --> Ext
    Ext -- "REST / JWT" --> API
    UI -- "REST / JWT" --> API
    API -- "SQL with row-level security<br/>data and auth" --> DB
    API -- "anonymized prompts<br/>and function responses" --> AI
    API -- "OAuth2<br/>event export" --> Cal
```

The original diagram is on the wiki page *Project Overview → Architecture & Context Diagram*.

## 3. Subsystems

| # | Subsystem (epic) | Responsibilities | Technology |
|---|---|---|---|
| 1 | **Infrastructure, Database & Auth** | Registration and sign-in, JWT, PostgreSQL schema and migrations, row-level security policies, secrets, CORS and rate limiting, Docker images, CI/CD | Supabase, PostgreSQL, Docker, GitHub Actions |
| 2 | **Moodle Extension Core** | Manifest V3 extension, background service worker, content scripts that read Moodle pages, date parsing, throttled sync with a local cache and queue, session/cookie monitoring, popup UI | Chrome Extensions API, JavaScript/TypeScript |
| 3 | **Backend Sync Engine** | Sync endpoint, payload validation, upsert by Moodle ID, "Recently Modified" change detection, conflict handling, caching, sync logging, calendar export | Python, FastAPI, Pydantic, Supabase client |
| 4 | **React Dashboard & UI** | Date-ordered task list, countdowns, summary widgets, search and filters, semester calendar, Google Calendar connection and export UI | React |
| 5 | **AI Layer** | AI gateway with quotas and error handling, versioned system prompts, PII anonymization middleware, chat agent with function calling, Appeal Assistant | Gemini API (Google AI Studio) |

## 4. Main flows

### 4.1 Silent sync (scenarios 2 and 5)

```mermaid
sequenceDiagram
    participant S as Student (browsing Moodle)
    participant E as Extension
    participant A as FastAPI
    participant D as Supabase
    participant U as Dashboard
    S->>E: Opens a Moodle page
    E->>E: Content script reads tasks and parses dates
    E->>E: Throttle/debounce, queue in local cache
    E->>A: POST sync payload (JWT)
    A->>A: Validate payload
    A->>D: Upsert tasks by Moodle ID
    A->>A: Compare due dates and set is_modified
    U->>A: GET tasks (JWT)
    A->>D: Query (row-level security applies)
    A-->>U: Tasks, with "Recently Modified" flags
```

Target: the dashboard is up to date within about **3 seconds**.

### 4.2 AI request (scenario 3)

```mermaid
sequenceDiagram
    participant U as Dashboard (chat)
    participant A as FastAPI AI gateway
    participant P as PII anonymization middleware
    participant G as Gemini API
    participant D as Supabase
    U->>A: Natural-language request (JWT)
    A->>P: Prompt plus task context
    P->>P: Replace names, IDs and emails with placeholders
    P->>G: Anonymized prompt (system instructions, tools)
    G-->>A: Answer or function call (e.g. create_reminder)
    A->>D: Run the function (e.g. save the event)
    A->>P: Restore personal details locally
    A-->>U: Final answer
```

## 5. Data model

Logical entities (to be finalized in the Supabase migrations):

```mermaid
erDiagram
    USERS ||--o{ COURSES : has
    USERS ||--o{ TASKS : owns
    COURSES ||--o{ TASKS : contains
    USERS {
        uuid id PK "auth.users"
        text email
        timestamptz created_at
    }
    COURSES {
        uuid id PK
        uuid user_id FK
        int moodle_course_id "not null"
        text name
    }
    TASKS {
        uuid id PK
        uuid course_id FK
        uuid user_id FK
        text title
        timestamptz due_date "B-tree index"
        boolean is_modified "default false"
        text description
    }
```

**Indexes.** Every task query is limited to one student, so each composite index starts with `user_id`: `(user_id, due_date)` serves the dashboard's "soonest deadline first" query, `(user_id, moodle_course_id)` serves the course link, and the unique `(user_id, moodle_id)` serves the sync upsert. The full list, the `EXPLAIN` results and the 100 ms target are in [performance/indexing.md](performance/indexing.md) (US 1.2.2).

## 6. Security and privacy

- **Row-level security** on every user table: `auth.uid() = user_id`. Policies, privileges and tests are in [security/rls.md](security/rls.md) (US 1.3.1).
- **JWT** from Supabase Auth on every request from the extension and the dashboard.
- **No Moodle passwords** are stored or sent; the extension uses the student's existing session on the client side.
- **PII anonymization** on the server is mandatory before any Gemini request, and personal details are restored only locally ([ADR 0003](adr/0003-anonymize-pii-before-ai.md)).
- **Secrets** (Supabase keys, Gemini key, Google OAuth credentials) come only from environment variables or GitHub Actions secrets and are never committed.
- **CORS and rate limiting** on the API; encrypted local storage in the extension.

## 7. Communication

REST over HTTPS with JSON payloads. The extension and the dashboard talk only to the FastAPI backend. Only the backend talks to Gemini and Google Calendar.

## 8. Deployment and environments

| Environment | Description |
|---|---|
| Local development | Docker Compose: FastAPI container, with a Supabase project or local Supabase |
| CI | GitHub Actions: lint, tests and Docker build on every pull request |
| Production | Multi-stage Docker image for the backend; Supabase cloud (free tier) |

_Hosting for the backend and dashboard is still to be decided. Record the choice in an ADR._

## 9. Testing strategy

| Level | Tools | Focus |
|---|---|---|
| Unit | Pytest (backend), a JS test runner (extension, React) | Parsing, upsert and change detection, anonymization |
| Integration | Pytest with a test Supabase database | API plus database plus row-level security |
| End-to-end | Playwright / Selenium | Extension → backend → dashboard flows |
| Non-functional | Load and timing checks | Dashboard < 3 s, auth middleware < 50 ms, queries < 100 ms, appeal letter < 5 s |

## 10. Open questions

- Hosting for the backend and dashboard.
- Language for the extension and frontend (JavaScript or TypeScript).
- Extension packaging and distribution (unpacked vs Chrome Web Store).
