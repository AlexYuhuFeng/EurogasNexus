/**
 * The Source Center's own registry read state.
 *
 * The surface renders a slice the workspace batch fills, and a slice cannot tell a failed read
 * from a measured zero: the batch clears `sources` when its read fails, so the strip's "Total
 * sources 0" and the catalog's "No active warnings" were statements about a read that had not
 * answered (recorded in `docs/release/FUNCTIONAL_ACCEPTANCE_REPORT.md`, 2026-09-25 limits).
 *
 * Five states name what the surface actually knows - `unread`, `pending`, `failed`, a measured
 * `empty`, a measured `ready` - and two rules keep it honest:
 *
 * - numbers and rows are presented only while a committed reading exists (`hasReading`): a read
 *   that answered, even with zero rows, is a measurement, while a read that never answered is
 *   not, and rows held from an earlier read are the last committed reading rather than a fresh
 *   one;
 * - the failure keeps the shared taxonomy (`endpointFailures` label and safe code, and the
 *   bounded retry surface whose control is disabled exactly while an attempt is in flight)
 *   instead of inventing wording or a second retry model of its own.
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

/** What the surface knows about its own read of the source registry. */
export type SourceRegistryReadState = "unread" | "pending" | "failed" | "empty" | "ready";

export interface SourceRegistryReadFacts {
  /** Rows the store holds for the registry lane. */
  rowCount: number;
  /** True while the workspace batch, or its bounded retry pass, is in flight. */
  loading: boolean;
  /** Workspace passes committed in this session; 0 means the lane has never answered. */
  committedPasses: number;
  /** The failure the store recorded for the sources endpoint, if any. */
  error?: string | null;
  /** The store's safe machine code for that failure, if any. */
  errorCode?: string | null;
  /** The store's own retry bookkeeping. */
  retry: EndpointRetryState;
}

export interface SourceRegistryReadSurface {
  state: SourceRegistryReadState;
  /** True while a committed reading exists: rows, or a read that answered with none. */
  hasReading: boolean;
  /**
   * The one-sentence state copy the surface renders in place of a measurement, or null in the two
   * measured states. It is a key, never text: a surface translates it like every other string.
   */
  noticeKey: string | null;
  /** The shared endpoint label for the failed read, or null in the other states. */
  failureEndpointKey: string | null;
  /** The shared safe-code message for the failed read, or null in the other states. */
  failureMessageKey: string | null;
  /** The bounded retry: disabled exactly while an attempt is in flight. */
  retry: EndpointRetrySurface;
}

const NOTICE_KEYS: Readonly<Record<SourceRegistryReadState, string | null>> = {
  unread: "sources.registry.unread",
  pending: "sources.registry.pending",
  failed: "sources.registry.failed",
  empty: null,
  ready: null,
};

/**
 * What the surface may state about the registry, from the store's own facts.
 *
 * A failure outranks everything the lane holds: the newest read of this lane did not answer, so
 * no number may be presented as fresh. It does not erase a reading outright - a lane that still
 * holds rows keeps them, and the caller says they are the last committed reading.
 *
 * `loading` outranks the row count for the same reason in the other direction: while a read is in
 * flight the surface is `pending`, whatever it happens to be showing from before.
 */
export function sourceRegistryReadSurface(
  facts: SourceRegistryReadFacts,
  t: TFunction,
): SourceRegistryReadSurface {
  const error = typeof facts.error === "string" && facts.error.trim() !== ""
    ? facts.error
    : null;
  const rows = Number.isFinite(facts.rowCount) && facts.rowCount > 0
    ? Math.floor(facts.rowCount)
    : 0;
  const committed = Number.isFinite(facts.committedPasses) && facts.committedPasses > 0
    ? Math.floor(facts.committedPasses)
    : 0;

  const state: SourceRegistryReadState = error
    ? "failed"
    : facts.loading
      ? "pending"
      : rows > 0
        ? "ready"
        : committed > 0
          ? "empty"
          : "unread";

  return {
    state,
    // A measured zero is an answer this surface may print; an unread lane is not.
    hasReading: rows > 0 || (committed > 0 && error === null),
    noticeKey: NOTICE_KEYS[state],
    failureEndpointKey: error
      ? (ENDPOINT_FAILURE_LABEL_KEYS.sources ?? UNKNOWN_ENDPOINT_FAILURE_LABEL_KEY)
      : null,
    failureMessageKey: error
      ? ENDPOINT_FAILURE_CODE_KEYS[safeEndpointFailureCode(facts.errorCode)]
      : null,
    retry: describeEndpointRetry(facts.retry, t),
  };
}
