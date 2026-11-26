// Fallback: read tasks from the Moodle page itself (User Story 2.3.1, AB#478; US 2.3.2-2.3.4).
//
// Used only when Moodle's calendar service (moodle.js) isn't available. Loaded as a content
// script before content.js (see manifest.json), and by the tests in extension/tests/ with a
// saved Moodle page. Every function takes the document and URL as parameters, so it can be
// tested without a browser.
(function (root) {
  // Labels Moodle puts before an activity's due date. Moodle 4.x shows "מסתיים:" / "Due:" in
  // the activity-dates block (next to "נפתח:" / "Opened:", the opening date, which is ignored);
  // older pages and quizzes use the others.
  const DUE_LABELS = ["מסתיים", "מועד הגשה", "נסגר ב", "Due:", "Due date", "Closes", "Closed:"];
  const DUE_LABEL_PREFIX = /^(?:מסתיים|מועד הגשה|נסגר ב|Due date|Due|Closes|Closed)[:\s-]*/i;
  // 12-hour clock: Moodle in Hebrew still writes AM/PM after the time ("11:59 PM").
  const TIME = /(\d{1,2}):(\d{2})(?:\s*(AM|PM|לפנה"צ|אחה"צ))?/i;

  const Moodle = root.TaskHubMoodle || (typeof require !== "undefined" ? require("./moodle.js") : null);
  const cleanText = Moodle.cleanText;
  const extractActivityId = Moodle.extractActivityId;

  // Tasks from the Timeline / Upcoming events blocks, plus the activity itself on a
  // single activity page. Deduplicated by moodle_id.
  function scrapeDom(doc, pageUrl) {
    const extracted = [];
    extracted.push(...scrapeTimelineAndUpcoming(doc));

    if (String(pageUrl || "").includes("/mod/")) {
      const singleTask = scrapeSingleActivityPage(doc, pageUrl);
      if (singleTask) extracted.push(singleTask);
    }

    return Array.from(new Map(extracted.map((item) => [item.moodle_id, item])).values());
  }

  // Dashboard Timeline and Upcoming Events blocks (US 2.3.2)
  function scrapeTimelineAndUpcoming(doc) {
    const results = [];
    const eventSelectors = [
      '[data-region="event-list-item"]',
      ".block_calendar_upcoming .event",
      ".calendar_event_due",
      ".eventlist .card",
    ];

    doc.querySelectorAll(eventSelectors.join(", ")).forEach((node) => {
      try {
        const titleEl = node.querySelector("h6 a, .eventname a, a[data-action='view-event'], a[href*='/mod/']");
        const courseEl = node.querySelector(".text-muted, .course a, [data-region='event-course-name']");
        const dateEl = node.querySelector(".date, time, [data-region='event-time'], .col-11");

        if (!titleEl || !titleEl.href) return;

        const moodleUrl = titleEl.href.split("#")[0];
        const moodleId = extractActivityId(moodleUrl);
        if (!moodleId) return;

        const rawTitle = Moodle.cleanEventTitle(titleEl.textContent);
        if (!rawTitle) return; // Moodle renders empty placeholder items before the real list
        const courseName = courseEl ? cleanText(courseEl.textContent) : extractCourseFromBreadcrumbs(doc);
        const dueDate = parseMoodleDateToISO(dateEl ? cleanText(dateEl.textContent) : "");
        if (!dueDate) return;

        results.push({
          moodle_id: moodleId,
          title: rawTitle,
          course_name: courseName || null,
          moodle_course_id: extractCourseId(node, doc),
          description: "",
          due_date: dueDate,
          moodle_url: moodleUrl,
        });
      } catch (e) {
        console.warn("[TaskHub] Failed parsing event node:", e);
      }
    });

    return results;
  }

  // A single assignment or quiz page (US 2.3.1)
  function scrapeSingleActivityPage(doc, pageUrl) {
    try {
      const moodleUrl = String(pageUrl).split("#")[0];
      const moodleId = extractActivityId(moodleUrl);
      if (!moodleId) return null;

      const titleEl = doc.querySelector("h1, h2, .page-header-headings h1");
      if (!titleEl) return null;

      let dueDate = null;
      doc.querySelectorAll("table.generaltable tr, .submissionstatustable tr, .activity-dates div").forEach((row) => {
        const text = cleanText(row.textContent);
        if (DUE_LABELS.some((label) => text.includes(label))) {
          const parsed = parseMoodleDateToISO(text);
          if (parsed) dueDate = parsed;
        }
      });
      if (!dueDate) return null;

      return {
        moodle_id: moodleId,
        title: cleanText(titleEl.textContent),
        course_name: extractCourseFromBreadcrumbs(doc) || null,
        moodle_course_id: extractCourseId(doc, doc),
        description: cleanText(doc.querySelector("#intro, .activity-description")?.textContent || "").slice(0, 300),
        due_date: dueDate,
        moodle_url: moodleUrl,
      };
    } catch (e) {
      console.warn("[TaskHub] Failed parsing single activity:", e);
      return null;
    }
  }

  // "11:59 PM" -> [23, 59]; "12:00 AM" -> [0, 0]; "18:00" -> [18, 0]. null if no time.
  function readTime(str) {
    const match = String(str).match(TIME);
    if (!match) return null;
    let hour = Number(match[1]);
    const minute = Number(match[2]);
    const half = (match[3] || "").toUpperCase();
    if (half === "PM" || half === 'אחה"צ') hour = hour === 12 ? 12 : hour + 12;
    if (half === "AM" || half === 'לפנה"צ') hour = hour === 12 ? 0 : hour;
    return [hour, minute];
  }

  // Hebrew and English Moodle date strings -> ISO 8601 UTC (US 2.3.3).
  // Dates without a time zone are read in the browser's local time (Israel for our students).
  function parseMoodleDateToISO(rawStr) {
    if (!rawStr) return null;

    // DD/MM/YYYY or DD.MM.YYYY with HH:MM (optionally AM/PM)
    const numericMatch = rawStr.match(/(\d{1,2})[./](\d{1,2})[./](\d{2,4})(.*)$/);
    const numericTime = numericMatch && readTime(numericMatch[4]);
    if (numericMatch && numericTime) {
      let [, day, month, year] = numericMatch;
      if (year.length === 2) year = "20" + year;
      const dateObj = new Date(Number(year), Number(month) - 1, Number(day), ...numericTime);
      if (!isNaN(dateObj.getTime())) return dateObj.toISOString();
    }

    // Hebrew month names
    const hebrewMonths = {
      "ינואר": 0, "פברואר": 1, "מרץ": 2, "מרס": 2, "אפריל": 3,
      "מאי": 4, "יוני": 5, "יולי": 6, "אוגוסט": 7,
      "ספטמבר": 8, "אוקטובר": 9, "נובמבר": 10, "דצמבר": 11,
    };
    const hebMatch = rawStr.match(/(\d{1,2})\s+ב?([א-ת]+)\s+(\d{4})(.*)$/);
    const hebTime = hebMatch && readTime(hebMatch[4]);
    if (hebMatch && hebTime) {
      const [, day, monthWord, year] = hebMatch;
      const monthIdx = hebrewMonths[monthWord];
      if (monthIdx !== undefined) {
        const dateObj = new Date(Number(year), monthIdx, Number(day), ...hebTime);
        if (!isNaN(dateObj.getTime())) return dateObj.toISOString();
      }
    }

    // English dates that Date() understands
    const cleanedEng = rawStr.replace(DUE_LABEL_PREFIX, "").trim();
    const fallbackDate = new Date(cleanedEng);
    if (!isNaN(fallbackDate.getTime())) return fallbackDate.toISOString();

    return null;
  }

  function extractCourseFromBreadcrumbs(doc) {
    const crumb = doc.querySelector('.breadcrumb a[href*="course/view.php"], nav[aria-label="Navigation bar"] a[href*="course/view.php"]');
    return crumb ? cleanText(crumb.textContent) : "";
  }

  // Numeric course id from a course/view.php?id=... link, a data-course-id attribute,
  // the breadcrumbs or the body class; null if none.
  function extractCourseId(rootEl, doc) {
    const courseLink = rootEl?.querySelector?.('a[href*="course/view.php"]');
    if (courseLink?.href) {
      const match = courseLink.href.match(/[?&]id=(\d+)/);
      if (match) return Number(match[1]);
    }

    const dataCourse = rootEl?.getAttribute?.("data-course-id") || rootEl?.closest?.("[data-course-id]")?.getAttribute("data-course-id");
    if (dataCourse && /^\d+$/.test(dataCourse)) return Number(dataCourse);

    const crumbLink = doc.querySelector('.breadcrumb a[href*="course/view.php"], nav a[href*="course/view.php"]');
    if (crumbLink?.href) {
      const match = crumbLink.href.match(/[?&]id=(\d+)/);
      if (match) return Number(match[1]);
    }

    const bodyCourseMatch = doc.body?.className?.match(/\bcourse-(\d+)\b/);
    if (bodyCourseMatch && Number(bodyCourseMatch[1]) > 1) return Number(bodyCourseMatch[1]);

    return null;
  }

  const api = { scrapeDom, scrapeTimelineAndUpcoming, scrapeSingleActivityPage, parseMoodleDateToISO };
  root.TaskHubDomScraper = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
