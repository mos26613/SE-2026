const test = require("node:test");
const assert = require("node:assert/strict");
const {
  MessageTypes,
  createMessage,
  isValidMessage,
  createMessageHandler,
  sendCrossContextMessage,
} = require("../messaging.js");

test("Cross-Context Message Passing Infrastructure (US 2.1.4, AB#473)", async () => {
  // AC 1: Standard message structures with typed payloads
  const msg = createMessage(MessageTypes.SCRAPED_DATA, [{ id: 1, title: "Test" }]);
  assert.equal(msg.type, "SCRAPED_DATA");
  assert.equal(Array.isArray(msg.payload), true);
  assert.ok(msg.meta.timestamp > 0);
  assert.equal(isValidMessage(msg), true);
  assert.equal(isValidMessage({ type: "UNKNOWN_TYPE" }), false);

  // AC 2: Async response handling with promises / sendResponse
  const asyncHandlers = {
    [MessageTypes.CHECK_SESSION]: async (payload) => {
      await new Promise((r) => setTimeout(r, 10));
      return { active: true, domain: payload.domain };
    },
    [MessageTypes.FORCE_SCRAPE]: async () => {
      throw new Error("Simulated scraping timeout error");
    },
  };

  const listener = createMessageHandler(asyncHandlers);

  // Verify async handler returns true to keep channel open
  let asyncResponse = null;
  const keptChannelOpen = listener(
    createMessage(MessageTypes.CHECK_SESSION, { domain: "moodle.jct.ac.il" }),
    { tab: { id: 10 } },
    (res) => {
      asyncResponse = res;
    }
  );
  assert.equal(keptChannelOpen, true, "onMessage listener must return true for async sendResponse");

  // Wait for async execution
  await new Promise((r) => setTimeout(r, 30));
  assert.deepEqual(asyncResponse, {
    success: true,
    data: { active: true, domain: "moodle.jct.ac.il" },
  });

  // AC 3: Errors caught, logged and surfaced cleanly
  let errorResponse = null;
  listener(createMessage(MessageTypes.FORCE_SCRAPE), {}, (res) => {
    errorResponse = res;
  });

  await new Promise((r) => setTimeout(r, 30));
  assert.equal(errorResponse.success, false);
  assert.equal(errorResponse.error, "Simulated scraping timeout error");
  assert.equal(errorResponse.type, "FORCE_SCRAPE");
});
