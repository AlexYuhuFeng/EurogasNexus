/**
 * The answer bar's tier 1 parser: arithmetic, conversions with the units authority's factors,
 * gas-day answers and glossary hits, table-driven. The rule under test is as much what gives
 * *no* answer (a hub name being typed, a date, a decimal comma) as what does.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import type { UnitsReferenceDTO } from "../src/api/client.ts";
import { calculate } from "../src/app/answer/expression.ts";
import { gasDayAnswer, parseDay } from "../src/app/answer/gasDay.ts";
import { definitionSubject, findTerm, shortDefinition } from "../src/app/answer/glossary.ts";
import { clipboardNumber, formatAnswerNumber, parseNumber } from "../src/app/answer/numbers.ts";
import { convertQuery, fxHeldFrom, type FxHeld } from "../src/app/answer/units.ts";

/** The server's `units_reference()`; `tests/api/test_analysis_api.py` keeps it in step. */
const UNITS = JSON.parse(
  readFileSync(new URL("./fixtures/unitsReference.json", import.meta.url), "utf8"),
) as UnitsReferenceDTO;
const FX: FxHeld = { source: "ECB", rates: { GBP: { rate: 0.8356, date: "2026-11-13" }, USD: { rate: 1.0832, date: "2026-11-13" } } };

const close = (actual: number | null | undefined, expected: number, digits = 4) => {
  assert.ok(actual !== null && actual !== undefined, "no value");
  assert.ok(Math.abs(actual - expected) < 10 ** -digits, `${actual} != ${expected}`);
};

test("number policy: point decimals, comma thousands in groups of three, nothing else", () => {
  const cases: Array<[string, number | null]> = [
    ["42.5", 42.5], [".5", 0.5], ["1,000", 1000], ["12,345.6", 12345.6], ["1,234,567", 1234567],
    ["3,5", null], ["1,00", null], ["1,0000", null], ["１２．５", 12.5], ["", null], ["1.2.3", null],
  ];
  for (const [input, expected] of cases) assert.equal(parseNumber(input), expected, input);
});

test("arithmetic: what is a calculation, and its value", () => {
  const cases: Array<[string, number]> = [
    ["(42.5-39.8)*30", 81],
    ["2+3*4", 14],
    ["2^3^2", 512],
    ["-(2+3)*2", -10],
    ["200 + 15%", 230],
    ["200 - 15%", 170],
    ["15% of 200", 30],
    ["200 * 15%", 30],
    ["50%", 0.5],
    ["1,000 / 8", 125],
    ["（42.5－39.8）×30", 81],
    ["10 ÷ 4", 2.5],
    ["3 − 5", -2],
    ["0.1 + 0.2", 0.3],
  ];
  for (const [input, expected] of cases) close(calculate(input)?.value, expected, 9);
});

test("arithmetic: no answer while typing a name, a date or a lone number", () => {
  const none = [
    "2026", "-5", "TTF", "Dec-26", "2026-11-16", "26-27", "2026/27", "16/11", "TTF Dec-26", "NBP 2",
    "3,5 + 1", "1/0", "2 +", "(2+3", "2 3", "+44 20 7946 0000", "Q1-27", "D+2", "",
  ];
  for (const input of none) assert.equal(calculate(input), null, input);
  close(calculate("2026", true)?.value, 2026);
  close(calculate("-5", true)?.value, -5);
  assert.equal(calculate("(42.5-39.8)*30")?.expression, "(42.5 − 39.8) × 30");
});

test("energy and rate conversions use the authority's factors", () => {
  const cases: Array<[string, number, string]> = [
    ["1 MWh to th", 34.12141633, "th"],
    ["100 GWh in therms", 3412141.633, "th"],
    ["1 TWh to MMBtu", 3412141.633, "MMBtu"],
    ["3.6 GJ to MWh", 1, "MWh"],
    ["1,000 kWh → MWh", 1, "MWh"],
    ["500 MW to GWh/d", 12, "GWh/d"],
    ["24 GWh/d in MW", 1000, "MW"],
    ["10 mcm/d to m3/h", 416666.6667, "m³/h"],
    ["100 兆瓦时 换算成 撒姆", 3412.141633, "th"],
  ];
  for (const [input, expected, unit] of cases) {
    const result = convertQuery(input, UNITS, FX);
    close(result?.value, expected, 3);
    assert.equal(result?.unit, unit, input);
    // The one line is the factor used: "1 GWh = 3,412.142 th".
    assert.deepEqual(result?.notes.map((note) => note.key), ["answer.convert.factor"], input);
    assert.equal(result?.notes[0].values.to, unit, input);
  }
});

test("conversions typed as people type them, Spotlight-style, with the factor shown", () => {
  const cases: Array<[string, number, string]> = [
    // A rate into a bare unit is the same rate in that unit (MMBtu/d).
    ["800 GWh/d in MMBtu", 800 * 1000 / UNITS.energy_in_mwh.MMBtu, "MMBtu/d"],
    ["800 gigawatt hours a day in mmbtu", 800 * 1000 / UNITS.energy_in_mwh.MMBtu, "MMBtu/d"],
    ["how many MMBtu is 800 GWh/d", 800 * 1000 / UNITS.energy_in_mwh.MMBtu, "MMBtu/d"],
    ["800 GWh/d = ? MMBtu", 800 * 1000 / UNITS.energy_in_mwh.MMBtu, "MMBtu/d"],
    ["800 GWh per day is how many MMBtu", 800 * 1000 / UNITS.energy_in_mwh.MMBtu, "MMBtu/d"],
    ["800 GWh/d is equivalent to what MMBtu", 800 * 1000 / UNITS.energy_in_mwh.MMBtu, "MMBtu/d"],
    ["800 GWh/d 等于多少 MMBtu", 800 * 1000 / UNITS.energy_in_mwh.MMBtu, "MMBtu/d"],
    ["800 GWh/d to MWh/h", 800 * 1000 / 24, "MW"],
    ["10 mcm to GWh with gcv 11.2", 112, "GWh"],
    ["1 bcm in TWh", 11, "TWh"],
    ["€40/MWh to p/th", 40 * 0.8356 * 100 * UNITS.energy_in_mwh.th, "p/th"],
    ["convert 12 $/MMBtu to €/MWh", (12 / UNITS.energy_in_mwh.MMBtu) / 1.0832, "EUR/MWh"],
  ];
  for (const [input, expected, unit] of cases) {
    const result = convertQuery(input, UNITS, FX);
    close(result?.value, expected, 3);
    assert.equal(result?.unit, unit, input);
    assert.ok(result?.notes.some((note) => note.key === "answer.convert.factor"), input);
  }
  const factor = convertQuery("800 GWh/d in MMBtu", UNITS, FX)?.notes.find((note) => note.key === "answer.convert.factor");
  assert.deepEqual(factor?.values, { from: "GWh/d", factor: "3,412.142", to: "MMBtu/d" });
  // An amount is not a rate, and power is not read as per hour of an amount.
  assert.equal(convertQuery("800 GWh in MMBtu/d", UNITS, FX), null);
  assert.equal(convertQuery("500 MW in GWh", UNITS, FX), null);
});

test("volume to energy states its calorific value: the typed one, or the assumption", () => {
  const assumed = convertQuery("10 mcm to GWh", UNITS, FX);
  close(assumed?.value, 110);
  assert.equal(assumed?.notes[0].key, "answer.convert.gcv_assumed");
  assert.equal(assumed?.notes[0].values.gcv, 11);
  assert.match(String(assumed?.notes[0].values.conditions), /25 °C.*0 °C.*101\.325 kPa/);
  const stated = convertQuery("10 mcm to GWh at 11.2", UNITS, FX);
  close(stated?.value, 112);
  assert.equal(stated?.notes[0].key, "answer.convert.gcv_stated");
  close(convertQuery("100 GWh/d to mcm/d @ 10.5 kWh/m3", UNITS, FX)?.value, 9.5238095, 5);
  const outside = convertQuery("10 mcm to GWh at 40", UNITS, FX);
  assert.equal(outside?.value, null);
  assert.equal(outside?.notes[0].key, "answer.convert.gcv_range");
});

test("price conversions name the ECB rate and its date, and refuse without one", () => {
  const toPence = convertQuery("40 EUR/MWh to p/th", UNITS, FX);
  // 40 €/MWh × 0.8356 = 33.424 £/MWh = 97.95 p/th.
  close(toPence?.value, 40 * 0.8356 * 100 * UNITS.energy_in_mwh.th, 6);
  assert.equal(toPence?.unit, "p/th");
  assert.deepEqual(toPence?.notes, [
    { key: "answer.convert.fx", values: { source: "ECB", date: "2026-11-13", pair: "EURGBP", rate: "0.8356" } },
    { key: "answer.convert.factor", values: { from: "EUR/MWh", factor: "2.4489", to: "p/th" } },
  ]);
  const usd = convertQuery("12 $/MMBtu in €/MWh", UNITS, FX);
  close(usd?.value, (12 / UNITS.energy_in_mwh.MMBtu) / 1.0832, 6);
  // Same currency: no FX line at all, only the factor.
  const sameCurrency = convertQuery("100 p/th to GBP/MWh", UNITS, FX);
  close(sameCurrency?.value, 1 / UNITS.energy_in_mwh.th, 6);
  assert.deepEqual(sameCurrency?.notes.map((note) => note.key), ["answer.convert.factor"]);
  const none = convertQuery("40 EUR/MWh to p/th", UNITS, { source: "ECB", rates: {} });
  assert.equal(none?.value, null);
  assert.equal(none?.notes[0].key, "answer.convert.no_fx");
  assert.equal(convertQuery("40 EUR/MWh to p/th", null, FX), null, "no answer before the factors load");
});

test("conversions: no answer for half a conversion or mixed dimensions", () => {
  for (const input of ["40 EUR/MWh", "100 GWh", "100 GWh to", "100 GWh to EUR/MWh", "500 MW to GWh", "TTF to NBP", "10 mcm to GWh at"]) {
    assert.equal(convertQuery(input, UNITS, FX), null, input);
  }
});

test("held ECB rates come from the price-conversion read, latest value date", () => {
  const held = fxHeldFrom({
    fx: { GBP: { rate: 0.8356, value_dates: ["2026-11-12", "2026-11-13"] } },
    fx_fixing: { source_system: "ECB" },
  });
  assert.deepEqual(held, { source: "ECB", rates: { GBP: { rate: 0.8356, date: "2026-11-13" } } });
  assert.deepEqual(fxHeldFrom(null).rates, {});
});

test("gas day follows the CAM rule: before 05:00 UTC in winter it is still yesterday", () => {
  const morning = new Date("2026-11-16T04:30:00Z");
  const noon = new Date("2026-11-16T12:00:00Z");
  assert.deepEqual(gasDayAnswer("gas day", morning), {
    kind: "gas-day", gasDay: "2026-11-15", startUtc: "2026-11-15T05:00:00.000Z", endUtc: "2026-11-16T05:00:00.000Z", offset: 0,
  });
  assert.equal((gasDayAnswer("gas day today", noon) as { gasDay: string }).gasDay, "2026-11-16");
  assert.equal((gasDayAnswer("D+2", noon) as { gasDay: string }).gasDay, "2026-11-18");
  assert.equal((gasDayAnswer("d-1", noon) as { gasDay: string }).gasDay, "2026-11-15");
  assert.equal((gasDayAnswer("今天的燃气日", noon) as { gasDay: string }).gasDay, "2026-11-16");
  // Summer: 04:00 UTC.
  assert.equal((gasDayAnswer("gas day", new Date("2026-07-01T04:30:00Z")) as { startUtc: string }).startUtc, "2026-07-01T04:00:00.000Z");
  assert.deepEqual(gasDayAnswer("days to 1 Jan", noon), { kind: "days-to", days: 46, target: "2027-01-01", from: "2026-11-16" });
  assert.equal((gasDayAnswer("距离1月1日还有几天", noon) as { days: number }).days, 46);
  assert.deepEqual(gasDayAnswer("front month", noon), { kind: "front-month", label: "Dec-26", start: "2026-12-01", end: "2026-12-31" });
  for (const input of ["gas", "days", "D+", "day ahead", "TTF DA", "days to never"]) assert.equal(gasDayAnswer(input, noon), null, input);
  assert.equal(parseDay("29 Feb", "2026-11-16"), null);
  assert.equal(parseDay("2027-03-01", "2026-11-16"), "2027-03-01");
});

const TERMS = [
  { term: "TTF", aliases: ["Title Transfer Facility"], category: "hub", definition_en: "Title Transfer Facility, the Dutch virtual hub. More text.", definition_zh_cn: "荷兰产权转让设施。更多。" },
  { term: "Hedge ratio", aliases: ["对冲比率"], category: "risk", definition_en: "Share of exposure hedged." },
  { term: "UMM", aliases: ["Urgent Market Message"], category: "regulation", definition_en: "A REMIT disclosure of an outage." },
];

test("definition questions in English and Chinese name their subject", () => {
  const cases: Array<[string, string | null]> = [
    ["what is TTF", "TTF"], ["What's the hedge ratio?", "hedge ratio"], ["define UMM", "UMM"],
    ["what does UMM stand for", "UMM"], ["TTF 是什么", "TTF"], ["什么是对冲比率？", "对冲比率"],
    ["TTF的定义", "TTF"], ["TTF", null], ["TTF Dec-26", null],
  ];
  for (const [input, expected] of cases) assert.equal(definitionSubject(input), expected, input);
  assert.equal(findTerm("ttf", TERMS)?.term, "TTF");
  assert.equal(findTerm("title transfer facility", TERMS)?.term, "TTF");
  assert.equal(findTerm("对冲比率", TERMS)?.term, "Hedge ratio");
  assert.equal(findTerm("hedge-ratio", TERMS)?.term, "Hedge ratio");
  assert.equal(findTerm("tt", TERMS), null);
  assert.equal(shortDefinition(TERMS[0].definition_en), "Title Transfer Facility, the Dutch virtual hub.");
  assert.equal(shortDefinition(TERMS[0].definition_zh_cn), "荷兰产权转让设施。");
});

test("answers are written as the desk writes them and copied as plain numbers", () => {
  assert.equal(formatAnswerNumber(81), "81");
  assert.equal(formatAnswerNumber(0.1 + 0.2), "0.3");
  assert.equal(formatAnswerNumber(3412141.6331279), "3,412,141.63");
  assert.equal(formatAnswerNumber(-2), "−2");
  assert.equal(formatAnswerNumber(97.951234), "97.951234");
  assert.equal(clipboardNumber(3412141.6331279), "3412141.63313");
  assert.equal(clipboardNumber(-2), "-2");
});
