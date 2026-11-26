const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

test("Service Worker Lifecycle & Listener Initialization (US 2.2.1, AB#474)", async () => {
  // Mock Chrome APIs
  const storageState = {};
  const listeners = {
    onInstalled: [],
    onMessage: [],
    webNavigationOnCompleted: [],
  };

  globalThis.chrome = {
    storage: {
      local: {
        get: async (keys) => {
          if (Array.isArray(keys)) {
            const res = {};
            keys.forEach((k) => (res[k] = storageState[k]));
            return res;
          }
          return { ...storageState };
        },
        set: async (obj) => {
          Object.assign(storageState, obj);
        },
      },
    },
    runtime: {
      onInstalled: {
        addListener: (fn) => listeners.onInstalled.push(fn),
      },
      onMessage: {
        addListener: (fn) => listeners.onMessage.push(fn),
      },
    },
    webNavigation: {
      onCompleted: {
        addListener: (fn, filter) => listeners.webNavigationOnCompleted.push({ fn, filter }),
      },
    },
    action: {
      setBadgeText: () => {},
      setBadgeBackgroundColor: () => {},
    },
  };

  // Load background.js via vm / eval to test lifecycle in Node
  const bgCode = fs.readFileSync(path.resolve(__dirname, "../background.js"), "utf8");
  const runWorker = new Function(bgCode);
  runWorker();

  // AC 1: Event listeners initialized on onInstalled and webNavigation
  assert.ok(listeners.onInstalled.length > 0, "onInstalled listener must be registered");
  assert.ok(
    listeners.webNavigationOnCompleted.length > 0,
    "webNavigation.onCompleted listener must be registered"
  );
  assert.ok(listeners.onMessage.length > 0, "onMessage listener must be registered");

  // Trigger onInstalled (Installation event)
  for (const listener of listeners.onInstalled) {
    listener();
  }

  // AC 2: State persisted in chrome.storage.local instead of in-memory variables
  assert.equal(storageState.syncStatus, "NOT_SYNCED");
  assert.equal(storageState.lastPassiveRun, 0);

  // AC 3: Sleep / wake / termination cycle simulation
  const wakeRead = await chrome.storage.local.get(["syncStatus", "lastPassiveRun"]);
  assert.equal(wakeRead.syncStatus, "NOT_SYNCED");

  // Trigger webNavigation event on wake
  assert.doesNotThrow(() => {
    listeners.webNavigationOnCompleted[0].fn({
      frameId: 0,
      url: "https://moodle.jct.ac.il/my/",
    });
  }, "WebNavigation event handler must not crash during wake cycle");
});
