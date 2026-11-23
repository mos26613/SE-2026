// Popup UI Controller for Smart Student Task Hub Extension (Feature 2.1)
const DASHBOARD_URL = "http://localhost:5173";

document.addEventListener("DOMContentLoaded", async () => {
  const statusBadge = document.getElementById("statusBadge");
  const statusText = document.getElementById("statusText");
  const lastSyncText = document.getElementById("lastSyncText");
  const syncBtn = document.getElementById("syncBtn");
  const openDashboardBtn = document.getElementById("openDashboardBtn");
  const sessionAlert = document.getElementById("sessionAlert");
  const errorAlert = document.getElementById("errorAlert");
  const jwtInput = document.getElementById("jwtInput");

  // Load persisted sync state from chrome.storage.local
  async function refreshUI() {
    const data = await chrome.storage.local.get(["syncStatus", "lastSyncTime", "jwtToken"]);
    updateBadgeUI(data.syncStatus || "NOT_SYNCED");

    if (data.lastSyncTime) {
      const date = new Date(data.lastSyncTime);
      lastSyncText.textContent = `סנכרון אחרון: ${date.toLocaleDateString("he-IL")} בשעה ${date.toLocaleTimeString("he-IL", { hour: "2-digit", minute: "2-digit" })}`;
    }

    if (data.jwtToken) {
      jwtInput.value = data.jwtToken;
    }
  }

  function updateBadgeUI(status) {
    statusBadge.className = "badge";
    sessionAlert.style.display = "none";

    switch (status) {
      case "CONNECTED":
        statusBadge.classList.add("connected");
        statusText.textContent = "Moodle: מסונכרן";
        break;
      case "SYNCING":
        statusBadge.classList.add("syncing");
        statusText.textContent = "מסנכרן...";
        break;
      case "SESSION_EXPIRED":
        statusBadge.classList.add("expired");
        statusText.textContent = "סשן פג תוקף";
        sessionAlert.style.display = "block";
        break;
      case "ERROR":
        statusBadge.classList.add("expired");
        statusText.textContent = "שגיאת סנכרון";
        break;
      default:
        statusBadge.classList.add("neutral");
        statusText.textContent = "לא מסונכרן";
    }
  }

  // Trigger manual sync via background worker (US 2.1.3)
  syncBtn.addEventListener("click", () => {
    errorAlert.style.display = "none";
    syncBtn.disabled = true;
    syncBtn.textContent = "מסנכרן נתונים...";
    updateBadgeUI("SYNCING");

    chrome.runtime.sendMessage({ type: "MANUAL_SYNC_TRIGGER" }, async (response) => {
      syncBtn.disabled = false;
      syncBtn.textContent = "סנכרן מטלות עכשיו (Sync Now)";

      if (response && response.success) {
        await refreshUI();
      } else {
        errorAlert.textContent = response?.error || "אירעה שגיאה בסנכרון מול Moodle.";
        errorAlert.style.display = "block";
        await refreshUI();
      }
    });
  });

  openDashboardBtn.addEventListener("click", () => {
    chrome.tabs.create({ url: DASHBOARD_URL });
  });

  jwtInput.addEventListener("change", async (e) => {
    await chrome.storage.local.set({ jwtToken: e.target.value.trim() });
  });

  await refreshUI();
});
