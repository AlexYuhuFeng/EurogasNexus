// Focused, browser-free tests for the durable economics browser harness.
//
// The module is import-safe: required environment and Playwright are resolved
// only when main() runs. These checks therefore exercise the actual config,
// sanitizer and golden functions without launching Chromium or reading a secret.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  CAPACITY_GOLDENS,
  ENV_NAMES,
  LNG_GOLDEN,
  resolveAllowNonLoopback,
  sanitizeDiagnostic,
  validateBaseConfiguration,
} from "../../scripts/uat/economics_workflow_smoke.mjs";

test("loopback Web origins are accepted without a remote opt-in", () => {
  const accepted = validateBaseConfiguration("http://127.0.0.1:3000", false);
  assert.deepEqual(accepted, { origin: "http://127.0.0.1:3000", loopback: true });
  assert.equal(validateBaseConfiguration("http://localhost:3000", false).loopback, true);
});

test("base URL is required and cannot carry credentials, path or query", () => {
  assert.throws(() => validateBaseConfiguration("", false), /required/);
  assert.throws(
    () => validateBaseConfiguration("http://user:secret@127.0.0.1:3000", false),
    /embedded credentials/,
  );
  assert.throws(
    () => validateBaseConfiguration("http://127.0.0.1:3000/api", false),
    /origin only/,
  );
  assert.throws(
    () => validateBaseConfiguration("http://127.0.0.1:3000/?debug=1", false),
    /origin only/,
  );
});

test("remote UAT requires exactly 1 and HTTPS", () => {
  assert.equal(resolveAllowNonLoopback(""), false);
  assert.equal(resolveAllowNonLoopback("1"), true);
  assert.throws(() => resolveAllowNonLoopback("true"), /unset or exactly '1'/);
  assert.throws(
    () => validateBaseConfiguration("https://uat.example.invalid", false),
    /UAT opt-in/,
  );
  assert.throws(
    () => validateBaseConfiguration("http://uat.example.invalid", true),
    /must use HTTPS/,
  );
  assert.deepEqual(
    validateBaseConfiguration("https://uat.example.invalid", true),
    { origin: "https://uat.example.invalid", loopback: false },
  );
});

test("diagnostics remove credentials, bearer headers and excess length", () => {
  const sanitized = sanitizeDiagnostic(
    "Authorization: Bearer abc.def password=p@ss "
      + "http://user:secret@127.0.0.1:3000/x",
    ["p@ss"],
  );
  assert.equal(sanitized.includes("p@ss"), false);
  assert.equal(sanitized.includes("abc.def"), false);
  assert.equal(sanitized.includes("user:secret"), false);
  assert.ok(sanitized.length <= 503);
});

test("capacity goldens keep the documented exact strings", () => {
  const byId = Object.fromEntries(CAPACITY_GOLDENS.map((golden) => [golden.id, golden]));
  assert.equal(byId["capacity-23h"].expectedTotalCost, "460.0000");
  assert.equal(byId["capacity-23h"].expectedCostPerDelivered, "4.0000");
  assert.equal(byId["capacity-23h"].expectedDurationMicroseconds, 82_800_000_000);
  assert.equal(byId["capacity-25h"].expectedTotalCost, "500.0000");
  assert.equal(byId["capacity-25h"].expectedDurationMicroseconds, 90_000_000_000);
  assert.equal(byId["capacity-pence-24h"].expectedTotalCost, "85.9848");
  assert.equal(byId["capacity-pence-24h"].expectedCostPerDelivered, "0.7165");
  assert.equal(byId["capacity-pence-24h"].currency, "GBP");
  assert.equal(byId["capacity-pence-24h"].tariffUnit, "p/(kWh/h)/h");
});

test("LNG golden keeps the exact money and energy split", () => {
  assert.equal(LNG_GOLDEN.expectedPurchaseOutlayEur, "2000.0000");
  assert.equal(LNG_GOLDEN.expectedSaleProceedsEur, "2700.0000");
  assert.equal(LNG_GOLDEN.expectedDownstreamCostsEur, "150.0000");
  assert.equal(LNG_GOLDEN.expectedCargoMarginEur, "550.0000");
  assert.equal(LNG_GOLDEN.expectedNetPresentValueEur, "482.5000");
  assert.equal(LNG_GOLDEN.expectedTotalUndiscountedCashEur, "550.0000");
  assert.equal(LNG_GOLDEN.expectedTotalConsumedMwh, "7");
  assert.equal(LNG_GOLDEN.expectedPhysicalLossMwh, "3");
  assert.equal(LNG_GOLDEN.expectedTotalReductionMwh, "10");
  assert.equal(LNG_GOLDEN.expectedPhysicalReadiness, "NOT_ASSESSED");
  assert.equal(LNG_GOLDEN.expectedRefusalViolation, "STAGE_CONSERVATION_FAILED");
});

test("browser script has no mock money and no secret-file assumption", () => {
  const source = readFileSync(
    new URL("../../scripts/uat/economics_workflow_smoke.mjs", import.meta.url),
    "utf8",
  );
  assert.match(source, /route\.continue\(\)/);
  assert.doesNotMatch(source, /route\.fulfill/);
  assert.doesNotMatch(source, /browser-runtime-secrets/);
  assert.doesNotMatch(source, /\.local-runtime/);
  assert.equal(ENV_NAMES.username, "EUROGAS_NEXUS_DEV_LOGIN_USERNAME");
  assert.equal(ENV_NAMES.password, "EUROGAS_NEXUS_DEV_LOGIN_PASSWORD");
  assert.equal(ENV_NAMES.baseUrl, "EUROGAS_UAT_BASE_URL");
  assert.equal(ENV_NAMES.playwrightPath, "EUROGAS_UAT_PLAYWRIGHT_PATH");
  assert.equal(ENV_NAMES.outputDir, "EUROGAS_UAT_OUTPUT_DIR");
  assert.equal(ENV_NAMES.axePath, "EUROGAS_UAT_AXE_PATH");
  assert.match(source, /Control\+Enter/);
  assert.match(source, /capacity-billing/);
  assert.match(source, /lng-economics-only/);
});
