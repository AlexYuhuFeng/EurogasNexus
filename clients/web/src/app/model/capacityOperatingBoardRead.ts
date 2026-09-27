/**
 * The capacity operating board's own read state.
 *
 * The board is not one read: its rows are a join of two workspace reads keyed `point_id:direction`
 * (`flows` and `capacity`), and the batch clears the rows of a read that failed. A joined board
 * therefore cannot tell a failed read from a measured zero either - a board of "0 / 0" with the
 * filter sentence "No operating points match the current filters." was reachable from a read that
 * never answered (`docs/release/FUNCTIONAL_ACCEPTANCE_REPORT.md`, 2026-09-27 capacity diagnosis).
 *
 * Six states name what the board actually knows - `unread`, `pending`, `failed`, `partial` (one
 * required read did not answer, the other's rows are held), a measured `empty`, a measured `ready`
 * - with two rules:
 *
 * - only a board whose two required reads both answered may state a count, a KPI or a filter
 *   result (`measured`): a read that never answered is not a board of zero, and a measured empty
 *   result is not a filter that matched nothing;
 * - a failure keeps the shared taxonomy (`endpointFailures` label and safe code, and the bounded
 *   retry surface whose control is disabled exactly while an attempt is in flight) instead of
 *   inventing wording or a second retry model of its own.
 */

import type { TFunction } from "i18next";

import {
  describeEndpointRetry,
  ENDPOINT_FAILURE_CODE_KEYS,
  ENDPOINT_FAILURE_LABEL_KEYS,
  safeEndpointFailureCode,
  UNKNOWN_ENDPOINT_FAILURE_LABEL_KEY,
  type EndpointRetryState,
  type EndpointRetrySurface,
} from "@/app/model/endpointFailures";

/** The two reads the board's rows are joined from: both are required for a measurement. */
export const CAPACITY_BOARD_READ_LANES = ["flows", "capacity"] as const;
export type CapacityBoardReadLane = (typeof CAPACITY_BOARD_READ_LANES)[number];

/** What the store holds for one required read. */
export interface CapacityBoardReadLaneFacts {
  rows: number;
  error?: string | null;
  errorCode?: string | null;
}

export interface CapacityOperatingBoardReadFacts {
  flows: CapacityBoardReadLaneFacts;
  capacity: CapacityBoardReadLaneFacts;
  /** True while the workspace batch, or its bounded retry pass, is in flight. */
  loading: boolean;
  /** Workspace passes committed in this session; 0 means no read has answered. */
  committedPasses: number;
  /** The store's own retry bookkeeping. */
  retry: EndpointRetryState;
}

/** What the board knows about its own reads. */
export type CapacityBoardReadState =
  | "unread"
  | "pending"
  | "failed"
  | "partial"
  | "empty"
  | "ready";

export interface CapacityBoardFailedRead {
  lane: CapacityBoardReadLane;
  /** Shared endpoint label for the failed read, never a loader key. */
  labelKey: string;
  /** Shared safe-code message for the failed read, never the backend's prose. */
  messageKey: string;
}

export interface CapacityOperatingBoardReadSurface {
  state: CapacityBoardReadState;
  /** True while rows (whichever read answered) or a fully measured board are on screen. */
  hasReading: boolean;
  /**
   * True only when both required reads answered in this session. Only then may the board state a
   * count, a KPI or a filter result: one missing read is not a zero, and the rows held from one
   * read are not the joined set.
   */
  measured: boolean;
  /**
   * The one-sentence state copy the surface renders in place of a measurement, or null in the two
   * measured states. It is a key, never text: a surface translates it like every other string. A
   * caller that already has a reading on screen suppresses the non-failure states (the rule the
   * Source Center's registry notice follows); a failure always renders it.
   */
  noticeKey: string | null;
  /** The required reads that failed, with the shared vocabulary; at most one per lane. */
  failedReads: CapacityBoardFailedRead[];
  /** The bounded retry: disabled exactly while an attempt is in flight. */
  retry: EndpointRetrySurface;
}

const NOTICE_KEYS: Readonly<Record<CapacityBoardReadState, string | null>> = {
  unread: "capacity.board.unread",
  pending: "capacity.board.pending",
  failed: "capacity.board.failed",
  partial: "capacity.board.partial",
  empty: "capacity.board.empty",
  ready: null,
};

function laneError(facts: CapacityBoardReadLaneFacts): string | null {
  return typeof facts.error === "string" && facts.error.trim() !== "" ? facts.error : null;
}

function laneRows(facts: CapacityBoardReadLaneFacts): number {
  return Number.isFinite(facts.rows) && facts.rows > 0 ? Math.floor(facts.rows) : 0;
}

/**
 * What the board may state, from the store's own facts.
 *
 * A failed required read outranks everything else: the newest pass did not answer it, so no count
 * and no filter result may be presented. It does not erase the other read's rows - when the read
 * that answered holds any, they stay on screen as a `partial`, explicitly incomplete board.
 *
 * `loading` outranks the row count for the same reason in the other direction: while a pass is in
 * flight the board is `pending`, whatever it happens to be showing from before.
 */
export function capacityOperatingBoardRead(
  facts: CapacityOperatingBoardReadFacts,
  t: TFunction,
): CapacityOperatingBoardReadSurface {
  const committedPasses = Number.isFinite(facts.committedPasses) && facts.committedPasses > 0
    ? Math.floor(facts.committedPasses)
    : 0;
  const lanes = CAPACITY_BOARD_READ_LANES.map((lane) => ({ lane, facts: facts[lane] }));
  const failed = lanes.filter((entry) => laneError(entry.facts) !== null);
  const answered = lanes.filter(
    (entry) => laneError(entry.facts) === null && committedPasses > 0,
  );
  const rowsHeld = lanes.some(
    (entry) => laneError(entry.facts) === null && laneRows(entry.facts) > 0,
  );
  const measured = failed.length === 0 && answered.length === lanes.length;

  const state: CapacityBoardReadState = failed.length > 0
    ? rowsHeld
      ? "partial"
      : "failed"
    : facts.loading
      ? "pending"
      : measured
        ? rowsHeld
          ? "ready"
          : "empty"
        : "unread";

  return {
    state,
    hasReading: rowsHeld || measured,
    measured,
    noticeKey: NOTICE_KEYS[state],
    failedReads: failed.map((entry) => ({
      lane: entry.lane,
      labelKey:
        ENDPOINT_FAILURE_LABEL_KEYS[entry.lane] ?? UNKNOWN_ENDPOINT_FAILURE_LABEL_KEY,
      messageKey: ENDPOINT_FAILURE_CODE_KEYS[safeEndpointFailureCode(entry.facts.errorCode)],
    })),
    retry: describeEndpointRetry(facts.retry, t),
  };
}
