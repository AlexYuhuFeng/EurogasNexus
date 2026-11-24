import assert from "node:assert/strict";
import test from "node:test";

import { readFileSync } from "node:fs";

import {
  formatMarksDay,
  formatMoney,
  formatPrice,
  formatQuantity,
  marksBehind,
  marksLine,
  nextMonth,
  splitList,
} from "../src/app/model/riskLimitsModel.ts";

const read = (path: string) => readFileSync(new URL(`../src/${path}`, import.meta.url), "utf8");

test("money uses desk shorthand and never prints a missing figure as zero", () => {
  assert.equal(formatMoney(12_500_000, "EUR"), "€12.50m");
  assert.equal(formatMoney(-45_000, "GBP"), "-£45k");
  assert.equal(formatMoney(950, "USD"), "$950");
  assert.equal(formatMoney(1200, "NOK"), "NOK 1,200");
  assert.equal(formatMoney(null, "EUR"), "-");
  assert.equal(formatQuantity(28_800), "28,800 MWh");
  assert.equal(formatQuantity(undefined), "-");
  assert.equal(formatPrice(33.1254, "EUR/MWh"), "33.125 EUR/MWh");
});

test("lists split on commas and spaces", () => {
  assert.deepEqual(splitList(" TTF, NBP;THE  "), ["TTF", "NBP", "THE"]);
  assert.deepEqual(splitList(""), []);
});

test("next month rolls the year in December", () => {
  assert.equal(nextMonth(new Date(Date.UTC(2026, 11, 15))), "2027-01");
  assert.equal(nextMonth(new Date(Date.UTC(2026, 9, 31))), "2026-11");
});


test("QA-R-07: a risk row says the day of its marks, and late or stale in words", () => {
  assert.equal(formatMarksDay("2026-11-18"), "18 Nov");
  assert.deepEqual(marksLine({ marks_as_of: "2026-11-23", state: "current" }), { key: "risk.marks.current", day: "23 Nov" });
  assert.deepEqual(marksLine({ marks_as_of: "2026-11-20", state: "late" }), { key: "risk.marks.late", day: "20 Nov" });
  assert.deepEqual(marksLine({ marks_as_of: "2026-11-18", state: "stale" }), { key: "risk.marks.stale", day: "18 Nov" });
  assert.deepEqual(marksLine({ marks_as_of: null, state: "never" }), { key: "risk.marks.never", day: null });
  // A mandate is not priced: no marks line.
  assert.equal(marksLine({ marks_as_of: null, state: "current" }), null);
  assert.equal(marksLine({}), null);
  assert.equal(marksBehind("late"), true);
  assert.equal(marksBehind("stale"), true);
  assert.equal(marksBehind("current"), false);
});

test("QA-R-07: the limits panel and the position page mark late rows with text, not colour alone", () => {
  const en = JSON.parse(read("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(read("i18n/zh.json")) as Record<string, string>;
  for (const key of ["risk.marks.current", "risk.marks.late", "risk.marks.stale", "risk.marks.never", "risk.marks.help", "risk.marks.column"]) {
    assert.ok(en[key], key);
    assert.ok(zh[key], key);
  }
  assert.match(en["risk.marks.late"], /late/);
  assert.match(en["risk.marks.stale"], /stale/);
  for (const page of ["components/RiskLimitsPanel.tsx", "components/PositionLadderPanel.tsx"]) {
    const source = read(page);
    assert.match(source, /<MarksAsOf /, page);
    assert.match(source, /marksRowAttributes\(row\)/, page);
  }
});
