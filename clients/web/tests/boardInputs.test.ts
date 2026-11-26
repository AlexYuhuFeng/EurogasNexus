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
  assert.match(panel, /latestBoardPrice\(markets, hub, "day-ahead", currency, quoteUnit\)/);
  assert.match(panel, /price_unit: quoteUnit/);
  assert.match(panel, /data-manual-inputs="true"/);
  assert.match(panel, /t\("selldown\.from_board"/);
});

test("NBP is taken from the board in p/th, as the desk quotes it, without a factor here", async () => {
  const { latestBoardPrice } = await import("../src/app/model/boardInputs.ts");
  const { hubQuoteUnit } = await import("../src/app/contractChoices.ts");
  const rows = [{ hub: "NBP", product: "NBP day-ahead", price: 104.2, unit: "p/th", price_gbp_mwh: 35.56, period_start_utc: "2026-11-26T05:00:00Z", source_system: "ICE_ENDEX" }];
  assert.equal(hubQuoteUnit("NBP"), "GBp/th");
  assert.equal(hubQuoteUnit("TTF"), "EUR/MWh");
  assert.equal(latestBoardPrice(rows as never, "NBP", "day-ahead", "GBP", "GBp/th")?.value, 104.2);
  assert.equal(latestBoardPrice(rows as never, "NBP", "day-ahead", "GBP")?.value, 35.56);
});
