#!/usr/bin/env node
/**
 * The map asks no host but its own and its one basemap (owner review 2026-11-26).
 *
 * The basemap is OpenStreetMap data through OpenFreeMap (tiles.openfreemap.org: ODbL, commercial
 * use allowed). Signs in, opens Desk → Network, waits for the map to draw and fails when any
 * request leaves for another host: a tile service whose terms exclude a commercial product
 * (tile.openstreetmap.org, CARTO, AMap), a font CDN, an analytics beacon. Without internet the
 * map falls back to the bundled outline and the check still holds.
 * Run against a running web client and API, as the browser sweep is:
 *
 *     EUROGAS_UAT_BASE_URL=http://127.0.0.1:3000 EUROGAS_NEXUS_DEV_LOGIN_USERNAME=... \
 *       EUROGAS_NEXUS_DEV_LOGIN_PASSWORD=... node scripts/uat/map_no_third_party.mjs
 */
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.EUROGAS_UAT_PLAYWRIGHT_PATH || "playwright");
const BASE = process.env.EUROGAS_UAT_BASE_URL || "http://127.0.0.1:3000";
const username = process.env.EUROGAS_NEXUS_DEV_LOGIN_USERNAME || "";
const password = process.env.EUROGAS_NEXUS_DEV_LOGIN_PASSWORD || "";

const own = new URL(BASE).host;
/** The one basemap host the product may call. */
const BASEMAP_HOST = "tiles.openfreemap.org";
const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();
const foreign = new Set();
let glyphs = 0;
// The context sees the map's worker requests too (tiles, glyphs).
context.on("request", (request) => {
  const url = new URL(request.url());
  if (["data:", "blob:"].includes(url.protocol)) return;
  if (url.pathname.includes("/basemaps/glyphs/")) glyphs += 1;
  if (url.host !== own && url.host !== BASEMAP_HOST) foreign.add(`${url.host}${url.pathname}`);
});
await page.goto(`${BASE}/?workspace=market&task=network`);
const user = page.locator("#sign-in-username");
await Promise.race([user.waitFor({ timeout: 60000 }), page.locator(".maplibregl-canvas").waitFor({ timeout: 60000 })]);
if (await user.isVisible().catch(() => false)) {
  await user.fill(username);
  await page.locator("#sign-in-password").fill(password);
  await page.locator(".sign-in-dev-form button[type=submit]").click();
}
await page.locator(".maplibregl-canvas").waitFor({ timeout: 90000 });
await page.waitForFunction(() => !document.body.innerText.includes("Loading network layers"), null, { timeout: 90000 });
// Pan and zoom so a tile-based style would have to fetch more.
const box = await page.locator(".maplibregl-canvas").boundingBox();
await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
await page.mouse.wheel(0, -600);
await page.waitForTimeout(4000);
await browser.close();
if (foreign.size) {
  console.error(`the map requested hosts other than its own and ${BASEMAP_HOST}:\n  ${[...foreign].join("\n  ")}`);
  process.exit(1);
}
console.log(`map: only its own host and ${BASEMAP_HOST} (bundled glyph ranges read: ${glyphs})`);
