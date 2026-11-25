# 0004. Read deadlines from Moodle's calendar service, with page scraping as a fallback

- **Status:** Accepted
- **Date:** 2026-11-25
- **Deciders:** Moshe Grossman (US 2.3.1 owner), after review feedback on PR #15
- **Work item:** User Story 2.3.1 (AB#478)

## Context

The extension has to collect every assignment and its exact deadline from the student's Moodle. The original plan (US 2.3.1 acceptance criteria, UML diagram b) was to read them from the page with resilient CSS/XPath selectors.

On moodle.jct.ac.il (checked in November 2026) that isn't enough. The dashboard shows a month calendar whose items have a link but **no due time and no course**, so the page alone can't produce complete tasks. Selectors also break whenever the institution changes theme or upgrades Moodle (US 2.3.4).

Moodle's own Timeline block gets its data from the calendar web service `core_calendar_get_action_events_by_timesort`, through `lib/ajax/service.php`, with the student's session and the page's `sesskey`. It returns every upcoming deadline with the exact time, the course id and name, and the link.

## Options considered

1. **Page scraping only** (the original plan). No dependency on Moodle internals, but incomplete on JCT's dashboard and fragile across themes and versions.
2. **The calendar service only.** Complete and theme-independent, but if the service is missing or changes, the extension gets nothing.
3. **The calendar service first, page scraping as a fallback.** Complete where the service works, and still collects what the page shows where it doesn't.

## Decision

Option 3.

- `extension/moodle.js` calls `core_calendar_get_action_events_by_timesort` from the Moodle tab. The request is read-only and is the same one Moodle's Timeline block sends; no password or token leaves the browser. It keeps only activity types with real deadlines (`assign`, `quiz`, ...), reads up to 4 pages of 50 events, and includes deadlines up to 30 days overdue.
- If the call fails for any reason (no `sesskey`, an HTTP error, a Moodle error code), `extension/dom_scraper.js` reads the page with selectors as before.
- Both return tasks directly in the backend's format (`moodle_id`, `title`, `course_name`, `moodle_course_id`, `description`, `due_date`, `moodle_url`), so nothing has to be renamed in between.
- **Load on Moodle (NFR-9):** on ordinary page loads the extension asks Moodle at most once per 15 minutes. A manual "Sync Now" always asks.

## Consequences

- Complete, exact deadlines on JCT, independent of the theme.
- **Risk: the service is internal to Moodle.** Its name, parameters or answer can change between Moodle versions, and an institution can restrict it. In that case the fallback takes over automatically, with less complete data. `extension/tests/moodle.test.js` documents the answer shape we rely on, so a change shows up as a failing test once a new sample answer is added.
- The acceptance criteria of US 2.3.1 and UML diagram b are updated to describe this, and the task fields use the backend's names instead of `courseId`, `assignmentName`, `dueDate` and `link`.
- The selectors are still maintained, as the fallback, and are tested with saved Moodle pages (`extension/tests/fixtures/`).
