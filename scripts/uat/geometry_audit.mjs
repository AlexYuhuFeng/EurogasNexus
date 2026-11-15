// Geometry audit (UX-10): how many distinct font sizes, control heights and corner radii the
// key screens actually render, measured in a real browser on seeded data, held to budgets.
//
// The design tokens (clients/web/src/styles/tokens.css) define six text sizes, two control
// heights (plus the 44 px touch height) and three radii. Counting what the browser computes,
// rather than what the stylesheets declare, catches every way a size escapes the scale: an
// `em` that compounds, a legacy rule that wins, a component that sets its own height.
//
// Budgets live in scripts/uat/geometry_budget.json. They were set at the values measured
// after the token conversion, so they can only go down: a change that adds a size, height or
// radius fails here. Lower a budget in the same change that earns it.
//
// Requires the API and the Vite dev server (the browser-acceptance harness starts both) and a
// development sign-in (EUROGAS_NEXUS_DEV_LOGIN_USERNAME / _PASSWORD).
//
//   node scripts/uat/geometry_audit.mjs            # measure, compare with budgets, exit 1 on excess
//   node scripts/uat/geometry_audit.mjs --report   # measure and print, never fail
//
// Environment: EUROGAS_UAT_BASE_URL (default http://127.0.0.1:3000), EUROGAS_UAT_PLAYWRIGHT_PATH,
// EUROGAS_UAT_OUTPUT_DIR (default artifacts/uat-browser), EUROGAS_GEOMETRY_BUDGET (budget file).
import { createRequire } from "node:module";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const HERE = path.dirname(fileURLToPath(import.meta.url));
const BASE = process.env.EUROGAS_UAT_BASE_URL || "http://127.0.0.1:3000";
const OUTPUT_DIR = process.env.EUROGAS_UAT_OUTPUT_DIR || path.resolve("artifacts", "uat-browser");
const BUDGET_FILE = process.env.EUROGAS_GEOMETRY_BUDGET || path.join(HERE, "geometry_budget.json");
const REPORT_ONLY = process.argv.includes("--report");

const budget = JSON.parse(readFileSync(BUDGET_FILE, "utf8"));

/**
 * Runs in the page. Every rendered element counts, scrolled out of view or not; elements with no
 * box (display: none, collapsed panels, inactive tabs) do not. The map's own MapLibre controls are
 * not ours to size and are left out, which the report states.
 */
function measurePage() {
  const view = document.defaultView;
  const visible = (el) => {
    const style = view.getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity) === 0) return false;
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  };
  const bump = (map, key, sample) => {
    const entry = map[key] || (map[key] = { count: 0, samples: [] });
    entry.count += 1;
    if (sample && entry.samples.length < 4) entry.samples.push(sample);
  };
  const describe = (el) => {
    const cls = typeof el.className === "string" ? el.className.trim().split(/\s+/).slice(0, 2).join(".") : "";
    const text = (el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 24);
    return `${el.tagName.toLowerCase()}${cls ? "." + cls : ""}${text ? ` "${text}"` : ""}`;
  };
  const excluded = (el) => Boolean(el.closest(".maplibregl-control-container, .maplibregl-canvas-container"));
  const fontSizes = {};
  const fontWeights = {};
  const radii = {};
  const controlHeights = {};
  const rowButtons = {};
  const shadows = {};
  let controlsUnder24 = 0;
  let numericCells = 0;
  let untabularNumericCells = 0;
  const controlSelector = [
    "button",
    "select",
    "textarea",
    "input:not([type=checkbox]):not([type=radio]):not([type=hidden]):not([type=range]):not([type=color])",
    "[role=tab]",
    "[role=button]",
  ].join(",");
  const rowLike = '[class*="row"], [class*="card"], [class*="item"]:not([role=tab])';
  const numeric = /^[+\-−–]?\s?[£€$]?\s?\d[\d,. ]*(%|[a-zA-Z/]{0,8})?$/;

  for (const el of document.body.querySelectorAll("*")) {
    if (el.closest("svg") && el.tagName.toLowerCase() !== "svg") continue;
    if (excluded(el) || !visible(el)) continue;
    const style = view.getComputedStyle(el);
    const hasText = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
    if (hasText) {
      bump(fontSizes, `${Math.round(parseFloat(style.fontSize) * 100) / 100}px`, describe(el));
      bump(fontWeights, style.fontWeight, describe(el));
    }
    const radius = style.borderTopLeftRadius;
    const painted =
      (style.backgroundColor && style.backgroundColor !== "rgba(0, 0, 0, 0)") ||
      parseFloat(style.borderTopWidth) > 0 ||
      parseFloat(style.borderLeftWidth) > 0 ||
      style.boxShadow !== "none" ||
      style.backgroundImage !== "none";
    if (radius && radius !== "0px" && painted) bump(radii, radius, describe(el));
    if (style.boxShadow && style.boxShadow !== "none") bump(shadows, style.boxShadow);
    if (el.matches(controlSelector)) {
      const h = Math.round(el.getBoundingClientRect().height);
      // A table row, card or list item that is clickable is a row, not a control: its height
      // follows its content (--ds-row). Counted apart so it neither hides nor inflates controls.
      if (el.matches(rowLike)) bump(rowButtons, String(h), describe(el));
      else bump(controlHeights, String(h), describe(el));
      if (h < 24) controlsUnder24 += 1;
    }
    if ((el.tagName === "TD" || el.tagName === "TH") && numeric.test((el.textContent || "").trim())) {
      numericCells += 1;
      if (!style.fontVariantNumeric.includes("tabular-nums")) untabularNumericCells += 1;
    }
  }
  return {
    fontSizes,
    fontWeights,
    radii,
    controlHeights,
    rowButtons,
    shadows: Object.keys(shadows).length,
    controlsUnder24,
    numericCells,
    untabularNumericCells,
    scrollHeight: document.documentElement.scrollHeight,
  };
}

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

const union = (pages, key) => {
  const merged = {};
  for (const p of pages) {
    for (const [value, entry] of Object.entries(p[key])) {
      const m = merged[value] || (merged[value] = { count: 0, samples: [] });
      m.count += entry.count;
      for (const s of entry.samples) if (m.samples.length < 4) m.samples.push(`${p.screen}: ${s}`);
    }
  }
  return merged;
};

const offScale = (values, scale) => Object.keys(values).filter((v) => !scale.includes(v));

export async function runGeometryAudit() {
  const { chromium } = require(
    process.env.EUROGAS_UAT_PLAYWRIGHT_PATH ? path.resolve(process.env.EUROGAS_UAT_PLAYWRIGHT_PATH) : "playwright",
  );
  mkdirSync(OUTPUT_DIR, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const report = { base: BASE, measuredAt: new Date().toISOString(), viewports: [], failures: [] };
  try {
    for (const width of budget.viewports) {
      const context = await browser.newContext({
        viewport: { width, height: width >= 1440 ? 900 : 768 },
        reducedMotion: "reduce",
      });
      await context.addInitScript(() => {
        try {
          window.localStorage.setItem("theme", "light");
          window.localStorage.setItem("eurogas.language.v1", "en");
        } catch {
          /* storage unavailable: defaults apply */
        }
      });
      const page = await context.newPage();
      await signIn(page);
      const pages = [];
      for (const [screen, search] of budget.screens) {
        await page.goto(`${BASE}/${search}`, { waitUntil: "domcontentloaded" });
        await page.locator("main").waitFor({ state: "visible", timeout: 20_000 });
        await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => undefined);
        await page.waitForTimeout(budget.settleMs ?? 2500);
        pages.push({ screen, ...(await page.evaluate(measurePage)) });
      }
      await context.close();
      const fontSizes = union(pages, "fontSizes");
      const fontWeights = union(pages, "fontWeights");
      const radii = union(pages, "radii");
      const controlHeights = union(pages, "controlHeights");
      const rowButtons = union(pages, "rowButtons");
      const summary = {
        width,
        fontSizes: Object.keys(fontSizes).length,
        fontWeights: Object.keys(fontWeights).length,
        controlHeights: Object.keys(controlHeights).length,
        radii: Object.keys(radii).length,
        shadows: Math.max(...pages.map((p) => p.shadows)),
        controlsUnder24: pages.reduce((a, p) => a + p.controlsUnder24, 0),
        untabularNumericCells: pages.reduce((a, p) => a + p.untabularNumericCells, 0),
        numericCells: pages.reduce((a, p) => a + p.numericCells, 0),
        offScale: {
          fontSizes: offScale(fontSizes, budget.scale.fontSizes),
          fontWeights: offScale(fontWeights, budget.scale.fontWeights),
          controlHeights: offScale(controlHeights, budget.scale.controlHeights),
          radii: offScale(radii, budget.scale.radii),
        },
        values: { fontSizes, fontWeights, controlHeights, radii, rowButtons },
        perScreen: pages.map((p) => ({
          screen: p.screen,
          fontSizes: Object.keys(p.fontSizes).length,
          controlHeights: Object.keys(p.controlHeights).length,
          radii: Object.keys(p.radii).length,
          shadows: p.shadows,
          controlsUnder24: p.controlsUnder24,
          untabularNumericCells: p.untabularNumericCells,
        })),
      };
      report.viewports.push(summary);
      const limits = budget.budgets[String(width)] ?? budget.budgets.default;
      for (const metric of Object.keys(limits)) {
        const measured = metric.startsWith("offScale.")
          ? summary.offScale[metric.slice("offScale.".length)].length
          : summary[metric];
        if (measured > limits[metric]) {
          report.failures.push(`${width}px ${metric}: ${measured} > budget ${limits[metric]}`);
        }
      }
    }
  } finally {
    await browser.close();
  }
  writeFileSync(path.join(OUTPUT_DIR, "geometry-audit.json"), JSON.stringify(report, null, 2));
  for (const v of report.viewports) {
    const list = (o) => Object.entries(o).sort((a, b) => b[1].count - a[1].count).map(([k, e]) => `${k}(${e.count})`).join(" ");
    console.log(`\n${v.width}px across ${budget.screens.length} screens`);
    console.log(`  font sizes      ${v.fontSizes}: ${list(v.values.fontSizes)}`);
    console.log(`  font weights    ${v.fontWeights}: ${list(v.values.fontWeights)}`);
    console.log(`  control heights ${v.controlHeights}: ${list(v.values.controlHeights)}`);
    console.log(`  radii           ${v.radii}: ${list(v.values.radii)}`);
    console.log(`  clickable rows  (not budgeted): ${list(v.values.rowButtons)}`);
    console.log(`  max shadows/screen ${v.shadows}; controls under 24 px ${v.controlsUnder24}; numeric cells without tabular figures ${v.untabularNumericCells} of ${v.numericCells}`);
    console.log(`  off scale: ${JSON.stringify(v.offScale)}`);
  }
  if (report.failures.length) {
    console.log(`\nGeometry budget exceeded:\n  ${report.failures.join("\n  ")}`);
    if (!REPORT_ONLY) process.exitCode = 1;
  } else {
    console.log("\nGeometry within budget.");
  }
  return report;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  runGeometryAudit().catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
}
