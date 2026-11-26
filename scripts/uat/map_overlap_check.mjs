#!/usr/bin/env node
/**
 * Nothing on the live map overlaps anything else (owner review 2026-11-26).
 *
 * Signs in, opens Desk → Network at the four review sizes (1440x900, 1180x820 iPad landscape,
 * 820x1180, 390x844) in English and Chinese, and fails when
 *   - two HTML overlays of the map intersect (finder, zoom, control stack, attribution, notices,
 *     intensity legend, key, callouts), or one of them leaves the map;
 *   - a map label sits under an HTML overlay: every overlay box is sampled on a 6 px grid with
 *     MapLibre's own `queryRenderedFeatures` on the label layers, which answers from the labels'
 *     placed collision boxes (the map instance is on its container as `egnMap`);
 *   - the label layers allow overlap among themselves (MapLibre's collision is then off).
 * Run against a running web client and API, as the browser sweep is:
 *
 *     EUROGAS_UAT_BASE_URL=http://127.0.0.1:3000 EUROGAS_NEXUS_DEV_LOGIN_USERNAME=... \
 *       EUROGAS_NEXUS_DEV_LOGIN_PASSWORD=... node scripts/uat/map_overlap_check.mjs
 *
 * EUROGAS_UAT_BROWSER=webkit runs it in WebKit; EUROGAS_UAT_SHOTS=<dir> also saves a screenshot
 * per size and language.
 */
import { createRequire } from "node:module";
import { mkdirSync } from "node:fs";

const require = createRequire(import.meta.url);
const playwright = require(process.env.EUROGAS_UAT_PLAYWRIGHT_PATH || "playwright");
const BASE = process.env.EUROGAS_UAT_BASE_URL || "http://127.0.0.1:3000";
const username = process.env.EUROGAS_NEXUS_DEV_LOGIN_USERNAME || "";
const password = process.env.EUROGAS_NEXUS_DEV_LOGIN_PASSWORD || "";
const SIZES = (process.env.EUROGAS_UAT_SIZES || "1440x900,1180x820,820x1180,390x844").split(",");
const LANGUAGES = (process.env.EUROGAS_UAT_LANGUAGES || "en,zh-CN").split(",");
const SHOTS = process.env.EUROGAS_UAT_SHOTS || "";

const OVERLAYS = [
  ".map-finder",
  ".map-finder-toggle",
  ".map-control-stack",
  ".maplibregl-ctrl-top-right .maplibregl-ctrl",
  ".maplibregl-ctrl-bottom-left .maplibregl-ctrl",
  ".map-basemap-state",
  ".map-intensity-legend",
  ".map-scene-key",
  ".map-callout",
  ".map-replay-bar",
];
const LABEL_LAYERS = ["map-labels", "selection-labels"];

const browser = await playwright[process.env.EUROGAS_UAT_BROWSER || "chromium"].launch();
const failures = [];
if (SHOTS) mkdirSync(SHOTS, { recursive: true });
for (const language of LANGUAGES) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: language });
  await context.addInitScript((lang) => {
    try {
      window.localStorage.setItem("eurogas.language.v1", lang);
    } catch {
      // Storage blocked: the browser's language applies.
    }
  }, language);
  const page = await context.newPage();
  await page.goto(`${BASE}/?workspace=market&task=network`);
  const user = page.locator("#sign-in-username");
  await Promise.race([user.waitFor({ timeout: 60000 }), page.locator(".maplibregl-canvas").waitFor({ timeout: 60000 })]);
  if (await user.isVisible().catch(() => false)) {
    await user.fill(username);
    await page.locator("#sign-in-password").fill(password);
    await page.keyboard.press("Enter");
    await page.locator("main").waitFor({ timeout: 60000 });
  }
  for (const size of SIZES) {
    const [width, height] = size.split("x").map(Number);
    await page.setViewportSize({ width, height });
    await page.goto(`${BASE}/?workspace=market&task=network`);
    await page.waitForSelector('[data-map-ready="true"]', { timeout: 90000 });
    await page.waitForTimeout(6000);
    const found = await page.evaluate(({ overlays, labelLayers }) => {
      const problems = [];
      const root = document.querySelector(".gas-map");
      const container = root?.querySelector(".maplibre-canvas");
      const map = container?.egnMap;
      if (!root || !container || !map) return ["the map or its instance is missing"];
      const frame = container.getBoundingClientRect();
      const visible = (element) => {
        const rect = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none";
      };
      const boxes = [];
      for (const selector of overlays) {
        for (const element of root.querySelectorAll(selector)) {
          if (!visible(element)) continue;
          boxes.push({ name: selector, rect: element.getBoundingClientRect() });
        }
      }
      const hit = (a, b) => a.left < b.right - 1 && b.left < a.right - 1 && a.top < b.bottom - 1 && b.top < a.bottom - 1;
      for (let i = 0; i < boxes.length; i += 1) {
        const { rect, name } = boxes[i];
        if (rect.left < frame.left - 1 || rect.right > frame.right + 1 || rect.top < frame.top - 1 || rect.bottom > frame.bottom + 1) {
          problems.push(`${name} leaves the map`);
        }
        for (let j = i + 1; j < boxes.length; j += 1) {
          if (hit(rect, boxes[j].rect)) problems.push(`${name} overlaps ${boxes[j].name}`);
        }
      }
      const layers = labelLayers.filter((id) => map.getLayer(id));
      for (const id of layers) {
        if (map.getLayoutProperty(id, "text-allow-overlap") === true) problems.push(`${id} allows overlapping labels`);
      }
      // Labels under an overlay: MapLibre answers from each label's placed collision box.
      for (const { rect, name } of boxes) {
        for (let x = rect.left + 2; x < rect.right - 1; x += 6) {
          for (let y = rect.top + 2; y < rect.bottom - 1; y += 6) {
            const features = map.queryRenderedFeatures([x - frame.left, y - frame.top], { layers });
            if (features.length) {
              problems.push(`label "${features[0].properties?.text ?? ""}" under ${name}`);
              x = rect.right;
              break;
            }
          }
        }
      }
      return [...new Set(problems)];
    }, { overlays: OVERLAYS, labelLayers: LABEL_LAYERS });
    if (SHOTS) await page.screenshot({ path: `${SHOTS}/${language}-${size}.png` });
    for (const problem of found) failures.push(`${language} ${size}: ${problem}`);
    console.log(`${language} ${size}: ${found.length ? found.join("; ") : "no overlap"}`);
  }
  await context.close();
}
await browser.close();
if (failures.length) {
  console.error(`overlaps on the map:\n  ${failures.join("\n  ")}`);
  process.exit(1);
}
console.log("map: no overlay or label overlaps at any size or language");
