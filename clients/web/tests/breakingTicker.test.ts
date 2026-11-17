/**
 * The situational strip (role-first redesign §5): the model's qualification per audience, the
 * ranking, the urgent window, hide and reappear, link targets, rejection of unsourced items, and
 * the component's four states.
 */
import assert from "node:assert/strict";
import test, { after } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "node:fs";

import type {
  CurrentUserDTO,
  DecisionCaseSummaryDTO,
  DeskTodayDTO,
  MonitoringAlertDTO,
  NominationWindowOccurrenceDTO,
  ScreenOrderObservationDTO,
} from "../src/api/client.ts";
import {
  BREAKING_WINDOW_MS,
  DEFAULT_STRIP_THRESHOLDS,
  STRIP_LIST_LIMIT,
  buildSituation,
  canAcknowledgeAlerts,
  hideKey,
  pruneHidden,
  qualifyingItems,
  rankItems,
  targetSearch,
  todayFacts,
  zoneHubs,
  type Situation,
  type SituationContext,
  type SituationInputs,
  type SituationItem,
  type StripSource,
  type TickerOutage,
} from "../src/app/model/tickerItems.ts";
import type { StripAudience } from "../src/app/experience/roleComposition.ts";
import { hiddenFrom, serializeHidden, stripThresholdsFrom } from "../src/app/preferences/stripPreferences.ts";
import { closeApiStoreHarness, loadApiStore } from "./support/apiStoreHarness.ts";

after(closeApiStoreHarness);

const NOW = Date.parse("2026-11-17T10:00:00Z");
const hoursAgo = (hours: number) => new Date(NOW - hours * 3600_000).toISOString();
const inMinutes = (minutes: number) => new Date(NOW + minutes * 60_000).toISOString();

const t = (key: string, options?: Record<string, unknown>) =>
  options ? `${key}:${Object.entries(options).map(([k, v]) => `${k}=${v}`).join("|")}` : key;

function outage(id: string, overrides: Partial<TickerOutage> = {}): TickerOutage {
  // The demo's big unplanned outage: 52 of 70 mcm/d out, 563 GWh/d, in the NBP zone.
  return {
    event_id: id, facility_name: `Asset ${id}`, balancing_zone: "NBP", event_type: "unplanned",
    status: "active", start_utc: hoursAgo(3), published_at_utc: hoursAgo(3), version: 1, unit: "mcm/d",
    unavailable_capacity: 52, technical_capacity: 70, unavailable_gwh_d: 563.2, source_system: "REMIT",
    source_reference: `remit:${id}:v1`, ...overrides,
  };
}

function alert(id: string, category: string, alertType: string, severity: MonitoringAlertDTO["severity"], evidence: Record<string, unknown> = {}, overrides: Partial<MonitoringAlertDTO> = {}): MonitoringAlertDTO {
  return {
    alert_id: id, fingerprint: id, category, alert_type: alertType, severity, status: "open",
    title_en: `Alert ${id}`, title_zh_cn: `告警 ${id}`, message_en: "", message_zh_cn: "",
    entity_type: alertType, entity_id: String(evidence.entity_id ?? id), event_time_utc: hoursAgo(1),
    detected_at_utc: hoursAgo(1), updated_at_utc: hoursAgo(1), acknowledged_at_utc: null, resolved_at_utc: null,
    occurrence_count: 1, evidence_snapshot: evidence, source_refs: [`${category}:${id}`], warnings: [],
    llm_provider_id: "", llm_status: "", llm_summary_en: null, llm_summary_zh_cn: null, llm_last_attempt_at_utc: null,
    simulated: false, human_review_required: true, ...overrides,
  };
}

const creditBreach = (books: string[], extra: Partial<MonitoringAlertDTO> = {}) =>
  alert("c1", "limits", "credit", "critical", { counterparty: "Rhinmark", counterparty_id: "CP-1", status: "breach", utilisation_pct: 112, book_ids: books }, extra);
const mandateBreach = (trader: string) =>
  alert("m1", "limits", "mandate", "critical", { name: "NBP desk", trader, mandate_id: "M-1", status: "breach", utilisation_pct: 130, book_ids: ["UK"] });
const ingestion = alert("s1", "data_source", "ingestion_failed", "critical", { entity_id: "GIE AGSI" });

function inputs(overrides: Partial<SituationInputs> = {}): SituationInputs {
  return {
    alerts: [], outages: [], cases: [], windows: [], bookedTrades: [], sources: [],
    today: { bookHubs: ["NBP"], limitCounts: { breach: 1, watch: 2 }, dayPnl: { value: 12_400, unit: "GBP" }, simulated: true },
    ...overrides,
  };
}

function context(audience: StripAudience, overrides: Partial<SituationContext> = {}, person: Partial<SituationContext["person"]> = {}): SituationContext {
  return {
    audience,
    person: { name: "demo.trader", principalId: "p-trader", permissions: ["market.read", "portfolio.read", "scenario.create", "review.read"], dataScopes: [], ...person },
    thresholds: DEFAULT_STRIP_THRESHOLDS, contextHub: null, nowMs: NOW, hidden: new Set(), ...overrides,
  };
}

const ids = (situation: Situation) => situation.items.map((item) => item.id);

/* ------------------------------------------------------------------ trader */

test("trader: a large unplanned outage where the book holds a position is urgent; planned, small and elsewhere are not", () => {
  const situation = buildSituation(
    inputs({
      outages: [
        outage("big"),
        outage("planned", { event_type: "planned" }),
        outage("small", { unavailable_capacity: 5, unavailable_gwh_d: 54, technical_capacity: 70 }),
        outage("tiny", { unavailable_capacity: 2, unavailable_gwh_d: 21, technical_capacity: 70 }),
        outage("elsewhere", { balancing_zone: "PSV" }),
        outage("scheduled", { status: "scheduled" }),
      ],
    }),
    context("trader"),
  );
  assert.equal(situation.state, "urgent");
  // 54 GWh/d passes the 50 GWh/d rule even at 7 % of the asset; 21 GWh/d at 3 % does not.
  assert.deepEqual(ids(situation), ["outage:big", "outage:small"]);
  const [big] = situation.items;
  assert.equal(big.severity, "critical");
  assert.equal(big.audience, "outage_position");
  assert.equal(big.magnitude, 563.2);
  assert.equal(big.unit, "GWh/d");
  assert.deepEqual(big.comparison, { key: "strip.comparison.of_capacity", values: { value: 563, total: 758, unit: "GWh/d" } });
  assert.equal(big.source.name, "REMIT");
});

test("trader: a focus hub counts as much as a position; without either the zone is out", () => {
  const ttf = outage("ttf", { balancing_zone: "21YNL----TTF---1" });
  assert.deepEqual(ids(buildSituation(inputs({ outages: [ttf] }), context("trader"))), []);
  const focused = buildSituation(inputs({ outages: [ttf] }), context("trader", { thresholds: { ...DEFAULT_STRIP_THRESHOLDS, focusHubs: ["TTF"] } }));
  assert.deepEqual(ids(focused), ["outage:ttf"]);
  assert.equal(focused.items[0].audience, "outage_focus_hub");
  // The context hub is a focus hub while none is chosen.
  assert.deepEqual(ids(buildSituation(inputs({ outages: [ttf] }), context("trader", { contextHub: "TTF" }))), ["outage:ttf"]);
  // Norway lands into four hubs, NBP among them.
  assert.deepEqual(zoneHubs("NO"), ["NBP", "TTF", "THE", "ZTP"]);
  assert.deepEqual(zoneHubs("GASPOOL"), ["THE"]);
});

test("WP-06: changing a threshold changes which fixture outage qualifies", () => {
  // 30 GWh/d, 20 % of the asset: below both defaults (50 GWh/d, 50 %).
  const medium = outage("medium", { unavailable_capacity: 14, technical_capacity: 70, unavailable_gwh_d: 30 });
  const at = (effective: Record<string, string>) =>
    ids(buildSituation(inputs({ outages: [medium] }), context("trader", { thresholds: stripThresholdsFrom(effective) })));
  assert.deepEqual(at({}), []);
  assert.deepEqual(at({ strip_outage_gwh_d: "25" }), ["outage:medium"]);
  assert.deepEqual(at({ strip_outage_share_pct: "25" }), []);
  assert.deepEqual(at({ strip_outage_gwh_d: "100", strip_outage_share_pct: "25" }), []);
  // The big one (563 GWh/d, 74 %) stops counting only when both thresholds are above it.
  const big = outage("big");
  const bigAt = (effective: Record<string, string>) =>
    ids(buildSituation(inputs({ outages: [big] }), context("trader", { thresholds: stripThresholdsFrom(effective) })));
  assert.deepEqual(bigAt({ strip_outage_gwh_d: "500" }), ["outage:big"]);
  assert.deepEqual(bigAt({ strip_outage_gwh_d: "500", strip_outage_share_pct: "75" }), ["outage:big"]);
  const shareOnly = outage("share", { unavailable_gwh_d: null, unavailable_capacity: 40, technical_capacity: 70 });
  const shareAt = (effective: Record<string, string>) =>
    ids(buildSituation(inputs({ outages: [shareOnly] }), context("trader", { thresholds: stripThresholdsFrom(effective) })));
  assert.deepEqual(shareAt({}), ["outage:share"]);
  assert.deepEqual(shareAt({ strip_outage_share_pct: "75" }), []);
  assert.deepEqual(stripThresholdsFrom({ strip_focus_hubs: "NBP,XYZ,TTF", strip_quiet_line: "off" }).focusHubs, ["NBP", "TTF"]);
  assert.equal(stripThresholdsFrom({ strip_quiet_line: "off" }).showQuietLine, false);
});

test("trader: pipeline state never reaches the strip; the trader's own mandate and lines they trade against do", () => {
  const situation = buildSituation(
    inputs({ alerts: [ingestion, mandateBreach("demo.trader"), mandateBreach("someone.else"), creditBreach(["UK"])] }),
    context("trader", {}, { dataScopes: ["BOOKS:UK"] }),
  );
  assert.ok(!situation.items.some((item) => item.kind === "source"));
  assert.deepEqual(situation.items.map((item) => item.audience).sort(), ["credit_line", "own_mandate"]);
  // A line behind books the trader does not hold is not theirs.
  const other = buildSituation(inputs({ alerts: [creditBreach(["NL"])] }), context("trader", {}, { dataScopes: ["BOOKS:UK"] }));
  assert.deepEqual(ids(other), []);
});

test("trader quiet line: booked today from the ETRM import, read-only; a count when no booking time is held; else the next window", () => {
  const trade = (id: string, observed: string, start = "2026-12-01T06:00:00Z"): ScreenOrderObservationDTO =>
    ({ order_observation_id: id, source_system: "ETRM", observed_at_utc: observed, delivery_start_utc: start }) as ScreenOrderObservationDTO;
  const window = { window_id: "w1", name: "NBP D-1", closes_at_utc: inMinutes(180) } as NominationWindowOccurrenceDTO;
  const timed = buildSituation(inputs({ bookedTrades: [trade("a", hoursAgo(1)), trade("b", hoursAgo(2)), trade("old", "2026-11-10T09:00:00Z")], windows: [window] }), context("trader"));
  assert.equal(timed.state, "quiet");
  assert.deepEqual(timed.quiet?.phrase, { key: "strip.quiet.booked_today", values: { count: 2 } });
  assert.equal(timed.quiet?.source, "ETRM");
  const untimed = buildSituation(inputs({ bookedTrades: [trade("a", "2026-12-01T06:00:00Z")] }), context("trader"));
  assert.deepEqual(untimed.quiet?.phrase, { key: "strip.quiet.booked_count", values: { count: 1 } });
  // Nothing booked today: the next window, else the plain fact that none was booked today.
  const oldOnly = [trade("old", "2026-11-10T09:00:00Z")];
  assert.equal(buildSituation(inputs({ bookedTrades: oldOnly, windows: [window] }), context("trader")).quiet?.phrase.key, "strip.quiet.next_window");
  assert.deepEqual(buildSituation(inputs({ bookedTrades: oldOnly, windows: [] }), context("trader")).quiet?.phrase, { key: "strip.quiet.booked_today", values: { count: 0 } });
  const none = buildSituation(inputs({ windows: [window] }), context("trader"));
  assert.equal(none.quiet?.phrase.key, "strip.quiet.next_window");
  // The trader opens the planning task; nothing nominates.
  assert.deepEqual(none.quiet?.target, { page: "scenario", task: "nomination" });
  // Switched off: nothing urgent and no quiet line is zero height.
  const off = buildSituation(inputs({ windows: [window] }), context("trader", { thresholds: { ...DEFAULT_STRIP_THRESHOLDS, showQuietLine: false } }));
  assert.equal(off.state, "hidden");
});

/* ------------------------------------------------------------------ other audiences */

test("finance has no strip; compliance has a quiet count; the platform audience sees source attention", () => {
  const everything = inputs({ outages: [outage("big")], alerts: [creditBreach(["UK"]), ingestion] });
  assert.equal(buildSituation(everything, context("finance")).state, "hidden");
  const compliance = buildSituation(
    inputs({ cases: [{ case_id: "k1", objective: "x", status: "DECIDED", last_record: { outcome: "ACCEPT", actor: "r", recorded_at_utc: hoursAgo(30) } } as DecisionCaseSummaryDTO] }),
    context("compliance"),
  );
  assert.equal(compliance.state, "quiet");
  assert.deepEqual(compliance.quiet?.phrase, { key: "strip.quiet.decided_week", values: { count: 1 } });

  const failing: StripSource = { source_id: "gie", source_system: "GIE AGSI", attention: true, statusKey: "connectors.status.failing", last_failure_at_utc: hoursAgo(1) };
  const held: StripSource = { source_id: "entsog", source_system: "ENTSOG", attention: true, statusKey: "connectors.status.not_approved", last_failure_at_utc: null };
  const platform = buildSituation(inputs({ alerts: [ingestion], sources: [failing, held] }), context("platform"));
  // The data-source alert for the same source is not a second line.
  assert.deepEqual(ids(platform), ["source:gie"]);
  assert.deepEqual(platform.items[0].target, { page: "sources", params: { view: "attention", source: "gie" } });
  // Held back by the approval gate: news when a run was last refused, standing otherwise.
  const refused = { ...held, last_failure_at_utc: hoursAgo(2) };
  const heldNow = buildSituation(inputs({ sources: [refused] }), context("platform"));
  assert.deepEqual(ids(heldNow), ["source:entsog"]);
  assert.equal(heldNow.items[0].headline.key, "strip.headline.source_held_back");
  const standing = buildSituation(inputs({ sources: [held] }), context("platform"));
  assert.deepEqual(standing.quiet?.phrase, { key: "strip.quiet.sources_attention", values: { count: 1 } });
  // An operator who reads alerts but has no source list still hears the ingestion failure.
  assert.deepEqual(ids(buildSituation(inputs({ alerts: [ingestion], sources: null }), context("platform"))), ["alert:s1"]);
  for (const audience of ["trader", "risk", "analyst", "desk_head", "operations", "originator"] as const) {
    assert.ok(!qualifyingItems(inputs({ alerts: [ingestion], sources: [failing] }), context(audience)).items.length, audience);
  }
});

test("risk: every breach, a new credit watch and an overdue case; quiet counts otherwise", () => {
  const watch = alert("w1", "limits", "credit", "warning", { counterparty: "Nordvik", counterparty_id: "CP-2", status: "watch", utilisation_pct: 86, book_ids: ["NL"] });
  const overdue = { case_id: "k1", objective: "Buy Q1 TTF", status: "OPEN", decision_due_at_utc: hoursAgo(1), last_record: null, record_count: 0 } as unknown as DecisionCaseSummaryDTO;
  const risk = context("risk", {}, { name: "demo.risk", permissions: ["portfolio.read", "review.read", "review.record"] });
  const situation = buildSituation(inputs({ alerts: [creditBreach(["NL"]), mandateBreach("demo.trader"), watch], cases: [overdue] }), risk);
  assert.deepEqual(situation.items.map((item) => item.audience).sort(), ["case_overdue", "credit_watch", "limit_breach", "limit_breach"]);
  const quiet = buildSituation(inputs({ cases: [overdue] }), { ...risk, nowMs: NOW + BREAKING_WINDOW_MS + 3600_000 });
  assert.deepEqual(quiet.quiet?.phrase, { key: "strip.quiet.risk_counts", values: { breach: 1, watch: 2, waiting: 1 } });
});

test("originator: a decision on their own case; desk head: a case past half its time and the day's P&L", () => {
  const mine = { case_id: "k1", objective: "LNG cargo bid", status: "DECIDED", created_by: "demo.originator", created_at_utc: hoursAgo(20), record_count: 1, last_record: { outcome: "rejected", actor: "demo.risk", recorded_at_utc: hoursAgo(1) } } as unknown as DecisionCaseSummaryDTO;
  const theirs = { ...mine, case_id: "k2", created_by: "someone" };
  const originator = buildSituation(inputs({ cases: [mine, theirs] }), context("originator", {}, { name: "demo.originator" }));
  assert.deepEqual(ids(originator), ["case:k1"]);
  assert.equal(originator.items[0].headline.key, "strip.headline.case_decided.reject");
  assert.deepEqual(originator.items[0].target, { page: "scenario", task: "review", params: { case: "k1" } });

  const waiting = { case_id: "k3", objective: "Storage plan", status: "UNDER_REVIEW", created_at_utc: hoursAgo(5), decision_due_at_utc: inMinutes(60), record_count: 0, last_record: null } as unknown as DecisionCaseSummaryDTO;
  const early = { ...waiting, case_id: "k4", created_at_utc: hoursAgo(1), decision_due_at_utc: inMinutes(600) };
  const head = buildSituation(inputs({ cases: [waiting, early], outages: [outage("big")], alerts: [creditBreach(["UK"])] }), context("desk_head"));
  assert.deepEqual(head.items.map((item) => item.audience).sort(), ["case_half_time", "limit_breach", "outage_book"]);
  const calm = buildSituation(inputs(), context("desk_head"));
  assert.deepEqual(calm.quiet?.phrase, { key: "strip.quiet.desk_head", values: { pnl: "+12,400 GBP", breach: 1 } });
});

test("operations: a window closing within the hour is information, then the next window is the quiet line", () => {
  const soon = { window_id: "w1", name: "NBP within-day", closes_at_utc: inMinutes(30), source_system: "demo" } as NominationWindowOccurrenceDTO;
  const later = { window_id: "w2", name: "TTF D-1", closes_at_utc: inMinutes(300) } as NominationWindowOccurrenceDTO;
  const ops = context("operations", {}, { permissions: ["market.read", "portfolio.read"] });
  const situation = buildSituation(inputs({ windows: [soon, later] }), ops);
  assert.deepEqual(ids(situation), ["window:w1"]);
  assert.equal(situation.items[0].severity, "info");
  // A read-only role reads the deadlines on Delivery; nothing nominates.
  assert.deepEqual(situation.items[0].target, { page: "contracts", task: "delivery" });
  const quiet = buildSituation(inputs({ windows: [later] }), ops);
  assert.equal(quiet.quiet?.phrase.key, "strip.quiet.next_window");
  assert.equal(quiet.quiet?.phrase.values.window, "TTF D-1");
  // An outage in a zone where the book delivers.
  assert.deepEqual(ids(buildSituation(inputs({ outages: [outage("big")] }), ops)), ["outage:big"]);
});

test("analyst: a large unplanned outage anywhere in north-west Europe and shadow-strategy alerts", () => {
  const strategy = alert("st1", "strategy", "drift", "warning", { entity_id: "run-7" });
  const situation = buildSituation(inputs({ outages: [outage("ttf", { balancing_zone: "NL" }), outage("it", { balancing_zone: "IT" })], alerts: [strategy] }), context("analyst"));
  assert.deepEqual(ids(situation), ["outage:ttf", "alert:st1"]);
  assert.deepEqual(situation.items[1].target, { page: "strategy", task: "shadow" });
});

/* ------------------------------------------------------------------ rows waiting on a backend */

test("rows that wait on a backend signal: price move (G3), delivery shortfall (G5), fundamentals surprise", () => {
  const price = buildSituation(
    inputs({ priceMoves: [
      { hub: "NBP", product: "DA", move_pct: -6.2, price: 82.1, unit: "p/th", at_utc: hoursAgo(1), source: "ICE Endex (customer licence)", simulated: false },
      { hub: "NBP", product: "FM", move_pct: 2.1, price: 84, unit: "p/th", at_utc: hoursAgo(1), source: "ICE Endex", simulated: false },
      { hub: "PSV", product: "DA", move_pct: 9, price: 40, unit: "EUR/MWh", at_utc: hoursAgo(1), source: "EEX", simulated: false },
    ] }),
    context("trader"),
  );
  assert.deepEqual(ids(price), ["price:NBP:DA"]);
  const tighter = buildSituation(inputs({ priceMoves: [{ hub: "NBP", product: "FM", move_pct: 2.1, price: 84, unit: "p/th", at_utc: hoursAgo(1), source: "ICE Endex", simulated: true }] }), context("trader", { thresholds: stripThresholdsFrom({ strip_price_move_pct: "2" }) }));
  assert.deepEqual(ids(tighter), ["price:NBP:FM"]);
  assert.equal(tighter.items[0].simulated, true);

  const shortfall = buildSituation(
    inputs({ shortfalls: [
      { contract_id: "C1", contract_name: "Haldor supply", gas_day: "2026-11-17", shortfall_mwh: 1200, tolerance_pct: 2, shortfall_pct: 5, at_utc: hoursAgo(1), source: "TSO allocation", book_ids: ["UK"] },
      { contract_id: "C2", contract_name: "Within tolerance", gas_day: "2026-11-17", shortfall_mwh: 100, tolerance_pct: 2, shortfall_pct: 1, at_utc: hoursAgo(1), source: "TSO allocation", book_ids: ["UK"] },
    ] }),
    context("operations"),
  );
  assert.deepEqual(ids(shortfall), ["shortfall:C1:2026-11-17"]);
  assert.deepEqual(shortfall.items[0].target, { page: "contracts", task: "delivery", params: { contract: "C1" } });

  const surprise = buildSituation(inputs({ fundamentals: [{ series: "storage_change", value: -2.1, unit: "TWh", deviation_pct: 40, hub: null, at_utc: hoursAgo(1), source: "GIE AGSI+" }] }), context("analyst"));
  assert.deepEqual(ids(surprise), ["fundamentals:storage_change"]);
});

/* ------------------------------------------------------------------ the rules of §5.3 and §5.5 */

test("ranking: severity, then own book, then size against the threshold, then newest; at most seven, the rest counted", () => {
  const item = (id: string, severity: SituationItem["severity"], ownBook: boolean, ratio: number, hours: number) =>
    ({ id, severity, ownBook, ratio, occurredAt: hoursAgo(hours) }) as SituationItem;
  const ranked = rankItems([
    item("warning-own", "warning", true, 1, 1),
    item("critical-other", "critical", false, 5, 1),
    item("critical-own-small", "critical", true, 1.2, 1),
    item("critical-own-big", "critical", true, 4, 2),
    item("critical-own-big-newer", "critical", true, 4, 1),
  ]);
  assert.deepEqual(ranked.map((row) => row.id), ["critical-own-big-newer", "critical-own-big", "critical-own-small", "critical-other", "warning-own"]);

  const many = Array.from({ length: 10 }, (_, n) => outage(`o${n}`, { unavailable_gwh_d: 100 + n }));
  const situation = buildSituation(inputs({ outages: many }), context("trader"));
  assert.equal(situation.items.length, STRIP_LIST_LIMIT);
  assert.equal(situation.more, 3);
});

test("urgent for six hours after it became true or materially changed; then standing (bell only)", () => {
  const old = outage("old", { start_utc: hoursAgo(7), published_at_utc: hoursAgo(7) });
  assert.deepEqual(ids(buildSituation(inputs({ outages: [old] }), context("trader"))), []);
  // A new version of the message (a revision) is a material change: urgent again.
  const revised = { ...old, published_at_utc: hoursAgo(1), version: 2 };
  assert.deepEqual(ids(buildSituation(inputs({ outages: [revised] }), context("trader"))), ["outage:old"]);
  // A standing breach is not news either.
  const standing = creditBreach(["UK"], { detected_at_utc: hoursAgo(30) });
  assert.deepEqual(ids(buildSituation(inputs({ alerts: [standing] }), context("risk"))), []);
});

test("hide: the item leaves this person's strip and comes back when its size or status changes", () => {
  const big = outage("big");
  const first = buildSituation(inputs({ outages: [big] }), context("trader"));
  const hidden = new Set([hideKey(first.items[0])]);
  assert.deepEqual(ids(buildSituation(inputs({ outages: [big] }), context("trader", { hidden }))), []);
  const larger = { ...big, unavailable_capacity: 60, unavailable_gwh_d: 650, version: 2 };
  assert.deepEqual(ids(buildSituation(inputs({ outages: [larger] }), context("trader", { hidden }))), ["outage:big"]);
  // The stored list keeps only entries that still name a current item.
  assert.deepEqual(pruneHidden([...hidden, "outage:gone@active|1|1"], first.items), [...hidden]);
  // The stored form follows the server's pattern, newline separated and bounded.
  assert.equal(serializeHidden([...hidden, "not an entry", ...hidden]), [...hidden][0]);
  assert.deepEqual(hiddenFrom({ strip_hidden: `${[...hidden][0]}\nbad entry` }), [...hidden]);
  assert.equal(serializeHidden(Array.from({ length: 50 }, (_, n) => `outage:e${n}@a`)).split("\n").length, 40);
});

test("links open the object where the job continues", () => {
  const trader = buildSituation(inputs({ outages: [outage("demo-umm-1")], alerts: [mandateBreach("demo.trader")] }), context("trader"));
  const outageItem = trader.items.find((item) => item.kind === "outage")!;
  assert.equal(targetSearch(outageItem.target), "workspace=market&task=network&outage=demo-umm-1");
  const limit = trader.items.find((item) => item.kind === "limit")!;
  assert.equal(targetSearch(limit.target), "workspace=contracts&task=exposure");
  assert.deepEqual(limit.explain, { subject: "mandate", id: "M-1" });
  assert.deepEqual(outageItem.report, { kind: "outage", id: "demo-umm-1" });
});

test("an item without a named source is rejected; a simulated figure carries its mark", () => {
  const unsourced = creditBreach(["UK"], { source_refs: [] });
  const situation = buildSituation(inputs({ alerts: [unsourced] }), context("risk"));
  assert.deepEqual(ids(situation), []);
  assert.equal(situation.rejected, 1);
  const demo = buildSituation(inputs({ outages: [outage("demo", { source_reference: "demo:umm" })] }), context("trader"));
  assert.equal(demo.items[0].simulated, true);
  assert.equal(buildSituation(inputs({ outages: [outage("real")] }), context("trader")).items[0].simulated, false);
  const simulatedLimit = buildSituation(inputs({ alerts: [creditBreach(["UK"], { simulated: true })] }), context("risk"));
  assert.equal(simulatedLimit.items[0].simulated, true);
});

test("book-scoped items are dropped without the book (alert_scope.py) or without portfolio.read", () => {
  const scoped = { dataScopes: ["BOOKS:UK"], name: "demo.risk" };
  // Behind two books, one not held: the person cannot see every book behind it.
  assert.deepEqual(ids(buildSituation(inputs({ alerts: [creditBreach(["UK", "NL"])] }), context("risk", {}, scoped))), []);
  assert.deepEqual(ids(buildSituation(inputs({ alerts: [creditBreach(["UK"])] }), context("risk", {}, scoped))), ["credit:CP-1"]);
  // A firm-level line (no books) under isolation is head-office only.
  assert.deepEqual(ids(buildSituation(inputs({ alerts: [creditBreach([])] }), context("risk", {}, scoped))), []);
  assert.deepEqual(ids(buildSituation(inputs({ alerts: [creditBreach([])] }), context("risk", {}, { dataScopes: ["BOOKS:*"] }))), ["credit:CP-1"]);
  assert.deepEqual(ids(buildSituation(inputs({ alerts: [creditBreach(["UK"])] }), context("risk", {}, { permissions: ["market.read"] }))), []);
});

test("acknowledge is offered only with the governed permission (ANALYST floor, commercial role); D5 changes nothing", () => {
  const person = (roles: string[], commercial = true) => ({ role: roles[0], roles, experience: { commercial_capabilities: commercial ? ["market.read"] : [] } }) as unknown as CurrentUserDTO;
  assert.equal(canAcknowledgeAlerts(person(["ANALYST"])), true);
  assert.equal(canAcknowledgeAlerts(person(["OPERATOR"])), true);
  assert.equal(canAcknowledgeAlerts(person(["REVIEWER"])), false);
  assert.equal(canAcknowledgeAlerts(person(["VIEWER"])), false);
  assert.equal(canAcknowledgeAlerts(person(["ADMIN"], false)), false);
  assert.equal(canAcknowledgeAlerts(null), false);
});

test("Today's read gives the book's hubs, the limit counts and the day's P&L change", () => {
  const figure = (value: number, unit = "GBP") => ({ key: "k", label: "", value, unit, as_of: null, state: "current", simulated: true, source: "s" });
  const today = {
    simulated: true,
    rows: [
      { key: "key_figures", tightest_limit: { counts: { breach: 1, watch: 3, expired: 0, shown: 4 } } },
      { key: "changes" },
      { key: "book", hubs: [
        { hub: "NBP", position_today: figure(30, "MW"), position_front_month: figure(25, "MW"), net_open_mwh: 100, day_pnl_change: figure(12_000) },
        { hub: "TTF", position_today: figure(0, "MW"), position_front_month: figure(0, "MW"), net_open_mwh: 0, day_pnl_change: figure(0) },
      ] },
      { key: "fundamentals" },
    ],
  } as unknown as DeskTodayDTO;
  assert.deepEqual(todayFacts(today), { bookHubs: ["NBP"], limitCounts: { breach: 1, watch: 3 }, dayPnl: { value: 12_000, unit: "GBP" }, simulated: true });
});

/* ------------------------------------------------------------------ the component */

async function renderStrip(situation: Situation, extra: Record<string, unknown> = {}) {
  const { load } = await loadApiStore();
  const { SituationStrip } = await load<{ SituationStrip: React.ComponentType<Record<string, unknown>> }>("/src/components/BreakingTicker.tsx");
  return renderToStaticMarkup(
    React.createElement(SituationStrip, {
      situation, t, language: "en", nowMs: NOW, compact: false, canAcknowledge: false, flash: false,
      onOpen: () => undefined, onHide: () => undefined, onAcknowledge: () => undefined, ...extra,
    }),
  );
}

test("hidden renders nothing at all: no band, no region", async () => {
  assert.equal(await renderStrip(buildSituation(inputs({ today: null }), context("finance"))), "");
});

test("quiet is one static muted line; urgent is one item and '+n more'; no marquee and no pause", async () => {
  const quiet = await renderStrip(buildSituation(inputs({ windows: [{ window_id: "w", name: "NBP D-1", closes_at_utc: inMinutes(90) } as NominationWindowOccurrenceDTO] }), context("trader")));
  assert.match(quiet, /data-shell-region="ticker"/);
  assert.match(quiet, /data-strip-state="quiet"/);
  assert.match(quiet, /strip\.quiet\.next_window:window=NBP D-1\|close=[^|]+\|until=strip\.span\.hours:count=2\|clock=/);
  assert.doesNotMatch(quiet, /is-critical|is-warning/);

  const urgent = await renderStrip(buildSituation(inputs({ outages: [outage("big"), outage("second", { unavailable_gwh_d: 300 })] }), context("trader")));
  assert.match(urgent, /data-strip-state="urgent"/);
  assert.match(urgent, /is-critical/);
  assert.match(urgent, /strip\.headline\.outage:asset=Asset big/);
  assert.equal((urgent.match(/strip\.headline\.outage/g) ?? []).length, 1, "one item on the line");
  assert.match(urgent, /strip\.more:count=1/);
  assert.doesNotMatch(urgent, /ticker-track|ticker-pause|aria-pressed|Breaking/);
  // A simulated figure carries its mark on the line.
  const demo = await renderStrip(buildSituation(inputs({ outages: [outage("demo", { source_system: "DEMO" })] }), context("trader")));
  assert.match(demo, /data-state="simulated"/);
  assert.match(demo, /strip\.details/);
});

test("on a phone the list opens as a sheet; the closed state is one line with its trigger", async () => {
  const situation = buildSituation(inputs({ alerts: [mandateBreach("demo.trader")] }), context("trader"));
  const closed = await renderStrip(situation, { compact: true });
  assert.match(closed, /data-strip-expand/);
  assert.match(closed, /aria-expanded="false"/);
  assert.match(closed, /data-dialog="situation-strip"/);
});

test("the strip's stylesheet has no animation and uses tokens; the old marquee is gone", () => {
  const css = readFileSync(new URL("../src/components/situationStrip.css", import.meta.url), "utf8");
  assert.doesNotMatch(css, /@keyframes|animation\s*:/);
  assert.doesNotMatch(css, /#[0-9a-f]{3,8}\b|rgba?\(/i);
  assert.match(css, /prefers-reduced-motion: reduce\) \{\s*\.situation-strip \{\s*transition: none;/);
  const system = readFileSync(new URL("../src/styles/design-system.css", import.meta.url), "utf8");
  assert.doesNotMatch(system, /ticker-scroll|ticker-track|breaking-ticker/);
  const shell = readFileSync(new URL("../src/components/ShellTicker.tsx", import.meta.url), "utf8");
  // The announcer sits outside the region, so a hidden strip leaves no band and is still heard.
  assert.match(shell, /role="status" aria-live="polite" data-strip-announcer/);
  assert.ok(shell.indexOf("data-strip-announcer") > shell.indexOf("<SituationStrip"));
});

/* ------------------------------------------------------------------ server alerts behind the backend rows */

test("the server's price-move, shortfall and fundamentals alerts reach the strip with their alert", () => {
  const price = alert("pm1", "market", "price_move", "warning",
    { hub: "NBP", product: "DA", move_pct: -6.4, price: 82.1, unit: "GBp/th", source_system: "DEMO_Sim", simulated: true },
    { simulated: true });
  const small = alert("pm2", "market", "price_move", "warning",
    { hub: "NBP", product: "FM", move_pct: 2.4, price: 84, unit: "GBp/th", source_system: "DEMO_Sim" });
  const trader = buildSituation(inputs({ alerts: [price, small] }), context("trader"));
  // The person's own threshold (5 %) applies on top of the server's 2 % floor.
  assert.deepEqual(ids(trader), ["price:NBP:DA"]);
  assert.equal(trader.items[0].alertId, "pm1");
  assert.equal(trader.items[0].simulated, true);
  assert.equal(trader.items[0].source.name, "DEMO_Sim");
  assert.deepEqual(trader.items[0].explain, { subject: "alert", id: "pm1" });
  const lower = buildSituation(inputs({ alerts: [price, small] }), context("trader", { thresholds: stripThresholdsFrom({ strip_price_move_pct: "2" }) }));
  assert.equal(lower.items.length, 2);

  const short = alert("sf1", "delivery", "shortfall", "critical",
    { contract_id: "C1", contract_name: "Haldor supply", gas_day: "2026-11-16", shortfall_mwh: 1200, shortfall_pct: 20, tolerance_pct: 5, source_system: "DEMO", book_ids: ["UK"] });
  const ops = buildSituation(inputs({ alerts: [short] }), context("operations"));
  assert.deepEqual(ids(ops), ["shortfall:C1:2026-11-16"]);
  assert.equal(ops.items[0].alertId, "sf1");
  // Behind a book the person cannot see: dropped (alert_scope.py).
  assert.deepEqual(ids(buildSituation(inputs({ alerts: [short] }), context("operations", {}, { dataScopes: ["BOOKS:NL"] }))), []);

  const lng = alert("fd1", "fundamentals", "lng_sendout", "warning",
    { series: "lng_sendout", value: 1.9, unit: "TWh/d", deviation_pct: 140, source_system: "GIE" });
  assert.deepEqual(ids(buildSituation(inputs({ alerts: [lng] }), context("analyst"))), ["fundamentals:lng_sendout"]);
  // Each row reaches only its audience.
  assert.deepEqual(ids(buildSituation(inputs({ alerts: [lng, short] }), context("trader"))), []);
});

test("platform: a failed job and a new problem report within six hours; the analyst's next data arrival", () => {
  const job = { job_id: "j1", kind: "INGESTION", status: "FAILED", finished_at_utc: hoursAgo(1), started_at_utc: hoursAgo(1), created_at_utc: hoursAgo(1) };
  const oldJob = { ...job, job_id: "j0", finished_at_utc: hoursAgo(9) };
  const report = { report_id: "r1", severity: "P2", summary: "Prices board blank on my laptop", status: "open", created_at_utc: hoursAgo(2) };
  const platform = buildSituation(
    inputs({ jobs: [job, oldJob] as never, reports: [report] as never }),
    context("platform"),
  );
  assert.deepEqual(ids(platform).sort(), ["job:j1", "report:r1"]);
  assert.equal(platform.items.find((item) => item.kind === "job")?.headline.key, "strip.headline.job_failed.INGESTION");
  assert.deepEqual(platform.items.find((item) => item.kind === "problem_report")?.target, { page: "runtime", params: { view: "support" } });
  // Nobody else sees platform work.
  assert.deepEqual(ids(buildSituation(inputs({ jobs: [job] as never, reports: [report] as never }), context("trader"))), []);

  const scheduled: StripSource[] = [
    { source_id: "gie", source_system: "GIE AGSI", attention: false, statusKey: "connectors.status.live", last_failure_at_utc: null, next_run_at_utc: inMinutes(95) },
    { source_id: "ecb", source_system: "ECB", attention: false, statusKey: "connectors.status.live", last_failure_at_utc: null, next_run_at_utc: inMinutes(40) },
    { source_id: "old", source_system: "Old", attention: false, statusKey: "connectors.status.live", last_failure_at_utc: null, next_run_at_utc: hoursAgo(1) },
  ];
  const analyst = buildSituation(inputs({ sources: scheduled }), context("analyst"));
  assert.equal(analyst.state, "quiet");
  assert.deepEqual(analyst.quiet?.phrase, { key: "strip.quiet.next_data", values: { source: "ECB", close: inMinutes(40) } });
});

test("a mandate breached by a rule says the rule, not a utilisation inside the limit", () => {
  const rule = alert("m2", "limits", "mandate", "critical",
    { name: "NBP desk", trader: "demo.trader", mandate_id: "M-2", status: "breach", utilisation_pct: 75, breaches: "TTF is outside the mandate", book_ids: ["UK"] });
  const [item] = buildSituation(inputs({ alerts: [rule] }), context("trader")).items;
  assert.deepEqual(item.headline, { key: "strip.headline.mandate.breach_rule", values: { name: "NBP desk", reason: "TTF is outside the mandate" } });
  assert.equal(item.comparison, null);
});
