import assert from "node:assert/strict";
import test from "node:test";

import {
  formatMoney,
  formatPrice,
  formatQuantity,
  nextMonth,
  splitList,
} from "../src/app/model/riskLimitsModel.ts";

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

