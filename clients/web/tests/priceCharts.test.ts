/** Prices charts (UX-09): the forward curve in the hub's quotation and the NBP–TTF spread. */
import assert from "node:assert/strict";
import test from "node:test";

import { curveCloseDays, curveHubs, forwardCurve, inQuoteUnit, nbpTtfSpread, spreadByMonth, termStructure } from "../src/app/model/priceCharts.ts";

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

/* Term structure (F.1, F.3 #1): today's curve with the prior close and a week ago as ghosts. */
const closes = [
  ...["2026-12", "2027-01", "2027-02"].map((tenor, index) => ({ hub: "TTF", tenor, price: 31 - index, unit: "EUR/MWh", observed_at_utc: "2026-11-16T18:00:00Z" })),
  ...["2026-12", "2027-01"].map((tenor, index) => ({ hub: "TTF", tenor, price: 30.5 - index, unit: "EUR/MWh", observed_at_utc: "2026-11-13T18:00:00Z" })),
  ...["2026-12", "2027-01", "2027-02"].map((tenor, index) => ({ hub: "TTF", tenor, price: 29 - index, unit: "EUR/MWh", observed_at_utc: "2026-11-09T18:00:00Z" })),
];

test("term structure: the prior close and the close a week before are ghost curves on the same months", () => {
  assert.deepEqual(curveCloseDays(closes, "TTF"), ["2026-11-09", "2026-11-13", "2026-11-16"]);
  const curve = termStructure(closes, "TTF", "2026-12");
  assert.deepEqual(curve.months, ["2026-12", "2027-01", "2027-02"]);
  assert.deepEqual(curve.current, [31, 30, 29]);
  assert.equal(curve.priorClose?.day, "2026-11-13");
  // The prior close did not quote Feb-27: a gap, never the older 9 Nov value.
  assert.deepEqual(curve.priorClose?.values, [30.5, 29.5, null]);
  assert.equal(curve.weekAgo?.day, "2026-11-09");
  assert.deepEqual(curve.weekAgo?.values, [29, 28, 27]);
});

test("term structure: one close held means no ghost curves (nothing invented)", () => {
  const curve = termStructure(closes.slice(0, 3), "TTF");
  assert.equal(curve.priorClose, null);
  assert.equal(curve.weekAgo, null);
});

test("spread by delivery month: one unit or refused; fewer than six months held is a table", () => {
  const ttf = forwardCurve(closes, "TTF");
  const nbp = forwardCurve(rows, "NBP");
  assert.equal(spreadByMonth(nbp, ttf).refused, "units");
  const other = { ...ttf, values: ttf.values.map((value) => (value == null ? null : value - 0.25)) };
  const spread = spreadByMonth(ttf, other);
  assert.equal(spread.refused, null);
  assert.deepEqual(spread.values, [0.25, 0.25, 0.25]);
  assert.equal(spread.form, "table");
});
