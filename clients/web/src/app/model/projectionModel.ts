/**
 * Shared projection reading helpers (Architecture V2 Wave 5).
 *
 * Every projection under `/api/projections/...` has the same shape: one `as_of_utc`,
 * one time basis, and named slices that each carry availability, freshness,
 * entitlement and the bound that was applied. These helpers read that structure
 * once, so every surface applies the same honesty rules instead of re-implementing
 * them per workspace:
 *
 * - a slice the backend marks unavailable is reported as unavailable, never as an
 *   empty list that reads like "no data in this market";
 * - a slice whose rows an entitlement withheld is reported as restricted with the
 *   withheld count, never as a zero;
 * - degradation is freshness and availability only - a slice the backend served in
 *   full minus entitled rows is restricted, not stale;
 * - the as-of and the freshness are the backend's answers; the client never
 *   recomputes them from wall-clock time.
 */

import type { ProjectionSliceDTO } from "@/api/client";

/** Read one slice out of a projection's slice map without widening the projection type. */
function sliceOf(slices: unknown, key: string): ProjectionSliceDTO<unknown> | undefined {
  return (slices as Record<string, ProjectionSliceDTO<unknown> | undefined> | undefined)?.[key];
}

export interface SliceReading {
  readonly key: string;
  readonly available: boolean;
  readonly rowCount: number;
  readonly freshnessState: string;
  readonly lastObservedAtUtc: string | null;
  readonly expectedWithinMinutes: number | null;
  readonly restricted: boolean;
  readonly filteredOut: number;
  readonly contextRule: string | null;
  readonly notes: readonly string[];
}

function readingFor(key: string, slice: ProjectionSliceDTO<unknown> | undefined): SliceReading {
  return {
    key,
    available: slice?.available === true,
    rowCount: slice?.row_count ?? 0,
    freshnessState: (slice?.freshness?.state ?? "UNKNOWN").toUpperCase(),
    lastObservedAtUtc: slice?.freshness?.last_observed_at_utc ?? null,
    expectedWithinMinutes: slice?.freshness?.expected_within_minutes ?? null,
    restricted: slice ? (slice.entitlement?.filtered_out ?? 0) > 0 : false,
    filteredOut: slice?.entitlement?.filtered_out ?? 0,
    contextRule: slice?.context_filter?.rule ?? null,
    notes: slice?.notes ?? [],
  };
}

/** One reading per slice, in the surface's reading order. */
export function projectionSliceReadings<Slices extends object, Key extends keyof Slices & string>(
  slices: Slices | null | undefined,
  order: readonly Key[],
): SliceReading[] {
  if (!slices) return [];
  return order.map((key) => readingFor(key, sliceOf(slices, key)));
}

/** Readings that are stale, missing or unavailable, so a surface can qualify a value. */
export function degradedReadings(readings: readonly SliceReading[]): SliceReading[] {
  return readings.filter(
    (reading) => !reading.available || reading.freshnessState !== "FRESH",
  );
}

/**
 * The rows a slice carries, or an empty list when the backend did not make it
 * available. Callers that must tell an unavailable slice apart from an empty one use
 * the readings; this helper is for rendering tables.
 */
export function projectionSliceRows<Row, Slices extends object, Key extends keyof Slices & string>(
  slices: Slices | null | undefined,
  key: Key,
): Row[] {
  const slice = slices ? sliceOf(slices, key) : undefined;
  if (!slice?.available) return [];
  return (slice.rows ?? []) as Row[];
}

/** The payload a payload-carrying slice (an aggregate, not a row set) reports. */
export function projectionSlicePayload<
  Payload,
  Slices extends object,
  Key extends keyof Slices & string,
>(slices: Slices | null | undefined, key: Key): Payload | null {
  const slice = slices ? sliceOf(slices, key) : undefined;
  if (!slice?.available) return null;
  return (slice.payload ?? null) as Payload | null;
}

/**
 * Whether a projection may be used as a surface's coherent source: an absent
 * payload, or one whose named anchor slice the backend did not serve, means the
 * caller must fall back to what it read before - explicitly, and never by treating
 * missing rows as an empty result.
 */
export function projectionSliceIsAvailable(slices: unknown, key: string): boolean {
  return sliceOf(slices, key)?.available === true;
}
