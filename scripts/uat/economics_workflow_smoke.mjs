// Durable browser acceptance for the existing capacity-billing and LNG
// economics-only workflows.
//
// The run is deliberately evidence-oriented and bounded:
// - it logs in to the existing development fixture (never creates or seeds one);
// - it types the capacity form and the LNG dynamic stage/cost/discount rows in
//   English and Simplified Chinese at 1440px and 390px;
// - it uses the product's Ctrl+Enter submit path, asserts focus is visible on
//   the monetary result, and proves an edit invalidates a displayed result;
// - it proves the backend's exact 422 refusals for inconsistent billed capacity
//   energy and broken LNG energy conservation;
// - it delays one actual backend request through Playwright routing to prove the
//   in-flight guard refuses a duplicate submit. The route handler only waits and
//   calls `route.continue()`; it never fulfills, mocks or rewrites a response.
//
// Required environment (no defaults are read from a secret file):
// - EUROGAS_NEXUS_DEV_LOGIN_USERNAME / EUROGAS_NEXUS_DEV_LOGIN_PASSWORD
// - EUROGAS_UAT_BASE_URL: Web origin, loopback unless explicitly opted out
// - EUROGAS_UAT_PLAYWRIGHT_PATH: absolute path to the installed Playwright entry
//
// Optional environment:
// - EUROGAS_UAT_ALLOW_NON_LOOPBACK=1 with an HTTPS EUROGAS_UAT_BASE_URL:
//   explicit remote UAT configuration. Plain HTTP is refused off loopback.
// - EUROGAS_UAT_OUTPUT_DIR: optional directory for bounded JSON + viewport PNGs
// - EUROGAS_UAT_AXE_PATH: optional axe-core file; when absent the run tries the
//   dependency beside Playwright. If axe is unavailable it is reported, never
//   silently declared passing.
//
// The script writes no database rows, seeds no fixture, grants no authority,
// retrieves no provider data and prints no credential. It does create a normal
// login session through the app's existing development form.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const LANGUAGE_STORAGE_KEY = "eurogas.language.v1";
const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const MAX_DETAIL_LENGTH = 500;
const MAX_CHECKS = 320;
const MAX_FAILURES = 60;
const DUPLICATE_PROBE_WAIT_MS = 200;
const SUBMIT_TIMEOUT_MS = 30_000;
const LOGIN_TIMEOUT_MS = 20_000;
const AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];
const LOOPBACK_HOSTS = new Set(["127.0.0.1", "localhost", "::1"]);

export const ENV_NAMES = Object.freeze({
  username: "EUROGAS_NEXUS_DEV_LOGIN_USERNAME",
  password: "EUROGAS_NEXUS_DEV_LOGIN_PASSWORD",
  baseUrl: "EUROGAS_UAT_BASE_URL",
  playwrightPath: "EUROGAS_UAT_PLAYWRIGHT_PATH",
  outputDir: "EUROGAS_UAT_OUTPUT_DIR",
  axePath: "EUROGAS_UAT_AXE_PATH",
  allowNonLoopback: "EUROGAS_UAT_ALLOW_NON_LOOPBACK",
});

export const LANGUAGES = Object.freeze([
  { id: "en", startsWith: "en", i18n: "en.json" },
  { id: "zh-CN", startsWith: "zh", i18n: "zh.json" },
]);

export const VIEWPORTS = Object.freeze([
  { id: "desktop-1440", width: 1440, height: 900 },
  { id: "mobile-390", width: 390, height: 844 },
]);

const CAPTURE_VIEWPORTS = VIEWPORTS;
const ENDPOINTS = Object.freeze({
  capacity: "/api/research/capacity-billing",
  lng: "/api/research/lng-economics-only",
});

function deepFreeze(value) {
  if (value === null || typeof value !== "object") return value;
  Object.freeze(value);
  for (const child of Object.values(value)) deepFreeze(child);
  return value;
}

export const CAPACITY_GOLDENS = deepFreeze([
  {
    id: "capacity-23h",
    scenarioId: "synthetic-capacity-23h",
    tariffId: "synthetic-tariff-23h",
    tariffRate: "2",
    tariffUnit: "EUR/(MWh/h)/h",
    currency: "EUR",
    bookedCapacityMwhPerHour: "10",
    deliveredEnergyMwh: "115",
    billedCapacityEnergyMwh: "230",
    billingStart: "2026-01-01T00:00:00+00:00",
    billingEnd: "2026-01-01T23:00:00+00:00",
    sourceReferences: [
      "synthetic-input:booking-23h",
      "synthetic-input:tariff-23h",
    ],
    expectedTotalCost: "460.0000",
    expectedCostPerDelivered: "4.0000",
    expectedDurationMicroseconds: 82_800_000_000,
    expectedDurationHours: "23",
  },
  {
    id: "capacity-25h",
    scenarioId: "synthetic-capacity-25h",
    tariffId: "synthetic-tariff-25h",
    tariffRate: "2",
    tariffUnit: "EUR/(MWh/h)/h",
    currency: "EUR",
    bookedCapacityMwhPerHour: "10",
    deliveredEnergyMwh: "125",
    billedCapacityEnergyMwh: "250",
    billingStart: "2026-01-02T00:00:00+00:00",
    billingEnd: "2026-01-03T01:00:00+00:00",
    sourceReferences: [
      "synthetic-input:booking-25h",
      "synthetic-input:tariff-25h",
    ],
    expectedTotalCost: "500.0000",
    expectedCostPerDelivered: "4.0000",
    expectedDurationMicroseconds: 90_000_000_000,
    expectedDurationHours: "25",
  },
  {
    id: "capacity-pence-24h",
    scenarioId: "synthetic-capacity-pence-24h",
    tariffId: "synthetic-tariff-pence-24h",
    tariffRate: "0.035827",
    tariffUnit: "p/(kWh/h)/h",
    currency: "GBP",
    bookedCapacityMwhPerHour: "10",
    deliveredEnergyMwh: "120",
    billedCapacityEnergyMwh: "240",
    billingStart: "2026-01-04T00:00:00+00:00",
    billingEnd: "2026-01-05T00:00:00+00:00",
    sourceReferences: [
      "synthetic-input:booking-pence-24h",
      "synthetic-input:tariff-pence-24h",
    ],
    expectedTotalCost: "85.9848",
    expectedCostPerDelivered: "0.7165",
    expectedDurationMicroseconds: 86_400_000_000,
    expectedDurationHours: "24",
  },
]);

export const LNG_GOLDEN = deepFreeze({
  contractId: "synthetic-contract-lng-1",
  cargoId: "synthetic-cargo-lng-1",
  terminalId: "synthetic-terminal-lng-1",
  resourceId: "synthetic-resource-lng-1",
  valuationDate: "2026-09-29",
  purchasePaymentDate: "2026-09-29",
  salePaymentDate: "2026-11-30",
  purchasedEnergyMwh: "100",
  deliveredEnergyMwh: "90",
  purchaseUnitPrice: "20",
  saleUnitPrice: "30",
  purchasePriceSource: "synthetic-input:purchase-price-1",
  salePriceSource: "synthetic-input:sale-price-1",
  purchaseBasis: "FOB",
  costScopeStatement:
    "Synthetic acceptance input: the purchase price excludes shipping, "
    + "regasification and the separately invoiced downstream cost.",
  costId: "synthetic-cost-1",
  costCategory: "regas",
  costAmountEur: "150",
  costPaymentDate: "2026-09-29",
  costSource: "synthetic-input:invoiced-cost-1",
  chargeBasis: "invoiced_cash",
  discountAsOf: "2026-09-29",
  discountCurve: "synthetic-curve:eur-flat",
  discountSource: "synthetic-input:discount-factor-1",
  saleDiscountFactor: "0.975",
  energyBasisReference: "synthetic-energy-basis:cargo-mwh",
  energyUnit: "MWh",
  reportingCurrency: "EUR",
  stage1Input: "100",
  stage1Output: "96",
  stage1Consumed: "3",
  stage1Loss: "1",
  stage2Input: "96",
  stage2Output: "90",
  stage2Consumed: "4",
  stage2Loss: "2",
  expectedPurchaseOutlayEur: "2000.0000",
  expectedSaleProceedsEur: "2700.0000",
  expectedDownstreamCostsEur: "150.0000",
  expectedCargoMarginEur: "550.0000",
  expectedNetPresentValueEur: "482.5000",
  expectedTotalUndiscountedCashEur: "550.0000",
  expectedTotalConsumedMwh: "7",
  expectedPhysicalLossMwh: "3",
  expectedTotalReductionMwh: "10",
  expectedPhysicalReadiness: "NOT_ASSESSED",
  expectedRefusalCode: "lng_economics_only_refused",
  expectedRefusalViolation: "STAGE_CONSERVATION_FAILED",
});

export class ConfigurationError extends Error {}
export class AcceptanceFailure extends Error {
  constructor(scope, message) {
    super(message);
    this.scope = scope;
  }
}

/** Reject an implicit or unsafe UAT Web origin. */
export function validateBaseConfiguration(rawValue, allowNonLoopback = false) {
  if (typeof rawValue !== "string" || rawValue.trim() === "") {
    throw new ConfigurationError(
      `${ENV_NAMES.baseUrl} is required; no default Web URL is assumed.`,
    );
  }
  let url;
  try {
    url = new URL(rawValue);
  } catch {
    throw new ConfigurationError(
      `${ENV_NAMES.baseUrl} must be an absolute http(s) origin.`,
    );
  }
  if (!["http:", "https:"].includes(url.protocol)) {
    throw new ConfigurationError(
      `${ENV_NAMES.baseUrl} must use http or https.`,
    );
  }
  if (url.username || url.password) {
    throw new ConfigurationError(
      `${ENV_NAMES.baseUrl} must not contain embedded credentials.`,
    );
  }
  if ((url.pathname !== "/" && url.pathname !== "") || url.search || url.hash) {
    throw new ConfigurationError(
      `${ENV_NAMES.baseUrl} must be an origin only (no path, query or fragment).`,
    );
  }
  const host = url.hostname.toLowerCase();
  const loopback = LOOPBACK_HOSTS.has(host) || LOOPBACK_HOSTS.has(host.replace(/^\[|\]$/g, ""));
  if (!loopback) {
    if (allowNonLoopback !== true) {
      throw new ConfigurationError(
        "Non-loopback Web access requires explicit UAT opt-in via "
          + `${ENV_NAMES.allowNonLoopback}=1.`,
      );
    }
    if (url.protocol !== "https:") {
      throw new ConfigurationError(
        "An opted-in non-loopback UAT Web origin must use HTTPS.",
      );
    }
  }
  return { origin: url.origin, loopback };
}

/** Parse the explicit remote-UAT opt-in. No other value is treated as consent. */
export function resolveAllowNonLoopback(rawValue) {
  const value = typeof rawValue === "string" ? rawValue.trim() : "";
  if (value === "") return false;
  if (value === "1") return true;
  throw new ConfigurationError(
    `${ENV_NAMES.allowNonLoopback} must be unset or exactly '1'.`,
  );
}

/** Produce a bounded, credential-free diagnostic string. */
export function sanitizeDiagnostic(value, secrets = []) {
  let text = String(value ?? "");
  for (const secret of secrets) {
    if (typeof secret === "string" && secret.length > 0) {
      text = text.split(secret).join("[REDACTED]");
    }
  }
  text = text
    .replace(/https?:\/\/[^\s/@]+:[^\s/@]+@/gi, "https://[REDACTED]@")
    .replace(/\bBearer\s+[A-Za-z0-9._~+/=-]+/gi, "Bearer [REDACTED]")
    .replace(
      /\b(Authorization|X-Eurogas-Identity|X-Eurogas-Api-Key)\s*:\s*[^\s,;]+/gi,
      "$1: [REDACTED]",
    )
    .replace(/\s+/g, " ")
    .trim();
  return text.length > MAX_DETAIL_LENGTH
    ? `${text.slice(0, MAX_DETAIL_LENGTH)}...`
    : text;
}

function safeName(value) {
  return String(value).replace(/[^a-zA-Z0-9._-]+/g, "-");
}

function withTimeout(promise, milliseconds, message) {
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(message)), milliseconds);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

function readConfiguration() {
  const allowNonLoopback = resolveAllowNonLoopback(
    process.env[ENV_NAMES.allowNonLoopback],
  );
  const base = validateBaseConfiguration(
    process.env[ENV_NAMES.baseUrl],
    allowNonLoopback,
  );
  const username = (process.env[ENV_NAMES.username] || "").trim();
  const password = process.env[ENV_NAMES.password] || "";
  if (!username || !password) {
    throw new ConfigurationError(
      `${ENV_NAMES.username} and ${ENV_NAMES.password} are required; `
        + "this script reads no secret file and has no login defaults.",
    );
  }
  const playwrightPath = (process.env[ENV_NAMES.playwrightPath] || "").trim();
  if (!playwrightPath) {
    throw new ConfigurationError(
      `${ENV_NAMES.playwrightPath} is required; no Playwright package fallback is assumed.`,
    );
  }
  if (!path.isAbsolute(playwrightPath)) {
    throw new ConfigurationError(
      `${ENV_NAMES.playwrightPath} must be an absolute file path.`,
    );
  }
  const outputRaw = (process.env[ENV_NAMES.outputDir] || "").trim();
  const outputDir = outputRaw ? path.resolve(outputRaw) : null;
  if (outputDir) {
    try {
      mkdirSync(path.join(outputDir, "screenshots"), { recursive: true });
    } catch {
      throw new ConfigurationError(
        "The configured output directory could not be created.",
      );
    }
  }
  return {
    base,
    username,
    password,
    playwrightPath,
    outputDir,
    remoteUat: allowNonLoopback && !base.loopback,
  };
}

function loadAxeSource(playwrightPath) {
  const explicit = (process.env[ENV_NAMES.axePath] || "").trim();
  if (explicit) {
    try {
      return readFileSync(explicit, "utf8");
    } catch {
      throw new ConfigurationError(
        `${ENV_NAMES.axePath} was configured but could not be read.`,
      );
    }
  }
  try {
    const requireFromPlaywright = createRequire(path.resolve(playwrightPath));
    return readFileSync(requireFromPlaywright.resolve("axe-core/axe.min.js"), "utf8");
  } catch {
    return null;
  }
}

function loadI18n(language) {
  return JSON.parse(
    readFileSync(
      path.join(REPO_ROOT, "clients", "web", "src", "i18n", language.i18n),
      "utf8",
    ),
  );
}

function recordPass(summary, scope, detail = "") {
  if (summary.checks.length >= MAX_CHECKS) return;
  summary.checks.push({
    scope,
    status: "pass",
    detail: sanitizeDiagnostic(detail, summary._secrets),
  });
}

function recordFailure(summary, scope, detail) {
  if (summary.failures.length >= MAX_FAILURES) return;
  const message = sanitizeDiagnostic(detail, summary._secrets);
  if (summary.failures.some((failure) => failure.scope === scope && failure.message === message)) {
    return;
  }
  summary.failures.push({ scope, message });
}

function verify(summary, scope, condition, passDetail, failureDetail) {
  if (!condition) {
    recordFailure(summary, scope, failureDetail);
    throw new AcceptanceFailure(scope, failureDetail);
  }
  recordPass(summary, scope, passDetail);
}

async function ensureAuthenticated(page, config, summary) {
  const target = `${config.base.origin}/?workspace=contracts&task=routes`;
  await page.goto(target, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(400);
  if (await page.locator("main").isVisible().catch(() => false)) {
    recordPass(summary, "auth/existing-session", "reused the existing browser session");
    return;
  }

  const usernameInput = page.locator("#sign-in-username");
  await usernameInput.waitFor({ state: "visible", timeout: 15_000 });
  await usernameInput.fill(config.username);
  await page.locator("#sign-in-password").fill(config.password);
  await page.locator(".sign-in-dev-form button[type=submit]").click();
  await page.locator("main").waitFor({ state: "visible", timeout: LOGIN_TIMEOUT_MS });
  recordPass(summary, "auth/dev-fixture-login", "authenticated through the existing form");
}

async function setLanguage(page, language) {
  await page.evaluate(
    ([key, value]) => window.localStorage.setItem(key, value),
    [LANGUAGE_STORAGE_KEY, language.id],
  );
}

async function gotoContracts(page, config, language, task, summary) {
  await page.goto(
    `${config.base.origin}/?workspace=contracts&task=${encodeURIComponent(task)}`,
    { waitUntil: "domcontentloaded" },
  );
  await page.locator("main").waitFor({ state: "visible", timeout: LOGIN_TIMEOUT_MS });
  await page
    .waitForFunction(
      (prefix) => document.documentElement.lang.toLowerCase().startsWith(prefix),
      language.startsWith,
      { timeout: 5_000 },
    )
    .catch(() => {});
  const htmlLang = await page.evaluate(() => document.documentElement.lang);
  verify(
    summary,
    `${language.id}/document-language`,
    htmlLang.toLowerCase().startsWith(language.startsWith),
    `document language ${htmlLang}`,
    `document language did not start with ${language.startsWith}`,
  );
}

async function waitForPanelSubmit(page, panelSelector) {
  const submitSelector = `${panelSelector} button[aria-keyshortcuts="Control+Enter"]`;
  const button = page.locator(submitSelector);
  await button.waitFor({ state: "visible", timeout: 5_000 });
  await page.waitForFunction(
    (selector) => {
      const element = document.querySelector(selector);
      return element instanceof HTMLButtonElement && !element.disabled;
    },
    submitSelector,
    { timeout: 5_000 },
  );
}

async function fillCapacity(page, golden) {
  const panel = page.locator(".capacity-billing-panel");
  const fields = {
    "#capacity-billing-scenario-id": golden.scenarioId,
    "#capacity-billing-tariff-id": golden.tariffId,
    "#capacity-billing-tariff-rate": golden.tariffRate,
    "#capacity-billing-booked": golden.bookedCapacityMwhPerHour,
    "#capacity-billing-delivered": golden.deliveredEnergyMwh,
    "#capacity-billing-billed": golden.billedCapacityEnergyMwh,
    "#capacity-billing-start": golden.billingStart,
    "#capacity-billing-end": golden.billingEnd,
    "#capacity-billing-source-references": golden.sourceReferences.join("\n"),
  };
  for (const [selector, value] of Object.entries(fields)) {
    await page.locator(selector).fill(value);
  }
  await page.locator("#capacity-billing-tariff-unit").selectOption(golden.tariffUnit);
  await page.locator("#capacity-billing-currency").selectOption(golden.currency);
  return panel;
}

function isEndpointResponse(response, endpoint) {
  try {
    const url = new URL(response.url());
    return url.pathname === endpoint && response.request().method() === "POST";
  } catch {
    return false;
  }
}

async function timedSubmitWithDuplicateGuard({
  page,
  panelSelector,
  endpoint,
  submit,
  summary,
  scope,
}) {
  let requests = 0;
  let releaseFirst = () => {};
  let markStarted = () => {};
  const firstHeld = new Promise((resolve) => {
    releaseFirst = resolve;
  });
  const firstStarted = new Promise((resolve) => {
    markStarted = resolve;
  });
  const pattern = `**${endpoint}`;
  const handler = async (route) => {
    if (route.request().method() !== "POST") {
      await route.continue();
      return;
    }
    requests += 1;
    if (requests === 1) {
      markStarted();
      await firstHeld;
    }
    await route.continue();
  };

  await page.route(pattern, handler);
  try {
    const responsePromise = page.waitForResponse(
      (response) => isEndpointResponse(response, endpoint),
      { timeout: SUBMIT_TIMEOUT_MS },
    );
    responsePromise.catch(() => {});
    await submit();
    await withTimeout(
      firstStarted,
      SUBMIT_TIMEOUT_MS,
      "submit never produced a backend request",
    );
    const inFlight = await page
      .waitForFunction(
        () => Boolean(document.querySelector('[aria-busy="true"]')),
        null,
        { timeout: 5_000 },
      )
      .then(() => true)
      .catch(() => false);
    verify(
      summary,
      `${scope}/in-flight`,
      inFlight,
      "submission entered the aria-busy state",
      "submission never reported an in-flight state",
    );

    // Dispatch the panel's own chord while the first request is held. The
    // handler must be inert while busy; this is not a second request helper.
    await page.locator(panelSelector).evaluate((panel) => {
      panel.dispatchEvent(
        new KeyboardEvent("keydown", {
          key: "Enter",
          code: "Enter",
          ctrlKey: true,
          bubbles: true,
          cancelable: true,
        }),
      );
    });
    await page.waitForTimeout(DUPLICATE_PROBE_WAIT_MS);
    verify(
      summary,
      `${scope}/duplicate-submit`,
      requests === 1,
      "one backend request while the first submission was in flight",
      `duplicate submit reached the backend (${requests} requests)`,
    );

    // Release the actual request only after proving the in-flight guard. The
    // response the browser receives is the backend's own, not a route fixture.
    releaseFirst();
    const response = await responsePromise;
    verify(
      summary,
      `${scope}/response-actual-backend`,
      response.status() === 200,
      "actual backend response received",
      `actual backend returned HTTP ${response.status()}`,
    );
    return response;
  } finally {
    releaseFirst();
    await page.unroute(pattern, handler).catch(() => {});
  }
}

async function assertFocusVisible(summary, page, selector, snippets, scope) {
  const focused = await page
    .waitForFunction(
      (resultSelector) => document.activeElement === document.querySelector(resultSelector),
      selector,
      { timeout: 5_000 },
    )
    .then(() => true)
    .catch(() => false);
  verify(
    summary,
    `${scope}/focus-reached`,
    focused,
    "success response moved focus to the monetary result",
    "success response did not move focus to the monetary result",
  );
  const state = await page.locator(selector).evaluate((element) => {
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return {
      active: document.activeElement === element,
      visible: rect.width > 0 && rect.height > 0
        && style.display !== "none" && style.visibility !== "hidden"
        && rect.bottom > 0 && rect.top < window.innerHeight,
      outlineStyle: style.outlineStyle,
      outlineWidth: Number.parseFloat(style.outlineWidth) || 0,
    };
  });
  verify(
    summary,
    `${scope}/focus-visible-monetary-summary`,
    state.active && state.visible && state.outlineStyle !== "none" && state.outlineWidth >= 1,
    `focused monetary result with a ${state.outlineWidth}px outline`,
    "monetary result was not focused with a visible outline",
  );
  const text = await page.locator(selector).innerText();
  for (const snippet of snippets) {
    verify(
      summary,
      `${scope}/exact-summary/${snippet}`,
      text.includes(snippet),
      `rendered ${snippet}`,
      `rendered result did not contain ${snippet}`,
    );
  }
}

async function assertCapacityResponse(summary, response, golden, scope) {
  const body = await response.json();
  summary.actual_backend_responses = true;
  const data = body?.data ?? {};
  verify(
    summary,
    `${scope}/total-cost`,
    data.total_cost === golden.expectedTotalCost,
    `total_cost=${data.total_cost}`,
    `expected total_cost ${golden.expectedTotalCost}`,
  );
  verify(
    summary,
    `${scope}/cost-per-delivered`,
    data.cost_per_delivered_mwh === golden.expectedCostPerDelivered,
    `cost_per_delivered_mwh=${data.cost_per_delivered_mwh}`,
    `expected cost_per_delivered_mwh ${golden.expectedCostPerDelivered}`,
  );
  verify(
    summary,
    `${scope}/duration-microseconds`,
    data.duration_microseconds === golden.expectedDurationMicroseconds,
    `duration_microseconds=${data.duration_microseconds}`,
    `expected duration_microseconds ${golden.expectedDurationMicroseconds}`,
  );
  verify(
    summary,
    `${scope}/duration-hours`,
    data.duration_hours === golden.expectedDurationHours,
    `duration_hours=${data.duration_hours}`,
    `expected duration_hours ${golden.expectedDurationHours}`,
  );
  verify(
    summary,
    `${scope}/physical-readiness`,
    data.physical_readiness === "NOT_ASSESSED",
    "physical_readiness=NOT_ASSESSED",
    "physical readiness was not NOT_ASSESSED",
  );
  verify(
    summary,
    `${scope}/model-version`,
    data.model_version === "capacity-billing/v1",
    "model_version=capacity-billing/v1",
    "unexpected capacity-billing model version",
  );
  verify(
    summary,
    `${scope}/references-unverified`,
    body?.meta?.references_verified === false
      && body?.meta?.booked_rights_established === false
      && body?.meta?.customer_approval === false,
    "sandbox metadata keeps references, booked rights and approval unestablished",
    "sandbox metadata overstated authority",
  );
}

async function assertCapacityUi(summary, page, golden, scope) {
  const result = page.locator(".capacity-billing-result");
  await result.waitFor({ state: "visible", timeout: 10_000 });
  await assertFocusVisible(
    summary,
    page,
    ".capacity-billing-result",
    [golden.expectedTotalCost, golden.expectedCostPerDelivered, "NOT_ASSESSED"],
    scope,
  );
}

async function runCapacityCase({
  page,
  summary,
  language,
  golden,
  withTimingGuard,
}) {
  const scope = `${language.id}/${golden.id}`;
  await fillCapacity(page, golden);
  await waitForPanelSubmit(page, ".capacity-billing-panel");
  let response;
  if (withTimingGuard) {
    response = await timedSubmitWithDuplicateGuard({
      page,
      panelSelector: ".capacity-billing-panel",
      endpoint: ENDPOINTS.capacity,
      submit: () => page.locator("#capacity-billing-scenario-id").press("Control+Enter"),
      summary,
      scope,
    });
  } else {
    const responsePromise = page.waitForResponse(
      (candidate) => isEndpointResponse(candidate, ENDPOINTS.capacity),
      { timeout: SUBMIT_TIMEOUT_MS },
    );
    await page.locator("#capacity-billing-scenario-id").press("Control+Enter");
    response = await responsePromise;
    verify(
      summary,
      `${scope}/response`,
      response.status() === 200,
      "actual backend response received",
      `actual backend returned HTTP ${response.status()}`,
    );
  }
  await assertCapacityResponse(summary, response, golden, scope);
  await assertCapacityUi(summary, page, golden, scope);
  recordPass(summary, `${scope}/http`, `POST ${ENDPOINTS.capacity}`);
}

async function assertRefusal({
  page,
  summary,
  response,
  panelSelector,
  expectedCode,
  expectedViolation,
  scope,
}) {
  verify(
    summary,
    `${scope}/status`,
    response.status() === 422,
    "HTTP 422 refusal",
    `expected HTTP 422, got ${response.status()}`,
  );
  const body = await response.json();
  const detail = body?.detail ?? {};
  verify(
    summary,
    `${scope}/code`,
    detail.code === expectedCode,
    `refusal code ${expectedCode}`,
    `expected refusal code ${expectedCode}`,
  );
  const codes = Array.isArray(detail.codes) ? detail.codes : [];
  verify(
    summary,
    `${scope}/violation`,
    codes.includes(expectedViolation),
    `stable violation ${expectedViolation}`,
    `expected stable violation ${expectedViolation}`,
  );
  const alert = page.locator(`${panelSelector} [role="alert"]`);
  await alert.waitFor({ state: "visible", timeout: 10_000 });
  const text = await alert.innerText();
  verify(
    summary,
    `${scope}/ui-refusal`,
    text.includes(expectedCode) && text.includes(expectedViolation),
    "UI showed the stable refusal and field detail",
    "UI did not show the expected stable refusal codes",
  );
  const resultCount = await page.locator(`${panelSelector} [role="region"]`).count();
  verify(
    summary,
    `${scope}/no-partial-result`,
    resultCount === 0,
    "no result survived the refusal",
    "a result region survived the refusal",
  );
}

async function assertStaleEditClears({ summary, page, selector, edit, scope }) {
  await edit();
  await page.locator(selector).waitFor({ state: "detached", timeout: 5_000 });
  recordPass(summary, `${scope}/stale-edit-invalidated`, "edited input removed the old result");
}

async function axeViolations(page, axeSource, summary, scope) {
  if (axeSource === null) {
    summary.axe.status = "unavailable";
    summary.observations.push(`${scope}: axe-core not available; no axe claim is made`);
    return;
  }
  const hasAxe = await page.evaluate(() => Boolean(window.axe));
  if (!hasAxe) await page.addScriptTag({ content: axeSource });
  const violations = await page.evaluate(async (tags) => {
    const result = await window.axe.run(document, {
      runOnly: { type: "tag", values: tags },
    });
    return result.violations.map((violation) => ({
      id: violation.id,
      impact: violation.impact,
      nodes: violation.nodes.length,
      targets: violation.nodes.slice(0, 3).map((node) => node.target),
    }));
  }, AXE_TAGS);
  summary.axe.status = "ran";
  summary.axe.runs += 1;
  summary.axe.violations += violations.length;
  verify(
    summary,
    `${scope}/axe`,
    violations.length === 0,
    "axe WCAG 2/2.1 A/AA found no violations",
    `axe violations: ${JSON.stringify(violations).slice(0, 350)}`,
  );
}

async function assertViewportAndCapture({
  page,
  summary,
  scope,
  viewport,
  outputDir,
  axeSource,
  prefix,
}) {
  await page.setViewportSize({ width: viewport.width, height: viewport.height });
  await page.waitForTimeout(150);
  const overflow = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  verify(
    summary,
    `${scope}/${viewport.id}/overflow`,
    overflow.scrollWidth <= overflow.clientWidth + 2,
    "no document horizontal overflow",
    `horizontal overflow ${overflow.scrollWidth}px > ${overflow.clientWidth}px`,
  );
  if (outputDir) {
    const filename = `${safeName(prefix)}-${viewport.id}.png`;
    await page.screenshot({
      path: path.join(outputDir, "screenshots", filename),
      fullPage: false,
    });
    summary.screenshots.push(filename);
    recordPass(summary, `${scope}/${viewport.id}/screenshot`, filename);
  }
  await axeViolations(page, axeSource, summary, `${scope}/${viewport.id}`);
}

function lngLabel(labels, key) {
  const value = labels[`contracts.lng_economics.${key}`];
  if (typeof value !== "string" || value.trim() === "") {
    throw new AcceptanceFailure("i18n", `missing LNG label contracts.lng_economics.${key}`);
  }
  return value;
}

async function lngField(scope, labels, key) {
  return scope
    .getByLabel(lngLabel(labels, key), { exact: false })
    .and(scope.locator("input,textarea,select"))
    .first();
}

async function setLngField(scope, labels, key, value) {
  const field = await lngField(scope, labels, key);
  const tag = await field.evaluate((element) => element.tagName);
  if (tag === "SELECT") {
    await field.selectOption(value);
  } else {
    await field.fill(value);
  }
}

async function sectionByLegend(panel, labels, key) {
  const section = panel
    .locator("fieldset.lng-economics-section")
    .filter({ hasText: lngLabel(labels, key) })
    .first();
  await section.waitFor({ state: "visible", timeout: 10_000 });
  return section;
}

async function addLngRow(section, labels, addKey, rowSelector) {
  await section.getByRole("button", { name: lngLabel(labels, addKey), exact: true }).click();
  const row = section.locator(rowSelector).last();
  await row.waitFor({ state: "visible", timeout: 5_000 });
  return row;
}

async function fillLngGolden(page, labels) {
  await page
    .locator(".contract-task-tabs")
    .getByRole("button", {
      name: labels["contracts.view.lng_economics"],
      exact: true,
    })
    .click();
  const panel = page.locator(".lng-economics-panel");
  await panel.waitFor({ state: "visible", timeout: 10_000 });
  const direct = {
    contract_id: LNG_GOLDEN.contractId,
    cargo_id: LNG_GOLDEN.cargoId,
    terminal_id: LNG_GOLDEN.terminalId,
    resource_id: LNG_GOLDEN.resourceId,
    valuation_date: LNG_GOLDEN.valuationDate,
    purchase_payment_date: LNG_GOLDEN.purchasePaymentDate,
    sale_payment_date: LNG_GOLDEN.salePaymentDate,
    cost_scope_statement: LNG_GOLDEN.costScopeStatement,
    purchased_energy: LNG_GOLDEN.purchasedEnergyMwh,
    delivered_energy: LNG_GOLDEN.deliveredEnergyMwh,
    purchase_unit_price: LNG_GOLDEN.purchaseUnitPrice,
    sale_unit_price: LNG_GOLDEN.saleUnitPrice,
    purchase_price_source: LNG_GOLDEN.purchasePriceSource,
    sale_price_source: LNG_GOLDEN.salePriceSource,
    purchase_basis: LNG_GOLDEN.purchaseBasis,
    energy_basis_reference: LNG_GOLDEN.energyBasisReference,
    energy_unit: LNG_GOLDEN.energyUnit,
    reporting_currency: LNG_GOLDEN.reportingCurrency,
  };
  for (const [key, value] of Object.entries(direct)) {
    await setLngField(panel, labels, key, value);
  }

  const energySection = await sectionByLegend(panel, labels, "energy_section");
  const stageValues = [
    {
      stage_id: "synthetic-stage-1",
      stage_kind: "shipping",
      stage_input: LNG_GOLDEN.stage1Input,
      stage_output: LNG_GOLDEN.stage1Output,
      stage_consumed: LNG_GOLDEN.stage1Consumed,
      stage_physical_loss: LNG_GOLDEN.stage1Loss,
      stage_source_references: "synthetic-input:stage-shipping-1",
    },
    {
      stage_id: "synthetic-stage-2",
      stage_kind: "regasification",
      stage_input: LNG_GOLDEN.stage2Input,
      stage_output: LNG_GOLDEN.stage2Output,
      stage_consumed: LNG_GOLDEN.stage2Consumed,
      stage_physical_loss: LNG_GOLDEN.stage2Loss,
      stage_source_references: "synthetic-input:stage-regas-1",
    },
  ];
  for (const stage of stageValues) {
    const row = await addLngRow(
      energySection,
      labels,
      "add_stage",
      "fieldset.lng-economics-row",
    );
    for (const [key, value] of Object.entries(stage)) {
      await setLngField(row, labels, key, value);
    }
  }

  const costSection = await sectionByLegend(panel, labels, "costs_section");
  const costRow = await addLngRow(
    costSection,
    labels,
    "add_cost",
    "fieldset.lng-economics-row",
  );
  for (const [key, value] of Object.entries({
    cost_id: LNG_GOLDEN.costId,
    cost_category: LNG_GOLDEN.costCategory,
    cost_amount: LNG_GOLDEN.costAmountEur,
    cost_payment_date: LNG_GOLDEN.costPaymentDate,
    cost_source_reference: LNG_GOLDEN.costSource,
    cost_charge_basis: LNG_GOLDEN.chargeBasis,
  })) {
    await setLngField(costRow, labels, key, value);
  }

  const discountSection = await sectionByLegend(panel, labels, "discounts_section");
  for (const factor of [
    { paymentDate: LNG_GOLDEN.valuationDate, factor: "1" },
    { paymentDate: LNG_GOLDEN.salePaymentDate, factor: LNG_GOLDEN.saleDiscountFactor },
  ]) {
    const row = await addLngRow(
      discountSection,
      labels,
      "add_discount",
      "fieldset.lng-economics-row",
    );
    for (const [key, value] of Object.entries({
      discount_payment_date: factor.paymentDate,
      discount_factor: factor.factor,
      discount_curve_reference: LNG_GOLDEN.discountCurve,
      discount_source_reference: LNG_GOLDEN.discountSource,
      discount_as_of: LNG_GOLDEN.discountAsOf,
    })) {
      await setLngField(row, labels, key, value);
    }
  }

  return panel;
}

async function assertLngRenderedEnergy(page, summary, labels, scope) {
  const block = page
    .locator(".lng-economics-result .route-cost-issues")
    .filter({ hasText: labels["contracts.lng_economics.energy_result"] })
    .first();
  await block.waitFor({ state: "visible", timeout: 5_000 });
  const pairs = await block.locator(".contract-definition-list > div").evaluateAll((rows) =>
    rows.map((row) => ({
      label: (row.querySelector("span")?.textContent ?? "").trim(),
      value: (row.querySelector("strong")?.textContent ?? "").trim(),
    })),
  );
  for (const [key, expected] of [
    ["total_consumed", LNG_GOLDEN.expectedTotalConsumedMwh],
    ["physical_loss", LNG_GOLDEN.expectedPhysicalLossMwh],
    ["total_reduction", LNG_GOLDEN.expectedTotalReductionMwh],
  ]) {
    const label = labels[`contracts.lng_economics.${key}`];
    const pair = pairs.find((entry) => entry.label === label);
    verify(
      summary,
      `${scope}/ui/${key}`,
      Boolean(pair && pair.value.startsWith(expected)),
      `${label}: ${expected}`,
      `rendered ${key} did not match ${expected}`,
    );
  }
}

async function assertLngGolden(page, summary, response, language, labels) {
  const scope = `${language.id}/lng-golden`;
  const body = await response.json();
  summary.actual_backend_responses = true;
  const data = body?.data ?? {};
  const expected = {
    purchase_outlay_eur: LNG_GOLDEN.expectedPurchaseOutlayEur,
    sale_proceeds_eur: LNG_GOLDEN.expectedSaleProceedsEur,
    total_downstream_costs_eur: LNG_GOLDEN.expectedDownstreamCostsEur,
    cargo_margin_eur: LNG_GOLDEN.expectedCargoMarginEur,
    net_present_value_eur: LNG_GOLDEN.expectedNetPresentValueEur,
    total_undiscounted_cash_eur: LNG_GOLDEN.expectedTotalUndiscountedCashEur,
    total_consumed_energy_mwh: LNG_GOLDEN.expectedTotalConsumedMwh,
    physical_loss_energy_mwh: LNG_GOLDEN.expectedPhysicalLossMwh,
    total_reduction_energy_mwh: LNG_GOLDEN.expectedTotalReductionMwh,
    physical_readiness: LNG_GOLDEN.expectedPhysicalReadiness,
  };
  for (const [key, value] of Object.entries(expected)) {
    verify(
      summary,
      `${scope}/${key}`,
      data[key] === value,
      `${key}=${value}`,
      `expected ${key}=${value}`,
    );
  }
  verify(
    summary,
    `${scope}/readiness-assessed`,
    data.readiness_assessed === false,
    "readiness_assessed=false",
    "readiness_assessed was not false",
  );
  verify(
    summary,
    `${scope}/references-unverified`,
    body?.meta?.references_verified === false
      && body?.meta?.readiness_assessed === false
      && body?.meta?.customer_approval === false,
    "sandbox metadata keeps references, readiness and approval unestablished",
    "sandbox metadata overstated authority",
  );
  const result = page.locator(".lng-economics-result");
  await result.waitFor({ state: "visible", timeout: 10_000 });
  await assertFocusVisible(
    summary,
    page,
    ".lng-economics-result",
    [
      LNG_GOLDEN.expectedPurchaseOutlayEur,
      LNG_GOLDEN.expectedSaleProceedsEur,
      LNG_GOLDEN.expectedDownstreamCostsEur,
      LNG_GOLDEN.expectedCargoMarginEur,
      LNG_GOLDEN.expectedNetPresentValueEur,
      "NOT_ASSESSED",
    ],
    scope,
  );
  await assertLngRenderedEnergy(page, summary, labels, scope);
  recordPass(summary, `${scope}/http`, `POST ${ENDPOINTS.lng}`);
}

async function runCapacityLanguage({ page, config, language, summary, labels, axeSource }) {
  await gotoContracts(page, config, language, "routes", summary);
  const capacityPanel = page.locator(".capacity-billing-panel");
  await capacityPanel.waitFor({ state: "visible", timeout: 10_000 });
  verify(
    summary,
    `${language.id}/capacity/panel`,
    (await capacityPanel.count()) === 1,
    "capacity-billing panel is mounted",
    "capacity-billing panel is not mounted",
  );
  const capacityText = await capacityPanel.innerText();
  verify(
    summary,
    `${language.id}/capacity/localized-label`,
    capacityText.includes(labels["portfolio.capacity_billing.title"]),
    `rendered ${labels["portfolio.capacity_billing.title"]}`,
    "capacity-billing panel did not render its localized title",
  );

  const golden = CAPACITY_GOLDENS[0];
  await runCapacityCase({
    page,
    summary,
    language,
    golden,
    withTimingGuard: true,
  });
  for (const viewport of CAPTURE_VIEWPORTS) {
    await assertViewportAndCapture({
      page,
      summary,
      scope: `${language.id}/${golden.id}`,
      viewport,
      outputDir: config.outputDir,
      axeSource,
      prefix: `capacity-${language.id}`,
    });
  }
  await page.setViewportSize({ width: 1440, height: 900 });

  await assertStaleEditClears({
    summary,
    page,
    selector: ".capacity-billing-result",
    edit: () => page.locator("#capacity-billing-tariff-rate").fill("3"),
    scope: `${language.id}/capacity`,
  });
  await page.locator("#capacity-billing-tariff-rate").fill(golden.tariffRate);
  await page.locator("#capacity-billing-billed").fill("240");
  await waitForPanelSubmit(page, ".capacity-billing-panel");
  const refusalPromise = page.waitForResponse(
    (candidate) => isEndpointResponse(candidate, ENDPOINTS.capacity),
    { timeout: SUBMIT_TIMEOUT_MS },
  );
  await page.locator("#capacity-billing-scenario-id").press("Control+Enter");
  const refusal = await refusalPromise;
  await assertRefusal({
    page,
    summary,
    response: refusal,
    panelSelector: ".capacity-billing-panel",
    expectedCode: "capacity_billing_refused",
    expectedViolation: "BILLED_CAPACITY_ENERGY_INCONSISTENT",
    scope: `${language.id}/capacity-refusal-billed-energy`,
  });

  for (const next of CAPACITY_GOLDENS.slice(1)) {
    await runCapacityCase({
      page,
      summary,
      language,
      golden: next,
      withTimingGuard: false,
    });
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  recordPass(summary, `${language.id}/capacity/workflow`, "capacity workflow completed");
}

async function runLngLanguage({ page, config, language, summary, labels, axeSource }) {
  await gotoContracts(page, config, language, "resources", summary);
  const panel = await fillLngGolden(page, labels);
  await waitForPanelSubmit(page, ".lng-economics-panel");

  const response = await timedSubmitWithDuplicateGuard({
    page,
    panelSelector: ".lng-economics-panel",
    endpoint: ENDPOINTS.lng,
    submit: () => lngField(panel, labels, "cargo_id").then((field) => field.press("Control+Enter")),
    summary,
    scope: `${language.id}/lng-golden`,
  });
  await assertLngGolden(page, summary, response, language, labels);

  for (const viewport of CAPTURE_VIEWPORTS) {
    await assertViewportAndCapture({
      page,
      summary,
      scope: `${language.id}/lng-golden`,
      viewport,
      outputDir: config.outputDir,
      axeSource,
      prefix: `lng-${language.id}`,
    });
  }
  await page.setViewportSize({ width: 1440, height: 900 });

  await assertStaleEditClears({
    summary,
    page,
    selector: ".lng-economics-result",
    edit: () => setLngField(panel, labels, "sale_unit_price", "31"),
    scope: `${language.id}/lng`,
  });

  const energySection = await sectionByLegend(panel, labels, "energy_section");
  const firstStage = energySection.locator("fieldset.lng-economics-row").first();
  await setLngField(firstStage, labels, "stage_physical_loss", "2");
  await waitForPanelSubmit(page, ".lng-economics-panel");
  const refusalPromise = page.waitForResponse(
    (candidate) => isEndpointResponse(candidate, ENDPOINTS.lng),
    { timeout: SUBMIT_TIMEOUT_MS },
  );
  const cargoField = await lngField(panel, labels, "cargo_id");
  await cargoField.press("Control+Enter");
  const refusal = await refusalPromise;
  await assertRefusal({
    page,
    summary,
    response: refusal,
    panelSelector: ".lng-economics-panel",
    expectedCode: LNG_GOLDEN.expectedRefusalCode,
    expectedViolation: LNG_GOLDEN.expectedRefusalViolation,
    scope: `${language.id}/lng-refusal-conservation`,
  });
  recordPass(summary, `${language.id}/lng/workflow`, "LNG workflow completed");
}

async function writeSummaryIfConfigured(summary, outputDir) {
  if (!outputDir) return;
  try {
    writeFileSync(
      path.join(outputDir, "economics-workflow.json"),
      `${JSON.stringify(summary, null, 2)}\n`,
      "utf8",
    );
  } catch {
    summary.status = "failed";
    summary.failures.push({
      scope: "output",
      message: "The configured output directory could not be written.",
    });
  }
}

export async function main() {
  const summary = {
    schema_version: "economics-workflow-acceptance/v1",
    status: "failed",
    synthetic_inputs: true,
    actual_backend_responses: false,
    generated_at_utc: new Date().toISOString(),
    languages: LANGUAGES.map((language) => language.id),
    viewports: VIEWPORTS.map((viewport) => viewport.id),
    base: null,
    output: "not-configured",
    axe: { status: "not-run", available: false, runs: 0, violations: 0 },
    checks: [],
    failures: [],
    observations: [],
    screenshots: [],
    _secrets: [],
  };

  let browser = null;
  let config = null;
  let exitCode = 1;
  try {
    config = readConfiguration();
    summary._secrets = [config.username, config.password];
    summary.base = {
      loopback: config.base.loopback,
      explicit_non_loopback_uat: config.remoteUat,
    };
    summary.output = config.outputDir ? "configured" : "not-configured";
    const axeSource = loadAxeSource(config.playwrightPath);
    summary.axe.available = axeSource !== null;
    if (axeSource === null) {
      summary.axe.status = "unavailable";
      summary.observations.push("axe-core is not installed beside Playwright; axe is not claimed");
    }

    const requireFromPlaywright = createRequire(path.resolve(config.playwrightPath));
    const { chromium } = requireFromPlaywright(config.playwrightPath);
    browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    await ensureAuthenticated(page, config, summary);

    for (const language of LANGUAGES) {
      await setLanguage(page, language);
      const labels = loadI18n(language);
      await runCapacityLanguage({
        page,
        config,
        language,
        summary,
        labels,
        axeSource,
      });
      await runLngLanguage({
        page,
        config,
        language,
        summary,
        labels,
        axeSource,
      });
    }
    summary.status = "passed";
    exitCode = 0;
  } catch (error) {
    summary.status = "failed";
    const scope = error instanceof AcceptanceFailure ? error.scope : "run";
    const detail = error instanceof ConfigurationError
      ? error.message
      : error instanceof AcceptanceFailure
        ? error.message
        : sanitizeDiagnostic(error, summary._secrets);
    recordFailure(summary, scope, detail || "unexpected failure");
    exitCode = error instanceof ConfigurationError ? 2 : 1;
  } finally {
    if (browser) {
      try {
        await browser.close();
      } catch {
        summary.status = "failed";
        summary.failures.push({
          scope: "browser-close",
          message: "Browser close failed; no traceback or credential was emitted.",
        });
        exitCode = 1;
      }
    }
    delete summary._secrets;
    await writeSummaryIfConfigured(summary, config?.outputDir ?? null);
    if (summary.status !== "passed") exitCode = Math.max(exitCode, 1);
    console.log(JSON.stringify(summary, null, 2));
  }
  return exitCode;
}

const invokedPath = process.argv[1]
  ? pathToFileURL(path.resolve(process.argv[1])).href
  : "";
if (invokedPath && import.meta.url === invokedPath) {
  process.exitCode = await main();
}
