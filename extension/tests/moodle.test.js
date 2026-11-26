// Tests for extension/moodle.js (User Story 2.3.1, AB#478).
// Run from the repo root:  node --test extension/tests/
// Uses only Node's built-in test runner: no npm install, nothing extra inside extension/.
const test = require("node:test");
const assert = require("node:assert/strict");
const M = require("../moodle.js");

// Shaped like a real core_calendar_get_action_events_by_timesort answer from moodle.jct.ac.il
// (Nov 2026), with made-up ids.
const EVENTS = [
  {
    id: 900001, name: "שיעור יום ב 10:30", modulename: "zoom", timesort: 1795509000,
    url: "https://moodle.example.ac.il/mod/zoom/view.php?id=111", course: { id: 75107, fullname: "151103.3.5786 - מעבדה במבנה המחשב" },
  },
  {
    id: 900002, name: "יש להגיש את 'הגשת תרגיל עיוני 4  Submission box for theoretical assignment 4'",
    activityname: "", modulename: "assign", timesort: 1795730340,
    url: "https://moodle.example.ac.il/mod/assign/view.php?id=971083",
    course: { id: 78317, fullname: "151131.2.5787 - ‏קומפיילרים ומתרגמים" },
    description: "<p>Submit a <b>PDF</b>&nbsp;file.</p>",
  },
  {
    id: 900003, name: "Quiz 2 closes", activityname: "Quiz 2", modulename: "quiz", timesort: 1796000000,
    url: "https://moodle.example.ac.il/mod/quiz/view.php?id=555#section", course: { id: 78222, fullname: "Databases" },
  },
];

function fakeFetch(pages) {
  const calls = [];
  const fn = async (url, options) => {
    calls.push({ url, body: JSON.parse(options.body) });
    const page = pages.shift();
    if (page instanceof Error) throw page;
    return { ok: page.status ? page.status < 400 : true, status: page.status || 200, json: async () => page.body };
  };
  fn.calls = calls;
  return fn;
}

const ok = (events) => ({ body: [{ error: false, data: { events } }] });
const NOW = Date.UTC(2026, 10, 23, 12, 0, 0);

test("cleanText removes extra whitespace and invisible RTL characters", () => {
  assert.equal(M.cleanText("  ‏הגשת‫   תרגיל\n1‎ "), "הגשת תרגיל 1");
  assert.equal(M.cleanText(null), "");
});

test("stripHtml removes tags and entities", () => {
  assert.equal(M.stripHtml("<p>Submit a <b>PDF</b>&nbsp;file.</p><script>x()</script>"), "Submit a PDF file.");
});

test("cleanEventTitle removes Moodle's 'is due' wrappers", () => {
  assert.equal(M.cleanEventTitle("יש להגיש את 'הגשת תרגיל 1'"), "הגשת תרגיל 1");
  assert.equal(M.cleanEventTitle("Assignment 1 is due"), "Assignment 1");
  assert.equal(M.cleanEventTitle("Quiz 2 closes"), "Quiz 2");
  assert.equal(M.cleanEventTitle("Plain title"), "Plain title");
});

test("findSesskey reads the key from the page HTML", () => {
  assert.equal(M.findSesskey('<a href="/login/logout.php?sesskey=AbC123xyZ9">'), "AbC123xyZ9");
  assert.equal(M.findSesskey('M.cfg = {"sesskey":"Q1w2E3r4T5"}'), "Q1w2E3r4T5");
  assert.equal(M.findSesskey("<html></html>"), null);
});

test("eventToTask returns the backend's task shape", () => {
  assert.deepEqual(M.eventToTask(EVENTS[1]), {
    moodle_id: "971083",
    title: "הגשת תרגיל עיוני 4 Submission box for theoretical assignment 4",
    course_name: "151131.2.5787 - קומפיילרים ומתרגמים",
    moodle_course_id: 78317,
    description: "Submit a PDF file.",
    due_date: "2026-11-26T21:59:00.000Z", // 23:59 Israel time
    moodle_url: "https://moodle.example.ac.il/mod/assign/view.php?id=971083",
  });
});

test("eventToTask prefers activityname and drops the #fragment", () => {
  const task = M.eventToTask(EVENTS[2]);
  assert.equal(task.title, "Quiz 2");
  assert.equal(task.moodle_url, "https://moodle.example.ac.il/mod/quiz/view.php?id=555");
});

test("eventToTask skips lessons (Zoom) and events without a date", () => {
  assert.equal(M.eventToTask(EVENTS[0]), null);
  assert.equal(M.eventToTask({ ...EVENTS[1], timesort: 0 }), null);
});

test("fetchEventsFromMoodle calls the calendar service and maps the answer", async () => {
  const fetchFn = fakeFetch([ok(EVENTS)]);
  const tasks = await M.fetchEventsFromMoodle({ baseUrl: "https://moodle.example.ac.il", sesskey: "KEY123abc", fetchFn, now: NOW });

  assert.equal(fetchFn.calls.length, 1);
  assert.equal(fetchFn.calls[0].url, "https://moodle.example.ac.il/lib/ajax/service.php?sesskey=KEY123abc&info=core_calendar_get_action_events_by_timesort");
  const [call] = fetchFn.calls[0].body;
  assert.equal(call.methodname, "core_calendar_get_action_events_by_timesort");
  assert.equal(call.args.timesortfrom, Math.floor(NOW / 1000) - 30 * 86400);
  assert.deepEqual(tasks.map((t) => t.moodle_id), ["971083", "555"]); // the Zoom lesson is left out
});

test("fetchEventsFromMoodle follows pages until a short page", async () => {
  const page1 = Array.from({ length: 50 }, (_, i) => ({ ...EVENTS[1], id: i + 1, url: `https://m/mod/assign/view.php?id=${i + 1}` }));
  const fetchFn = fakeFetch([ok(page1), ok([EVENTS[2]])]);
  const tasks = await M.fetchEventsFromMoodle({ baseUrl: "https://m", sesskey: "KEY123abc", fetchFn, now: NOW });
  assert.equal(tasks.length, 51);
  assert.equal(fetchFn.calls[1].body[0].args.aftereventid, 50);
});

test("fetchEventsFromMoodle fails clearly so content.js can fall back to the DOM", async () => {
  await assert.rejects(M.fetchEventsFromMoodle({ baseUrl: "https://m", sesskey: null, fetchFn: fakeFetch([]) }), /sesskey/);
  await assert.rejects(
    M.fetchEventsFromMoodle({ baseUrl: "https://m", sesskey: "KEY123abc", fetchFn: fakeFetch([{ body: [{ error: true, exception: { errorcode: "invalidsesskey" } }] }]) }),
    /invalidsesskey/,
  );
  await assert.rejects(M.fetchEventsFromMoodle({ baseUrl: "https://m", sesskey: "KEY123abc", fetchFn: fakeFetch([{ status: 503, body: {} }]) }), /503/);
});

test("isPassiveFetchDue allows one Moodle request per 15 minutes on page loads", () => {
  const now = Date.UTC(2026, 10, 25, 12, 0);
  const minutes = (n) => n * 60 * 1000;
  assert.equal(M.PASSIVE_FETCH_INTERVAL_MS, minutes(15));
  assert.equal(M.isPassiveFetchDue(undefined, now), true); // never asked yet
  assert.equal(M.isPassiveFetchDue(0, now), true);
  assert.equal(M.isPassiveFetchDue(now - minutes(1), now), false);
  assert.equal(M.isPassiveFetchDue(now - minutes(14), now), false);
  assert.equal(M.isPassiveFetchDue(now - minutes(15), now), true);
  assert.equal(M.isPassiveFetchDue(now + minutes(60), now), true); // clock moved back
});
