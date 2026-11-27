// Tests for extension/session.js (User Story 2.4.1, AB#482): Moodle session cookie detection.
// Run from the repo root:  node --test extension/tests/   (or `npm test` inside extension/)
// A fake `chrome` object stands in for the browser, so nothing here needs Chrome.
const test = require("node:test");
const assert = require("node:assert/strict");
const S = require("../session.js");

const URL_MOODLE = "https://moodle.jct.ac.il/";
const NOW = Date.UTC(2026, 10, 26, 12, 0, 0); // 26 Nov 2026, 12:00 UTC
const inSeconds = (ms) => Math.floor(ms / 1000);
const HOUR = 3600 * 1000;

function cookie(overrides = {}) {
  return {
    name: "MoodleSessionjct", domain: "moodle.jct.ac.il", value: "x",
    expirationDate: inSeconds(NOW + 2 * HOUR), ...overrides,
  };
}

// A fake chrome.cookies: `jar` is what getAll returns, `fire` calls the registered listener.
function fakeChrome(jar) {
  const queries = [];
  let listener = null;
  return {
    queries,
    jar,
    cookies: {
      getAll: async (query) => { queries.push(query); return jar.slice(); },
      onChanged: { addListener: (fn) => { listener = fn; } },
    },
    register(fn) { listener = fn; },
    fire: (changeInfo) => listener(changeInfo),
  };
}

// --- Task 2.4.1.2: presence and expiration date ---

test("findSessionCookie matches by prefix: MoodleSession and MoodleSessionjct", () => {
  assert.equal(S.findSessionCookie([cookie({ name: "MoodleSession" })]).name, "MoodleSession");
  assert.equal(S.findSessionCookie([cookie({ name: "MoodleSessionjct" })]).name, "MoodleSessionjct");
});

test("findSessionCookie ignores other cookies and returns null when there is none", () => {
  assert.equal(S.findSessionCookie([cookie({ name: "MOODLEID1_" }), cookie({ name: "theme" })]), null);
  assert.equal(S.findSessionCookie([]), null);
  assert.equal(S.findSessionCookie(undefined), null);
});

test("findSessionCookie prefers an unexpired cookie over a leftover expired one", () => {
  const expired = cookie({ name: "MoodleSession", expirationDate: inSeconds(NOW - HOUR) });
  const valid = cookie({ name: "MoodleSessionjct", expirationDate: inSeconds(NOW + HOUR) });
  assert.equal(S.findSessionCookie([expired, valid], NOW).name, "MoodleSessionjct");
  assert.equal(S.findSessionCookie([valid, expired], NOW).name, "MoodleSessionjct");
});

test("describeSession: active cookie reports its expiration date", () => {
  const state = S.describeSession(cookie(), NOW);
  assert.equal(state.state, "ACTIVE");
  assert.equal(state.active, true);
  assert.equal(state.expiresAt, new Date(NOW + 2 * HOUR).toISOString());
  assert.equal(state.checkedAt, new Date(NOW).toISOString());
});

test("describeSession: no cookie is MISSING and not active", () => {
  const state = S.describeSession(null, NOW);
  assert.deepEqual([state.state, state.active, state.expiresAt], ["MISSING", false, null]);
});

test("describeSession: an expired cookie is EXPIRED, and still reports when it expired", () => {
  const state = S.describeSession(cookie({ expirationDate: inSeconds(NOW - HOUR) }), NOW);
  assert.equal(state.state, "EXPIRED");
  assert.equal(state.active, false);
  assert.equal(state.expiresAt, new Date(NOW - HOUR).toISOString());
});

test("describeSession: a cookie that expires exactly now is expired", () => {
  assert.equal(S.describeSession(cookie({ expirationDate: inSeconds(NOW) }), NOW).state, "EXPIRED");
});

test("describeSession: a browser-session cookie (no expirationDate) is active with expiresAt null", () => {
  const sessionCookie = cookie();
  delete sessionCookie.expirationDate;
  const state = S.describeSession(sessionCookie, NOW);
  assert.deepEqual([state.state, state.active, state.expiresAt], ["ACTIVE", true, null]);
});

// --- Task 2.4.1.1: query with the chrome.cookies API ---

test("readSessionState asks chrome.cookies.getAll for the given Moodle url", async () => {
  const chrome = fakeChrome([cookie()]);
  const state = await S.readSessionState(chrome, URL_MOODLE, NOW);
  assert.deepEqual(chrome.queries, [{ url: URL_MOODLE }]);
  assert.equal(state.state, "ACTIVE");
});

test("readSessionState: active cookie, missing cookie and expired cookie", async () => {
  assert.equal((await S.readSessionState(fakeChrome([cookie()]), URL_MOODLE, NOW)).state, "ACTIVE");
  assert.equal((await S.readSessionState(fakeChrome([]), URL_MOODLE, NOW)).state, "MISSING");
  const expired = cookie({ expirationDate: inSeconds(NOW - 1000) });
  assert.equal((await S.readSessionState(fakeChrome([expired]), URL_MOODLE, NOW)).state, "EXPIRED");
});

test("sameSession compares state and expiry but not the check time", () => {
  const a = S.describeSession(cookie(), NOW);
  const b = S.describeSession(cookie(), NOW + 5000);
  assert.equal(S.sameSession(a, b), true);
  assert.equal(S.sameSession(a, S.describeSession(null, NOW)), false);
  assert.equal(S.sameSession(a, S.describeSession(cookie({ expirationDate: inSeconds(NOW + 9 * HOUR) }), NOW)), false);
  assert.equal(S.sameSession(undefined, a), false);
});

// --- Task 2.4.1.3: change events ---

test("cookieAppliesToHost: own host, parent domain with a dot, and lookalikes", () => {
  const host = "moodle.jct.ac.il";
  assert.equal(S.cookieAppliesToHost("moodle.jct.ac.il", host), true);
  assert.equal(S.cookieAppliesToHost(".jct.ac.il", host), true);
  assert.equal(S.cookieAppliesToHost("jct.ac.il", host), true);
  assert.equal(S.cookieAppliesToHost("oodle.jct.ac.il", host), false);
  assert.equal(S.cookieAppliesToHost("evil-moodle.jct.ac.il", host), false);
  assert.equal(S.cookieAppliesToHost("other.ac.il", host), false);
  assert.equal(S.cookieAppliesToHost("", host), false);
  assert.equal(S.cookieAppliesToHost(undefined, host), false);
});

test("describeCookieChange: added, and removed for each reason the browser gives", () => {
  assert.deepEqual(
    S.describeCookieChange({ cookie: cookie(), removed: false, cause: "explicit" }, URL_MOODLE),
    { kind: "added", cause: "explicit" }
  );
  for (const cause of ["explicit", "expired", "expired_overwrite", "evicted"]) {
    assert.deepEqual(
      S.describeCookieChange({ cookie: cookie(), removed: true, cause }, URL_MOODLE),
      { kind: "removed", cause }
    );
  }
});

test("describeCookieChange ignores an overwrite (it is followed by an 'added' event)", () => {
  assert.equal(S.describeCookieChange({ cookie: cookie(), removed: true, cause: "overwrite" }, URL_MOODLE), null);
});

test("describeCookieChange ignores other cookies and cookies of other sites", () => {
  assert.equal(S.describeCookieChange({ cookie: cookie({ name: "theme" }), removed: false, cause: "explicit" }, URL_MOODLE), null);
  assert.equal(S.describeCookieChange({ cookie: cookie({ domain: "example.com" }), removed: false, cause: "explicit" }, URL_MOODLE), null);
  assert.equal(S.describeCookieChange({}, URL_MOODLE), null);
  assert.equal(S.describeCookieChange(undefined, URL_MOODLE), null);
});

test("listener: adding the cookie fires an ACTIVE state update", async () => {
  const chrome = fakeChrome([cookie()]);
  const updates = [];
  chrome.register(S.createCookieListener(chrome, URL_MOODLE, async (state, change) => updates.push([state, change]), () => NOW));

  await chrome.fire({ cookie: cookie(), removed: false, cause: "explicit" });

  assert.equal(updates.length, 1);
  assert.equal(updates[0][0].state, "ACTIVE");
  assert.deepEqual(updates[0][1], { kind: "added", cause: "explicit" });
});

test("listener: removing the cookie fires a MISSING state update", async () => {
  const chrome = fakeChrome([]); // the browser no longer has it
  const updates = [];
  chrome.register(S.createCookieListener(chrome, URL_MOODLE, async (state, change) => updates.push([state, change]), () => NOW));

  await chrome.fire({ cookie: cookie(), removed: true, cause: "explicit" });

  assert.equal(updates.length, 1);
  assert.equal(updates[0][0].state, "MISSING");
  assert.equal(updates[0][0].active, false);
  assert.deepEqual(updates[0][1], { kind: "removed", cause: "explicit" });
});

test("listener: the browser removing an expired cookie fires a state update", async () => {
  const chrome = fakeChrome([]);
  const updates = [];
  chrome.register(S.createCookieListener(chrome, URL_MOODLE, async (state) => updates.push(state), () => NOW));
  await chrome.fire({ cookie: cookie(), removed: true, cause: "expired" });
  assert.equal(updates.length, 1);
  assert.equal(updates[0].active, false);
});

test("listener: renewing the cookie (overwrite, then added) fires once", async () => {
  const chrome = fakeChrome([cookie()]);
  const updates = [];
  chrome.register(S.createCookieListener(chrome, URL_MOODLE, async (state) => updates.push(state), () => NOW));

  await chrome.fire({ cookie: cookie(), removed: true, cause: "overwrite" });
  await chrome.fire({ cookie: cookie(), removed: false, cause: "explicit" });

  assert.equal(updates.length, 1);
  assert.equal(updates[0].state, "ACTIVE");
});

test("listener: unrelated cookies do not fire anything or call chrome.cookies", async () => {
  const chrome = fakeChrome([cookie()]);
  const updates = [];
  chrome.register(S.createCookieListener(chrome, URL_MOODLE, async (state) => updates.push(state), () => NOW));

  await chrome.fire({ cookie: cookie({ name: "theme" }), removed: false, cause: "explicit" });
  await chrome.fire({ cookie: cookie({ domain: "example.com" }), removed: false, cause: "explicit" });

  assert.equal(updates.length, 0);
  assert.equal(chrome.queries.length, 0);
});
