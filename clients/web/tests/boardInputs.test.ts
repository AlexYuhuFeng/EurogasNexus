import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { latestBoardPrice } from "../src/app/model/boardInputs.ts";

// UX_REFERENCE rule 25: a calculation takes its prices from the board by default.

const rows = [
  { hub: "TTF", product: "Day-ahead", price: 41.9, unit: "EUR/MWh", currency: "EUR", period_start_utc: "2026-11-16T05:00:00Z", source_system: "DEMO_Sim" },
  { hub: "TTF", product: "day_ahead", price: 42.47, unit: "EUR/MWh", currency: "EUR", period_start_utc: "2026-11-17T05:00:00Z", source_system: "DEMO_Sim" },
  { hub: "TTF", product: "Month-ahead", price: 40.1, unit: "EUR/MWh", currency: "EUR", period_start_utc: "2026-12-01T05:00:00Z" },
  { hub: "NBP", product: "DA", price: 98.654, unit: "p/th", currency: "GBP", price_gbp_mwh: 33.662, period_start_utc: "2026-11-17T05:00:00Z", source_system: "ICE" },
];

test("the latest day-ahead close in the hub's currency per MWh, with its day and source", () => {
  assert.deepEqual(latestBoardPrice(rows, "ttf", "day-ahead", "EUR"), { value: 42.47, day: "2026-11-17", source: "DEMO_Sim", simulated: true });
  // An NBP p/th quote uses the server's own GBP/MWh figure, never a client factor.
  assert.deepEqual(latestBoardPrice(rows, "NBP", "day-ahead", "GBP"), { value: 33.662, day: "2026-11-17", source: "ICE", simulated: false });
  assert.equal(latestBoardPrice(rows, "TTF", "within-day", "EUR"), null);
  assert.equal(latestBoardPrice(rows, "NBP", "day-ahead", "EUR"), null, "no FX in the client");
});

test("sell-down prefills from the board and says which inputs were typed", () => {
  const panel = readFileSync(new URL("../src/components/SellDownPanel.tsx", import.meta.url), "utf8");
  assert.match(panel, /latestBoardPrice\(markets, hub, "day-ahead", currency\)/);
  assert.match(panel, /data-manual-inputs="true"/);
  assert.match(panel, /t\("selldown\.from_board"/);
});
