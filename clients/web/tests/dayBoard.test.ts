/**
 * The day board: the desk's clock, composed and held to what each read established.
 *
 * The board is a composition, and the failure it has to be held away from is a quiet one: three
 * reads with three different postures collapsing into one grid of zeroes. A windows read that
 * answered "no runtime database" is not a schedule with no deadlines; a review register nobody read
 * is not a register with nothing pending; a monitoring summary that was never fetched is not an
 * alert centre with nothing open. These tests state each of those separately, on the model rather
 * than through a renderer, plus the source pins that keep the strip mounted, un-primary and bilingual.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import type {
  ApiMeta,
  IntradayOpportunityDTO,
  MonitoringAlertDTO,
  MonitoringSummaryDTO,
  NominationWindowOccurrenceDTO,
  NominationWindowReadDTO,
  ReviewDecisionDTO,
} from "../src/api/client.ts";
import {
  NOMINATION_WINDOWS_MISSING,
  dayBoardAlerts,
  dayBoardClock,
  dayBoardCountdown,
  dayBoardDecisions,
  dayBoardModel,
} from "../src/app/model/dayBoardModel.ts";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
const zh = JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>;

const GAS_DAY = "2026-05-29";

function windowRow(
  overrides: Partial<NominationWindowOccurrenceDTO> = {},
): NominationWindowOccurrenceDTO {
  return {
    window_id: "de-renom-1",
    name: "DE renomination window",
    country: "DE",
    opens_at: "05:00:00",
    closes_at: "05:30:00",
    opens_at_utc: "2026-05-29T05:00:00+00:00",
    closes_at_utc: "2026-05-29T05:30:00+00:00",
    next_gas_day: "2026-05-30",
    next_opens_at_utc: "2026-05-30T04:00:00+00:00",
    next_closes_at_utc: "2026-05-30T04:30:00+00:00",
    maximum_change_mwh: 150,
    maximum_change_pct: null,
    valid_from_utc: "2026-01-01T00:00:00+00:00",
    valid_to_utc: null,
    source_system: "cam",
    source_reference: "cam:DE:1",
    ...overrides,
  };
}

function windowsRead(
  overrides: Partial<NominationWindowReadDTO> = {},
): NominationWindowReadDTO {
  return {
    gas_day: GAS_DAY,
    calendar: "EU-CAM-UTC-2025",
    gas_day_start_utc: "2026-05-28T22:00:00+00:00",
    gas_day_end_utc: "2026-05-29T22:00:00+00:00",
    time_basis: "utc-clock-on-gas-day",
    assessed_at_utc: "2026-05-29T09:12:33+00:00",
    window_masters_declared: 2,
    windows: [windowRow()],
    ...overrides,
  };
}

/** A measured envelope: the route reached the masters it named. */
function measuredMeta(overrides: Partial<ApiMeta> = {}): ApiMeta {
  return {
    research_only: true,
    human_review_required: true,
    source_references: ["nomination_window_masters"],
    missing_inputs: [],
    warnings: [],
    ...overrides,
  };
}

function opportunity(
  overrides: Partial<IntradayOpportunityDTO> = {},
): IntradayOpportunityDTO {
  return {
    opportunity_id: "opp-1",
    scan_id: "scan-1",
    opportunity_type: "spread",
    status: "ACTIONABLE_REVIEW",
    buy_quote_id: "q1",
    sell_quote_id: "q2",
    route_id: "route-1",
    route_name: "NBP to TTF",
    buy_venue: "NBP",
    sell_venue: "TTF",
    buy_hub: "NBP",
    sell_hub: "TTF",
    product: "within-day",
    delivery_start_utc: "2026-05-29T00:00:00+00:00",
    delivery_end_utc: "2026-05-29T23:59:59+00:00",
    comparison_currency: "GBP",
    comparison_unit: "MWh",
    buy_ask: 30,
    sell_bid: 33,
    gross_spread: 3,
    route_cost: 0.4,
    trading_cost: 0.1,
    risk_buffer: 0.2,
    net_margin: 2.3,
    max_quantity_mwh: 1200,
    indicative_net_value: 2760,
    quote_age_seconds: 12,
    confidence_score: 0.82,
    cost_components: [],
    source_refs: ["market_quotes:q1"],
    assumptions: [],
    missing_inputs: [],
    warnings: [],
    detected_at_utc: "2026-05-29T08:00:00+00:00",
    valid_until_utc: "2026-05-29T10:00:00+00:00",
    simulated: false,
    human_review_required: true,
    ...overrides,
  };
}

function decision(entityId: string, entityType = "intraday_opportunity"): ReviewDecisionDTO {
  return {
    decision_id: `decision-${entityId}`,
    entity_type: entityType,
    entity_id: entityId,
    actor: "operator-1",
    decision: "accepted",
    note: null,
    created_at_utc: "2026-05-29T08:30:00+00:00",
  };
}

function alert(overrides: Partial<MonitoringAlertDTO> = {}): MonitoringAlertDTO {
  return {
    alert_id: "alert-1",
    fingerprint: "fingerprint-1",
    category: "market",
    alert_type: "spread",
    severity: "warning",
    status: "open",
    title_en: "Spread",
    title_zh_cn: "价差",
    message_en: "message",
    message_zh_cn: "消息",
    entity_type: "route",
    entity_id: "route-1",
    event_time_utc: "2026-05-29T07:00:00+00:00",
    detected_at_utc: "2026-05-29T07:00:00+00:00",
    updated_at_utc: "2026-05-29T07:00:00+00:00",
    acknowledged_at_utc: null,
    resolved_at_utc: null,
    occurrence_count: 1,
    evidence_snapshot: {},
    source_refs: [],
    warnings: [],
    llm_provider_id: "local",
    llm_status: "not_requested",
    llm_summary_en: null,
    llm_summary_zh_cn: null,
    llm_last_attempt_at_utc: null,
    simulated: false,
    human_review_required: true,
    ...overrides,
  };
}

const SUMMARY: MonitoringSummaryDTO = {
  open_count: 3,
  acknowledged_count: 1,
  critical_count: 1,
  warning_count: 2,
  info_count: 0,
  llm_pending_count: 0,
  simulated_count: 0,
};

test("the clock rows carry the deadline the API resolved, earliest first", () => {
  const read = windowsRead({
    window_masters_declared: 3,
    windows: [
      windowRow({
        window_id: "nl-late",
        name: "NL late window",
        closes_at_utc: "2026-05-29T14:00:00+00:00",
      }),
      windowRow({
        window_id: "de-early",
        name: "DE early window",
        closes_at_utc: "2026-05-29T05:30:00+00:00",
      }),
      windowRow({
        window_id: "be-mid",
        name: "BE mid window",
        closes_at_utc: "2026-05-29T09:00:00+00:00",
      }),
    ],
  });

  const clock = dayBoardClock(read, measuredMeta());
  assert.deepEqual(
    clock.rows.map((row) => row.windowId),
    ["de-early", "be-mid", "nl-late"],
  );
  assert.equal(clock.posture, "measured");
  assert.equal(clock.mastersDeclared, 3);
  assert.equal(clock.noWindowsReason, null);
  // The declared instant is what a row renders first; the gas day it was resolved onto travels
  // with it, because a deadline without its day is not a deadline.
  assert.equal(clock.rows[1].closesAtUtc, "2026-05-29T09:00:00+00:00");
  assert.equal(clock.rows[1].gasDay, GAS_DAY);
  assert.equal(clock.rows[0].sourceReference, "cam:DE:1");
  assert.equal(clock.rows[0].sourceSystem, "cam");
  assert.equal(clock.timeBasis, "utc-clock-on-gas-day");
  assert.equal(clock.assessedAtUtc, "2026-05-29T09:12:33+00:00");
});

test("a row carries the next occurrence the API resolved, so a closed day is still actionable", () => {
  const clock = dayBoardClock(windowsRead(), measuredMeta());
  const row = clock.rows[0];

  // The masters are daily rules: after this gas day's window has closed, the instant the desk
  // waits for is the next day's occurrence of the same clock - and it is the API's answer, not
  // "today's instant plus 24 hours".
  assert.equal(row.nextGasDay, "2026-05-30");
  assert.equal(row.nextOpensAtUtc, "2026-05-30T04:00:00+00:00");
  assert.equal(row.nextClosesAtUtc, "2026-05-30T04:30:00+00:00");
});

test("a row whose read declared no next occurrence states none rather than inventing one", () => {
  const clock = dayBoardClock(
    windowsRead({
      windows: [
        windowRow({
          next_gas_day: undefined,
          next_opens_at_utc: undefined,
          next_closes_at_utc: undefined,
        }),
      ],
    }),
    measuredMeta(),
  );

  assert.equal(clock.rows[0].nextOpensAtUtc, null);
  assert.equal(clock.rows[0].nextClosesAtUtc, null);
  assert.equal(clock.rows[0].nextGasDay, null);
});

test("a change limit the master does not declare stays undeclared, never zero", () => {
  const clock = dayBoardClock(
    windowsRead({
      window_masters_declared: 2,
      windows: [
        windowRow({ window_id: "no-limit", maximum_change_mwh: null, maximum_change_pct: null }),
        windowRow({
          window_id: "pct-only",
          maximum_change_mwh: null,
          maximum_change_pct: 15,
          closes_at_utc: "2026-05-29T06:30:00+00:00",
        }),
      ],
    }),
    measuredMeta(),
  );

  const byId = new Map(clock.rows.map((row) => [row.windowId, row]));
  assert.equal(byId.get("no-limit")?.maximumChangeMwh, null);
  assert.equal(byId.get("no-limit")?.maximumChangePct, null);
  assert.equal(byId.get("pct-only")?.maximumChangeMwh, null);
  assert.equal(byId.get("pct-only")?.maximumChangePct, 15);

  // The panel is where a null becomes a word: it renders the "not declared" key rather than a
  // number, which is the only place the absence is turned into text.
  const panel = readWebSource("components/decision/DayBoardPanel.tsx");
  assert.match(panel, /return parts\.length > 0 \? parts\.join\(" · "\) : t\("day_board\.not_declared"\)/);
  assert.ok(en["day_board.not_declared"] && zh["day_board.not_declared"]);
});

test("an unconfigured runtime database is not a measured zero", () => {
  const clock = dayBoardClock(
    windowsRead({ window_masters_declared: 0, windows: [] }),
    measuredMeta({
      source_references: ["runtime-db-not-configured"],
      missing_inputs: ["RUNTIME_STORE_DATABASE_URL", "nomination_window_masters"],
      warnings: ["Nomination windows are unavailable until a runtime DB is configured."],
    }),
  );

  assert.equal(clock.posture, "runtime-db-not-configured");
  assert.notEqual(clock.posture, "measured");
  // The route's `0` counts what it did not synthesize, so it is not repeated as a measurement.
  assert.equal(clock.mastersDeclared, null);
  assert.equal(clock.noWindowsReason, "runtime-db-not-configured");
  assert.deepEqual(clock.rows, []);
  assert.deepEqual(clock.missingInputs, [
    "RUNTIME_STORE_DATABASE_URL",
    "nomination_window_masters",
  ]);
});

test("a configured deployment that declares no master is a measured zero, with its reason", () => {
  const clock = dayBoardClock(
    windowsRead({ window_masters_declared: 0, windows: [] }),
    measuredMeta({ warnings: [NOMINATION_WINDOWS_MISSING] }),
  );

  assert.equal(clock.posture, "measured");
  assert.equal(clock.mastersDeclared, 0);
  assert.equal(clock.noWindowsReason, NOMINATION_WINDOWS_MISSING);
  assert.deepEqual(clock.rows, []);
  // The gas day was still read, so the board can say which day declares nothing.
  assert.equal(clock.gasDay, GAS_DAY);

  // A measured zero the read did not explain is reported without inventing a cause.
  const unexplained = dayBoardClock(
    windowsRead({ window_masters_declared: 0, windows: [] }),
    measuredMeta(),
  );
  assert.equal(unexplained.posture, "measured");
  assert.equal(unexplained.noWindowsReason, null);
});

test("a windows read that never happened is not-read, and carries no deadline", () => {
  const clock = dayBoardClock(null, null);
  assert.equal(clock.posture, "not-read");
  assert.equal(clock.mastersDeclared, null);
  assert.equal(clock.gasDay, null);
  assert.equal(clock.noWindowsReason, null);
  assert.deepEqual(clock.rows, []);
});

test("an actionable opportunity with a recorded decision is not unactioned", () => {
  const opportunities = [
    opportunity({ opportunity_id: "opp-decided" }),
    opportunity({ opportunity_id: "opp-open", valid_until_utc: "2026-05-29T11:00:00+00:00" }),
    opportunity({ opportunity_id: "opp-blocked", status: "BLOCKED" }),
  ];
  // A decision on another entity type - and on a non-actionable opportunity - is not a decision
  // on the work this section lists.
  const decisions = [decision("opp-decided"), decision("opp-blocked", "strategy_run")];

  const section = dayBoardDecisions(opportunities, decisions, true);
  assert.equal(section.posture, "measured");
  assert.deepEqual(
    section.rows.map((row) => row.opportunityId),
    ["opp-open"],
  );
  assert.equal(section.actionableCount, 2);
  assert.equal(section.decidedCount, 1);
  // The row carries the declared evidence, not a summary of it.
  const row = section.rows[0];
  assert.equal(row.validUntilUtc, "2026-05-29T11:00:00+00:00");
  assert.equal(row.routeName, "NBP to TTF");
  assert.equal(row.netMargin, 2.3);
  assert.equal(row.maxQuantityMwh, 1200);
  assert.equal(row.confidenceScore, 0.82);
  assert.deepEqual(row.sourceRefs, ["market_quotes:q1"]);
  assert.equal(row.simulated, false);
});

test("unactioned rows are ordered by the deadline they race", () => {
  const section = dayBoardDecisions(
    [
      opportunity({ opportunity_id: "later", valid_until_utc: "2026-05-29T18:00:00+00:00" }),
      opportunity({ opportunity_id: "sooner", valid_until_utc: "2026-05-29T10:15:00+00:00" }),
      opportunity({ opportunity_id: "middle", valid_until_utc: "2026-05-29T12:00:00+00:00" }),
    ],
    [],
    true,
  );
  assert.deepEqual(
    section.rows.map((row) => row.opportunityId),
    ["sooner", "middle", "later"],
  );
  assert.equal(section.decidedCount, 0);

  // Every actionable opportunity decided is a measured zero with a sentence, not an empty list.
  assert.deepEqual(dayBoardDecisions([opportunity()], [decision("opp-1")], true).rows, []);
});

test("an unread review register makes no claim about what is unactioned", () => {
  const opportunities = [opportunity({ opportunity_id: "opp-a" }), opportunity()];
  const section = dayBoardDecisions(opportunities, [], false);

  assert.equal(section.posture, "not-read");
  assert.deepEqual(section.rows, []);
  // Nothing here says "2 actionable, 0 decided": the register is what would make that a fact.
  assert.equal(section.decidedCount, null);
  assert.equal(section.actionableCount, 2);

  const panel = readWebSource("components/decision/DayBoardPanel.tsx");
  // The not-read branch renders its own sentence and no counts.
  assert.match(panel, /decisions\.posture === "not-read" \? \(\s*<p className="day-board-empty">\{t\("day_board\.decisions\.not_read"\)\}<\/p>/);
  assert.ok(en["day_board.decisions.not_read"] && zh["day_board.decisions.not_read"]);
});

test("the alert section counts open alerts and states the newest movement", () => {
  const alerts = [
    // Recurred, so moved even though its update equals its detection.
    alert({ alert_id: "a-recurred", occurrence_count: 3, updated_at_utc: "2026-05-29T09:00:00+00:00" }),
    // Updated later than detected, so moved.
    alert({
      alert_id: "a-updated",
      detected_at_utc: "2026-05-29T06:00:00+00:00",
      updated_at_utc: "2026-05-29T09:45:00+00:00",
    }),
    // Open and untouched: not a movement.
    alert({ alert_id: "a-quiet" }),
    // Acknowledged work is not what the pointer counts.
    alert({
      alert_id: "a-acknowledged",
      status: "acknowledged",
      occurrence_count: 5,
      updated_at_utc: "2026-05-29T12:00:00+00:00",
    }),
  ];

  const section = dayBoardAlerts(SUMMARY, measuredMeta(), alerts);
  assert.equal(section.posture, "measured");
  assert.equal(section.openCount, 3);
  assert.equal(section.criticalCount, 1);
  assert.equal(section.warningCount, 2);
  assert.equal(section.movedCount, 2);
  assert.equal(section.latestMovementUtc, "2026-05-29T09:45:00+00:00");
});

test("an unread monitoring summary produces no counts at all", () => {
  const unread = dayBoardAlerts(null, null, [alert({ occurrence_count: 4 })]);
  assert.equal(unread.posture, "not-read");
  assert.equal(unread.openCount, null);
  assert.equal(unread.criticalCount, null);
  assert.equal(unread.warningCount, null);
  assert.equal(unread.movedCount, null);
  assert.equal(unread.latestMovementUtc, null);

  // A summary the backend could not serve is likewise not a summary of zeroes.
  const unconfigured = dayBoardAlerts(SUMMARY, measuredMeta({
    source_references: ["runtime-db-not-configured"],
    missing_inputs: ["RUNTIME_STORE_DATABASE_URL"],
  }), []);
  assert.equal(unconfigured.posture, "runtime-db-not-configured");
  assert.equal(unconfigured.openCount, null);
});

test("the countdown states overdue, due, minutes and hours against the caller's clock", () => {
  const now = "2026-05-29T09:00:00+00:00";

  const overdue = dayBoardCountdown("2026-05-29T08:30:00+00:00", now);
  assert.equal(overdue.state, "overdue");
  assert.equal(overdue.amount, 30);
  assert.equal(overdue.unitKey, "day_board.countdown.unit_minutes");

  // A deadline missed by seconds is still missed.
  const justMissed = dayBoardCountdown("2026-05-29T08:59:30+00:00", now);
  assert.equal(justMissed.state, "overdue");
  assert.equal(justMissed.amount, 1);

  // Exactly at the deadline is neither early nor late, and does not render "0 min left".
  const due = dayBoardCountdown(now, now);
  assert.equal(due.state, "due");
  assert.equal(due.amount, 0);
  assert.equal(due.unitKey, null);

  const minutes = dayBoardCountdown("2026-05-29T09:42:00+00:00", now);
  assert.equal(minutes.state, "minutes");
  assert.equal(minutes.amount, 42);
  assert.equal(minutes.unitKey, "day_board.countdown.unit_minutes");

  // Under a minute left is still time left.
  const underAMinute = dayBoardCountdown("2026-05-29T09:00:30+00:00", now);
  assert.equal(underAMinute.state, "minutes");
  assert.equal(underAMinute.amount, 1);

  const hours = dayBoardCountdown("2026-05-29T12:30:00+00:00", now);
  assert.equal(hours.state, "hours");
  assert.equal(hours.amount, 3);
  assert.equal(hours.unitKey, "day_board.countdown.unit_hours");

  // An instant the client cannot read is stated as unreadable rather than as `NaN`.
  const unreadable = dayBoardCountdown("not-an-instant", now);
  assert.equal(unreadable.state, "unknown");
  assert.equal(unreadable.unitKey, null);
  assert.equal(unreadable.labelKey, "day_board.countdown.unknown");
});

test("the composed board keeps the three sections apart on one as-of", () => {
  const now = "2026-05-29T09:00:00+00:00";
  const model = dayBoardModel({
    windowsRead: windowsRead(),
    windowsMeta: measuredMeta(),
    opportunities: [opportunity({ opportunity_id: "opp-open" })],
    reviewDecisions: [],
    reviewRegisterRead: true,
    monitoringSummary: SUMMARY,
    monitoringMeta: measuredMeta(),
    monitoringAlerts: [alert()],
    now,
  });

  assert.equal(model.measuredAtUtc, now);
  assert.equal(model.clock.rows.length, 1);
  assert.equal(model.decisions.rows.length, 1);
  assert.equal(model.alerts.openCount, 3);
  // The countdown the surface renders is measured against the same instant the model reports.
  assert.equal(dayBoardCountdown(model.clock.rows[0].closesAtUtc, model.measuredAtUtc).state, "overdue");
});

test("the three deployment states read differently, and the countdown names its clock", () => {
  const panel = readWebSource("components/decision/DayBoardPanel.tsx");

  // Not read, unconfigured and measured-zero are three different sentences in the DOM: a `0` is
  // never asked to stand in for a read that established nothing.
  assert.match(
    panel,
    /clock\.posture === "not-read" \? \(\s*<p className="day-board-empty">\{t\("day_board\.clock\.not_read"\)\}<\/p>/,
  );
  assert.match(
    panel,
    /clock\.posture === "runtime-db-not-configured" \? \(\s*<div className="day-board-unavailable">/,
  );
  assert.match(
    panel,
    /clock\.noWindowsReason === "NOMINATION_WINDOWS_MISSING"\s*\?\s*t\("day_board\.clock\.no_masters"\)\s*:\s*t\("day_board\.clock\.none_today"\)/,
  );
  // The window count is only stated where the read measured it.
  assert.match(panel, /\{clock\.posture === "measured" && clock\.mastersDeclared !== null && \(/);
  // An unmeasured alert summary shows no count at all.
  assert.match(
    panel,
    /alerts\.posture !== "measured" \? \([\s\S]{0,200}?t\("day_board\.alerts\.not_read"\)/,
  );

  // The declared instant is the row's primary value, and the countdown is visibly qualified as
  // being measured against the browser's clock rather than left to look like the API's own instant.
  assert.match(panel, /<strong>\{formatUtcTimestamp\(row\.closesAtUtc\)\}<\/strong>/);
  assert.match(panel, /<strong>\{formatUtcTimestamp\(row\.validUntilUtc\)\}<\/strong>/);
  assert.match(
    panel,
    /<small className="day-board-qualifier">\{t\("day_board\.countdown\.browser_clock"\)\}<\/small>/,
  );
  assert.ok(en["day_board.clock.time_basis_help"].includes("API"));

  // The deadline the desk is actually waiting for once the day's window has closed: the next
  // occurrence the API resolved, shown only when this day's window can no longer be used.
  assert.match(
    panel,
    /dayBoardCountdown\(row\.closesAtUtc, measuredAtUtc\)\.state === "overdue" &&\s*row\.nextOpensAtUtc && \(/,
  );
  assert.match(panel, /className="day-board-next-window"/);
  assert.match(panel, /t\("day_board\.clock\.next_window"\)/);
});

test("the board is mounted in the Decision workspace, above every task's panel", () => {
  const workspace = readWebSource("components/DecisionWorkspace.tsx");

  assert.match(
    workspace,
    /import \{ DayBoardPanel \} from "@\/components\/decision\/DayBoardPanel";/,
  );
  const panelIndex = workspace.indexOf("<DayBoardPanel");
  const stripIndex = workspace.indexOf('{task === "review" && <ReviewContextStrip');
  assert.ok(panelIndex > 0, "the day board is mounted");
  assert.ok(stripIndex > panelIndex, "the day board sits above the per-task panels");
  // It is inside the task panel container, so it appears for every task rather than one page.
  assert.ok(workspace.indexOf('id="decision-task-panel"') < panelIndex);
  // It navigates through the workspace's own task switch.
  assert.match(workspace, /onOpenTask=\{openTask\}/);
  assert.match(workspace, /onOpenAlerts=\{\(\) => navigation\.openWorkspace\("market"\)\}/);
  // The reads belong to the mount, and the store coalesces them with the review task's own ask.
  assert.match(workspace, /void fetchNominationWindows\(\);/);
  assert.match(workspace, /void fetchReviewContext\(\);/);
  assert.match(workspace, /reviewRegisterRead: reviewIsUsable\(api\.reviewContext\)/);
});

test("the board adds no primary action and renders no alert list", () => {
  const panel = readWebSource("components/decision/DayBoardPanel.tsx");
  const workspace = readWebSource("components/DecisionWorkspace.tsx");

  // The board navigates; the workspace's single primary slot stays the task's own act.
  assert.equal(panel.includes("primaryAction="), false);
  assert.equal((workspace.match(/primaryAction=\{/g) ?? []).length, 1);
  assert.match(panel, /<button\s+type="button"\s+className="day-board-row"/);
  assert.match(panel, /onClick=\{\(\) => onOpenTask\("nomination"\)\}/);
  assert.match(panel, /onClick=\{\(\) => onOpenTask\("review"\)\}/);
  // The countdown's state is rendered, not merely computed: it classifies the element, so an
  // overdue deadline is styled as one.
  assert.match(panel, /className=\{`day-board-countdown is-\$\{countdown\.state\}`\}/);

  // The alert centre keeps its list: the section is counts, one instant and a pointer.
  assert.equal(panel.includes("monitoringAlerts"), false);
  assert.equal(panel.includes("alert_id"), false);
  assert.equal(/alerts\.rows/.test(panel), false);

  // The panel is presentational: it fetches nothing and reads no clock of its own.
  for (const banned of ["useEffect", "api.", "fetch(", "Date.now", "new Date("]) {
    assert.equal(panel.includes(banned), false, banned);
  }
});

test("the store reads the windows on demand, gated, coalesced and recorded", () => {
  const store = readWebSource("stores/api.ts");
  const coordinator = readWebSource("stores/workspaceLoading.ts");
  const client = readWebSource("api/client.ts");

  // The new path is reached from the client, through the shared GET helper.
  assert.match(
    client,
    /nominationWindows: \(gasDay\?: string, options\?: ApiRequestOptions\) =>/,
  );
  assert.match(client, /get<NominationWindowReadDTO>\(\s*"\/optimization\/nomination-windows"/);
  assert.match(client, /gasDay \? \{ gas_day: gasDay \} : undefined/);

  // On demand: the day board asks when it mounts, not on every workspace load.
  const loaders = /const WORKSPACE_LOADERS[\s\S]*?\n\];/.exec(store)?.[0] ?? "";
  assert.equal(loaders.includes("api.nominationWindows"), false);
  assert.match(store, /fetchNominationWindows: async \(gasDay\) => \{/);
  assert.match(store, /const refresh = readRefreshCoordinator\.nominationWindows\.tryStart\(\);/);
  assert.match(store, /isIdentityGateOpen\(get\(\)\.authState\)\) return;/);
  assert.match(store, /nominationWindows: result\.value\.data\.windows,/);
  assert.match(store, /nominationWindowsMeta: result\.value\.meta,/);
  // A failed read is recorded where every other endpoint failure is, and rewrites no rows.
  assert.match(store, /endpointErrors\.nominationWindows = result\.error\.message;/);
  assert.match(store, /endpointErrorCodes\.nominationWindows = result\.error\.code;/);

  // The lane exists, and an identity or workspace reset cancels it and clears the clock.
  assert.match(coordinator, /readonly nominationWindows = new ReadRefreshLane\(\);/);
  assert.match(coordinator, /this\.nominationWindows\.cancel\(\);/);
  assert.match(coordinator, /nominationWindowsRead: null,/);
  assert.match(coordinator, /nominationWindowsMeta: null,/);
});

test("the board's posture comes from the read envelope, not from a row count", () => {
  const model = readWebSource("app/model/dayBoardModel.ts");

  assert.match(model, /import \{ readState, type ReadPosture \} from "\.\/readPosture\.ts";/);
  assert.match(model, /const read = readState\(windowsMeta\);/);
  assert.match(model, /const read = readState\(meta\);/);
  assert.match(model, /posture: "runtime-db-not-configured"/);
  // Nothing here turns an absent read into a zero: every count the board states comes from a
  // payload the route actually served.
  assert.equal(model.includes("?? 0"), false);
});

test("every board string is declared in both locales, and none carries a question mark", () => {
  const panel = readWebSource("components/decision/DayBoardPanel.tsx");
  const model = readWebSource("app/model/dayBoardModel.ts");

  const keys = new Set<string>();
  for (const match of panel.matchAll(/t\("([^"]+)"\)/g)) keys.add(match[1]);
  for (const match of model.matchAll(/labelKey: "([^"]+)"/g)) keys.add(match[1]);
  // The keys the panel composes from the model's descriptor are read through the same translator.
  for (const match of model.matchAll(/"(day_board\.countdown\.[a-z_]+)"/g)) keys.add(match[1]);
  assert.ok(keys.size >= 30, `expected the board's vocabulary, saw ${keys.size}`);

  for (const key of keys) {
    assert.ok(en[key]?.trim(), `en ${key}`);
    assert.ok(zh[key]?.trim(), `zh ${key}`);
    assert.notEqual(en[key], zh[key], key);
    assert.equal(en[key].includes("?"), false, `${key} carries a question mark`);
    assert.equal(zh[key].includes("?"), false, `${key} carries a question mark`);
  }

  // The endpoint label the new read records is declared too, so the failure banner translates it.
  const label = readWebSource("app/model/endpointFailures.ts");
  assert.match(label, /nominationWindows: "workspace\.endpoint\.nomination_windows",/);
  for (const locale of [en, zh]) {
    assert.ok(locale["workspace.endpoint.nomination_windows"]?.trim());
  }
  assert.notEqual(
    en["workspace.endpoint.nomination_windows"],
    zh["workspace.endpoint.nomination_windows"],
  );
});
