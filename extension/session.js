// Moodle session cookie detection (User Story 2.4.1, AB#482).
//
// The extension must know whether the student has an active Moodle login. Moodle keeps it in
// the "MoodleSession" cookie (on moodle.jct.ac.il the name has a site-specific suffix, so we
// match by prefix). This file reads that cookie with the chrome.cookies API and reports:
//   - is it there, and when does it expire  -> readSessionState()
//   - did it just appear or disappear       -> createCookieListener()
//
// No chrome.* calls happen at load time: every function that needs the API gets it as a
// parameter, so the tests in extension/tests/session.test.js can run it with a fake and no
// browser. background.js loads this file (import "./session.js") and passes the real `chrome`.
(function (root) {
  const COOKIE_PREFIX = "MoodleSession";

  // The three answers: a usable cookie, no cookie, or a cookie whose expiry date has passed.
  const STATES = { ACTIVE: "ACTIVE", MISSING: "MISSING", EXPIRED: "EXPIRED" };

  // The session cookie among a list of cookies. If the site set more than one, an unexpired
  // one wins, so a leftover expired cookie never hides a working login.
  function findSessionCookie(cookies, nowMs = Date.now()) {
    const matches = (cookies || []).filter(
      (c) => c && typeof c.name === "string" && c.name.startsWith(COOKIE_PREFIX)
    );
    if (matches.length === 0) return null;
    return matches.find((c) => !isExpired(c, nowMs)) || matches[0];
  }

  // A cookie without an expirationDate is a browser-session cookie: valid until the browser closes.
  function isExpired(cookie, nowMs) {
    return typeof cookie.expirationDate === "number" && cookie.expirationDate * 1000 <= nowMs;
  }

  // The authentication state for one cookie (or none). `expiresAt` is an ISO date, or null when
  // there is no cookie or it lasts for the browser session.
  function describeSession(cookie, nowMs = Date.now()) {
    const checkedAt = new Date(nowMs).toISOString();
    if (!cookie) return { state: STATES.MISSING, active: false, expiresAt: null, checkedAt };
    const expiresAt = typeof cookie.expirationDate === "number"
      ? new Date(cookie.expirationDate * 1000).toISOString()
      : null;
    if (isExpired(cookie, nowMs)) return { state: STATES.EXPIRED, active: false, expiresAt, checkedAt };
    return { state: STATES.ACTIVE, active: true, expiresAt, checkedAt };
  }

  // Ask the browser for the cookies that apply to `url` (for example "https://moodle.jct.ac.il/").
  async function readSessionState(chromeApi, url, nowMs = Date.now()) {
    const cookies = await chromeApi.cookies.getAll({ url });
    return describeSession(findSessionCookie(cookies, nowMs), nowMs);
  }

  // Do two states say the same thing? checkedAt is ignored: it changes on every check.
  function sameSession(a, b) {
    return Boolean(a) && Boolean(b) && a.state === b.state && a.expiresAt === b.expiresAt;
  }

  function hostOf(url) {
    return new URL(url).hostname.toLowerCase();
  }

  // A cookie set for "jct.ac.il" (or ".jct.ac.il") also applies to moodle.jct.ac.il, but a cookie
  // for "oodle.jct.ac.il" or "other.ac.il" does not.
  function cookieAppliesToHost(cookieDomain, host) {
    const domain = String(cookieDomain || "").replace(/^\./, "").toLowerCase();
    return domain !== "" && (host === domain || host.endsWith("." + domain));
  }

  // Is this chrome.cookies.onChanged event about the Moodle session cookie of `url`?
  // Returns { kind: "added" | "removed", cause } or null when it should be ignored.
  function describeCookieChange(changeInfo, url) {
    const cookie = changeInfo && changeInfo.cookie;
    if (!cookie || typeof cookie.name !== "string" || !cookie.name.startsWith(COOKIE_PREFIX)) return null;
    if (!cookieAppliesToHost(cookie.domain, hostOf(url))) return null;
    // Setting a cookie that already exists is reported as "removed (overwrite)" and then
    // "added". Only the second one is a real change, so the first is skipped.
    if (changeInfo.removed && changeInfo.cause === "overwrite") return null;
    return { kind: changeInfo.removed ? "removed" : "added", cause: changeInfo.cause };
  }

  // The listener for chrome.cookies.onChanged. On a real change of the session cookie it reads
  // the state again (the truth is in the cookie jar, not in the event) and calls
  // onChange(state, change). Returned so that background.js registers it and tests can call it.
  function createCookieListener(chromeApi, url, onChange, now = Date.now) {
    return async function onCookieChanged(changeInfo) {
      const change = describeCookieChange(changeInfo, url);
      if (!change) return;
      const state = await readSessionState(chromeApi, url, now());
      await onChange(state, change);
    };
  }

  const api = {
    COOKIE_PREFIX, STATES,
    findSessionCookie, describeSession, readSessionState, sameSession,
    cookieAppliesToHost, describeCookieChange, createCookieListener,
  };
  root.TaskHubSession = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
