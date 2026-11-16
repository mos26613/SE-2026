# Requirements

> **Source of truth:** the Azure DevOps backlog (organization `mogrossm`) and the Project Initiation Document in its wiki. This page summarizes them. Detailed user stories, acceptance criteria and tasks live in Azure Boards. Link to them with `AB#<id>`.

## 1. Vision

Give university students one place to see every Moodle assignment and deadline, warn them when deadlines change, and help them with academic chores through a privacy-safe AI assistant. Setup and running costs are zero, because everything uses free tiers.

## 2. Objectives (SMART)

| # | Objective | Measurable goal |
|---|---|---|
| 1.1 | Centralize learning data | All assignments from all connected courses appear on the dashboard **within 3 seconds** of logging in, with no manual entry. |
| 1.2 | Clear chronological view | Assignments in date order with live countdown timers, plus a semester calendar view up to the end of the semester. |
| 2.1 | Deadline change tracking | Any assignment whose due date the lecturer changed or postponed is highlighted in **bold red** ("Recently Modified"). |
| 2.2 | Smart academic assistance | An AI agent that sets reminders through function calling, and an Appeal Generator that produces a formal appeal draft **within 5 seconds**. |

## 3. Users and external systems

**User roles**

| Role | Needs |
|---|---|
| **Student** (end user) | See all tasks in one place, get countdowns and alerts, manage tasks, chat with the AI, generate appeal letters. |
| **System administrator / DevOps lead** | Monitor the Docker infrastructure and the integrity of the Supabase database, configure row-level security policies, and maintain the CI/CD pipelines. |

**Application domain expert:** academic faculty and learning coordinators, who define how assignments and submissions work.

**External systems**

| System | Role |
|---|---|
| Moodle (institutional LMS) | Source of assignment data, read passively by the extension |
| Google AI Studio / Gemini API | Natural-language chat, function calling, appeal letter generation |
| Google Calendar API | Export of deadlines and reminders |
| Supabase | Authentication (JWT) and PostgreSQL database with row-level security |

## 4. Functional requirements (by epic and feature)

### Epic 1: Infrastructure, Database & Authentication (AB#7)

| Feature | Description | User stories |
|---|---|---|
| 1.1 (AB#179) | User authentication and identity management | Registration, sign-in with JWT, password reset, auth middleware latency (NFR) |
| 1.2 (AB#180) | Core database schema in PostgreSQL | Users/Courses/Tasks schema, indexing for fast queries, migrations, connection pooling (NFR) |
| 1.3 (AB#181) | Information security and row-level security | Multi-tenant row-level security (NFR), secrets management, CORS and rate limiting, anonymization standards |
| 1.4 (AB#182) | Docker, CI/CD and infrastructure | Docker Compose dev environment, GitHub Actions quality gates, multi-stage production build, PR review rules |

### Epic 2: Moodle Scraping & Extension Core (AB#8)

| Feature | Description | User stories |
|---|---|---|
| 2.1 (AB#281) | Extension base (Manifest V3) and popup | Skeleton and manifest, popup status UI, manual sync button, message passing between extension parts |
| 2.2 (AB#282) | Background data collection in the service worker | Service worker lifecycle, detecting Moodle navigation, debounced/throttled sync scheduler, local cache and queue |
| 2.3 (AB#323) | Generic page-scraping script for Moodle | Selectors for assignment pages, calendar and dashboard parser, date parsing, compatibility with Moodle themes and versions |
| 2.4 (AB#344) | Cookies, session expiry and security | Session cookie detection, expiry and re-login alerts, encrypted local storage, secure transport and CORS |

### Epic 3: Backend Sync & Moodle Integration (AB#9)

| Feature | Description | User stories |
|---|---|---|
| 3.1 (AB#365) | Secure API and endpoints | Sync endpoint for the extension, strict payload validation, token-secured endpoints, rate limiting |
| 3.2 (AB#386) | Database upsert and state management | Supabase client, upsert on a unique Moodle ID, timeouts and retries, sync transaction logging |
| 3.3 (AB#407) | Moodle change detection and sync | Detect modified assignments, keep exported calendar events in sync, resolve conflicts with local edits, background worker performance |
| 3.4 (AB#428) | Data export and backup | One-click export of a deadline, bulk export, encryption at rest, lightweight export script |

### Epic 4: User Interface, Dashboard & Time Management (AB#10)

| Feature | Description | User stories |
|---|---|---|
| 4.1 (AB#11) | Central React dashboard, under 3 seconds | Overview of upcoming tasks, load time under 3 s, summary widgets (today / this week / overdue), responsive and accessible |
| 4.2 (AB#12) | Chronological view, filters and countdowns | Sort by deadline, filter by date range, live countdown per task, highlight urgent and overdue tasks |
| 4.3 (AB#13) | Search, course filter, semester calendar | Free-text search, filter by course, semester calendar view, configurable semester dates |
| 4.4 (AB#14) | Google Calendar integration (UI) | Connect a Google account, export button and status on each task card, bulk export screen, connection and sync status panel |

### Epic 5: AI Layer & Academic Automation (AB#6)

| Feature | Description | User stories |
|---|---|---|
| 5.1 (AB#15) | Gemini API connection and AI gateway | Central AI gateway, rate limits and quotas, graceful error handling, versioned system prompts |
| 5.2 (AB#16) | Strict PII anonymization before AI calls | Remove ID numbers, remove names and emails, mandatory anonymization middleware, restore personal details locally in responses |
| 5.3 (AB#17) | Chat agent with function calling | Chat window, answers grounded in real task data, reminders and events from free text, stays in scope and resists misuse |
| 5.4 (AB#18) | AI Appeal Assistant | Submit grader comments and the student's answer, generate a formal letter, within 5 seconds, edit and copy |

## 5. Key user scenarios

| # | Scenario | Triggered by | Expected outcome | Exceptions |
|---|---|---|---|---|
| 1 | **Fetch upcoming assignments and scan workload** | Student opens the dashboard | Date-ordered view with countdowns and a workload meter for the coming week | No assignments ("No upcoming assignments for the next 7 days"); many deadlines at the same time (high-workload alert) |
| 2 | **Deadline change and "Recently Modified" alert** | Lecturer changes a deadline in Moodle | The task shows a red badge, which clears after the student first views it; the new date is saved | Student doesn't log in for a long time; new date is already in the past |
| 3 | **Calendar reminder and appeal generation** | Student uses the AI chat | Event saved to the calendar and database through function calling; or a formal appeal draft ready to copy | Missing details (the AI asks for them); function call fails |
| 4 | **Session expiry and cookie cleanup** | Automatic, when the extension tries to sync | Expired cookies are cleared, automatic syncing stops, and the dashboard shows "Moodle session expired, please log in again" | Network or Moodle downtime mistaken for expiry |
| 5 | **Silent background scraping and refresh within 3 s** | Student browsing Moodle | Data reaches the server and the dashboard updates within about 3 seconds, without interrupting browsing | Moodle page structure changed after an update; server takes longer than 3 s (show cached data and a refresh notice) |

## 6. Non-functional requirements

| ID | Category | Requirement | Related work item |
|---|---|---|---|
| NFR-1 | Performance | Dashboard loads in **under 3 seconds** | AB#20 |
| NFR-2 | Performance | JWT authentication middleware adds **under 50 ms** | AB#201 |
| NFR-3 | Performance | Database task queries respond in **under 100 ms** | AB#211 |
| NFR-4 | Performance | Appeal letter generated in **under 5 seconds** | AB#49 |
| NFR-5 | Security | Each user can access only their own rows, enforced by row-level security (`auth.uid() = user_id`) | AB#226 |
| NFR-6 | Privacy | No personal data (names, ID numbers, emails) is sent to the AI; anonymization is mandatory middleware | AB#41 |
| NFR-7 | Security | Moodle passwords are never stored on or sent to the server; secrets come only from environment variables | AB#231 |
| NFR-8 | Reliability | Database connection pooling, timeouts and retries | AB#221, AB#397 |
| NFR-9 | Load on Moodle | Debounced/throttled syncing and caching, to avoid putting load on institutional servers | AB#313, AB#318 |
| NFR-10 | Usability | Responsive and accessible dashboard | AB#22 |
| NFR-11 | Cost | Setup and running costs of 0 NIS, using free tiers only | — |

## 7. Constraints and assumptions

- **Read-only:** the system only reads Moodle data and never submits assignments or changes grades.
- **No stored credentials:** the extension uses the student's existing Moodle session on the client side.
- **Session management:** expired Moodle session cookies must be detected and handled.
- **Moodle variability:** page structure differs between institutions and versions, so the scraper needs a compatibility layer.
- **Free tiers only:** Supabase, GitHub, Google AI Studio and Docker.
- **Timeline:** one academic semester (12 weeks), in phases A–E: initiation, backlog, infrastructure, three development sprints, and automated testing and closure.

## 8. Out of scope

- Submitting assignments or uploading files to Moodle.
- Managing, changing or calculating grades.
- Browsers other than Google Chrome.
- Storing Moodle usernames or passwords.

## 9. Glossary

| Term | Meaning |
|---|---|
| **DOM scraping** | Reading assignment data directly from the HTML of Moodle pages |
| **RLS (Row Level Security)** | A PostgreSQL feature that isolates each user's rows from everyone else's |
| **PII stripping** | Removing personally identifiable information (names, ID numbers, emails) before data is sent to the AI |
| **Function calling** | The AI model's ability to trigger system functions, such as adding a calendar event |
| **Upsert** | Insert a record, or update it if it already exists |
