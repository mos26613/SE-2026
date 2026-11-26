// Moodle data extraction helpers (User Story 2.3.1, AB#478).
//
// Loaded as a content script before content.js (see manifest.json), and by the tests
// in extension/tests/ through Node's require(). No DOM or chrome.* APIs in here, so it
// can be tested without a browser.
//
// Main source: Moodle's own calendar web service, core_calendar_get_action_events_by_timesort.
// It is the same read-only request Moodle's Timeline block makes, sent from the Moodle tab
// with the student's existing session, so it works on any Moodle page and theme and gives
// the exact due time, course and link. The DOM scraper in content.js is only a fallback.
(function (root) {
  // Activity types that have real deadlines. Zoom lessons, attendance etc. are left out.
  const DEADLINE_MODULES = new Set(["assign", "quiz", "workshop", "lesson", "forum", "h5pactivity", "scorm", "data", "choice", "feedback"]);
  const LOOKBACK_DAYS = 30; // also sync recently overdue tasks
  const PAGE_SIZE = 50;
  const MAX_PAGES = 4;
  // NFR-9: ask Moodle at most once per 15 minutes on ordinary page loads. Every Moodle page
  // load runs content.js, so without this each click would send up to MAX_PAGES requests.
  // A manual "Sync Now" always runs, and starts the same window. Same interval as
  // SYNC_THROTTLE_MS in background.js.
  const PASSIVE_FETCH_INTERVAL_MS = 15 * 60 * 1000;

  // Zero-width characters and bidi controls Hebrew Moodle pages are full of.
  const INVISIBLE_CHARS = /[​-‏‪-‮⁠-⁩﻿]/g;

  function cleanText(str) {
    if (!str) return "";
    return String(str).replace(INVISIBLE_CHARS, "").replace(/\s+/g, " ").trim();
  }

  function stripHtml(html) {
    if (!html) return "";
    const text = String(html)
      .replace(/<(script|style)[^>]*>[\s\S]*?<\/\1>/gi, " ")
      .replace(/<br\s*\/?>|<\/(p|div|li|h\d)>/gi, " ")
      .replace(/<[^>]+>/g, " ")
      .replace(/&nbsp;/g, " ")
      .replace(/&amp;/g, "&")
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">")
      .replace(/&quot;/g, '"')
      .replace(/&#0?39;/g, "'");
    return cleanText(text);
  }

  // "יש להגיש את 'הגשת תרגיל 1'" -> "הגשת תרגיל 1"; "Assignment 1 is due" -> "Assignment 1"
  function cleanEventTitle(name) {
    let title = cleanText(name);
    const hebrew = title.match(/^(?:יש להגיש את|יש להשלים את|נסגר|נפתח)\s*['"׳״](.+)['"׳״]$/);
    if (hebrew) return cleanText(hebrew[1]);
    const english = title.match(/^(.+?)\s+(?:is due|closes|should be completed)$/i);
    if (english) return cleanText(english[1]);
    return title;
  }

  // Moodle activity (course module) id from mod/<type>/view.php?id=XXXX
  function extractActivityId(url) {
    if (!url || !String(url).includes("/mod/")) return null;
    const match = String(url).match(/[?&]id=(\d+)/);
    return match ? match[1] : null;
  }

  function findSesskey(html) {
    const match = String(html || "").match(/sesskey=([A-Za-z0-9]{6,})|"sesskey"\s*:\s*"([A-Za-z0-9]{6,})"/);
    return match ? match[1] || match[2] : null;
  }

  // Whether a page load may ask Moodle again. lastFetch is the time of the last request (ms).
  function isPassiveFetchDue(lastFetch, now = Date.now()) {
    if (!Number.isFinite(lastFetch) || lastFetch <= 0) return true;
    if (lastFetch > now) return true; // clock moved back: don't stay blocked
    return now - lastFetch >= PASSIVE_FETCH_INTERVAL_MS;
  }

  // One calendar event -> one task in the backend's format (backend/app/models.py TaskIn), or null.
  function eventToTask(event) {
    if (!event || !DEADLINE_MODULES.has(event.modulename)) return null;
    if (!event.timesort) return null;

    const url = event.url ? String(event.url).split("#")[0] : null;
    const activityId = extractActivityId(url);
    const title = cleanText(event.activityname) || cleanEventTitle(event.name);
    if (!title) return null;

    return {
      moodle_id: activityId || `event-${event.id}`,
      title: title.slice(0, 500),
      course_name: cleanText(event.course?.fullname) || null,
      moodle_course_id: Number.isInteger(event.course?.id) ? event.course.id : null,
      description: stripHtml(event.description).slice(0, 1500),
      due_date: new Date(event.timesort * 1000).toISOString(),
      moodle_url: url,
    };
  }

  // Ask Moodle for the student's upcoming (and recently overdue) deadlines.
  // fetchFn and now are parameters so the tests can replace them.
  async function fetchEventsFromMoodle({ baseUrl, sesskey, fetchFn, now = Date.now() }) {
    if (!sesskey) throw new Error("Moodle sesskey not found on the page");
    const endpoint = `${baseUrl}/lib/ajax/service.php?sesskey=${encodeURIComponent(sesskey)}&info=core_calendar_get_action_events_by_timesort`;
    const events = [];
    let afterEventId = 0;

    for (let page = 0; page < MAX_PAGES; page++) {
      const args = {
        timesortfrom: Math.floor(now / 1000) - LOOKBACK_DAYS * 86400,
        limitnum: PAGE_SIZE,
        limittononsuspendedevents: true,
      };
      if (afterEventId) args.aftereventid = afterEventId;

      const response = await fetchFn(endpoint, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify([{ index: 0, methodname: "core_calendar_get_action_events_by_timesort", args }]),
      });
      if (!response.ok) throw new Error(`Moodle responded with status ${response.status}`);

      const [result] = await response.json();
      if (!result || result.error) {
        const code = result?.exception?.errorcode || "unknown";
        throw new Error(`Moodle calendar service error: ${code}`);
      }

      const batch = result.data?.events || [];
      events.push(...batch);
      if (batch.length < PAGE_SIZE) break;
      afterEventId = batch[batch.length - 1].id;
    }

    const tasks = events.map(eventToTask).filter(Boolean);
    return Array.from(new Map(tasks.map((t) => [t.moodle_id, t])).values());
  }

  const api = {
    cleanText, stripHtml, cleanEventTitle, extractActivityId, findSesskey, eventToTask, fetchEventsFromMoodle,
    isPassiveFetchDue, DEADLINE_MODULES, PASSIVE_FETCH_INTERVAL_MS,
  };
  root.TaskHubMoodle = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
