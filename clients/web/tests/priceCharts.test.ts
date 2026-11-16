/** Prices charts (UX-09): the forward curve in the hub's quotation and the NBP–TTF spread. */
import assert from "node:assert/strict";
import test from "node:test";

import { curveHubs, forwardCurve, inQuoteUnit, nbpTtfSpread } from "../src/app/model/priceCharts.ts";

const at = "2026-11-16T01:00:00Z";
const rows = [
  { hub: "TTF", tenor: "2026-12", price: 31.4, unit: "EUR/MWh", observed_at_utc: at, price_gbp_mwh: 27.0, source_system: "DEMO_Sim" },
  { hub: "TTF", tenor: "2027-02", price: 30.0, unit: "EUR/MWh", observed_at_utc: at, price_gbp_mwh: 26.0, source_system: "DEMO_Sim" },
  { hub: "TTF", tenor: "2026-12", price: 99, unit: "EUR/MWh", observed_at_utc: "2026-11-10T00:00:00Z", price_gbp_mwh: 80, source_system: "DEMO_Sim" },
  { hub: "TTF", tenor: "month-ahead", price: 31.4, unit: "EUR/MWh", observed_at_utc: at, source_system: "DEMO_Sim" },
  { hub: "NBP", tenor: "2026-12", price: 33.662, unit: "GBP/MWh", observed_at_utc: at, price_gbp_mwh: 33.662, source_system: "DEMO_Sim" },
  { hub: "NBP", tenor: "2027-01", price: 34, unit: "GBP/MWh", observed_at_utc: at, price_gbp_mwh: 34, source_system: "DEMO_Sim" },
];

test("NBP is drawn in pence per therm, TTF in EUR/MWh (rule 17)", () => {
  assert.equal(Number(inQuoteUnit("NBP", 33.662, "GBP/MWh")!.toFixed(3)), 98.654);
  assert.equal(inQuoteUnit("TTF", 31.4, "EUR/MWh"), 31.4);
  assert.equal(inQuoteUnit("TTF", 31.4, "GBP/MWh"), null, "no FX in the client");
  const nbp = forwardCurve(rows, "NBP");
  assert.equal(nbp.unit, "GBp/th");
  assert.deepEqual(nbp.months, ["2026-12", "2027-01"]);
  assert.equal(nbp.values[0], 98.6536);
});

test("the curve keeps the latest close per month and leaves a missing month as a gap", () => {
  const ttf = forwardCurve(rows, "TTF");
  assert.deepEqual(ttf.months, ["2026-12", "2027-01", "2027-02"]);
  assert.deepEqual(ttf.values, [31.4, null, 30]);
  assert.equal(ttf.simulated, true);
  assert.equal(ttf.asOf, at);
  assert.deepEqual(forwardCurve(rows, "TTF", "2027-01").months, ["2027-02"], "past months dropped");
  assert.deepEqual(curveHubs(rows), ["TTF", "NBP"]);
});

test("the NBP–TTF spread uses the backend's GBP prices and is quoted in p/th", () => {
  const spread = nbpTtfSpread(rows);
  assert.deepEqual(spread.months, ["2026-12"]);
  assert.equal(spread.values[0], Number(((33.662 - 27) * 2.9307107).toFixed(4)));
  assert.equal(spread.unit, "GBp/th");
});
