/**
 * Analysis Snapshot recording (Architecture V2 Wave 4, client half).
 *
 * The platform can record an Analysis Snapshot - the reproducibility reference a later run
 * cites - but nothing in the product did, so a user could only cite a snapshot some other
 * caller had recorded. This module is the rule for recording one from the Active Context the
 * user is standing in.
 *
 * Three things it decides rather than leaves to the caller:
 *
 * - **which keys may be sent.** The backend accepts a declared subset of Active Context keys
 *   and refuses anything else (`active_context_key_unsupported`), so the client sends only
 *   keys from that list. A context key that exists in the shell but is not expressible is
 *   omitted here and refused by the backend if it ever reaches it - never silently dropped
 *   into a snapshot that claims to describe the context.
 * - **when recording is allowed.** A snapshot is persisted evidence, so the route answers 503
 *   without a runtime database; a run already in flight blocks a second one; and a context
 *   with nothing in it is refused here, because a descriptor that freezes nothing is not
 *   evidence of anything.
 * - **what is sent.** Only the supported, non-empty context keys, plus the instant the caller
 *   froze. No client-invented key, no assumption, and no field the backend would have to guess.
 */

/**
 * Active Context keys the backend accepts (`ACTIVE_CONTEXT_KEYS` in
 * `domain/data_platform/snapshots.py`). Mirrored, not invented: the snapshot request is refused
 * for anything else, so a surface must not offer what the route will reject.
 */
export const SNAPSHOT_CONTEXT_KEYS = [
  "workspace",
  "task",
  "gas_day",
  "product",
  "hub",
  "route_id",
  "resource_id",
  "strategy_id",
  "strategy_version_id",
  "strategy_run_id",
  "portfolio_id",
] as const;

export type SnapshotContextKey = (typeof SNAPSHOT_CONTEXT_KEYS)[number];

export interface AnalysisSnapshotRequest {
  readonly as_of_utc: string;
  readonly active_context: Record<string, string>;
}

export interface AnalysisSnapshotReadiness {
  readonly canRecord: boolean;
  readonly blockerKeys: readonly string[];
  readonly firstBlockerKey: string | null;
}

/**
 * Whether the current context may be recorded, and what has to be true first.
 *
 * The runtime database is checked first because the route refuses the write without one; an
 * empty context is checked next, because freezing nothing records a descriptor that names no
 * version set; a run in flight is last, so a transient state never hides a real precondition.
 */
export function analysisSnapshotReadiness(input: {
  /** The Active Context values the shell holds, keyed by their context names. */
  readonly context: Partial<Record<SnapshotContextKey, string | null | undefined>>;
  readonly runtimeDbReady: boolean;
  readonly recording: boolean;
}): AnalysisSnapshotReadiness {
  const blockerKeys: string[] = [];
  if (!input.runtimeDbReady) blockerKeys.push("review.snapshot.blocker.runtime_db");
  if (snapshotContextValues(input.context).length === 0) {
    blockerKeys.push("review.snapshot.blocker.empty_context");
  }
  if (input.recording) blockerKeys.push("review.snapshot.blocker.in_flight");
  return {
    canRecord: blockerKeys.length === 0,
    blockerKeys,
    firstBlockerKey: blockerKeys.length > 0 ? blockerKeys[0] : null,
  };
}

/** The context entries that will actually be sent, in the contract's declaration order. */
export function snapshotContextValues(
  context: Partial<Record<SnapshotContextKey, string | null | undefined>>,
): Array<[SnapshotContextKey, string]> {
  const entries: Array<[SnapshotContextKey, string]> = [];
  for (const key of SNAPSHOT_CONTEXT_KEYS) {
    const value = (context[key] ?? "").trim();
    if (value) entries.push([key, value]);
  }
  return entries;
}

/**
 * The request body for the context as it stands.
 *
 * `as_of_utc` is supplied by the caller rather than read from the clock here, so the rule stays
 * pure and the instant a snapshot claims is the instant the surface froze it.
 */
export function analysisSnapshotRequest(
  context: Partial<Record<SnapshotContextKey, string | null | undefined>>,
  asOfUtc: string,
): AnalysisSnapshotRequest {
  return {
    as_of_utc: asOfUtc,
    active_context: Object.fromEntries(snapshotContextValues(context)),
  };
}

/**
 * A context projection of the whole shell context, keeping only the keys a snapshot may carry.
 *
 * The shell's Active Context is wider than the backend can express (organisation and a decision
 * case are declared unsupported), so this is the one place that narrowing happens.
 */
export function snapshotContextFrom(
  context: Record<string, string | null | undefined>,
): Partial<Record<SnapshotContextKey, string>> {
  const narrowed: Partial<Record<SnapshotContextKey, string>> = {};
  for (const key of SNAPSHOT_CONTEXT_KEYS) {
    const value = (context[key] ?? "").trim();
    if (value) narrowed[key] = value;
  }
  return narrowed;
}
