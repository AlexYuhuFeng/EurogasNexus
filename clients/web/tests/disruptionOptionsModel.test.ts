/**
 * LNG-3 and LNG-4 options panel, pure logic. LNG-3 reads (no ranks): the default first, then
 * the frontier, the dominated options with who beats them and where, then the infeasible ones.
 * LNG-4 reads: the server's rank among options that can happen, then those that cannot; the
 * flags, the recommended set and its reasons, the split into direct P&L and opportunity cost,
 * the consequences with their sources, the FX picker and the demurrage as the contract states
 * it. The figures are the worked example's (illustrative).
 */
import assert from "node:assert/strict";
import test from "node:test";

import type { DisruptionOptionDTO } from "../src/api/client.ts";
import {
  DEFAULT_FX,
  canChoose,
  consequences,
  costSplit,
  demurrageLine,
  flagsOf,
  fxQuery,
  kindOf,
  lineSources,
  linesByBasis,
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

// ------------------------------------------------------------------------------- LNG-4

const breach = {
  obligation_id: "cepsa",
  contract_id: "cepsa-huelva",
  counterparty: "Cepsa",
  point: "Huelva",
  text: "breaks the firm delivery to Cepsa at Huelva: 50,000 MWh short on 24 Jan (penalty not held)",
  shortfall_mwh: 50_000,
  days: [{ gas_day: "2027-01-24", mwh: 50_000 }],
  penalty_eur_mwh: null,
  penalty_held: false,
  penalty_terms: null,
  exposure_eur: null,
};
const rankedBorrow = option({ option_id: "b", key: "A:stay+borrow", kind: "borrow", title: "borrow", rank: 2, possible: true, on_frontier: true, score: -89_000 });
const rankedSwapB = option({ option_id: "s", key: "A:swap:B+absorb", kind: "swap", title: "swap B", rank: 1, possible: true, on_frontier: true, score: -60_000 });
const huelva = option({
  option_id: "c",
  key: "A:swap:C+absorb",
  kind: "swap",
  title: "swap C (Huelva)",
  rank: 3,
  possible: true,
  feasible: true,
  breaches: [breach],
  flags: { physically_possible: true, contract_breach: true, disrupts_normal_cargo: true },
  disrupts: [{ supply_id: "C", label: "IBE-3", mwh: 850_000, from: "Huelva", to: "Zeebrugge", cause: "swapped" }],
  score: -215_000,
});
const divert = option({
  option_id: "d",
  key: "A:divert:D",
  kind: "divert",
  title: "divert to D",
  rank: 4,
  possible: true,
  objectives: { pnl_expected: -362_400, pnl_worst: -432_400, cost: 247_000, flexibility_mwh: 0, disrupted_mwh: 0 },
  direct_pnl_expected: -187_000,
  opportunity_cost_expected: 175_400,
  opportunity: [
    { kind: "berth_delay", text: "GATE-1 waits 2 days at D", value_eur: -65_000, sources: ["demurrage: charter party GATE-1", "ECB 2027-01-19"] },
    { kind: "capacity_forgone", text: "slot capacity forgone at D", value_eur: -50_000, sources: ["lng.disruption.spare_slot_value"] },
  ],
  score: -362_400,
});
const notPossible = option({ option_id: "x", key: "A:divert:X", kind: "divert", title: "divert to X", rank: 5, possible: false, feasible: false, reasons: ["no berth"], score: -10 });

test("LNG-4: options that can happen by rank, then the ones that cannot, with flags and reasons", () => {
  const rows = optionRows({
    options: [notPossible, divert, huelva, rankedBorrow, rankedSwapB],
    recommended: "s",
    recommended_set: [
      { option_id: "b", key: "A:stay+borrow", title: "borrow", basis: "clean", reason: "breaks no contract and moves no cargo" },
      { option_id: "s", key: "A:swap:B+absorb", title: "swap B", basis: "best_expected", reason: "highest expected P&L without a breach" },
    ],
  });
  assert.deepEqual(rows.map((row) => [row.option.option_id, row.standing]), [
    ["s", "recommended"],
    ["b", "recommended"],
    ["c", "dominated"],
    ["d", "dominated"],
    ["x", "infeasible"],
  ]);
  assert.deepEqual(rows[1].recommended, [{ basis: "clean", reason: "breaks no contract and moves no cargo" }]);
  assert.deepEqual(rows[2].flags, ["contract_breach", "disrupts_normal_cargo"]);
  assert.deepEqual(rows[4].flags, ["not_possible"]);
  assert.equal(kindOf(option({ kind: "substitute" })), "substitute");
  assert.equal(kindOf(option({ kind: "spot" })), "spot");
});

test("LNG-4: flags read from the breaches when the flags block is absent", () => {
  assert.deepEqual(flagsOf({ feasible: true, breaches: [breach] }), ["contract_breach"]);
  assert.deepEqual(flagsOf({ feasible: true }), []);
});

test("LNG-4: a breach option can be chosen; one that cannot physically happen cannot", () => {
  assert.equal(canChoose(huelva, true, false), true);
  assert.equal(canChoose(notPossible, true, false), false);
});

test("LNG-4: the expected P&L is direct P&L less opportunity cost", () => {
  assert.deepEqual(costSplit(divert), { direct: -187_000, opportunity: 175_400, pnl: -362_400 });
  // An LNG-3 option with no split: all of it is direct.
  assert.deepEqual(costSplit(option({ objectives: { pnl_expected: -20, pnl_worst: 0, cost: 0, flexibility_mwh: 0, disrupted_mwh: 0 } })), {
    direct: -20,
    opportunity: 0,
    pnl: -20,
  });
});

test("LNG-4: the consequences name the contract, the cargo moved and the opportunity costs with sources", () => {
  const huelvaLines = consequences(huelva);
  assert.deepEqual(huelvaLines.map((line) => line.kind), ["breach", "moves"]);
  assert.match(huelvaLines[0].text, /Cepsa at Huelva: 50,000 MWh short on 24 Jan \(penalty not held\)/);
  assert.deepEqual(huelvaLines[0].sources, ["contract cepsa-huelva"]);
  assert.equal(huelvaLines[0].value, null);
  assert.equal(huelvaLines[1].text, "IBE-3 · 850,000 MWh · Huelva → Zeebrugge · swapped");
  const divertLines = consequences(divert);
  assert.deepEqual(divertLines.map((line) => [line.kind, line.value]), [
    ["opportunity", -65_000],
    ["opportunity", -50_000],
  ]);
  assert.deepEqual(divertLines[0].sources, ["demurrage: charter party GATE-1", "ECB 2027-01-19"]);
  const cover = consequences(option({ covers: [{ source_id: "hub:PEG:cepsa", obligation_id: "cepsa", mwh: 50_000, days: [] }] }));
  assert.equal(cover[0].text, "hub:PEG:cepsa: 50,000 MWh for cepsa");
});

test("LNG-4: each cost line lists its sources, and lines group by basis", () => {
  const lines = [
    { label: "gas", value: -100, text: "gas", sources: ["PEG 30.20 EUR/MWh (settlement 2027-01-19)", " "], basis: "direct" as const },
    { label: "tariff", value: -5, text: "tariff", sources: [], basis: "direct" as const },
    { label: "call", value: -65_000, text: "call", sources: ["charter party"], basis: "opportunity" as const },
  ];
  assert.equal(lineSources(lines[0]), "PEG 30.20 EUR/MWh (settlement 2027-01-19)");
  assert.equal(lineSources(lines[1]), null);
  const grouped = linesByBasis(lines);
  assert.deepEqual(grouped.direct.map((line) => line.label), ["gas", "tariff"]);
  assert.deepEqual(grouped.opportunity.map((line) => line.label), ["call"]);
});

test("LNG-4: the FX picker sends nothing by default and checks a rate entered by hand", () => {
  assert.deepEqual(fxQuery(DEFAULT_FX), { query: undefined, error: null });
  assert.deepEqual(fxQuery({ ...DEFAULT_FX, source: "WMR", rateDate: "2027-01-19", reporting: "GBP" }), {
    query: { fx_source: "WMR", fx_rate_date: "2027-01-19", reporting_currency: "GBP" },
    error: null,
  });
  assert.deepEqual(fxQuery({ ...DEFAULT_FX, source: "manual", rate: "1,08" }), {
    query: { fx_source: "manual", fx_rate: 1.08, fx_currency: "USD" },
    error: null,
  });
  for (const rate of ["", "0", "-1", "abc"]) {
    assert.deepEqual(fxQuery({ ...DEFAULT_FX, source: "manual", rate }), { query: undefined, error: "lng.cargo.options.fx.rate_invalid" });
  }
});

test("LNG-4: demurrage shows the contract's currency, the rate used, its source and date", () => {
  const line = demurrageLine({
    rate_per_day: 77_000,
    currency: "USD",
    source: "Confirmation Notice GATE-1",
    terms: "per day pro rata",
    laytime_hours: 36,
    laytime_source: "Confirmation Notice GATE-1",
    eur_per_day: 70_000,
    fx: { from: "USD", to: "EUR", rate: 1 / 1.1, source: "ECB", label: "ECB reference rate", rate_date: "2027-01-19", tried: [], simulated: false, entered_by_hand: false, missing: null },
    note: "",
    warning: null,
  });
  assert.equal(line.original, "77,000 USD/day");
  assert.equal(line.eurPerDay, 70_000);
  assert.equal(line.rate, "1 USD = 0.909091 EUR · ECB reference rate · 2027-01-19");
  assert.equal(line.source, "Confirmation Notice GATE-1");
  assert.deepEqual(demurrageLine(null), { original: null, eurPerDay: null, rate: null, source: null, warning: null });
});
