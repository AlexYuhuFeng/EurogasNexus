/**
 * The market ladder: products down, hubs across, best bid/offer across venues in native units.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import type { MarketQuoteDTO } from "../src/api/client.ts";
import { buildMarketLadder, formatLadderPrice, formatLadderVolume } from "../src/app/model/marketLadderModel.ts";

const quote = (overrides: Partial<MarketQuoteDTO>): MarketQuoteDTO => ({
  quote_id: Math.random().toString(36),
  source_system: "Trayport",
  venue: "Trayport",
  instrument_id: "x",
  hub: "TTF",
  product: "day-ahead",
  delivery_start_utc: "2026-11-02T05:00:00Z",
  delivery_end_utc: "2026-11-03T05:00:00Z",
  bid_price: 31.5,
  ask_price: 31.6,
  bid_quantity_mwh: 720,
  ask_quantity_mwh: 600,
  currency: "EUR",
  unit: "MWh",
  observed_at_utc: "2026-10-30T09:00:00Z",
  received_at_utc: "2026-10-30T09:00:00Z",
  source_reference: "t",
  freshness: "imported",
  quality_score: 1,
  simulated: false,
  ...overrides,
});

test("best bid and offer across venues, latest tick per venue only", () => {
  const rows = buildMarketLadder(
    [
      quote({ source_system: "Trayport", bid_price: 31.5, ask_price: 31.6 }),
      quote({ source_system: "ICE_OCM", bid_price: 31.55, ask_price: 31.65 }),
      // An older Trayport tick with a better bid must not win.
      quote({ source_system: "Trayport", bid_price: 40, observed_at_utc: "2026-10-30T08:00:00Z" }),
    ],
    ["TTF"],
  );
  const cell = rows[0].cells.TTF;
  assert.equal(rows[0].label, "DA");
  assert.equal(cell.bid?.price, 31.55);
  assert.equal(cell.bid?.source, "ICE_OCM");
  assert.equal(cell.offer?.price, 31.6);
  assert.equal(cell.crossed, false);
});

test("products sort by delivery and imported NBP rows read in p/th and th/d", () => {
  const rows = buildMarketLadder(
    [
      quote({ product: "nov-26", delivery_start_utc: "2026-11-01T05:00:00Z", delivery_end_utc: "2026-12-01T05:00:00Z", metadata_json: { product_label: "Nov-26" } }),
      quote({
        hub: "NBP",
        currency: "GBP",
        bid_price: 28.15,
        ask_price: 28.25,
        metadata_json: { native_unit: "GBp/th", native_bid: 82.5, native_ask: 82.8, native_bid_qty: 25000, native_quantity_unit: "th/d" },
      }),
    ],
    ["TTF", "NBP"],
  );
  // DA (a prompt product) leads even though Nov-26 starts first.
  assert.deepEqual(rows.map((row) => row.label), ["DA", "Nov-26"]);
  const nbp = rows[0].cells.NBP;
  assert.equal(formatLadderPrice(nbp.bid), "82.50");
  assert.equal(nbp.bid?.priceUnit, "GBp/th");
  assert.equal(formatLadderVolume(nbp.bid), "25,000");
  assert.equal(nbp.bid?.volumeUnit, "th/d");
});

test("simulated quotes never compete with real ones, and month-ahead merges into its month", () => {
  const nov = { delivery_start_utc: "2026-11-01T05:00:00Z", delivery_end_utc: "2026-12-01T05:00:00Z" };
  const rows = buildMarketLadder(
    [
      quote({ ...nov, product: "month-ahead", source_system: "EEX_Sim", simulated: true, bid_price: 40 }),
      quote({ ...nov, product: "nov-26", bid_price: 32.1, metadata_json: { product_label: "Nov-26" } }),
      quote({ product: "cal-27", delivery_start_utc: "2027-01-01T05:00:00Z", delivery_end_utc: "2028-01-01T05:00:00Z", metadata_json: { product_label: "Cal-27" } }),
      quote({ product: "jan-27", delivery_start_utc: "2027-01-01T05:00:00Z", delivery_end_utc: "2027-02-01T05:00:00Z", metadata_json: { product_label: "Jan-27" } }),
    ],
    ["TTF"],
  );
  assert.deepEqual(rows.map((row) => row.label), ["Nov-26", "Jan-27", "Cal-27"]);
  assert.equal(rows[0].cells.TTF.bid?.price, 32.1);
  assert.equal(rows[0].cells.TTF.bid?.simulated, false);
});

test("a crossed market is flagged, not hidden", () => {
  const rows = buildMarketLadder(
    [quote({ source_system: "Trayport", bid_price: 31.7, ask_price: 31.8 }), quote({ source_system: "EEX", bid_price: 31.4, ask_price: 31.6 })],
    ["TTF"],
  );
  assert.equal(rows[0].cells.TTF.crossed, true);
});

test("the ladder is a view of the market page and the manual maps screen concepts", () => {
  const terminal = readFileSync(new URL("../src/components/MarketTerminal.tsx", import.meta.url), "utf8");
  assert.match(terminal, /<MarketLadder/);
  const en = JSON.parse(readFileSync(new URL("../src/i18n/en.json", import.meta.url), "utf8"));
  const zh = JSON.parse(readFileSync(new URL("../src/i18n/zh.json", import.meta.url), "utf8"));
  for (const key of Object.keys(en).filter((item) => item.startsWith("ladder.") || item.startsWith("manual.from_screen."))) {
    assert.ok(zh[key], key);
  }
});
