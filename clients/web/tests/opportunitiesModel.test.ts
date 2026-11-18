import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import type { OpportunityLegDTO, OpportunityListDTO, OpportunityRowDTO } from "../src/api/client.ts";
import { markRowsToCells, nextMonths } from "../src/app/model/firmMarksModel.ts";
import {
  bucketRows,
  bucketTotal,
  canOpenCase,
  emptyReason,
  formatMeasure,
  formatValue,
  hasAnyOpportunity,
  legFigure,
  opportunityFromLocation,
  qualityMarker,
  readinessLines,
  rowLead,
  showReadiness,
  timeLeft,
  withOpportunity,
} from "../src/app/model/opportunitiesModel.ts";

function row(overrides: Partial<OpportunityRowDTO> = {}): OpportunityRowDTO {
  return {
    opportunity_id: "opp_1",
    key: "k",
    type: "locational",
    type_code: "L",
    lane: "could_act",
    state: "actionable",
    claim: "TTF → THE · Jan-27 · 10,000 MWh/d",
    headline: { value: "0.23", unit: "EUR/MWh" },
    value: { amount: "71300", currency: "EUR" },
    volume: { value: "310000", unit: "MWh" },
    period: "Jan-27",
    quality: { class: "sourced", label: "sourced" },
    simulated: false,
    book_ids: ["B1"],
    expires_at_utc: "2026-11-27T12:00:00+00:00",
    deadline_utc: null,
    version: 1,
    first_seen_utc: "2026-11-18T08:00:00+00:00",
    last_evaluated_utc: "2026-11-18T09:42:00+00:00",
    reasons: [],
    blocked: null,
    rank: { position: 1, reason: "ranked 1st: EUR 71k, all inputs sourced, expires in 9 days" },
    user_state: null,
    ...overrides,
  };
}

const READY = {
  book: { ready: true, contracts: 4, approved_hedge_bands: 1, missing: null },
  prices: { ready: true, licensed_quote_sources: ["ICE"], settlement_sources: [], firm_marks: 0, missing: null },
  published_costs: { ready: true, transport_tariffs: 412, terminal_terms: 4, missing: null },
  assumptions: { ready: true, approved_versions: 1, missing: null },
  types_now: [],
};

function list(overrides: Partial<OpportunityListDTO> = {}): OpportunityListDTO {
  return {
    as_of_utc: "2026-11-18T09:42:00+00:00",
    evaluation: { evaluation_id: "e1", status: "ok", finished_at_utc: "2026-11-18T09:42:00+00:00", demo_desk: false, next: "on request" },
    lanes: {
      must_act: { total: 0, offset: 0, items: [], next_cursor: null },
      could_act: { total: 9, offset: 0, items: [row()], next_cursor: "c" },
    },
    groups: {},
    confirming: 0,
    hidden_by_you: 0,
    per_lane_shown: 7,
    simulated: false,
    banner: null,
    readiness: READY,
    ...overrides,
  };
}

test("figures keep their native unit: prices to three decimals, energy whole, money compact", () => {
  assert.equal(formatMeasure({ value: "0.23", unit: "EUR/MWh" }, { signed: true }), "+0.230 EUR/MWh");
  assert.equal(formatMeasure({ value: "-24000", unit: "MWh" }), "−24,000 MWh");
  assert.equal(formatMeasure({ value: "187200", unit: "MWh" }, { signed: true }), "187,200 MWh"); // a size, unsigned
  assert.equal(formatMeasure({ value: "0.002525", unit: "EUR/MWh" }), "0.0025 EUR/MWh");
  assert.equal(formatMeasure({ value: "-0.0001", unit: "EUR/MWh" }), "−0.0001 EUR/MWh");
  assert.equal(formatMeasure({ value: "-0.00001", unit: "MWh" }), "0 MWh"); // never "-0"
  assert.equal(formatMeasure({ value: null, unit: "EUR/MWh" }), "–"); // unknown is never zero
  assert.equal(formatValue({ amount: "71300", currency: "EUR" }), "EUR 71k");
  assert.equal(formatValue({ amount: "1250000", currency: "EUR" }), "EUR 1.25m");
  assert.equal(formatValue({ amount: "782.75", currency: "EUR" }), "EUR 783");
  assert.equal(formatValue({ amount: "-86000", currency: "GBP" }), "GBP −86k");
  assert.equal(formatValue(null), "–");
});

test("an arithmetic row shows its contribution, a term signed, the value as money", () => {
  const leg = (overrides: Partial<OpportunityLegDTO>): OpportunityLegDTO => ({
    kind: "term", label_key: "x", label: "x", quantity: null, rate: null, fx: null, contribution: null,
    subtotal: null, input_class: null, source_family: null, source_ref: "", as_of_utc: null, input_keys: [], note: "",
    ...overrides,
  });
  assert.equal(legFigure(leg({ contribution: { value: "40.565", unit: "EUR/MWh" } })), "+40.565 EUR/MWh");
  assert.equal(legFigure(leg({ contribution: { value: "-0.151484", unit: "EUR/MWh" } })), "−0.151 EUR/MWh");
  assert.equal(legFigure(leg({ kind: "subtotal", subtotal: { value: "0.487", unit: "EUR/MWh" } })), "0.487 EUR/MWh");
  assert.equal(legFigure(leg({ kind: "value", contribution: { value: "71300", unit: "EUR", currency: "EUR" } })), "EUR 71k");
});

test("the lanes come as the server ranked them; must act leads with a mark, could act with its rank", () => {
  const data = list();
  assert.deepEqual(bucketRows(data, "could_act").map((item) => item.opportunity_id), ["opp_1"]);
  assert.equal(bucketTotal(data, "could_act"), 9); // more than shown is counted, not dropped
  assert.equal(bucketTotal(data, "watching"), 0);
  assert.ok(hasAnyOpportunity(data));
  assert.equal(rowLead(row(), "could_act"), "1");
  assert.equal(rowLead(row({ lane: "must_act" }), "must_act"), "!");
  assert.equal(rowLead(row(), "watching"), "");
});

test("a simulated row is always marked; a weaker class than sourced is named", () => {
  assert.equal(qualityMarker(row()), null);
  assert.equal(qualityMarker(row({ simulated: true })), "simulated");
  assert.equal(qualityMarker(row({ quality: { class: "firm_mark", label: "firm's mark" } })), "firm_mark");
  assert.equal(qualityMarker(row({ quality: { class: "assumption", label: "assumption" } })), "assumption");
});

test("day one: the page says why it is empty and what it needs, each with its one fix", () => {
  const empty = list({
    as_of_utc: null,
    evaluation: null,
    lanes: {},
    readiness: {
      ...READY,
      book: { ready: false, contracts: 0, approved_hedge_bands: 0, missing: "no contracts in your books" },
      prices: { ready: false, licensed_quote_sources: [], settlement_sources: [], firm_marks: 0, missing: "x" },
    },
  });
  assert.equal(hasAnyOpportunity(empty), false);
  assert.equal(emptyReason(empty), "opportunities.empty.day_one");
  assert.ok(showReadiness(empty));
  const lines = readinessLines(empty.readiness);
  assert.deepEqual(lines.map((line) => [line.key, line.ready, line.fix]), [
    ["book", false, "add_contract"],
    ["prices", false, "enter_marks"],
    ["published_costs", true, null],
  ]);
  assert.deepEqual(lines[2].values, { tariffs: 412, terminals: 4 });
  // Everything present: "What it needs" is absent (H.1).
  assert.equal(showReadiness(list()), false);
  assert.equal(emptyReason(list({ lanes: {}, confirming: 2 })), "opportunities.empty.confirming");
  assert.equal(emptyReason(list({ lanes: {} })), "opportunities.empty.nothing");
});

test("one primary action, offered only where the server lists it", () => {
  const detail = { ...row(), object: null, snapshot: null, versions: [], case: null, ended_reason: null };
  assert.ok(canOpenCase({ ...detail, next_steps: ["open_as_case", "watch", "dismiss"] }));
  assert.equal(canOpenCase({ ...detail, state: "blocked", next_steps: ["watch", "dismiss"] }), false);
  assert.equal(canOpenCase(null), false);
});

test("time left reads in days or hours; a passed time says so", () => {
  const now = new Date("2026-11-18T12:00:00Z");
  assert.deepEqual(timeLeft("2026-11-27T12:00:00+00:00", now), { key: "opportunities.time.days", count: 9 });
  assert.deepEqual(timeLeft("2026-11-18T17:30:00+00:00", now), { key: "opportunities.time.hours", count: 5 });
  assert.deepEqual(timeLeft("2026-11-18T11:00:00+00:00", now), { key: "opportunities.time.passed", count: 0 });
  assert.equal(timeLeft(null, now), null);
});

test("the open opportunity rides in the address, other context kept", () => {
  assert.equal(opportunityFromLocation("?workspace=scenario&task=opportunities&opportunity=opp_1"), "opp_1");
  assert.equal(opportunityFromLocation("?opportunity=<script>"), null);
  assert.equal(withOpportunity("workspace=scenario&gasDay=2026-11-18", "opp_2"), "workspace=scenario&gasDay=2026-11-18&opportunity=opp_2");
  assert.equal(withOpportunity("workspace=scenario&opportunity=opp_2", null), "workspace=scenario");
});

test("the firm's marks grid: next months, native units, blanks skipped, a bad cell named", () => {
  assert.deepEqual(nextMonths(new Date("2026-11-18T00:00:00Z"), 3), ["2026-12", "2027-01", "2027-02"]);
  const months = ["2026-12", "2027-01"];
  const result = markRowsToCells(
    [
      { hub: "TTF", values: { "2026-12": "40,5", "2027-01": "" } },
      { hub: "NBP", values: { "2027-01": "98.2" } },
    ],
    months,
  );
  assert.deepEqual(result, {
    cells: [
      { hub: "TTF", period: "2026-12", value: 40.5, unit: "EUR/MWh" },
      { hub: "NBP", period: "2027-01", value: 98.2, unit: "GBp/th" },
    ],
  });
  assert.deepEqual(markRowsToCells([{ hub: "TTF", values: { "2026-12": "abc" } }], months), { error: "not_a_number", cell: "TTF 2026-12" });
  assert.deepEqual(markRowsToCells([{ hub: "TTF", values: {} }], months), { error: "empty", cell: "" });
  assert.deepEqual(markRowsToCells([{ hub: "TTF", values: {} }, { hub: "TTF", values: {} }], months), { error: "duplicate_hub", cell: "TTF" });
});

test("the page offers no order, nomination or instruction; one primary action", () => {
  const read = (name: string) => readFileSync(new URL(`../src/components/opportunities/${name}`, import.meta.url), "utf8");
  const sources = ["OpportunitiesPage.tsx", "OpportunityDetail.tsx", "FirmMarksGrid.tsx"].map(read).join("\n");
  assert.doesNotMatch(sources, /\b(placeOrder|submitOrder|nominate|execute|settle)\w*\(/i);
  assert.equal((read("OpportunityDetail.tsx").match(/variant="primary"/g) ?? []).length, 1);
  const en = JSON.parse(readFileSync(new URL("../src/i18n/en.json", import.meta.url), "utf8")) as Record<string, string>;
  const zh = JSON.parse(readFileSync(new URL("../src/i18n/zh.json", import.meta.url), "utf8")) as Record<string, string>;
  const keys = Object.keys(en).filter((key) => key.startsWith("opportunities."));
  assert.ok(keys.length > 80);
  for (const key of keys) {
    assert.ok(zh[key], `${key} has a Chinese string`);
    assert.doesNotMatch(en[key], /\b(buy now|sell now|place an order|execute|nominate)\b/i, key);
  }
  assert.ok(en["opportunities.purpose"].length <= 110); // H.1
});
