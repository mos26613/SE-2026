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

    // Deduplicate tasks by moodle_id
    return Array.from(
      new Map(extracted.map((item) => [item.moodle_id, item])).values()
    );
  }

  // Extract tasks from Dashboard Timeline, Upcoming Events, and Monthly Calendar blocks (US 2.3.2)
  function scrapeTimelineAndUpcoming() {
    const results = [];
    const eventSelectors = [
      '[data-region="event-list-item"]',
      '[data-region="timeline-view"] [data-region="event-list-item"]',
      '[data-region="timeline"] [data-region="event-list-item"]',
      ".block_timeline [data-region='event-list-item']",
      ".block_calendar_upcoming .event",
      ".block_calendar_month .event",
      ".block_calendar_month [data-region='day'] a[href*='/mod/']",
      ".block_calendar_month td.day a[href*='/mod/']",
      ".calendar_event_due",
      ".eventlist .card"
    ];

    const eventNodes = document.querySelectorAll(eventSelectors.join(", "));

    eventNodes.forEach((node) => {
      try {
        if (!node) return;

        const isDirectLink = node.tagName === "A" && node.href;
        const titleEl = isDirectLink
          ? node
          : node.querySelector("h6 a, .eventname a, a[data-action='view-event'], a[href*='/mod/']");
        const courseEl = node.querySelector
          ? node.querySelector(".text-muted, .course a, [data-region='event-course-name']")
          : null;
        const dateEl = node.querySelector
          ? node.querySelector(".date, time, [data-region='event-time'], [data-region='day-timestamp'], .col-11")
          : null;

        const href = titleEl && titleEl.href ? String(titleEl.href) : "";
        if (!href) return;

        const moodleUrl = href.split("#")[0];
        const moodleId = extractActivityId(moodleUrl);
        if (!moodleId) return;

        const rawTitle = cleanText(titleEl.textContent || titleEl.getAttribute("title") || "");
        if (!rawTitle) return;

        const courseName = courseEl && cleanText(courseEl.textContent)
          ? cleanText(courseEl.textContent)
          : extractCourseFromBreadcrumbs();
        const moodleCourseId = extractCourseId(node);

        const dayContainer = node.closest ? node.closest("[data-region='day'], td.day, .day") : null;
        const rawDate =
          (dateEl && cleanText(dateEl.textContent)) ||
          (dayContainer && (dayContainer.getAttribute("data-day-timestamp") || dayContainer.getAttribute("aria-label") || cleanText(dayContainer.textContent))) ||
          "";
        const dueDate = parseMoodleDateToISO(rawDate);

        if (!dueDate) return;

        results.push({
          moodle_id: moodleId,
          title: rawTitle,
          course_name: courseName || null,
          moodle_course_id: moodleCourseId,
          description: "",
          due_date: dueDate,
          moodle_url: moodleUrl
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
      const moodleUrl = window.location.href.split("#")[0];
      const moodleId = extractActivityId(moodleUrl);
      if (!moodleId) return null;

      const titleEl = document.querySelector("h1, h2, .page-header-headings h1");
      if (!titleEl) return null;

      const title = cleanText(titleEl.textContent);
      const courseName = extractCourseFromBreadcrumbs();
      const moodleCourseId = extractCourseId(document);

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

      return {
        moodle_id: moodleId,
        title: title,
        course_name: courseName || null,
        moodle_course_id: moodleCourseId,
        description: cleanText(document.querySelector("#intro, .activity-description")?.textContent || "").slice(0, 300),
        due_date: dueDate,
        moodle_url: moodleUrl
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

  // Extract Moodle activity ID as string from mod/.../view.php?id=XXXX
  function extractActivityId(url) {
    if (!url || !url.includes("/mod/")) return null;
    const match = url.match(/[?&]id=(\d+)/);
    return match ? String(match[1]) : null;
  }

  function extractCourseFromBreadcrumbs() {
    const crumb = document.querySelector('.breadcrumb a[href*="course/view.php"], nav[aria-label="Navigation bar"] a[href*="course/view.php"]');
    return crumb ? cleanText(crumb.textContent) : "";
  }

  // Extract numeric course ID from course/view.php?id=... links or attributes; fallback to null
  function extractCourseId(rootEl) {
    const courseLink = rootEl?.querySelector?.('a[href*="course/view.php"]');
    if (courseLink?.href) {
      const match = courseLink.href.match(/[?&]id=(\d+)/);
      if (match) return Number(match[1]);
    }

    const dataCourse = rootEl?.getAttribute?.("data-course-id") || rootEl?.closest?.("[data-course-id]")?.getAttribute("data-course-id");
    if (dataCourse && /^\d+$/.test(dataCourse)) {
      return Number(dataCourse);
    }

    const crumbLink = document.querySelector('.breadcrumb a[href*="course/view.php"], nav a[href*="course/view.php"]');
    if (crumbLink?.href) {
      const match = crumbLink.href.match(/[?&]id=(\d+)/);
      if (match) return Number(match[1]);
    }

    const bodyCourseMatch = document.body?.className?.match(/\bcourse-(\d+)\b/);
    if (bodyCourseMatch && Number(bodyCourseMatch[1]) > 1) {
      return Number(bodyCourseMatch[1]);
    }

    return null;
  }

  function cleanText(str) {
    return str ? str.replace(/\s+/g, " ").trim() : "";
  }
})();
