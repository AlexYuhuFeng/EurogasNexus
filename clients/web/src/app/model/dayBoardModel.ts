/**
 * The day board: what must be acted on today, and by when.
 *
 * Three sources already exist in the shell and none of them answered the desk's question on its
 * own. The nomination windows declare a clock (`GET /api/optimization/nomination-windows`); the
 * intraday scan publishes opportunities that are actionable; the alert centre counts what moved.
 * What was missing is the composition - read together, on one as-of, with the deadline each row
 * is racing - so this module is that composition and nothing else: pure, no React, no fetch, and
 * one explicit `now` so the countdown is testable instead of hidden in a render.
 *
 * The rules it keeps, in the order they matter:
 *
 * - **unavailable is not empty.** Every section carries the posture of the read behind it. A read
 *   that established nothing says so; a read that measured zero says zero. The three deployment
 *   states of the windows route are three different outcomes here, not three renderings of `[]`;
 * - **a declared field, or nothing.** A window master that declares no change limit renders as "not
 *   declared" and never as `0`, and the board never invents a deadline: a row exists because the
 *   API served one;
 * - **the alert centre keeps its list.** The alerts section is counts plus one instant - it points
 *   at the surface that owns the alerts instead of duplicating it;
 * - **an unread register is not an answered one.** "No decision is recorded" is a claim only the
 *   review register can support, so when the register was not read the section reports not-read and
 *   names no opportunity as unactioned.
 */

import type {
  ApiMeta,
  IntradayOpportunityDTO,
  MonitoringAlertDTO,
  MonitoringSummaryDTO,
  NominationWindowOccurrenceDTO,
  NominationWindowReadDTO,
  ReviewDecisionDTO,
} from "@/api/client";
import { readState, type ReadPosture } from "./readPosture.ts";

/** The opportunity status the desk acts on. Everything else is context, not work. */
export const ACTIONABLE_OPPORTUNITY_STATUS = "ACTIONABLE_REVIEW";

/** The entity type a review decision on an opportunity carries. */
export const OPPORTUNITY_ENTITY_TYPE = "intraday_opportunity";

/** The composition's own warning for a configured deployment that declares no window master. */
export const NOMINATION_WINDOWS_MISSING = "NOMINATION_WINDOWS_MISSING";

/** Why a measured read carried no window. `null` when it carried one, or said nothing. */
export type NoWindowReason =
  | "runtime-db-not-configured"
  | typeof NOMINATION_WINDOWS_MISSING
  | null;

/** One nomination window's deadline, as the API resolved it onto the gas day. */
export interface DayBoardDeadlineRow {
  readonly windowId: string;
  readonly name: string;
  readonly country: string | null;
  /** The gas day the window was resolved onto, as the read declared it. */
  readonly gasDay: string;
  /** The declared opening instant, or null when the route served none. */
  readonly opensAtUtc: string | null;
  /** The deadline: the instant the window closes. The primary value of the row. */
  readonly closesAtUtc: string;
  /**
   * When the same daily rule next opens, on the following gas day, and the gas day that is.
   *
   * Null only when the route served no next occurrence. Both instants come from the API: the board
   * does not add a day to a clock, because the gas day is 23/24/25 hours long.
   */
  readonly nextGasDay: string | null;
  readonly nextOpensAtUtc: string | null;
  readonly nextClosesAtUtc: string | null;
  /** The declared change limit in MWh, or null when the master declares none. */
  readonly maximumChangeMwh: number | null;
  /** The declared change limit as a share, or null when the master declares none. */
  readonly maximumChangePct: number | null;
  /** Where the master came from, as the row cites it. */
  readonly sourceSystem: string | null;
  readonly sourceReference: string | null;
}

/** Section 1: the clock the desk is trading against. */
export interface DayBoardClockSection {
  readonly posture: ReadPosture;
  /** The inputs the read named as missing; empty for a measured read. */
  readonly missingInputs: readonly string[];
  /** The gas day the read resolved, or null when nothing was read. */
  readonly gasDay: string | null;
  /** The time basis the API declared for the instants above. */
  readonly timeBasis: string | null;
  readonly calendar: string | null;
  /** When the API resolved the clock - its own as-of, not the browser's. */
  readonly assessedAtUtc: string | null;
  /**
   * How many window masters the read declared. Null unless the read measured: under an
   * unconfigured runtime database the route's `0` counts what the API did not synthesize, not
   * what the deployment declares, so it is not a measurement.
   */
  readonly mastersDeclared: number | null;
  /** Why the read carried no window, when it said why. */
  readonly noWindowsReason: NoWindowReason;
  /** One row per declared window, earliest deadline first. */
  readonly rows: readonly DayBoardDeadlineRow[];
}

/** One actionable opportunity with no recorded decision, and the deadline it races. */
export interface DayBoardActionRow {
  readonly opportunityId: string;
  readonly routeName: string;
  /** The declared deadline: the instant the opportunity stops being valid. */
  readonly validUntilUtc: string;
  /** The engine's net margin, or null when it reported none. Never defaulted to zero. */
  readonly netMargin: number | null;
  readonly maxQuantityMwh: number | null;
  readonly confidenceScore: number;
  readonly sourceRefs: readonly string[];
  /** Whether the row rests on a simulated source, as the row itself declares. */
  readonly simulated: boolean;
}

/** Section 2: actionable work with no decision recorded yet. */
export interface DayBoardDecisionSection {
  /** The posture of the review register - the read that makes "unactioned" a claim. */
  readonly posture: ReadPosture;
  /** The unactioned rows, earliest deadline first. Empty when the register was not read. */
  readonly rows: readonly DayBoardActionRow[];
  /** Actionable opportunities the market read carried, whatever the register says. */
  readonly actionableCount: number;
  /** How many of them the register holds a decision for; null when it was not read. */
  readonly decidedCount: number | null;
}

/** Section 3: a measured pointer into the alert centre, never a second alert list. */
export interface DayBoardAlertSection {
  readonly posture: ReadPosture;
  /** Counts as the summary measured them; null when it was not read. */
  readonly openCount: number | null;
  readonly criticalCount: number | null;
  readonly warningCount: number | null;
  /**
   * The newest instant an open alert moved (its `updated_at_utc`), or null when no open alert
   * moved. An alert counts as moved when it has recurred or its update is later than its first
   * detection.
   */
  readonly latestMovementUtc: string | null;
  /** How many open alerts moved; null when the summary was not read. */
  readonly movedCount: number | null;
}

export interface DayBoardModel {
  readonly clock: DayBoardClockSection;
  readonly decisions: DayBoardDecisionSection;
  readonly alerts: DayBoardAlertSection;
  /** The instant every countdown on the board was measured against - the browser's clock. */
  readonly measuredAtUtc: string;
}

export interface DayBoardInputs {
  /** The windows read's data block, or null before any read answered. */
  readonly windowsRead: NominationWindowReadDTO | null;
  /** The windows read's envelope: the posture comes from what the route said, not the row count. */
  readonly windowsMeta: ApiMeta | null;
  readonly opportunities: readonly IntradayOpportunityDTO[];
  readonly reviewDecisions: readonly ReviewDecisionDTO[];
  /**
   * Whether the review register behind "has a decision" was read. The store derives this from the
   * review projection (`reviewIsUsable`); the board treats "not read" as its own state.
   */
  readonly reviewRegisterRead: boolean;
  readonly monitoringSummary: MonitoringSummaryDTO | null;
  /** The monitoring summary's envelope, so a summary that was not read is not read as zeroes. */
  readonly monitoringMeta: ApiMeta | null;
  readonly monitoringAlerts: readonly MonitoringAlertDTO[];
  /** The instant the countdowns are measured against, passed in so the model stays testable. */
  readonly now: string;
}

/** An unparsable instant sorts last and never renders as `NaN`. */
function instantMs(value: string | null | undefined): number {
  if (!value) return Number.POSITIVE_INFINITY;
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? Number.POSITIVE_INFINITY : parsed;
}

/** Earliest deadline first, with the declared id as the tie-break so the order is stable. */
function byDeadline<T>(
  deadlineOf: (row: T) => string,
  idOf: (row: T) => string,
): (left: T, right: T) => number {
  return (left, right) => {
    const leftMs = instantMs(deadlineOf(left));
    const rightMs = instantMs(deadlineOf(right));
    if (leftMs !== rightMs) return leftMs < rightMs ? -1 : 1;
    const leftId = idOf(left);
    const rightId = idOf(right);
    return leftId < rightId ? -1 : leftId > rightId ? 1 : 0;
  };
}

/**
 * One row per declared window. `closes_after_utc_midnight` is deliberately not carried: the row
 * states the instant the API resolved, and a flag beside it would be a second way to say it.
 */
function deadlineRow(
  window: NominationWindowOccurrenceDTO,
  gasDay: string,
): DayBoardDeadlineRow {
  return {
    windowId: window.window_id,
    name: window.name,
    country: window.country ?? null,
    gasDay,
    opensAtUtc: window.opens_at_utc ?? null,
    closesAtUtc: window.closes_at_utc,
    nextGasDay: window.next_gas_day ?? null,
    nextOpensAtUtc: window.next_opens_at_utc ?? null,
    nextClosesAtUtc: window.next_closes_at_utc ?? null,
    maximumChangeMwh: window.maximum_change_mwh ?? null,
    maximumChangePct: window.maximum_change_pct ?? null,
    sourceSystem: window.source_system ?? null,
    sourceReference: window.source_reference ?? null,
  };
}

/**
 * Why a measured read carried no window, as the read itself stated it.
 *
 * A measured zero is a fact about the deployment, but the *cause* is only reported when the
 * composition named it: a zero without the warning is rendered as the measurement alone.
 */
function measuredZeroReason(
  windowsRead: NominationWindowReadDTO,
  warnings: readonly string[],
): NoWindowReason {
  if (windowsRead.window_masters_declared !== 0) return null;
  return warnings.includes(NOMINATION_WINDOWS_MISSING) ? NOMINATION_WINDOWS_MISSING : null;
}

/**
 * Section 1. The route's three deployment states become three outcomes, and only the measured one
 * reports a count.
 */
export function dayBoardClock(
  windowsRead: NominationWindowReadDTO | null,
  windowsMeta: ApiMeta | null,
): DayBoardClockSection {
  const read = readState(windowsMeta);
  if (read.posture === "not-read" || !windowsRead) {
    return {
      posture: "not-read",
      missingInputs: read.missingInputs,
      gasDay: null,
      timeBasis: null,
      calendar: null,
      assessedAtUtc: null,
      mastersDeclared: null,
      noWindowsReason: null,
      rows: [],
    };
  }

  const gasDay = windowsRead.gas_day;
  const rows = [...windowsRead.windows]
    .map((window) => deadlineRow(window, gasDay))
    .sort(byDeadline((row) => row.closesAtUtc, (row) => row.windowId));

  if (read.posture === "runtime-db-not-configured") {
    // The route resolved the gas day from its calendar, but it declared nothing about the
    // deployment's window masters: the count stays unmeasured and the reason is named.
    return {
      posture: "runtime-db-not-configured",
      missingInputs: read.missingInputs,
      gasDay,
      timeBasis: windowsRead.time_basis,
      calendar: windowsRead.calendar,
      assessedAtUtc: windowsRead.assessed_at_utc,
      mastersDeclared: null,
      noWindowsReason: "runtime-db-not-configured",
      rows,
    };
  }

  return {
    posture: "measured",
    missingInputs: [],
    gasDay,
    timeBasis: windowsRead.time_basis,
    calendar: windowsRead.calendar,
    assessedAtUtc: windowsRead.assessed_at_utc,
    mastersDeclared: windowsRead.window_masters_declared,
    noWindowsReason: measuredZeroReason(windowsRead, windowsMeta?.warnings ?? []),
    rows,
  };
}

function actionRow(opportunity: IntradayOpportunityDTO): DayBoardActionRow {
  return {
    opportunityId: opportunity.opportunity_id,
    routeName: opportunity.route_name,
    validUntilUtc: opportunity.valid_until_utc,
    netMargin: opportunity.net_margin ?? null,
    maxQuantityMwh: opportunity.max_quantity_mwh ?? null,
    confidenceScore: opportunity.confidence_score,
    sourceRefs: opportunity.source_refs ?? [],
    simulated: opportunity.simulated,
  };
}

function decisionKey(entityType: string, entityId: string): string {
  return `${entityType}\u0000${entityId}`;
}

/**
 * Section 2. "Unactioned" means an actionable opportunity for which the register holds no decision
 * for `intraday_opportunity` + `opportunity_id` - a claim the register has to have been read to
 * make.
 */
export function dayBoardDecisions(
  opportunities: readonly IntradayOpportunityDTO[],
  decisions: readonly ReviewDecisionDTO[],
  registerRead: boolean,
): DayBoardDecisionSection {
  const actionable = opportunities.filter(
    (opportunity) => opportunity.status === ACTIONABLE_OPPORTUNITY_STATUS,
  );

  if (!registerRead) {
    // The register was not read, so nothing here can say an opportunity has no decision. The
    // actionable opportunities themselves are a different read, and the panel does not even
    // render their count in this branch - it would read as work the register had cleared.
    return { posture: "not-read", rows: [], actionableCount: actionable.length, decidedCount: null };
  }

  const decided = new Set(
    decisions
      .filter((decision) => decision.entity_type === OPPORTUNITY_ENTITY_TYPE)
      .map((decision) => decisionKey(decision.entity_type, decision.entity_id)),
  );
  const rows = actionable
    .filter(
      (opportunity) => !decided.has(decisionKey(OPPORTUNITY_ENTITY_TYPE, opportunity.opportunity_id)),
    )
    .map(actionRow)
    .sort(byDeadline((row) => row.validUntilUtc, (row) => row.opportunityId));

  return {
    posture: "measured",
    rows,
    actionableCount: actionable.length,
    decidedCount: actionable.length - rows.length,
  };
}

/** An open alert that has moved since it was first seen. */
function alertMoved(alert: MonitoringAlertDTO): boolean {
  if (alert.occurrence_count > 1) return true;
  // An instant the client cannot read is not evidence of movement, so it is not counted as one.
  const updated = Date.parse(alert.updated_at_utc);
  const detected = Date.parse(alert.detected_at_utc);
  if (Number.isNaN(updated) || Number.isNaN(detected)) return false;
  return updated > detected;
}

/**
 * Section 3. Counts and one instant, measured from the summary the monitoring lane read. The alert
 * list itself belongs to the top bar's alert centre, so this section points there instead of
 * rendering a second one.
 */
export function dayBoardAlerts(
  summary: MonitoringSummaryDTO | null,
  meta: ApiMeta | null,
  alerts: readonly MonitoringAlertDTO[],
): DayBoardAlertSection {
  const read = readState(meta);
  // A summary is only a measurement when the envelope says so *and* the payload is there: a read
  // that answered with no summary established nothing about alert counts.
  if (!summary || read.posture !== "measured") {
    return {
      posture: !summary ? "not-read" : read.posture,
      openCount: null,
      criticalCount: null,
      warningCount: null,
      latestMovementUtc: null,
      movedCount: null,
    };
  }

  const moved = alerts.filter((alert) => alert.status === "open" && alertMoved(alert));
  const instants = moved
    .map((alert) => alert.updated_at_utc)
    .filter((value) => Number.isFinite(instantMs(value)));
  const latest = instants.reduce<string | null>(
    (newest, value) =>
      newest === null || instantMs(value) > instantMs(newest) ? value : newest,
    null,
  );

  return {
    posture: "measured",
    openCount: summary.open_count,
    criticalCount: summary.critical_count,
    warningCount: summary.warning_count,
    latestMovementUtc: latest,
    movedCount: moved.length,
  };
}

/** Compose the three sections on one as-of. */
export function dayBoardModel(inputs: DayBoardInputs): DayBoardModel {
  return {
    clock: dayBoardClock(inputs.windowsRead, inputs.windowsMeta),
    decisions: dayBoardDecisions(
      inputs.opportunities,
      inputs.reviewDecisions,
      inputs.reviewRegisterRead,
    ),
    alerts: dayBoardAlerts(inputs.monitoringSummary, inputs.monitoringMeta, inputs.monitoringAlerts),
    measuredAtUtc: inputs.now,
  };
}

/**
 * How the clock on one deadline reads right now.
 *
 * The arithmetic is deliberately trivial and floors: `minutes`/`hours` are a lower bound on the
 * time left, because a descriptor that rounds a deadline up tells a trader there is more time than
 * the instant the API declared. It is measured against the caller's `now`, which the surface labels
 * as the browser's clock - the deadline itself is the API's declared instant and is rendered
 * separately.
 */
export interface DayBoardCountdown {
  /** `unknown` when the deadline instant could not be read at all. */
  readonly state: "unknown" | "overdue" | "due" | "minutes" | "hours";
  /** The whole measure the descriptor states; 0 when the state carries none. */
  readonly amount: number;
  /** The translated word for the state. */
  readonly labelKey: string;
  /** The unit key the amount is expressed in, or null when the state carries no amount. */
  readonly unitKey: string | null;
}

const MINUTE_MS = 60_000;
const HOUR_MS = 3_600_000;

export function dayBoardCountdown(deadlineUtc: string, nowUtc: string): DayBoardCountdown {
  const deadline = Date.parse(deadlineUtc);
  const now = Date.parse(nowUtc);
  if (Number.isNaN(deadline) || Number.isNaN(now)) {
    return {
      state: "unknown",
      amount: 0,
      labelKey: "day_board.countdown.unknown",
      unitKey: null,
    };
  }

  const remaining = deadline - now;
  if (remaining < 0) {
    return {
      state: "overdue",
      // A deadline missed by less than a minute is still missed.
      amount: Math.max(1, Math.floor(-remaining / MINUTE_MS)),
      labelKey: "day_board.countdown.overdue",
      unitKey: "day_board.countdown.unit_minutes",
    };
  }
  if (remaining === 0) {
    return { state: "due", amount: 0, labelKey: "day_board.countdown.due", unitKey: null };
  }
  if (remaining < HOUR_MS) {
    return {
      state: "minutes",
      // Time left under a minute is still time left; rounding it to zero would read as the
      // deadline itself.
      amount: Math.max(1, Math.floor(remaining / MINUTE_MS)),
      labelKey: "day_board.countdown.in",
      unitKey: "day_board.countdown.unit_minutes",
    };
  }
  return {
    state: "hours",
    amount: Math.max(1, Math.floor(remaining / HOUR_MS)),
    labelKey: "day_board.countdown.in",
    unitKey: "day_board.countdown.unit_hours",
  };
}
