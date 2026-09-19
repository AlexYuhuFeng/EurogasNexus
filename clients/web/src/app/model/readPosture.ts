/**
 * How well a read answered (slice D of the D3 decision).
 *
 * The reference-network and contract routes answer an unconfigured runtime database with an
 * **empty list plus a stated reason** (`meta.missing_inputs`, and a
 * `runtime-db-not-configured` source), because the API never synthesizes topology or contracts.
 * That makes two different statements - the read established nothing, and the read established an
 * empty register - collapse into one line if a surface renders both as `0`, which states a fact
 * the deployment never established.
 *
 * This module is the one place that tells them apart, from the envelope the route actually sends
 * rather than from the row count.
 */

import type { ApiMeta } from "@/api/client";

/** What a read established. */
export type ReadPosture = "measured" | "runtime-db-not-configured" | "not-read";

export interface ReadState {
  readonly posture: ReadPosture;
  /** The inputs the read needed and did not have, named by the deployment. */
  readonly missingInputs: readonly string[];
  /** Where the rows came from, when the envelope says so. */
  readonly source: string | null;
}

/** The declared source tag a route uses when no runtime database is configured. */
const NOT_CONFIGURED_SOURCE = "runtime-db-not-configured";

/**
 * Read the posture of one response envelope.
 *
 * A meta with `missing_inputs` is not a measurement: the route is saying which input it lacked.
 * So is a `runtime-db-not-configured` source. Anything else is a measurement - including a
 * measurement of zero rows, which is a fact about the deployment and is rendered as one.
 */
export function readState(meta: ApiMeta | null | undefined): ReadState {
  if (!meta) return { posture: "not-read", missingInputs: [], source: null };
  const missingInputs = meta.missing_inputs ?? [];
  const sources = meta.source_references ?? [];
  if (missingInputs.length > 0 || sources.includes(NOT_CONFIGURED_SOURCE)) {
    return {
      posture: "runtime-db-not-configured",
      missingInputs,
      source: sources[0] ?? null,
    };
  }
  return { posture: "measured", missingInputs: [], source: sources[0] ?? null };
}

/**
 * The bound the reference-network reads ask for, mirroring `REFERENCE_NETWORK_READ_LIMIT` in the
 * API client and the route's own `limit` ceiling.
 *
 * It is stated on the surface because a bounded read that returns exactly its bound may have more
 * behind it: the panel says the list is the first N rather than implying it is all of them.
 */
export const REFERENCE_READ_LIMIT = 2000;

/** Whether a returned list reached the read's bound, so more rows may exist. */
export function readMayBeTruncated(rowCount: number): boolean {
  return rowCount >= REFERENCE_READ_LIMIT;
}
