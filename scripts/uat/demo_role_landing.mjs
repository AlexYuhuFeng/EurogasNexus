#!/usr/bin/env node
// Demo role landing check: each role signs in and its landing page shows its key figures.
//
// The owner signed in as demo.trader and saw panels with no data (2026-11-17): reads queued on
// the demo's connection pool and passed the browser's timeout. This check signs in as each
// role on a running demo (scripts/demo/start_public_demo.py), and fails when the landing page
// shows no figures, when a read the role is entitled to did not load (the top bar's data status
// lists it), or when Today, for a role that reads the market, has fewer than three key figures.
//
// Usage (against a demo started with the documented testers):
//   EUROGAS_UAT_BASE_URL=http://127.0.0.1:8080 EUROGAS_DEMO_PASSWORD=... \
//   EUROGAS_UAT_PLAYWRIGHT_PATH=.../playwright/index.js node scripts/uat/demo_role_landing.mjs
// Optional: EUROGAS_DEMO_IDENTITIES (comma list), EUROGAS_UAT_OUTPUT_DIR (screenshots + JSON).
// The password is read from the environment and never printed.

import { createRequire } from "node:module";
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.EUROGAS_UAT_PLAYWRIGHT_PATH || "playwright");

const BASE = (process.env.EUROGAS_UAT_BASE_URL || "http://127.0.0.1:8080").replace(/\/$/, "");
const PASSWORD = process.env.EUROGAS_DEMO_PASSWORD || "";
const OUT = process.env.EUROGAS_UAT_OUTPUT_DIR || "";
const SETTLE_MS = Number(process.env.EUROGAS_DEMO_SETTLE_MS || 20000);

// The five desks the demo is shown with; each has a different landing page.
const DEFAULT_IDENTITIES = ["demo.trader", "demo.risk", "demo.finance", "demo.compliance", "demo.ops"];
const IDENTITIES = (process.env.EUROGAS_DEMO_IDENTITIES || DEFAULT_IDENTITIES.join(","))
  .split(",").map((name) => name.trim()).filter(Boolean);

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function signIn(page, identity) {
  await page.goto(BASE, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.locator("#sign-in-username").waitFor({ timeout: 60000 });
  await page.locator("#sign-in-username").fill(identity);
  await page.locator("#sign-in-password").fill(PASSWORD);
  await page.locator("form button[type=submit]").first().click();
  await page.locator("main").waitFor({ timeout: 60000 });
}

// Reads the role could not load, as the top bar's data status lists them (opened, then closed).
async function failedReads(page) {
  const chip = page.locator(".topbar-status-chip");
  if (!(await chip.count())) return [];
  const count = Number(await page.locator("[data-topbar-status]").getAttribute("data-problem-count")) || 0;
  if (!count) return [];
  await chip.click();
  const entries = await page.locator("[data-endpoint-failure]").allInnerTexts().catch(() => []);
  await chip.click();
  return entries.map((text) => text.replace(/\s+/g, " ").trim());
}

// Figures a landing page shows: Today's key figures, table rows, or record cards.
async function landingFigures(page) {
  return page.evaluate(() => {
    const main = document.querySelector("main");
    if (!main) return { figures: 0, rows: 0, records: 0, numbers: 0 };
    const figures = main.querySelectorAll("[data-figure-key]").length;
    const rows = main.querySelectorAll("tbody tr").length;
    const records = main.querySelectorAll("[data-record], [data-record-id]").length;
    const numbers = (main.innerText.match(/\d[\d,.]*\s?(?:%|MWh|GWh|TWh|mcm|p\/th|€|£|EUR|GBP)/g) || []).length;
    return { figures, rows, records, numbers };
  });
}

async function check(browser, identity) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  const problems = [];
  const result = { identity, problems };
  try {
    await signIn(page, identity);
    const me = await page.evaluate(async () => (await (await fetch("/api/me", { credentials: "include" })).json()).data);
    const permissions = new Set(me?.permissions || []);
    result.landing = new URL(page.url()).search;
    await wait(SETTLE_MS);
    result.landingFigures = await landingFigures(page);
    const shown = result.landingFigures;
    if (shown.figures + shown.rows + shown.records === 0) problems.push("landing page shows no figures");
    result.landingFailedReads = await failedReads(page);
    if (result.landingFailedReads.length) problems.push(`landing reads did not load: ${result.landingFailedReads.join("; ")}`);
    if (OUT) await page.screenshot({ path: path.join(OUT, `landing_${identity}.png`) });

    if (permissions.has("market.read")) {
      await page.goto(`${BASE}/?workspace=market&task=overview`, { waitUntil: "domcontentloaded", timeout: 60000 });
      await page.locator('[data-today="ready"]').waitFor({ timeout: SETTLE_MS * 2 }).catch(() => {});
      await wait(2000);
      result.todayFigures = await page.locator("[data-figure-key]").count();
      if (result.todayFigures < 3) problems.push(`Today shows ${result.todayFigures} key figures (expected at least 3)`);
      if (OUT) await page.screenshot({ path: path.join(OUT, `today_${identity}.png`) });
    }
  } catch (error) {
    problems.push(`could not complete: ${String(error).slice(0, 200)}`);
  }
  await context.close();
  return result;
}

if (!PASSWORD) {
  console.error("Set EUROGAS_DEMO_PASSWORD (the demo testers' password).");
  process.exit(2);
}
if (OUT) mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch();
const results = [];
for (const identity of IDENTITIES) {
  const result = await check(browser, identity);
  results.push(result);
  console.log(`${result.problems.length ? "FAIL" : "ok  "} ${identity} landing=${result.landing ?? "-"} ` +
    `today=${result.todayFigures ?? "-"} ${result.problems.join(" | ")}`);
}
await browser.close();
if (OUT) writeFileSync(path.join(OUT, "demo_role_landing.json"), JSON.stringify(results, null, 2));
process.exit(results.some((result) => result.problems.length) ? 1 : 0);
