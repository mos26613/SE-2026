/**
 * Cross-Context Message Passing Infrastructure (US 2.1.4, AB#473).
 *
 * Provides typed message payloads, safe promise-based messaging,
 * async error handling and logging across Service Worker, Content Scripts and Popup UI.
 */
(function (root) {
  const MessageTypes = {
    SCRAPED_DATA: "SCRAPED_DATA",
    MANUAL_SYNC_TRIGGER: "MANUAL_SYNC_TRIGGER",
    CHECK_SESSION: "CHECK_SESSION",
    FORCE_SCRAPE: "FORCE_SCRAPE",
    GET_SYNC_STATUS: "GET_SYNC_STATUS",
  };

  function createMessage(type, payload = {}, meta = {}) {
    if (!Object.values(MessageTypes).includes(type)) {
      throw new Error(`Invalid message type: ${type}`);
    }
    return {
      type,
      payload,
      meta: {
        timestamp: Date.now(),
        ...meta,
      },
    };
  }

  function isValidMessage(message) {
    return (
      typeof message === "object" &&
      message !== null &&
      typeof message.type === "string" &&
      Object.values(MessageTypes).includes(message.type)
    );
  }

  function sendCrossContextMessage(message, tabId = null, timeoutMs = 5000) {
    return new Promise((resolve, reject) => {
      let timer = null;

      const callback = (response) => {
        if (timer) clearTimeout(timer);
        const lastError = chrome.runtime?.lastError;
        if (lastError) {
          console.warn(`[TaskHub Messaging] Runtime error sending ${message?.type}:`, lastError.message);
          return reject(new Error(lastError.message));
        }
        if (response && response.success === false) {
          return reject(new Error(response.error || "Operation failed in receiver context"));
        }
        resolve(response);
      };

      timer = setTimeout(() => {
        reject(new Error(`Message timeout after ${timeoutMs}ms for type: ${message?.type}`));
      }, timeoutMs);

      try {
        if (tabId !== null && chrome.tabs?.sendMessage) {
          chrome.tabs.sendMessage(tabId, message, callback);
        } else if (chrome.runtime?.sendMessage) {
          chrome.runtime.sendMessage(message, callback);
        } else {
          clearTimeout(timer);
          reject(new Error("Chrome messaging APIs unavailable in this context"));
        }
      } catch (err) {
        if (timer) clearTimeout(timer);
        console.error("[TaskHub Messaging] Unhandled error during dispatch:", err);
        reject(err);
      }
    });
  }

  function createMessageHandler(handlers) {
    return function (message, sender, sendResponse) {
      if (!isValidMessage(message)) {
        return false;
      }

      const handler = handlers[message.type];
      if (!handler) {
        return false;
      }

      Promise.resolve()
        .then(() => handler(message.payload, sender))
        .then((res) => {
          sendResponse({ success: true, data: res });
        })
        .catch((err) => {
          console.error(`[TaskHub Messaging] Handler error for ${message.type}:`, err);
          sendResponse({
            success: false,
            error: err.message || "Internal extension messaging error",
            type: message.type,
          });
        });

      return true; // Keep channel open for async sendResponse
    };
  }

  const api = {
    MessageTypes,
    createMessage,
    isValidMessage,
    sendCrossContextMessage,
    createMessageHandler,
  };

  root.TaskHubMessaging = api;
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this);
