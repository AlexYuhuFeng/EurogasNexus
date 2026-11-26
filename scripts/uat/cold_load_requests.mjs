#!/usr/bin/env node
// Cold-load request mix: one person, one browser tab; each page a cold load (page.goto).
//
// Counts every /api request a page load sends (method, path, status), the live streams it
// opens, the 429s and other refusals, and console errors. Written for the stream-cap defect
// (2026-11-26: a crawl of 32 pages as one user logged a 429 on a stream on 20 of them); its
// output is what tests/fixtures/client/cold_load_requests.json records and
// tests/security/test_cold_load_quotas.py replays against the per-person quotas.
//
// Usage (against a demo started with the documented testers, scripts/demo/start_public_demo.py):
//   EUROGAS_UAT_BASE_URL=http://127.0.0.1:8080 EUROGAS_DEMO_PASSWORD=... \
//   EUROGAS_UAT_PLAYWRIGHT_PATH=.../playwright/index.js \
//   node scripts/uat/cold_load_requests.mjs [workspace:task ...]
// Optional: EUROGAS_DEMO_IDENTITY (default demo.trader), EUROGAS_UAT_SETTLE_MS (8000),
// EUROGAS_UAT_MODE (cold | spa), EUROGAS_UAT_REPEAT (1), EUROGAS_UAT_OUTPUT (JSON file).
// Two runs at once as the same identity are two tabs of one person.
// The password is read from the environment and never printed.
import { createRequire } from "node:module";
import path from "node:path";
import { writeFileSync } from "node:fs";

const require = createRequire(import.meta.url);
const { chromium } = require(
  // A path from the environment is relative to the working directory, not to this file.
  process.env.EUROGAS_UAT_PLAYWRIGHT_PATH ? path.resolve(process.env.EUROGAS_UAT_PLAYWRIGHT_PATH) : "playwright",
);

const BASE = (process.env.EUROGAS_UAT_BASE_URL || "http://127.0.0.1:8080").replace(/\/$/, "");
const USER = process.env.EUROGAS_DEMO_IDENTITY || "demo.trader";
const PASSWORD = process.env.EUROGAS_DEMO_PASSWORD || "";
const SETTLE = Number(process.env.EUROGAS_UAT_SETTLE_MS || 8000);
const MODE = process.env.EUROGAS_UAT_MODE || "cold";
const REPEAT = Number(process.env.EUROGAS_UAT_REPEAT || 1);
const OUTPUT = process.env.EUROGAS_UAT_OUTPUT || "";
if (!PASSWORD) {
  console.error("Set EUROGAS_DEMO_PASSWORD (the demo testers' password).");
  process.exit(2);
}
const DEFAULT = [
  "market:overview", "market:curves", "contracts:overview", "market:network", "market:cargoes",
  "scenario:opportunities", "scenario:review", "contracts:resources", "contracts:exposure",
  "contracts:delivery", "scenario:nomination", "research:fundamentals", "research:spreads",
  "research:cargo", "research:reports", "sources:", "sources:infrastructure", "runtime:", "glossary:",
  "manual:", "settings:", "access:",
];
const pages = process.argv.slice(2).length ? process.argv.slice(2) : DEFAULT;

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();
let current = null;
const log = [];
page.on("request", (req) => {
  const url = new URL(req.url());
  if (!url.pathname.startsWith("/api/") || !current) return;
  current.requests.push({ method: req.method(), path: url.pathname + (url.pathname.startsWith("/api/stream") ? url.search : ""), at: Date.now() - current.started });
});
page.on("response", (res) => {
  const url = new URL(res.url());
  if (!url.pathname.startsWith("/api/") || !current) return;
  const hit = [...current.requests].reverse().find((r) => r.status === undefined && r.path.split("?")[0] === url.pathname);
  if (hit) hit.status = res.status();
});
page.on("console", (msg) => { if (current && msg.type() === "error") current.console.push(msg.text().slice(0, 200)); });

await page.goto(BASE, { waitUntil: "domcontentloaded" });
await page.locator("#sign-in-username").waitFor({ timeout: 60000 });
await page.locator("#sign-in-username").fill(USER);
await page.locator("#sign-in-password").fill(PASSWORD);
await page.locator("form button[type=submit]").first().click();
await page.locator("main").waitFor({ timeout: 60000 });
await page.waitForTimeout(3000);

for (let round = 0; round < REPEAT; round += 1) {
  for (const spec of pages) {
    const [workspace, task] = spec.split(":");
    const isSources = workspace === "sources";
    const query = `?workspace=${workspace}${task ? (isSources ? `&view=${task}` : `&task=${task}`) : ""}`;
    current = { page: spec, round, requests: [], console: [], started: Date.now() };
    log.push(current);
    if (MODE === "cold") await page.goto(`${BASE}/${query}`, { waitUntil: "domcontentloaded" });
    else await page.evaluate((q) => { history.pushState(null, "", q); dispatchEvent(new PopStateEvent("popstate")); }, query);
    await page.waitForTimeout(SETTLE);
  }
}
current = null;
await browser.close();

const summary = log.map((entry) => {
  const writes = entry.requests.filter((r) => !["GET", "HEAD", "OPTIONS"].includes(r.method));
  return {
    page: entry.page,
    round: entry.round,
    total: entry.requests.length,
    gets: entry.requests.length - writes.length,
    writes: writes.map((r) => `${r.method} ${r.path}`),
    streams: entry.requests.filter((r) => r.path.startsWith("/api/stream")).map((r) => `${r.path} ${r.status ?? "-"}`),
    refused: entry.requests.filter((r) => r.status === 429).map((r) => r.path),
    errors: entry.requests.filter((r) => r.status >= 400 && r.status !== 429).map((r) => `${r.status} ${r.path}`),
    console: entry.console.length,
  };
});
if (OUTPUT) writeFileSync(OUTPUT, JSON.stringify({ summary, log }, null, 2));
for (const s of summary) {
  console.log(`${s.page.padEnd(24)} r${s.round} total=${String(s.total).padStart(3)} writes=${s.writes.length} streams=${s.streams.length} 429=${s.refused.length} err=${s.errors.join(",") || "-"} console=${s.console}`);
}
console.log(`pages with a 429: ${summary.filter((s) => s.refused.length).length}/${summary.length}`);
