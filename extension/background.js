// Configuration constants - update API_BASE_URL for production deployment
const API_BASE_URL = "http://localhost:8000/api";
const SYNC_THROTTLE_MS = 15 * 60 * 1000; // 15 minutes throttle for passive sync (US 2.2.3)

// Initialize default extension state on installation
chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.set({
    syncStatus: "NOT_SYNCED",
    lastSyncTime: null,
    lastPassiveRun: 0,
    jwtToken: null
  });
});

// Listen for messages from content scripts and popup UI (US 2.1.4)
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "SCRAPED_DATA") {
    handleScrapedData(message.payload, sender.tab?.url, message.isManual)
      .then((res) => sendResponse({ success: true, data: res }))
      .catch((err) => sendResponse({ success: false, error: err.message }));
    return true;
  }

  if (message.type === "MANUAL_SYNC_TRIGGER") {
    triggerManualSync()
      .then((res) => sendResponse({ success: true, data: res }))
      .catch((err) => sendResponse({ success: false, error: err.message }));
    return true;
  }

  if (message.type === "CHECK_SESSION") {
    checkMoodleSession(message.domain)
      .then((isValid) => sendResponse({ isValid }))
      .catch(() => sendResponse({ isValid: false }));
    return true;
  }
});

// Validate active MoodleSession cookie before syncing (US 2.4.1 & 2.4.2)
async function checkMoodleSession(url) {
  try {
    if (!url) return false;
    // The cookie is "MoodleSession" plus a site-specific suffix on many Moodle sites
    // (on moodle.jct.ac.il too), so match by prefix instead of the exact name.
    const cookies = await chrome.cookies.getAll({ url: url });
    const cookie = cookies.find((c) => c.name.startsWith("MoodleSession"));

    if (!cookie || (cookie.expirationDate && cookie.expirationDate * 1000 < Date.now())) {
      await updateStatus("SESSION_EXPIRED");
      return false;
    }
    return true;
  } catch (error) {
    console.error("[TaskHub] Cookie check error:", error);
    return false;
  }
}

// Process scraped tasks and send authenticated payload to FastAPI backend (US 2.4.4)
async function handleScrapedData(tasks, tabUrl, isManual = false) {
  const storage = await chrome.storage.local.get(["lastPassiveRun", "jwtToken"]);
  const now = Date.now();

  if (!isManual && now - (storage.lastPassiveRun || 0) < SYNC_THROTTLE_MS) {
    console.log("[TaskHub] Passive sync throttled. Skipping.");
    return { skipped: true, reason: "THROTTLED" };
  }

  const isSessionActive = await checkMoodleSession(tabUrl);
  if (!isSessionActive) {
    throw new Error("Moodle session expired. Please log in to Moodle.");
  }

  if (!tasks || tasks.length === 0) {
    if (isManual) {
      // No upcoming assignments is a normal answer (Scenario 1), not an error: say so
      // instead of silently staying on "not synced".
      await chrome.storage.local.set({ syncStatus: "NO_TASKS", lastSyncTime: new Date().toISOString() });
      chrome.action.setBadgeText({ text: "" });
    }
    return { syncedCount: 0 };
  }

  await updateStatus("SYNCING");

  try {
    const headers = {
      "Content-Type": "application/json"
    };
    if (storage.jwtToken) {
      headers["Authorization"] = `Bearer ${storage.jwtToken}`;
    }

    const response = await fetch(`${API_BASE_URL}/tasks/sync`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        tasks: tasks
      })
    });

    if (response.status === 401 || response.status === 403) {
      // Our own login (the Task Hub token) expired, not the Moodle session: telling the
      // student to log in to Moodle again would not help.
      const authError = new Error("Your Task Hub login expired. Paste a new token below.");
      authError.status = "AUTH_EXPIRED";
      throw authError;
    }

    if (!response.ok) {
      throw new Error(`Server responded with status ${response.status}`);
    }

    const result = await response.json();
    const syncTimestamp = new Date().toISOString();

    await chrome.storage.local.set({
      syncStatus: "CONNECTED",
      lastSyncTime: syncTimestamp,
      lastPassiveRun: now
    });

    chrome.action.setBadgeText({ text: "✓" });
    chrome.action.setBadgeBackgroundColor({ color: "#10B981" });

    return result;
  } catch (error) {
    console.error("[TaskHub] Sync failed:", error);
    await updateStatus(error.status || "ERROR");
    chrome.action.setBadgeText({ text: "!" });
    chrome.action.setBadgeBackgroundColor({ color: "#EF4444" });
    throw error;
  }
}

// Trigger immediate DOM scrape on active Moodle tab (US 2.1.3)
async function triggerManualSync() {
  const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });

  if (!activeTab || !activeTab.url || !activeTab.url.includes("moodle")) {
    throw new Error("Please navigate to a Moodle page first.");
  }

  return new Promise((resolve, reject) => {
    chrome.tabs.sendMessage(
      activeTab.id,
      { type: "FORCE_SCRAPE" },
      async (response) => {
        if (chrome.runtime.lastError) {
          return reject(new Error("Could not connect to Moodle page. Refresh the page and try again."));
        }
        if (response && Array.isArray(response.tasks)) {
          try {
            const syncRes = await handleScrapedData(response.tasks, activeTab.url, true);
            resolve(syncRes);
          } catch (err) {
            reject(err);
          }
        } else {
          reject(new Error("No tasks found on current Moodle view."));
        }
      }
    );
  });
}

async function updateStatus(status) {
  await chrome.storage.local.set({ syncStatus: status });
}
