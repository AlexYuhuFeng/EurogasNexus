/**
 * LNG-3 options panel, pure logic: the default first, then the frontier, the dominated options
 * with who beats them and where, then the infeasible ones; scenario ranges; when "Choose" may
 * be pressed. The figures are the worked example's (illustrative).
 */
import assert from "node:assert/strict";
import test from "node:test";

import type { DisruptionOptionDTO } from "../src/api/client.ts";
import {
  canChoose,
  kindOf,
  optionRows,
  scenarioRange,
  standingOf,
  statusKey,
  timelineLine,
} from "../src/app/model/disruptionOptionsModel.ts";

const option = (patch: Partial<DisruptionOptionDTO>): DisruptionOptionDTO => ({
  option_id: "o",
  key: "A:stay+absorb",
  kind: "wait",
  title: "ZEE-1: stay, absorb the delay",
  feasible: true,
  reasons: [],
  notes: [],
  on_frontier: false,
  dominated_by: null,
  dominated_why: [],
  objectives: { pnl_expected: 0, pnl_worst: 0, cost: 0, flexibility_mwh: 0, disrupted_mwh: 0 },
  score: 0,
  affects_other_supplies: [],
  interruptible_mwh: 0,
  releases: [],
  swaps: [],
  obligations: [],
  scenarios: [],
  hedge_legs: [],
  legs: [],
  ...patch,
});

const borrow = option({ option_id: "b", key: "A:stay+borrow", kind: "borrow", title: "borrow", on_frontier: true, score: -89_000 });
const swap = option({ option_id: "s", key: "A:swap:B+absorb", kind: "swap", title: "swap", on_frontier: true, score: -404_200 });
const absorb = option({ option_id: "a", key: "A:stay+absorb", kind: "wait", dominated_by: "b", dominated_why: ["higher expected P&L", "lower cost"], score: -348_000 });
const buy = option({ option_id: "u", key: "A:stay+buy", kind: "buy", dominated_by: "b", dominated_why: ["higher expected P&L"], score: -142_500 });
const iberia = option({ option_id: "c", key: "A:swap:C+absorb", kind: "swap", feasible: false, reasons: ["breaks the firm delivery to Cepsa"], score: -959_500 });

test("the default leads, then the frontier, the dominated by score, the infeasible last", () => {
  const rows = optionRows({ options: [iberia, absorb, swap, buy, borrow], recommended: "b" });
  assert.deepEqual(rows.map((row) => [row.option.option_id, row.standing]), [
    ["b", "recommended"],
    ["s", "frontier"],
    ["u", "dominated"],
    ["a", "dominated"],
    ["c", "infeasible"],
  ]);
  assert.deepEqual(rows[3].beatenBy, { title: "borrow", where: ["higher expected P&L", "lower cost"] });
  assert.equal(rows[0].beatenBy, null);
  assert.equal(rows[4].beatenBy, null);
});

test("standing and kind", () => {
  assert.equal(standingOf(iberia, "c"), "infeasible");
  assert.equal(standingOf(borrow, null), "frontier");
  assert.equal(kindOf(absorb), "wait");
  assert.equal(kindOf(option({ kind: "something_new" })), "other");
});

test("the scenario range spans base, early, late and the price shocks", () => {
  const ranged = option({
    scenarios: [
      { scenario_id: "base", label: "base", pnl: -20_000 },
      { scenario_id: "late", label: "late", pnl: -158_000 },
      { scenario_id: "prices_up", label: "up", pnl: -18_000 },
    ],
  });
  assert.deepEqual(scenarioRange(ranged), { low: -158_000, high: -18_000 });
  assert.equal(scenarioRange(option({})), null);
});

test("Choose needs a feasible option, the right to record, and no choice in flight", () => {
  assert.equal(canChoose(borrow, true, false), true);
  assert.equal(canChoose(iberia, true, false), false);
  assert.equal(canChoose(borrow, false, false), false);
  assert.equal(canChoose(borrow, true, true), false);
});

test("timeline and status keys", () => {
  assert.deepEqual(timelineLine({ change: "recommendation", notified: true }), {
    changeKey: "lng.cargo.options.change.recommendation",
    told: true,
  });
  assert.equal(timelineLine({ change: null, notified: false }).changeKey, "lng.cargo.options.change.none");
  assert.equal(statusKey("as_planned"), "lng.cargo.options.status.as_planned");
});
