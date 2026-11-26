// Tests for the DOM fallback, extension/dom_scraper.js (US 2.3.1 AB#478, task 2.3.1.4).
// They load saved Moodle pages from tests/fixtures/ with jsdom.
// Run from extension/:  npm install  (once), then  npm test
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");
const S = require("../dom_scraper.js");

function page(name, url) {
  const html = fs.readFileSync(path.join(__dirname, "fixtures", name), "utf8");
  return { doc: new JSDOM(html, { url }).window.document, url };
}

// Dates without a time zone are read in local time, like in the student's browser.
const local = (y, m, d, h, min) => new Date(y, m - 1, d, h, min).toISOString();

test("Timeline block: real items become tasks, placeholders and dateless items are skipped", () => {
  const { doc, url } = page("dashboard_timeline.html", "https://moodle.example.ac.il/my/");
  const tasks = S.scrapeDom(doc, url);

  assert.equal(tasks.length, 2);
  assert.deepEqual(tasks[0], {
    moodle_id: "971083",
    title: "הגשת תרגיל 1",
    course_name: "קומפיילרים ומתרגמים",
    moodle_course_id: 78317,
    description: "",
    due_date: local(2026, 11, 30, 23, 59),
    moodle_url: "https://moodle.example.ac.il/mod/assign/view.php?id=971083",
  });
  assert.equal(tasks[1].moodle_id, "555");
  assert.equal(tasks[1].title, "Quiz 2");
  assert.equal(tasks[1].moodle_course_id, 78222);
  assert.equal(tasks[1].due_date, local(2026, 12, 6, 9, 30));
});

test("Upcoming events block in Hebrew: month name, course from the breadcrumbs", () => {
  const { doc, url } = page("upcoming_block.html", "https://moodle.example.ac.il/course/view.php?id=75107");
  const [task] = S.scrapeDom(doc, url);

  assert.equal(task.moodle_id, "812345");
  assert.equal(task.title, "דוח מעבדה 3");
  assert.equal(task.course_name, "מעבדה במבנה המחשב");
  assert.equal(task.moodle_course_id, 75107);
  assert.equal(task.due_date, local(2026, 12, 7, 23, 59));
});

test("Single assignment page: title, due date, course and description", () => {
  const { doc, url } = page("assign_view.html", "https://moodle.example.ac.il/mod/assign/view.php?id=971099#top");
  const tasks = S.scrapeDom(doc, url);

  assert.deepEqual(tasks, [
    {
      moodle_id: "971099",
      title: "הגשת תרגיל 2",
      course_name: "קומפיילרים ומתרגמים",
      moodle_course_id: 78317,
      description: "יש להגיש קובץ PDF אחד.",
      due_date: local(2026, 12, 13, 18, 0),
      moodle_url: "https://moodle.example.ac.il/mod/assign/view.php?id=971099",
    },
  ]);
});

test("Month calendar without due times (moodle.jct.ac.il dashboard): nothing incomplete is sent", () => {
  const { doc, url } = page("month_calendar.html", "https://moodle.example.ac.il/my/");
  assert.deepEqual(S.scrapeDom(doc, url), []);
});

test("The same activity on the page twice is returned once", () => {
  const { doc } = page("dashboard_timeline.html", "https://moodle.example.ac.il/my/");
  const list = doc.querySelector('[data-region="event-list-container"]');
  list.append(list.querySelector('[data-course-id="78317"]').cloneNode(true));
  const ids = S.scrapeDom(doc, "https://moodle.example.ac.il/my/").map((t) => t.moodle_id);
  assert.deepEqual(ids, ["971083", "555"]);
});

test("parseMoodleDateToISO reads numeric, Hebrew and English dates, and rejects junk", () => {
  assert.equal(S.parseMoodleDateToISO("30/11/2026 23:59"), local(2026, 11, 30, 23, 59));
  assert.equal(S.parseMoodleDateToISO("6.12.26, 09:30"), local(2026, 12, 6, 9, 30));
  assert.equal(S.parseMoodleDateToISO("מועד הגשה: יום ראשון, 13 בדצמבר 2026, 18:00"), local(2026, 12, 13, 18, 0));
  assert.equal(S.parseMoodleDateToISO("Due date: 2026-12-01T23:59:00+02:00"), "2026-12-01T21:59:00.000Z");
  assert.equal(S.parseMoodleDateToISO("לא נקבע"), null);
  assert.equal(S.parseMoodleDateToISO(""), null);
});

test("Real JCT assignment page: due date labelled מסתיים with a 12-hour time", () => {
  const { doc, url } = page("assign_view_jct.html", "https://moodle.jct.ac.il/mod/assign/view.php?id=971079");
  const [task] = S.scrapeDom(doc, url);

  assert.ok(task, "the fallback must find the assignment");
  assert.equal(task.moodle_id, "971079");
  assert.equal(task.title, "הגשת תרגיל עיוני 1 Submission box for theoretical assignment 1");
  assert.equal(task.course_name, "151131.5787 - קומפיילרים ומתרגמים");
  assert.equal(task.moodle_course_id, 78317);
  // The due date (מסתיים), not the opening date (נפתח) or the last-modified time
  assert.equal(task.due_date, local(2026, 11, 18, 23, 59));
});

test("12-hour times: PM adds 12 hours, 12 AM is midnight, 12 PM is noon", () => {
  assert.equal(S.parseMoodleDateToISO("מסתיים: יום רביעי, 18 נובמבר 2026, 11:59 PM"), local(2026, 11, 18, 23, 59));
  assert.equal(S.parseMoodleDateToISO("נפתח: יום שבת, 24 אוקטובר 2026, 12:00 AM"), local(2026, 10, 24, 0, 0));
  assert.equal(S.parseMoodleDateToISO("18 בנובמבר 2026, 12:30 PM"), local(2026, 11, 18, 12, 30));
  assert.equal(S.parseMoodleDateToISO("18/11/2026, 11:59 PM"), local(2026, 11, 18, 23, 59));
  assert.equal(S.parseMoodleDateToISO("Due: Wednesday, 18 November 2026, 11:59 PM"), local(2026, 11, 18, 23, 59));
});

test("English Moodle page: Due: next to Opened:", () => {
  const html = `<!DOCTYPE html><html><body>
    <h1>Lab 4</h1>
    <div data-region="activity-dates" class="activity-dates">
      <div><strong>Opened:</strong> Saturday, 24 October 2026, 12:00 AM</div>
      <div><strong>Due:</strong> Wednesday, 18 November 2026, 11:59 PM</div>
    </div></body></html>`;
  const doc = new JSDOM(html, { url: "https://moodle.example.ac.il/mod/assign/view.php?id=42" }).window.document;
  const [task] = S.scrapeDom(doc, "https://moodle.example.ac.il/mod/assign/view.php?id=42");
  assert.equal(task.due_date, local(2026, 11, 18, 23, 59));
});
