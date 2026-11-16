# 0002. Technology stack

- **Status:** Accepted
- **Date:** 2026-11-16
- **Deciders:** MASHAB team (recorded from the Project Initiation Document)

## Context

The system has to read assignment data from Moodle in the student's browser, store it securely per user, show it in a modern web dashboard, and add AI features. It has to be built by a four-person student team in one 12-week semester, at zero cost.

## Options considered

1. **Chrome extension + FastAPI + Supabase + React + Gemini.** The extension can use the student's own Moodle session, so no credentials are stored. FastAPI is light and Python-friendly for the AI work. Supabase provides Auth, PostgreSQL and row-level security on a free tier. Gemini through Google AI Studio supports function calling on a free tier.
2. **Server-side Moodle scraping.** Would need the student's Moodle credentials on the server, which is unacceptable for security and privacy.
3. **Self-hosted PostgreSQL with custom auth.** More work and more to secure, with no benefit for a project of this size.

## Decision

| Layer | Choice |
|---|---|
| Data collection | Chrome Extension, Manifest V3 |
| Frontend | React |
| Backend | Python + FastAPI, containerized with Docker |
| Database and auth | Supabase (PostgreSQL + row-level security, Supabase Auth with JWT) |
| AI | Google AI Studio / Gemini API |
| Integrations | Google Calendar API |
| CI/CD and testing | GitHub Actions, Pytest, Playwright / Selenium |

## Consequences

- Only Chrome is supported.
- The scraper depends on Moodle's page structure and needs a compatibility layer for different themes and versions.
- Free-tier limits (Supabase, Gemini) need rate limiting and quotas in the backend.
- Two languages are in use (Python and JavaScript), each with its own tools.
