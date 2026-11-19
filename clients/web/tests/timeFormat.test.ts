import assert from "node:assert/strict";
import test from "node:test";

import { deskMonthsIn, formatDeliveryMonth } from "../src/app/time/timeFormat.ts";
import { ladderMonthLabel } from "../src/app/model/positionLadderModel.ts";
import { monthCode } from "../src/app/model/termStructureCompare.ts";

// A delivery month reads as the desk writes it ("Jan-27"), never as an ISO month (rule 17).

test("an ISO delivery month reads as the desk's product code", () => {
  assert.equal(formatDeliveryMonth("2027-01"), "Jan-27");
  assert.equal(formatDeliveryMonth("2027-09-15"), "Sep-27");
  assert.equal(formatDeliveryMonth("Q1-27"), "Q1-27");
  assert.equal(formatDeliveryMonth("2027-13"), "2027-13");
  assert.equal(formatDeliveryMonth(null), "");
});

test("months inside a text are rewritten, full dates are left alone", () => {
  assert.equal(deskMonthsIn("TTF 2027-01"), "TTF Jan-27");
  assert.equal(deskMonthsIn("NBP 2026-12 and 2027-03"), "NBP Dec-26 and Mar-27");
  assert.equal(deskMonthsIn("gas day 2026-11-18"), "gas day 2026-11-18");
});

test("the older month helpers say the same as the shared one", () => {
  for (const month of ["2026-12", "2027-01", "2027-09"]) {
    assert.equal(ladderMonthLabel(month), formatDeliveryMonth(month));
    assert.equal(monthCode(month), formatDeliveryMonth(month));
  }
  assert.equal(monthCode("Cal-27"), null);
});
