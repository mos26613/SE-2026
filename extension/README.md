# Chrome extension (Moodle sync)

Manifest V3 extension that reads the student's assignments from Moodle (read-only) and sends them to the backend (`POST /api/tasks/sync`). Epic 2.

## Files

| File | What it does |
|---|---|
| `manifest.json` | Permissions, the Moodle host, which scripts run where |
| `moodle.js` | Pure helpers: asks Moodle's calendar service for deadlines and converts them to the backend's task format; text cleanup. Tested in `tests/` |
| `dom_scraper.js` | The fallback: reads tasks from the page itself (Timeline / Upcoming events blocks, a single activity page). Tested with saved Moodle pages in `tests/fixtures/` |
| `content.js` | Runs on Moodle pages. Gets the tasks (calendar service first, page scraping as fallback); on ordinary page loads asks Moodle at most once per 15 minutes |
| `package.json` | Test tooling only (`jsdom` for the fallback tests). The extension itself has no dependencies |
| `background.js` | Checks the Moodle session, sends tasks to the backend, keeps the sync status |
| `popup.html`, `popup.js` | The popup: status, last sync time, Sync Now, temporary token box |

## Where the tasks come from (US 2.3.1, AB#478)

1. **Moodle's calendar service** `core_calendar_get_action_events_by_timesort`, the same read-only request Moodle's own Timeline block makes. `content.js` sends it from the Moodle tab with the student's existing session and the page's `sesskey`. It returns every upcoming (and up to 30 days overdue) deadline with the exact due time, course name and id, and link, on any Moodle page or theme.
   - Only activity types with real deadlines are kept (`assign`, `quiz`, `workshop`, ... see `DEADLINE_MODULES` in `moodle.js`); Zoom lessons and the like are skipped.
   - Titles are cleaned: Moodle's "יש להגיש את '…'" / "… is due" wrapper, invisible RTL marks and extra whitespace are removed.
2. **Fallback: page scraping** (`dom_scraper.js`: the Timeline / Upcoming events blocks, or a single activity page) if the service isn't available, e.g. an old Moodle version.

Why the calendar service is the main source, and the risk that comes with it: [ADR 0004](../docs/adr/0004-moodle-calendar-service.md).

**Load on Moodle (NFR-9):** `content.js` runs on every Moodle page, so on ordinary page loads it asks Moodle at most **once per 15 minutes** (`PASSIVE_FETCH_INTERVAL_MS` in `moodle.js`, time of the last request in `chrome.storage.local` as `lastMoodleFetch`). **Sync Now** always asks. When there are no upcoming assignments, Sync Now shows "אין מטלות קרובות" (a normal state, Scenario 1), not an error.

Checked on moodle.jct.ac.il (Nov 2026): the service returned all 24 upcoming events. The JCT dashboard shows a month calendar whose items carry no due time or course, so scraping alone can't produce complete tasks there.

## Trying it

1. Start the backend (`backend/README.md`).
2. Chrome → `chrome://extensions` → Developer mode → **Load unpacked** → this `extension/` folder.
3. Paste a Supabase login token into the popup's token box (temporary until sign-in is built into the extension).
4. Open Moodle, click the extension icon → **Sync Now**. The tasks appear on the dashboard (http://localhost:5173).

After changing a file, click the reload arrow on the extension in `chrome://extensions` and refresh the Moodle tab.

## Tests

Node's built-in test runner, plus `jsdom` for the fallback tests that load saved Moodle pages. From `extension/`:

```
npm install
npm test
```

`tests/moodle.test.js` covers the calendar service and the throttle; `tests/dom_scraper.test.js` runs the fallback on the pages in `tests/fixtures/` (Timeline block, Upcoming events block in Hebrew, an assignment page, empty placeholders, and a month calendar without due times like JCT's dashboard). `node_modules/` is ignored by Git; loading the folder unpacked in Chrome works with or without it.
