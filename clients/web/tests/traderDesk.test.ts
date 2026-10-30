/**
 * The trader desk panel: product strip, price conversion and storage trajectory are the backend's.
 *
 * The model only formats; it never converts a price or fills a missing FX rate. The source pins keep
 * the panel mounted on the numeric market task, reading the three backend routes, and bilingual.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  FX_SOURCE_OPTIONS,
  PRICE_UNIT_OPTIONS,
  describeFxRate,
  STORAGE_CODES,
  formatConverted,
  formatSigned,
  storageStatusKey,
} from "../src/app/model/traderDeskModel.ts";

const read = (path: string) => readFileSync(new URL(path, import.meta.url), "utf8");

test("a missing converted value shows the caller's label instead of a number", () => {
  assert.equal(formatConverted(null, "FX unavailable"), "FX unavailable");
  assert.equal(formatConverted(undefined, "x"), "x");
  assert.equal(formatConverted(87.18891, "x"), "87.189", "below 100 keeps three decimals");
  assert.equal(formatConverted(123.456, "x"), "123.46");
});

test("signed flows keep their sign and unit, and n/a when absent", () => {
  assert.equal(formatSigned(3.2, "TWh/d"), "+3.20 TWh/d");
  assert.equal(formatSigned(-1.5, "TWh/d"), "-1.50 TWh/d");
  assert.equal(formatSigned(null, "TWh/d"), "n/a");
});

test("the desk offers the hub quotations and the EU aggregate first", () => {
  assert.deepEqual(PRICE_UNIT_OPTIONS.slice(0, 3), ["EUR/MWh", "GBp/th", "USD/MMBtu"]);
  assert.equal(STORAGE_CODES[0], "EU");
});

test("every storage status has an EN and ZH label", () => {
  const en = JSON.parse(read("../src/i18n/en.json"));
  const zh = JSON.parse(read("../src/i18n/zh.json"));
  for (const status of ["target_met", "on_track", "behind", "unreachable", "withdrawal_season"] as const) {
    const key = storageStatusKey(status);
    assert.ok(en[key], `en ${key}`);
    assert.ok(zh[key], `zh ${key}`);
  }
  for (const key of Object.keys(en).filter((item) => item.startsWith("desk."))) {
    assert.ok(zh[key], `zh parity ${key}`);
  }
});

test("the panel is mounted on the curves task and reads the three backend routes", () => {
  const cockpit = read("../src/components/MarketCockpit.tsx");
  assert.match(cockpit, /<TraderDeskPanel t=\{t\} \/>/);
  const client = read("../src/api/client.ts");
  for (const path of ["/market/products", "/market/price-conversion", "/storage/target-trajectory"]) {
    assert.ok(client.includes(`"${path}"`), path);
  }
});

test("the converter names the FX fix: ECB, WM/Reuters or BFIX, and an average names its window", () => {
  assert.deepEqual([...FX_SOURCE_OPTIONS], ["ECB", "WMR", "BFIX"]);
  assert.equal(
    describeFxRate("USD", { rate: 1.085, source: "WMR", value_dates: ["2026-10-01", "2026-10-31"] }),
    "EUR/USD 1.0850 (WMR 2026-10-01..2026-10-31, 2 fixes)",
  );
  assert.equal(describeFxRate("GBP", { rate: 0.85, source: "request" }), "EUR/GBP 0.8500 (request)");
  const client = read("../src/api/client.ts");
  assert.ok(client.includes("fx_source: fxSource"));
});
