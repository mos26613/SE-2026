# Chrome extension (Moodle sync)

Manifest V3 extension that reads the student's assignments from Moodle (read-only) and sends them to the backend (`POST /api/tasks/sync`). Epic 2.

## Files

| File | What it does |
|---|---|
| `manifest.json` | Permissions, the Moodle host, which scripts run where |
| `moodle.js` | Pure helpers: asks Moodle's calendar service for deadlines and converts them to the backend's task format; text cleanup. Tested in `tests/` |
| `content.js` | Runs on Moodle pages. Gets the tasks (calendar service first, page scraping as fallback) |
| `background.js` | Checks the Moodle session, sends tasks to the backend, keeps the sync status |
| `popup.html`, `popup.js` | The popup: status, last sync time, Sync Now, temporary token box |

## Where the tasks come from (US 2.3.1, AB#478)

1. **Moodle's calendar service** `core_calendar_get_action_events_by_timesort`, the same read-only request Moodle's own Timeline block makes. `content.js` sends it from the Moodle tab with the student's existing session and the page's `sesskey`. It returns every upcoming (and up to 30 days overdue) deadline with the exact due time, course name and id, and link, on any Moodle page or theme.
   - Only activity types with real deadlines are kept (`assign`, `quiz`, `workshop`, ... see `DEADLINE_MODULES` in `moodle.js`); Zoom lessons and the like are skipped.
   - Titles are cleaned: Moodle's "יש להגיש את '…'" / "… is due" wrapper, invisible RTL marks and extra whitespace are removed.
2. **Fallback: page scraping** (the Timeline / Upcoming events blocks, or a single activity page) if the service isn't available, e.g. an old Moodle version.

Checked on moodle.jct.ac.il (Nov 2026): the service returned all 24 upcoming events. The JCT dashboard shows a month calendar whose items carry no due time or course, so scraping alone can't produce complete tasks there.

## Trying it

1. Start the backend (`backend/README.md`).
2. Chrome → `chrome://extensions` → Developer mode → **Load unpacked** → this `extension/` folder.
3. Paste a Supabase login token into the popup's token box (temporary until sign-in is built into the extension).
4. Open Moodle, click the extension icon → **Sync Now**. The tasks appear on the dashboard (http://localhost:5173).

After changing a file, click the reload arrow on the extension in `chrome://extensions` and refresh the Moodle tab.

## Tests

Node's built-in test runner, no install needed. From the repo root:

```
node --test "extension/tests/*.test.js"
```
