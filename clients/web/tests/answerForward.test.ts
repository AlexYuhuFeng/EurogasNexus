/**
 * The answer bar's conversion for a delivery period: `78 p/th in eur/mwh jan27` goes to the
 * server (`POST /api/market/normalise`), which converts at that period's forward FX; spot and
 * one-currency conversions stay instant. EN and ZH period grammar, routing, and the answer row
 * shaped from the server's record.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import type { UnitsReferenceDTO } from "../src/api/client.ts";
import type { NormaliseResponseDTO } from "../src/api/comparablePrices.ts";
import { forwardAnswer, forwardRequest, type ForwardIntent } from "../src/app/answer/forward.ts";
import { parsePeriod, splitTrailingPeriod } from "../src/app/answer/period.ts";
import { routeQuery } from "../src/app/answer/route.ts";

const UNITS = JSON.parse(readFileSync(new URL("./fixtures/unitsReference.json", import.meta.url), "utf8")) as UnitsReferenceDTO;
const FX = { source: "ECB", rates: { GBP: { rate: 0.87, date: "2026-11-16" }, USD: { rate: 1.16, date: "2026-11-16" } } };
const NOW = new Date("2026-11-16T12:00:00Z");
const context = { units: UNITS, fx: FX, glossary: [], bookAllowed: true, zh: false, now: NOW };

test("period grammar: EN and ZH clauses resolve to the server's product codes", () => {
  const cases: Array<[string, string | null, boolean?]> = [
    ["jan27", "Jan-27"], ["jan-27", "Jan-27"], ["Jan 2027", "Jan-27"], ["january 27", "Jan-27"],
    ["2027-01", "Jan-27"], ["27年1月", "Jan-27"], ["2027年一月", "Jan-27"], ["27年12月", "Dec-27"],
    ["q1-27", "Q1-27"], ["Q1 27", "Q1-27"], ["27年一季度", "Q1-27"], ["2027年第3季度", "Q3-27"],
    ["sum-27", "Sum-27"], ["winter 2027", "Win-27"], ["27年冬季", "Win-27"], ["27夏", "Sum-27"],
    ["cal-28", "Cal-28"], ["cal28", "Cal-28"], ["gy-27", "GY-27"], ["28年日历年", "Cal-28"],
    ["m+1", "M+1"], ["M + 2", "M+2"], ["q+1", "Q+1"], ["cal+1", "Cal+1"], ["month ahead", "M+1"],
    ["次月", "M+1"], ["下季度", "Q+1"],
    ["da", "DA", true], ["day ahead", "DA", true], ["日前", "DA", true], ["wd", "WD", true],
    ["spot", "DA", true],
    ["th", null], ["eur/mwh", null], ["jan", null], ["q5-27", null], ["13月", null],
  ];
  for (const [clause, code, prompt] of cases) {
    const period = parsePeriod(clause);
    assert.equal(period?.code ?? null, code, clause);
    if (code) assert.equal(period?.prompt, Boolean(prompt), clause);
  }
});

test("a trailing period is split off the conversion line", () => {
  assert.deepEqual(splitTrailingPeriod("78 p/th in eur/mwh jan27"), {
    rest: "78 p/th in eur/mwh", period: { code: "Jan-27", label: "Jan-27", prompt: false },
  });
  assert.equal(splitTrailingPeriod("78 p/th in eur/mwh for Q1-27")?.rest, "78 p/th in eur/mwh");
  assert.equal(splitTrailingPeriod("78 便士/撒姆 换算成 欧元/兆瓦时 27年1月")?.period.code, "Jan-27");
  assert.equal(splitTrailingPeriod("100 GWh to th"), null);
});

test("routing: a future period across currencies is a look-up; spot and one currency stay instant", () => {
  const forward = routeQuery("78 p/th in eur/mwh jan27", context);
  assert.equal(forward.kind, "lookup");
  assert.deepEqual(forward.kind === "lookup" ? forward.intent : null, {
    kind: "convert", value: 78, from: "GBp/th", to: "EUR/MWh", period: "Jan-27",
  });
  const cal = routeQuery("12 $/mmbtu to €/mwh cal-28", context);
  assert.equal(cal.kind === "lookup" && cal.intent.kind === "convert" ? cal.intent.period : null, "Cal-28");
  // Day-ahead converts at spot, here, as before.
  const da = routeQuery("78 p/th in eur/mwh da", context);
  assert.equal(da.kind, "convert");
  // One currency: the period does not change the factor; instant.
  const same = routeQuery("40 eur/mwh to eur/mmbtu jan27", context);
  assert.equal(same.kind, "convert");
  // No period: unchanged instant conversion at the held ECB rate.
  const spot = routeQuery("78 p/th in eur/mwh", context);
  assert.equal(spot.kind, "convert");
  assert.equal(spot.kind === "convert" ? spot.conversion.value?.toFixed(3) : null, "30.592");
  // A price look-up is not mistaken for a conversion.
  assert.equal(routeQuery("TTF Jan-27", context).kind, "lookup");
  assert.equal(routeQuery("TTF Jan-27", context).kind === "lookup" ? (routeQuery("TTF Jan-27", context) as { intent: { kind: string } }).intent.kind : null, "price");
});

const INTENT: ForwardIntent = { kind: "convert", value: 78, from: "GBp/th", to: "EUR/MWh", period: "Jan-27" };

test("the request names the product; the server resolves it", () => {
  assert.deepEqual(forwardRequest(INTENT), {
    to_unit: "EUR/MWh",
    values: [{ value: 78, unit: "GBp/th", product: "Jan-27" }],
  });
});

test("the answer row shows the server's value, rate, method, dates and tolerance", () => {
  const response = {
    values: [{
      value: 30.50047, unit: "EUR/MWh", native: { value: 78, unit: "p/th" }, simulated: false,
      tolerance: { absolute: 0.0305, relative_pct: 0.1, basis: "forward FX" },
      normalisation: {
        from_unit: "p/th", to_unit: "EUR/MWh", unit_factor: 0.3412, factor: 0.391, heating_value: null,
        fx: {
          pair: "GBPEUR", desk_quote: { pair: "EUR/GBP", rate: 0.8725998, spot_rate: 0.87 }, base: "GBP", quote: "EUR", rate: 1 / 0.8725998, method: "derived: covered interest parity",
          label: "derived (interest parity from SONIA, €STR, flat rate)", value_date: "2027-01-15",
          spot: { pair: "GBPEUR", rate: 1 / 0.87, value_date: "2026-11-16", crossed_via: null, simulated: false },
          rates: [{ label: "SONIA (Sterling Overnight Index Average)" }, { label: "€STR (Euro Short-Term Rate)" }],
        },
      },
    }],
    series: null,
  } as unknown as NormaliseResponseDTO;
  const answer = forwardAnswer(INTENT, response);
  assert.equal(answer.label, "78 p/th · Jan-27");
  assert.equal(answer.value, "30.5005");
  assert.equal(answer.unit, "EUR/MWh");
  assert.deepEqual(answer.lines[0], {
    key: "answer.convert.fx_forward_derived",
    values: { pair: "EUR/GBP", period: "Jan-27", rate: "0.8726", benchmarks: "SONIA, €STR" },
  });
  assert.deepEqual(answer.lines[1], { key: "answer.convert.fx_spot_reference", values: { rate: "0.8700", date: "2026-11-16" } });
  assert.equal(answer.lines[2].key, "answer.convert.fx_tolerance");
  assert.equal(answer.copy?.withUnit, "30.5005 EUR/MWh");
});

test("a refusal says why and converts nothing", () => {
  const refused = forwardAnswer({ ...INTENT, period: "Cal-29" }, {
    values: [{ value: null, native: { value: 78, unit: "GBp/th" }, simulated: false,
      refused: { code: "beyond_horizon", message: "not convertible: Cal-29 is more than 24 months after the spot date" } }],
    series: null,
  });
  assert.equal(refused.value, null);
  assert.equal(refused.sentence && typeof refused.sentence !== "string" ? refused.sentence.key : null, "answer.convert.forward_beyond_horizon");
  const missing = forwardAnswer(INTENT, {
    values: [{ value: null, native: { value: 78, unit: "GBp/th" }, simulated: false,
      refused: { code: "not_convertible", message: "not convertible: no EURGBP rate held" } }],
    series: null,
  });
  assert.deepEqual(missing.sentence, { key: "answer.convert.forward_refused", values: { reason: "not convertible: no EURGBP rate held" } });
});
