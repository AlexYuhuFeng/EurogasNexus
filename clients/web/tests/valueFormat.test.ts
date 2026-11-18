import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import type { FxForwardDTO, NormalisedValueDTO } from "../src/api/comparablePrices.ts";
import {
  conversionAllowed,
  conversionExportColumns,
  convertedAmountText,
  convertedPriceText,
  currencyOfUnit,
  describeRate,
  energyOfUnit,
  NEVER_CONVERTED,
  rateStatement,
  REPORTING_CURRENCIES,
  targetCurrency,
  targetPriceUnit,
  totalRule,
} from "../src/app/time/valueFormat.ts";

// Display preferences (design basis G1-G7, CP-05): native first, converted values named.

const en = JSON.parse(readFileSync(new URL("../src/i18n/en.json", import.meta.url), "utf8")) as Record<string, string>;
const zh = JSON.parse(readFileSync(new URL("../src/i18n/zh.json", import.meta.url), "utf8")) as Record<string, string>;
const translate = (table: Record<string, string>) => (key: string, options: Record<string, unknown> = {}) =>
  (table[key] ?? key).replace(/\{\{(\w+)\}\}/g, (_, name: string) => String(options[name] ?? ""));
const t = translate(en);

const forward: FxForwardDTO = {
  pair: "EURUSD",
  desk_quote: { pair: "EUR/USD", rate: 1.16, spot_rate: 1.158 },
  base: "EUR",
  quote: "USD",
  rate: 1.16,
  quoted_as: "USD per 1 EUR",
  method: "derived: covered interest parity",
  label: "derived (interest parity from €STR, SOFR, flat rate)",
  input_class: "derived",
  simulated: false,
  value_date: "2027-01-15",
  delivery: { label: "Jan-27", kind: "month", first_gas_day: "2027-01-01", last_gas_day: "2027-01-31" },
  spot: { pair: "EURUSD", rate: 1.158, value_date: "2026-11-16", crossed_via: null, simulated: false },
  rates: [],
  days: 60,
  compounding: "simple",
  licensed: null,
  tolerance: { relative_pct: 0.1, absolute: 0.00116 },
  horizon_months: 24,
  limitations: [],
};

test("G7: contract terms, tariffs and frozen evidence are never converted; limits and prices may be", () => {
  for (const subject of NEVER_CONVERTED) assert.equal(conversionAllowed(subject), false, subject);
  assert.deepEqual([...NEVER_CONVERTED].sort(), ["contract_term", "frozen_evidence", "tariff"]);
  for (const subject of ["price", "position", "pnl", "limit", "total", "exposure"] as const) assert.equal(conversionAllowed(subject), true);
});

test("a native unit already in the reader's currency and energy unit needs no conversion", () => {
  const eurMwh = { reportingCurrency: "EUR", energyUnit: "MWh" as const };
  assert.equal(targetPriceUnit("EUR/MWh", eurMwh), null);
  assert.equal(targetPriceUnit("p/th", eurMwh), "EUR/MWh");
  assert.equal(targetPriceUnit("USD/MMBtu", eurMwh), "EUR/MWh");
  assert.equal(targetPriceUnit("EUR/MWh", { reportingCurrency: "USD", energyUnit: "MMBtu" }), "USD/MMBtu");
  assert.equal(targetPriceUnit("p/th", { reportingCurrency: "GBP", energyUnit: "th" }), null);
  assert.equal(targetCurrency("EUR", eurMwh), null);
  assert.equal(targetCurrency("gbp", eurMwh), "EUR");
  assert.equal(currencyOfUnit("p/th"), "GBP");
  assert.equal(currencyOfUnit("GBp/th"), "GBP");
  assert.equal(energyOfUnit("USD/MMBtu"), "MMBtu");
  assert.equal(energyOfUnit("p/therm"), "th");
});

test("the rate is always named: pair, rate, source, date and method (G3, G6)", () => {
  const statement = rateStatement(forward);
  assert.deepEqual(statement, {
    pair: "EUR/USD",
    rate: 1.16,
    source: "ecb",
    date: "2026-11-16",
    method: "forward",
    delivery: "Jan-27",
  });
  assert.equal(describeRate(statement, "en", t), "EUR/USD 1.1600 (ECB 16 Nov; forward Jan-27, derived)");
  const spot = { ...forward, method: "spot: ECB reference rate" as const, delivery: null, value_date: "2026-11-16" };
  assert.equal(describeRate(rateStatement(spot), "en", t), "EUR/USD 1.1600 (ECB 16 Nov; spot)");
  const simulated = { ...spot, simulated: true };
  assert.match(describeRate(rateStatement(simulated), "en", t), /simulated/i);
  assert.doesNotMatch(describeRate(rateStatement(forward), "zh-CN", translate(zh)), /convert\./);
});

test("a converted price carries its figure and the rate; a refusal says why instead of a number", () => {
  const result: NormalisedValueDTO = {
    value: 10.2,
    unit: "USD/MMBtu",
    native: { value: 30, unit: "EUR/MWh" },
    simulated: false,
    normalisation: { from_unit: "EUR/MWh", to_unit: "USD/MMBtu", unit_factor: 0.29, factor: 0.34, heating_value: null, fx: forward },
  };
  const text = convertedPriceText(result, "en", t);
  assert.equal(text.figure, "10.200 USD/MMBtu");
  assert.equal(text.text, "10.200 USD/MMBtu at EUR/USD 1.1600 (ECB 16 Nov; forward Jan-27, derived)");
  const unitsOnly = convertedPriceText({ ...result, unit: "EUR/MMBtu", normalisation: { ...result.normalisation!, fx: null } }, "en", t);
  assert.match(unitsOnly.text, /^10\.200 EUR\/MMBtu/);
  assert.match(unitsOnly.text, /unit/);
  const refused = convertedPriceText(
    { value: null, native: { value: 30, unit: "EUR/MWh" }, simulated: false, refused: { code: "not_convertible", message: "no EURCNY rate held" } },
    "en",
    t,
  );
  assert.equal(refused.refused, true);
  assert.equal(refused.text, "Not converted: the rate for this delivery is not held.");
  assert.equal(refused.reason, "no EURCNY rate held");
});

test("an amount converts at the stated rate with its line", () => {
  const text = convertedAmountText(-405192, { ...forward, method: "spot: ECB reference rate", delivery: null }, "en", t);
  assert.equal(text.figure, "\u2212470,023 USD");
  assert.equal(convertedAmountText(1, forward, "en", t, 0, true).simulated, true);
  assert.match(text.text, /at EUR\/USD 1\.1600 \(ECB 16 Nov; spot\)$/);
});

test("G4: a total across currencies is shown only converted; simulated never mixes into it", () => {
  assert.deepEqual(totalRule([{ value: 1, currency: "EUR" }, { value: 2, currency: "eur" }]), { kind: "native", currency: "EUR" });
  assert.deepEqual(totalRule([{ value: 1, currency: "EUR" }, { value: 2, currency: "GBP" }]), { kind: "converted", currencies: ["EUR", "GBP"] });
  assert.deepEqual(totalRule([{ value: 1, currency: "EUR", simulated: true }, { value: 2, currency: "EUR" }]), { kind: "refused", reason: "mixes_simulated" });
});

test("exports carry the conversion as columns (G6)", () => {
  assert.deepEqual(conversionExportColumns(forward), {
    fx_pair: "EUR/USD",
    fx_rate: "1.16",
    fx_rate_date: "2026-11-16",
    fx_method: "derived (interest parity from €STR, SOFR, flat rate)",
    fx_source: "ecb",
  });
  assert.deepEqual(Object.keys(conversionExportColumns(null)), ["fx_pair", "fx_rate", "fx_rate_date", "fx_method", "fx_source"]);
});

test("the client's currency list is the server's vocabulary", () => {
  const server = readFileSync(new URL("../../../src/eurogas_nexus/domain/settings/preferences.py", import.meta.url), "utf8");
  const block = /REPORTING_CURRENCIES: tuple\[str, \.\.\.\] = \(([\s\S]*?)\)/.exec(server)?.[1] ?? "";
  assert.deepEqual([...block.matchAll(/"([A-Z]{3})"/g)].map((match) => match[1]), [...REPORTING_CURRENCIES]);
  assert.match(server, /"energy_unit": ENERGY_UNITS/);
  assert.match(server, /ENERGY_UNITS: tuple\[str, \.\.\.\] = \("MWh", "th", "MMBtu", "GJ"\)/);
});

test("a conversion is a read: asking for one does not mark every kept answer stale", () => {
  const client = readFileSync(new URL("../src/api/client.ts", import.meta.url), "utf8");
  assert.match(client, /normaliseMarket:[^\n]*\n\s*postRead<NormaliseResponseDTO>\("\/market\/normalise"/);
  const postRead = /async function postRead[\s\S]*?\n}\n/.exec(client)?.[0] ?? "";
  assert.ok(postRead && !postRead.includes("notifyApiWrite"));
});
