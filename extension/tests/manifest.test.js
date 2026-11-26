const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const manifestPath = path.resolve(__dirname, "../manifest.json");

test("Manifest V3 Configuration Validation (US 2.1.1, AB#470)", () => {
  const content = fs.readFileSync(manifestPath, "utf-8");
  const manifest = JSON.parse(content);

  // AC 1: manifest_version strictly 3
  assert.equal(manifest.manifest_version, 3, "Manifest version must be 3");

  // AC 2: Required permissions declared
  const expectedPermissions = ["storage", "scripting", "activeTab"];
  for (const perm of expectedPermissions) {
    assert.ok(
      manifest.permissions?.includes(perm),
      `Required permission '${perm}' must be declared`
    );
  }

  // Host permissions for Moodle declared
  assert.ok(
    manifest.host_permissions?.some((p) => p.includes("moodle")),
    "Moodle host permissions must be declared"
  );

  // Service Worker background
  assert.equal(manifest.background?.service_worker, "background.js");
  assert.equal(manifest.background?.type, "module");

  // No deprecated Manifest V2 keys
  assert.equal(manifest.browser_action, undefined);
  assert.equal(manifest.page_action, undefined);
  assert.equal(manifest.background?.scripts, undefined);

  // Referenced files exist on disk
  const bgPath = path.resolve(__dirname, "..", manifest.background.service_worker);
  assert.ok(fs.existsSync(bgPath), `Background service worker file ${bgPath} must exist`);

  const popupPath = path.resolve(__dirname, "..", manifest.action.default_popup);
  assert.ok(fs.existsSync(popupPath), `Popup file ${popupPath} must exist`);

  for (const cs of manifest.content_scripts || []) {
    for (const js of cs.js || []) {
      const scriptPath = path.resolve(__dirname, "..", js);
      assert.ok(fs.existsSync(scriptPath), `Content script ${js} must exist`);
    }
  }
});
