// Read-Only DOM Scraper for Institutional Moodle Portals (Feature 2.3)
(function () {
  if (window.__taskHubScraperInjected) return;
  window.__taskHubScraperInjected = true;

  // Listen for manual sync requests from background service worker
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === "FORCE_SCRAPE") {
      const tasks = extractAllMoodleTasks();
      sendResponse({ tasks });
    }
    return true;
  });

  // Execute passive background scrape after dynamic widgets settle (US 2.2.2)
  setTimeout(() => {
    const tasks = extractAllMoodleTasks();
    if (tasks.length > 0) {
      chrome.runtime.sendMessage({
        type: "SCRAPED_DATA",
        payload: tasks,
        isManual: false
      });
    }
  }, 2000);

  // Aggregate tasks across different Moodle views and themes (US 2.3.4)
  function extractAllMoodleTasks() {
    const extracted = [];
    extracted.push(...scrapeTimelineAndUpcoming());

    if (window.location.href.includes("/mod/")) {
      const singleTask = scrapeSingleActivityPage();
      if (singleTask) extracted.push(singleTask);
    }

    // Deduplicate tasks by activity URL
    return Array.from(
      new Map(extracted.map((item) => [item.link, item])).values()
    );
  }

  // Extract tasks from Dashboard Timeline and Upcoming Events blocks (US 2.3.2)
  function scrapeTimelineAndUpcoming() {
    const results = [];
    const eventSelectors = [
      '[data-region="event-list-item"]',
      ".block_calendar_upcoming .event",
      ".calendar_event_due",
      ".eventlist .card"
    ];

    const eventNodes = document.querySelectorAll(eventSelectors.join(", "));

    eventNodes.forEach((node) => {
      try {
        const titleEl = node.querySelector("h6 a, .eventname a, a[data-action='view-event'], a");
        const courseEl = node.querySelector(".text-muted, .course a, [data-region='event-course-name']");
        const dateEl = node.querySelector(".date, time, [data-region='event-time'], .col-11");

        if (!titleEl || !titleEl.href) return;

        const rawTitle = cleanText(titleEl.textContent);
        const link = titleEl.href;
        const courseName = courseEl ? cleanText(courseEl.textContent) : extractCourseFromBreadcrumbs();
        const moodleCourseId = extractCourseId(node, link);
        const rawDate = dateEl ? cleanText(dateEl.textContent) : "";
        const dueDate = parseMoodleDateToISO(rawDate);

        if (!dueDate) return;

        results.push({
          moodle_course_id: moodleCourseId,
          course_name: courseName || "קורס כללי",
          title: rawTitle,
          task_type: inferTaskType(rawTitle, link),
          points: extractPoints(node.textContent),
          due_date: dueDate,
          is_submitted: inferSubmissionStatus(node.textContent),
          link: link,
          description: ""
        });
      } catch (e) {
        console.warn("[TaskHub] Failed parsing event node:", e);
      }
    });

    return results;
  }

  // Extract details from an individual assignment or quiz view page (US 2.3.1)
  function scrapeSingleActivityPage() {
    try {
      const titleEl = document.querySelector("h1, h2, .page-header-headings h1");
      if (!titleEl) return null;

      const title = cleanText(titleEl.textContent);
      const courseName = extractCourseFromBreadcrumbs();
      const moodleCourseId = extractCourseId(document, window.location.href);
      const link = window.location.href.split("#")[0];

      let dueDate = null;
      const rows = document.querySelectorAll("table.generaltable tr, .submissionstatustable tr, .activity-dates div");
      rows.forEach((row) => {
        const text = cleanText(row.textContent);
        if (text.includes("מועד הגשה") || text.includes("Due date") || text.includes("נסגר ב") || text.includes("Closes")) {
          const parsed = parseMoodleDateToISO(text);
          if (parsed) dueDate = parsed;
        }
      });

      if (!dueDate) return null;

      const pageBodyText = document.querySelector("#region-main")?.textContent || "";

      return {
        moodle_course_id: moodleCourseId,
        course_name: courseName || "קורס אקדמי",
        title: title,
        task_type: inferTaskType(title, link),
        points: extractPoints(pageBodyText),
        due_date: dueDate,
        is_submitted: inferSubmissionStatus(pageBodyText),
        link: link,
        description: cleanText(document.querySelector("#intro, .activity-description")?.textContent || "").slice(0, 300)
      };
    } catch (e) {
      console.warn("[TaskHub] Failed parsing single activity:", e);
      return null;
    }
  }

  // Normalize Hebrew and English Moodle date strings into ISO 8601 UTC format (US 2.3.3)
  function parseMoodleDateToISO(rawStr) {
    if (!rawStr) return null;

    // Numeric format: DD/MM/YYYY or DD.MM.YYYY with HH:MM
    const numericMatch = rawStr.match(/(\d{1,2})[./](\d{1,2})[./](\d{2,4}).*?(\d{1,2}):(\d{2})/);
    if (numericMatch) {
      let [, day, month, year, hour, minute] = numericMatch;
      if (year.length === 2) year = "20" + year;
      const dateObj = new Date(Number(year), Number(month) - 1, Number(day), Number(hour), Number(minute));
      if (!isNaN(dateObj.getTime())) return dateObj.toISOString();
    }

    // Hebrew month names format
    const hebrewMonths = {
      "ינואר": 0, "פברואר": 1, "מרץ": 2, "מרס": 2, "אפריל": 3,
      "מאי": 4, "יוני": 5, "יולי": 6, "אוגוסט": 7,
      "ספטמבר": 8, "אוקטובר": 9, "נובמבר": 10, "דצמבר": 11
    };

    const hebMatch = rawStr.match(/(\d{1,2})\s+ב?([א-ת]+)\s+(\d{4}).*?(\d{1,2}):(\d{2})/);
    if (hebMatch) {
      const [, day, monthWord, year, hour, minute] = hebMatch;
      const monthIdx = hebrewMonths[monthWord];
      if (monthIdx !== undefined) {
        const dateObj = new Date(Number(year), monthIdx, Number(day), Number(hour), Number(minute));
        if (!isNaN(dateObj.getTime())) return dateObj.toISOString();
      }
    }

    // Standard English date fallback
    const cleanedEng = rawStr.replace(/^(Due date|מועד הגשה|נסגר ב|Closes)[:\s-]*/i, "").trim();
    const fallbackDate = new Date(cleanedEng);
    if (!isNaN(fallbackDate.getTime())) {
      return fallbackDate.toISOString();
    }

    return null;
  }

  function extractCourseFromBreadcrumbs() {
    const crumb = document.querySelector('.breadcrumb a[href*="course/view.php"], nav[aria-label="Navigation bar"] a[href*="course"]');
    return crumb ? cleanText(crumb.textContent) : "";
  }

  function extractCourseId(rootEl, url) {
    const urlMatch = url.match(/[?&]id=(\d+)/);
    const dataCourse = rootEl?.getAttribute?.("data-course-id") || document.body.getAttribute("class")?.match(/course-(\d+)/)?.[1];
    return Number(dataCourse || urlMatch?.[1] || 0);
  }

  function inferTaskType(title, url) {
    if (url.includes("/mod/quiz/") || title.includes("בוחן") || title.toLowerCase().includes("quiz")) {
      return "בוחן מקוון";
    }
    if (title.includes("פרויקט") || title.toLowerCase().includes("project")) {
      return "פרויקט";
    }
    if (title.includes("תרגיל")) {
      return "תרגיל בית";
    }
    return "מטלת בית";
  }

  function extractPoints(text) {
    const match = text.match(/(\d+)\s*(?:נק'|נקודות|points|pts)/i);
    return match ? Number(match[1]) : null;
  }

  function inferSubmissionStatus(text) {
    return (
      text.includes("הוגש למתן ציון") ||
      text.includes("Submitted for grading") ||
      text.includes("הושלם")
    );
  }

  function cleanText(str) {
    return str ? str.replace(/\s+/g, " ").trim() : "";
  }
})();
