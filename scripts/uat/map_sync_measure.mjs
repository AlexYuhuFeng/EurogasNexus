#!/usr/bin/env node
/**
 * How Desk → Network loads and stays current: the reads it fires and what they cost, cold and
 * on return, and whether the map is kept or rebuilt (docs/ux/LIVE_MAP.md, "How the map stays
 * current").
 *
 * Phases, each with its own list of requests (path, status, bytes on the wire, duration):
 *
 * - cold: sign in, open Desk → Network; time to the map's first paint (`data-map-ready`) and to
 *   its full layers (the situation read drawn and the point labels placed);
 * - desk_return: Desk → Today, then back to Network;
 * - mode_return: another mode (Deals → Opportunities), then back to Desk → Network;
 * - idle: the page left open on the map for `EUROGAS_UAT_IDLE_MS` (default 65 s): what polls.
 *
 * "kept" says whether the same MapLibre instance (`data-map-instance`) is on screen after a
 * return. Run against a running web client and API, as the browser sweep is:
 *
 *     EUROGAS_UAT_BASE_URL=http://127.0.0.1:3000 EUROGAS_NEXUS_DEV_LOGIN_USERNAME=... \
 *       EUROGAS_NEXUS_DEV_LOGIN_PASSWORD=... node scripts/uat/map_sync_measure.mjs [out.json]
 */
import { createRequire } from "node:module";
import path from "node:path";
import { writeFileSync } from "node:fs";

const require = createRequire(import.meta.url);
const { chromium } = require(
  // A path from the environment is relative to the working directory, not to this file.
  process.env.EUROGAS_UAT_PLAYWRIGHT_PATH ? path.resolve(process.env.EUROGAS_UAT_PLAYWRIGHT_PATH) : "playwright",
);
const BASE = process.env.EUROGAS_UAT_BASE_URL || "http://127.0.0.1:3000";
const username = process.env.EUROGAS_NEXUS_DEV_LOGIN_USERNAME || "";
const password = process.env.EUROGAS_NEXUS_DEV_LOGIN_PASSWORD || "";
const IDLE_MS = Number(process.env.EUROGAS_UAT_IDLE_MS || 65_000);
const out = process.argv[2];

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
await context.addInitScript(() => {
  try {
    localStorage.setItem("egn.map.view", "network");
  } catch {
    // Storage blocked: the default view applies.
  }
});
const page = await context.newPage();

const lastTag = new Map();
let phase = "cold";
let phaseStarted = Date.now();
const enter = (name) => {
  phase = name;
  phaseStarted = Date.now();
};
const requests = [];
const kind = (url) => {
  if (url.pathname.startsWith("/api/")) return "api";
  if (url.pathname.includes("/basemaps/")) return "basemap";
  if (/\.(json|geojson|pbf|bin)$/.test(url.pathname)) return "data";
  return "asset";
};
context.on("requestfinished", async (request) => {
  const url = new URL(request.url());
  if (["data:", "blob:"].includes(url.protocol)) return;
  const response = await request.response();
  const sizes = await request.sizes().catch(() => ({ responseBodySize: 0, responseHeadersSize: 0 }));
  const timing = request.timing();
  // A revalidation the server answered 304 reaches the page as the cached 200: it is seen here
  // as the same ETag as the last read of that path, and a body of headers only.
  const etag = response ? (await response.allHeaders().catch(() => ({})))["etag"] ?? null : null;
  const key = url.pathname + url.search;
  const unchanged = Boolean(etag) && lastTag.get(key) === etag;
  if (etag) lastTag.set(key, etag);
  requests.push({
    unchanged,
    phase,
    kind: kind(url),
    path: url.pathname + (url.search.length > 1 && url.pathname.startsWith("/api/") ? url.search : ""),
    status: response ? response.status() : 0,
    bytes: sizes.responseBodySize + sizes.responseHeadersSize,
    ms: timing.responseEnd > 0 ? Math.round(timing.responseEnd) : null,
    // When it started, from the phase's start (the sign-in press, the return).
    at: Math.round(timing.startTime - phaseStarted),
  });
});

const mapState = () =>
  page.evaluate(() => {
    const map = [...document.querySelectorAll(".gas-map")].find((element) => element.offsetParent !== null);
    const canvas = map?.querySelector(".maplibre-canvas");
    return {
      ready: map?.getAttribute("data-map-ready") === "true",
      situation: map?.getAttribute("data-map-situation-as-of") ?? null,
      labels: map ? map.querySelectorAll(".map-node-label").length : 0,
      instance: canvas?.getAttribute("data-map-instance") ?? null,
      instances: document.querySelectorAll(".maplibre-canvas[data-map-instance]").length,
    };
  });

async function timeToMap(started) {
  const firstPaint = await page
    .waitForFunction(() => [...document.querySelectorAll(".gas-map")].some((element) => element.offsetParent !== null && element.getAttribute("data-map-ready") === "true"), null, { timeout: 120_000, polling: 25 })
    .then(() => Date.now() - started);
  const full = await page
    .waitForFunction(
      () => [...document.querySelectorAll(".gas-map")].some(
        (element) => element.offsetParent !== null
          && element.getAttribute("data-map-ready") === "true"
          && element.getAttribute("data-map-situation-as-of")
          && element.querySelectorAll(".map-node-label").length > 0,
      ),
      null,
      { timeout: 120_000, polling: 25 },
    )
    .then(() => Date.now() - started);
  return { first_paint_ms: firstPaint, full_layers_ms: full };
}

/**
 * A return measured inside the page, from the user's action (a tab pressed, an in-app link
 * followed) to the frame where the map shows, then to the frame with its full layers.
 */
const returnTo = (trigger) =>
  page.evaluate(async ({ kind, value }) => {
    const shown = () => [...document.querySelectorAll(".gas-map")].find((element) => element.offsetParent !== null);
    const started = performance.now();
    if (kind === "tab") {
      [...document.querySelectorAll("[role=tab]")].find((element) => new RegExp(value).test(element.textContent.trim()))?.click();
    } else {
      window.history.pushState({}, "", value);
      window.dispatchEvent(new PopStateEvent("popstate"));
    }
    let first = null;
    let full = null;
    while (performance.now() - started < 120_000) {
      await new Promise((resolve) => requestAnimationFrame(() => resolve()));
      const map = shown();
      if (!map || map.getAttribute("data-map-ready") !== "true") continue;
      first ??= performance.now() - started;
      if (map.getAttribute("data-map-situation-as-of") && map.querySelectorAll(".map-node-label").length > 0) {
        full = performance.now() - started;
        break;
      }
    }
    return { first_paint_ms: first === null ? null : Math.round(first), full_layers_ms: full === null ? null : Math.round(full) };
  }, trigger);

async function settle(ms = 3000) {
  await page.waitForLoadState("networkidle", { timeout: 30_000 }).catch(() => undefined);
  await page.waitForTimeout(ms);
}

const navigate = (search) =>
  page.evaluate((target) => {
    window.history.pushState({}, "", target);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }, search);

const report = { base: BASE, phases: {} };

// Cold: sign in and open the map.
await page.goto(`${BASE}/?workspace=market&task=network`);
const user = page.locator("#sign-in-username");
await user.waitFor({ timeout: 60_000 });
await user.fill(username);
await page.locator("#sign-in-password").fill(password);
enter("cold");
let started = phaseStarted;
await page.locator(".sign-in-dev-form button[type=submit]").click();
report.phases.cold = await timeToMap(started);
await settle();
const networkSearch = await page.evaluate(() => window.location.search);
const coldState = await mapState();
report.phases.cold.instance = coldState.instance;

// Desk → Today, then back to Network.
enter("desk_leave");
await page.evaluate(() => [...document.querySelectorAll("[role=tab]")].find((element) => /^(Today|今日)$/.test(element.textContent.trim()))?.click());
await settle(2000);
enter("desk_return");
report.phases.desk_return = await returnTo({ kind: "tab", value: "^(Network|管网)$" });
await settle();
const deskState = await mapState();
report.phases.desk_return.kept = deskState.instance === coldState.instance;
report.phases.desk_return.instance = deskState.instance;

// Another mode, then back.
enter("mode_leave");
await navigate("?mode=deals&task=opportunities");
await settle(2000);
enter("mode_return");
report.phases.mode_return = await returnTo({ kind: "nav", value: networkSearch });
await settle();
const modeState = await mapState();
report.phases.mode_return.kept = modeState.instance === coldState.instance;
report.phases.mode_return.instance = modeState.instance;

// Left open on the map.
enter("idle");
await page.waitForTimeout(IDLE_MS);
report.phases.idle = { window_ms: IDLE_MS };

await browser.close();

const summarise = (name) => {
  const rows = requests.filter((item) => item.phase === name);
  const reads = rows.filter((item) => item.kind !== "asset");
  return {
    requests: rows.length,
    bytes: rows.reduce((sum, item) => sum + item.bytes, 0),
    not_modified: rows.filter((item) => item.status === 304 || item.unchanged).length,
    assets: rows.filter((item) => item.kind === "asset").length,
    reads: reads.map(({ kind: k, path, status, bytes, ms, at, unchanged }) => ({ kind: k, path, status: unchanged ? 304 : status, bytes, ms, at })),
  };
};
for (const name of ["cold", "desk_leave", "desk_return", "mode_leave", "mode_return", "idle"]) {
  report.phases[name] = { ...(report.phases[name] ?? {}), ...summarise(name) };
}
if (out) writeFileSync(out, `${JSON.stringify(report, null, 2)}\n`);
for (const [name, value] of Object.entries(report.phases)) {
  const timing = value.first_paint_ms !== undefined
    ? ` first paint ${value.first_paint_ms} ms, full layers ${value.full_layers_ms} ms${value.kept === undefined ? "" : `, map ${value.kept ? "kept" : "rebuilt"}`}`
    : "";
  console.log(`${name}:${timing} · ${value.requests} requests, ${(value.bytes / 1024).toFixed(0)} KiB, ${value.not_modified} not modified`);
  for (const read of value.reads.filter((item) => item.kind === "api")) {
    console.log(`  +${read.at} ms ${read.status} ${read.path} ${(read.bytes / 1024).toFixed(1)} KiB ${read.ms ?? "–"} ms`);
  }
}
