// Whole-product browser acceptance for the current main ref.
//
// Requires:
// - development/test API on :8000 backed by migrated PostgreSQL
// - Vite dev server on :3000
// - preview/UAT fixtures plus scripts/uat/seed_browser_identity.py
// - Playwright + axe-core (CI installs exact versions outside the repo)
//
// The sweep is deliberately evidence-oriented: every declared workspace is
// rendered in English and Mandarin at 1440x900, 1920x1080, and 390x844,
// checked with axe, checked for document-level horizontal overflow, and
// captured as a screenshot. It does not convert unavailable/licensed data into
// a pass; it only verifies the UI state that the authenticated seeded runtime
// actually exposes.
import { createRequire } from "node:module";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const { chromium } = require(
  process.env.EUROGAS_UAT_PLAYWRIGHT_PATH || "playwright",
);
const axePath =
  process.env.EUROGAS_UAT_AXE_PATH || require.resolve("axe-core/axe.min.js");
const axeSource = readFileSync(axePath, "utf8");

const BASE = process.env.EUROGAS_UAT_BASE_URL || "http://127.0.0.1:3000";
const OUTPUT_DIR =
  process.env.EUROGAS_UAT_OUTPUT_DIR ||
  path.resolve("artifacts", "uat-browser");
const LANGUAGE_STORAGE_KEY = "eurogas.language.v1";

const WORKSPACES = [
  "network",
  "capacity",
  "market",
  "scenario",
  "contracts",
  "strategy",
  "review",
  "orders",
  "sources",
  "glossary",
  "runtime",
  "settings",
  "manual",
  "access",
  "research",
  "agents",
];

const LANGUAGES = [
  { id: "en", htmlPrefix: "en" },
  { id: "zh-CN", htmlPrefix: "zh" },
];

const VIEWPORTS = [
  { id: "desktop-1440", width: 1440, height: 900 },
  { id: "desktop-1920", width: 1920, height: 1080 },
  { id: "narrow-390", width: 390, height: 844 },
];

function safeName(value) {
  return value.replaceAll(/[^a-zA-Z0-9._-]+/g, "-");
}

function recordFailure(failures, scope, detail) {
  failures.push({ scope, detail: String(detail) });
}

async function ensureAuthenticated(page) {
  await page.goto(BASE, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(500);

  if (await page.locator("main").isVisible().catch(() => false)) return;

  const username = process.env.EUROGAS_NEXUS_DEV_LOGIN_USERNAME || "";
  const password = process.env.EUROGAS_NEXUS_DEV_LOGIN_PASSWORD || "";
  if (!username || !password) {
    throw new Error(
      "Browser UAT requires EUROGAS_NEXUS_DEV_LOGIN_USERNAME and EUROGAS_NEXUS_DEV_LOGIN_PASSWORD",
    );
  }

  const usernameInput = page.locator("#sign-in-username");
  await usernameInput.waitFor({ state: "visible", timeout: 15_000 });
  await usernameInput.fill(username);
  await page.locator("#sign-in-password").fill(password);
  await page.locator(".sign-in-dev-form button[type=submit]").click();
  await page.locator("main").waitFor({ state: "visible", timeout: 20_000 });
}

async function setLanguage(page, language) {
  await page.evaluate(
    ([key, value]) => window.localStorage.setItem(key, value),
    [LANGUAGE_STORAGE_KEY, language],
  );
}

async function axeViolations(page) {
  await page.addScriptTag({ content: axeSource });
  return page.evaluate(async () => {
    const result = await window.axe.run(document, {
      runOnly: {
        type: "tag",
        values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"],
      },
    });
    return result.violations.map((violation) => ({
      id: violation.id,
      impact: violation.impact,
      nodes: violation.nodes.length,
      help: violation.help,
      targets: violation.nodes.slice(0, 4).map((node) => node.target),
      html: violation.nodes.slice(0, 2).map((node) => node.html),
      failureSummary: violation.nodes.slice(0, 2).map((node) => node.failureSummary),
    }));
  });
}

async function inspectWorkspace(page, language, viewport, workspace, failures) {
  await page.setViewportSize({ width: viewport.width, height: viewport.height });
  await page.goto(
    `${BASE}/?workspace=${encodeURIComponent(workspace)}`,
    { waitUntil: "domcontentloaded" },
  );
  await page.waitForTimeout(350);

  const main = page.locator("main");
  try {
    await main.waitFor({ state: "visible", timeout: 12_000 });
  } catch {
    recordFailure(
      failures,
      `${language.id}/${viewport.id}/${workspace}`,
      "main landmark did not become visible",
    );
  }

  const state = await page.evaluate(() => ({
    lang: document.documentElement.lang,
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
    h1Count: document.querySelectorAll("main h1").length,
    signInVisible: Boolean(document.querySelector(".sign-in-screen")),
  }));

  const scope = `${language.id}/${viewport.id}/${workspace}`;
  if (!state.lang.toLowerCase().startsWith(language.htmlPrefix)) {
    recordFailure(
      failures,
      scope,
      `document language mismatch: ${state.lang}`,
    );
  }
  if (state.signInVisible) {
    recordFailure(failures, scope, "session fell back to sign-in screen");
  }
  if (state.h1Count !== 1) {
    recordFailure(failures, scope, `expected exactly one main h1, got ${state.h1Count}`);
  }
  if (state.scrollWidth > state.clientWidth + 2) {
    recordFailure(
      failures,
      scope,
      `document horizontal overflow ${state.scrollWidth}px > ${state.clientWidth}px`,
    );
  }

  const violations = await axeViolations(page);
  if (violations.length > 0) {
    recordFailure(failures, scope, `axe violations: ${JSON.stringify(violations)}`);
  }

  const screenshotDir = path.join(
    OUTPUT_DIR,
    safeName(language.id),
    viewport.id,
  );
  mkdirSync(screenshotDir, { recursive: true });
  await page.screenshot({
    path: path.join(screenshotDir, `${safeName(workspace)}.png`),
    fullPage: false,
  });

  return {
    language: language.id,
    viewport: viewport.id,
    workspace,
    axeViolations: violations.length,
    h1Count: state.h1Count,
    scrollWidth: state.scrollWidth,
    clientWidth: state.clientWidth,
  };
}

async function interactionChecks(page, failures) {
  await setLanguage(page, "en");
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`${BASE}/?workspace=market`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(350);

  const preferenceTrigger = page.locator(".topbar-preferences-trigger");
  try {
    await preferenceTrigger.click();
    const menu = page.locator('[role="menu"]#topbar-preferences-menu');
    await menu.waitFor({ state: "visible", timeout: 5_000 });
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("Escape");
    const focusReturned = await preferenceTrigger.evaluate(
      (element) => document.activeElement === element,
    );
    if (!focusReturned) {
      recordFailure(failures, "interaction/preferences", "Escape did not return focus to invoker");
    }
  } catch (error) {
    recordFailure(failures, "interaction/preferences", error);
  }

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${BASE}/?workspace=network`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(350);
  try {
    const disclosure = page.locator("details.topbar-context-disclosure");
    const initiallyOpen = await disclosure.getAttribute("open");
    if (initiallyOpen !== null) {
      recordFailure(failures, "interaction/narrow-disclosure", "narrow context disclosure should start closed");
    }
    await disclosure.locator("summary").click();
    await page.locator(".topbar-context-disclosure-content").waitFor({
      state: "visible",
      timeout: 5_000,
    });
  } catch (error) {
    recordFailure(failures, "interaction/narrow-disclosure", error);
  }
}

export async function runWorkflowSmoke() {
  mkdirSync(OUTPUT_DIR, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
  });
  const page = await context.newPage();

  const failures = [];
  const pageErrors = [];
  const results = [];
  let currentScope = "startup";

  page.on("pageerror", (error) => {
    pageErrors.push({ scope: currentScope, detail: String(error) });
  });

  try {
    await ensureAuthenticated(page);

    for (const language of LANGUAGES) {
      await setLanguage(page, language.id);
      for (const viewport of VIEWPORTS) {
        for (const workspace of WORKSPACES) {
          currentScope = `${language.id}/${viewport.id}/${workspace}`;
          try {
            results.push(
              await inspectWorkspace(
                page,
                language,
                viewport,
                workspace,
                failures,
              ),
            );
          } catch (error) {
            recordFailure(failures, currentScope, error);
          }
        }
      }
    }

    currentScope = "interaction-checks";
    await interactionChecks(page, failures);
  } finally {
    await context.close();
    await browser.close();
  }

  for (const error of pageErrors) {
    recordFailure(failures, error.scope, `pageerror: ${error.detail}`);
  }

  const summary = {
    ok: failures.length === 0,
    baseUrl: BASE,
    workspaces: WORKSPACES.length,
    languages: LANGUAGES.map((language) => language.id),
    viewports: VIEWPORTS,
    checks: results.length,
    results,
    failures,
  };
  writeFileSync(
    path.join(OUTPUT_DIR, "summary.json"),
    JSON.stringify(summary, null, 2),
    "utf8",
  );
  return summary;
}

const entryPath = process.argv[1] ? path.resolve(process.argv[1]) : "";
if (entryPath === fileURLToPath(import.meta.url)) {
  const result = await runWorkflowSmoke();
  console.log(JSON.stringify(result, null, 2));
  process.exit(result.ok ? 0 : 1);
}
