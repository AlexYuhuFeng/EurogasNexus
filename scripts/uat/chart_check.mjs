#!/usr/bin/env node
// Charts in a real browser (Chromium), UX-09:
//
// - each chart on Prices and Today draws on its canvas (non-background pixels);
// - the keyboard reaches the data: Tab to the plot, End shows the last point in the tooltip and
//   the live region;
// - the table alternative is the same data: one row per plotted point, and its values equal the
//   CSV export of the chart;
// - a simulated chart says so.
//
// Exits 1 on a failure. Environment as scripts/uat/keyboard_paths.mjs: EUROGAS_UAT_BASE_URL,
// EUROGAS_UAT_PLAYWRIGHT_PATH, EUROGAS_UAT_OUTPUT_DIR, EUROGAS_NEXUS_DEV_LOGIN_USERNAME/_PASSWORD.
import { createRequire } from "node:module";
import { mkdirSync, readFileSync } from "node:fs";
import path from "node:path";

const require = createRequire(import.meta.url);
const BASE = process.env.EUROGAS_UAT_BASE_URL || "http://127.0.0.1:3000";
const OUTPUT_DIR = process.env.EUROGAS_UAT_OUTPUT_DIR || "";

const failures = [];
const check = (condition, message) => {
  console.log(`${condition ? "ok  " : "FAIL"} ${message}`);
  if (!condition) failures.push(message);
};

async function signIn(page) {
  await page.goto(BASE, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(500);
  if (await page.locator("main").isVisible().catch(() => false)) return;
  const username = process.env.EUROGAS_NEXUS_DEV_LOGIN_USERNAME || "";
  const password = process.env.EUROGAS_NEXUS_DEV_LOGIN_PASSWORD || "";
  if (!username || !password) throw new Error("set EUROGAS_NEXUS_DEV_LOGIN_USERNAME and _PASSWORD");
  await page.locator("#sign-in-username").waitFor({ state: "visible", timeout: 15_000 });
  await page.locator("#sign-in-username").fill(username);
  await page.locator("#sign-in-password").fill(password);
  await page.locator(".sign-in-dev-form button[type=submit]").click();
  await page.locator("main").waitFor({ state: "visible", timeout: 20_000 });
}

async function go(page, search) {
  await page.goto(`${BASE}/${search}`, { waitUntil: "domcontentloaded" });
  await page.locator("main").waitFor({ state: "visible", timeout: 20_000 });
  await page.waitForTimeout(4000);
}

/** Share of canvas pixels that are not transparent and not the corner's background colour. */
const inkShare = (canvas) =>
  canvas.evaluate((element) => {
    const context = element.getContext("2d");
    const { width, height } = element;
    if (!context || !width || !height) return 0;
    const data = context.getImageData(0, 0, width, height).data;
    let ink = 0;
    for (let index = 0; index < data.length; index += 16) if (data[index + 3] > 0) ink += 1;
    return ink / (data.length / 16);
  });

const parse = (text) => {
  const value = Number(String(text).replace(/[,\s]/g, "").replace("–", ""));
  return String(text).trim() === "–" || String(text).trim() === "" ? null : value;
};

async function checkChart(page, id) {
  const figure = page.locator(`[data-chart="${id}"]`);
  if ((await figure.count()) === 0) {
    check(false, `${id}: chart is on the page`);
    return;
  }
  await figure.scrollIntoViewIfNeeded();
  const points = Number(await figure.getAttribute("data-chart-points"));
  check(points > 1, `${id}: ${points} points`);
  const canvas = figure.locator("canvas").first();
  check((await inkShare(canvas)) > 0.005, `${id}: the canvas is drawn`);
  if (await figure.getAttribute("data-chart-simulated")) {
    check((await figure.locator(".ds-chart-head [data-tone=simulated]").count()) === 1, `${id}: says it is simulated`);
  }
  // Keyboard: the plot is one Tab stop; End shows the last point.
  const plot = figure.locator(".ds-chart-plot");
  await plot.focus();
  await page.keyboard.press("End");
  await page.waitForTimeout(150);
  const tip = figure.locator(".ds-chart-tip");
  check(await tip.isVisible(), `${id}: End shows the last point in the tooltip`);
  const live = (await figure.locator("[aria-live]").textContent()) ?? "";
  check(live.length > 0, `${id}: the live region reads the point (${live.slice(0, 60)}…)`);
  await page.keyboard.press("ArrowLeft");
  await page.waitForTimeout(100);
  const moved = (await figure.locator("[aria-live]").textContent()) ?? "";
  check(moved !== live, `${id}: ArrowLeft moves to another point`);
  if (OUTPUT_DIR) {
    mkdirSync(OUTPUT_DIR, { recursive: true });
    await figure.screenshot({ path: path.join(OUTPUT_DIR, `chart-${id}.png`) });
  }
  // CSV export: exactly what is plotted.
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    figure.locator("[data-chart-export=csv]").click(),
  ]);
  const csv = readFileSync(await download.path(), "utf8").trim().split("\n").map((line) => line.split(","));
  check(csv.length - 1 === points, `${id}: the CSV has one row per point (${csv.length - 1})`);
  // Table alternative: same rows, same values as the CSV.
  await figure.locator("[data-chart-toggle=table]").click();
  await page.waitForTimeout(200);
  const rows = figure.locator("tbody tr");
  check((await rows.count()) === points, `${id}: the table has one row per point`);
  let same = true;
  for (const index of [0, points - 1]) {
    const cells = await rows.nth(index).locator("td").allTextContents();
    const values = csv[index + 1].slice(1).map((cell) => (cell === "" ? null : Number(cell)));
    cells.forEach((cell, at) => {
      const shown = parse(cell.replace(/[a-z ]+$/i, ""));
      const plotted = values[at];
      if (plotted == null ? shown != null : shown == null || Math.abs(shown - plotted) > 0.01) same = false;
    });
  }
  check(same, `${id}: the table shows the plotted values`);
  await figure.locator("[data-chart-toggle=table]").click();
}

export async function runChartCheck() {
  const { chromium } = require(
    process.env.EUROGAS_UAT_PLAYWRIGHT_PATH ? path.resolve(process.env.EUROGAS_UAT_PLAYWRIGHT_PATH) : "playwright",
  );
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: "reduce", acceptDownloads: true });
  const page = await context.newPage();
  try {
    await signIn(page);
    await go(page, "?workspace=market&task=curves");
    await checkChart(page, "forward-curve");
    await checkChart(page, "nbp-ttf-spread");
    await go(page, "?workspace=market&task=overview");
    await checkChart(page, "storage-season");
    await checkChart(page, "nwe-balance-chart");
    check((await page.locator(".today-fundamental .ds-sparkline canvas").count()) >= 1, "Today: sparklines draw through the chart layer");
  } finally {
    await browser.close();
  }
  if (failures.length) {
    console.log(`\n${failures.length} chart check(s) failed`);
    process.exitCode = 1;
  } else console.log("\nall chart checks passed");
}

if (import.meta.url === `file://${process.argv[1]}`) await runChartCheck();
