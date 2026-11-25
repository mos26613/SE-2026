// Read-only Moodle task extraction (Feature 2.3, US 2.3.1 AB#478)
//
// 1. Main source: Moodle's own calendar service (moodle.js). Exact due times, course
//    names and links, on any Moodle page or theme. See docs/adr/0004.
// 2. Fallback: reading the page itself (dom_scraper.js), if the service isn't available.
(function () {
  if (window.__taskHubScraperInjected) return;
  window.__taskHubScraperInjected = true;

  const Moodle = globalThis.TaskHubMoodle; // from moodle.js, loaded first (manifest.json)
  const DomScraper = globalThis.TaskHubDomScraper; // from dom_scraper.js

  // Manual "Sync Now" from the popup (through background.js): always asks Moodle.
  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === "FORCE_SCRAPE") {
      extractAllMoodleTasks().then(sendResponse);
      return true; // keep the channel open for the async answer
    }
    return false;
  });

  // Passive sync on page load (US 2.2.2), after dynamic widgets settle. Throttled before
  // asking Moodle (NFR-9): at most once per 15 minutes, whatever happens afterwards.
  setTimeout(async () => {
    const { lastMoodleFetch } = await chrome.storage.local.get("lastMoodleFetch");
    if (!Moodle.isPassiveFetchDue(lastMoodleFetch)) return;
    await chrome.storage.local.set({ lastMoodleFetch: Date.now() });

    const { tasks } = await extractAllMoodleTasks();
    if (tasks.length > 0) {
      chrome.runtime.sendMessage({
        type: "SCRAPED_DATA",
        payload: tasks,
        isManual: false,
      });
    }
  }, 2000);

  // Returns { tasks, source }. Tries Moodle's calendar service first.
  async function extractAllMoodleTasks() {
    try {
      const tasks = await Moodle.fetchEventsFromMoodle({
        baseUrl: window.location.origin,
        sesskey: Moodle.findSesskey(document.documentElement.innerHTML),
        fetchFn: window.fetch.bind(window),
      });
      return { tasks, source: "calendar-service" };
    } catch (e) {
      console.warn("[TaskHub] Moodle calendar service unavailable, falling back to the page:", e.message);
      return { tasks: DomScraper.scrapeDom(document, window.location.href), source: "dom" };
    }
  }
})();
