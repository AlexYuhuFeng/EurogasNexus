/**
 * Market context presentation model (Architecture V2 Wave 5, client half).
 *
 * The projection is the market surface's coherent read model: one as-of instant,
 * one time basis, and per-slice freshness and entitlement. These helpers turn that
 * payload into what a trader needs to read before trusting a number - when it was
 * taken, which slices are usable, which are stale or missing, and what the backend
 * withheld - instead of the surface joining several endpoints and reconciling
 * their timestamps itself.
 *
 * Rules:
 *
 * - a slice the backend marks unavailable is reported as unavailable, never as an
 *   empty list that reads like "no data in the market";
 * - a restricted slice is reported as restricted, never as a zero;
 * - the client renders the backend's as-of and freshness; it does not recompute
 *   freshness from wall-clock time.
 */

import type {
  IntradayOpportunityDTO,
  MarketContextProjectionDTO,
  MarketObsDTO,
  MarketQuoteDTO,
  MonitoringAlertDTO,
  NormalizedMarketObsDTO,
  ProjectionSliceDTO,
} from "@/api/client";

export type ProjectionSliceKey = keyof MarketContextProjectionDTO["slices"];

export const MARKET_CONTEXT_SLICE_ORDER: ProjectionSliceKey[] = [
  "quotes",
  "normalized_quotes",
  "market_observations",
  "intraday_opportunities",
  "spreads",
  "monitoring",
  "data_sources",
];

/** Translation keys for the slice labels the surface renders. */
export const MARK_CONTEXT_SLICE_LABEL_KEYS: Readonly<Record<ProjectionSliceKey, string>> = {
  quotes: "market_context.slice.quotes",
  normalized_quotes: "market_context.slice.normalized_quotes",
  market_observations: "market_context.slice.market_observations",
  intraday_opportunities: "market_context.slice.intraday_opportunities",
  spreads: "market_context.slice.spreads",
  monitoring: "market_context.slice.monitoring",
  data_sources: "market_context.slice.data_sources",
};

export interface SliceReading {
  readonly key: ProjectionSliceKey;
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

/** One row per slice, in reading order, for the surface's status strip. */
export function sliceReadings(
  projection: MarketContextProjectionDTO | null | undefined,
): SliceReading[] {
  if (!projection) return [];
  return MARKET_CONTEXT_SLICE_ORDER.map((key) => {
    const slice = projection.slices[key] as ProjectionSliceDTO<unknown> | undefined;
    return {
      key,
      available: slice?.available === true,
      rowCount: slice?.row_count ?? 0,
      freshnessState: (slice?.freshness?.state ?? "UNKNOWN").toUpperCase(),
      lastObservedAtUtc: slice?.freshness?.last_observed_at_utc ?? null,
      expectedWithinMinutes: slice?.freshness?.expected_within_minutes ?? null,
      restricted: slice?.entitlement ? slice.entitlement.filtered_out > 0 : false,
      filteredOut: slice?.entitlement?.filtered_out ?? 0,
      contextRule: slice?.context_filter?.rule ?? null,
      notes: slice?.notes ?? [],
    };
  });
}

/** Slices that are stale, missing or unavailable, so a surface can qualify a value. */
export function degradedSlices(
  projection: MarketContextProjectionDTO | null | undefined,
): SliceReading[] {
  return sliceReadings(projection).filter(
    (reading) => !reading.available || reading.freshnessState !== "FRESH",
  );
}

/**
 * The rows a slice carries, or an empty list when the backend did not make it
 * available. Callers that need to distinguish "unavailable" from "empty" must use
 * `sliceReadings`/`degradedSlices`; this helper is for rendering tables.
 */
export function sliceRows<Row>(
  projection: MarketContextProjectionDTO | null | undefined,
  key: ProjectionSliceKey,
): Row[] {
  const slice = projection?.slices?.[key] as ProjectionSliceDTO<Row> | undefined;
  if (!slice?.available) return [];
  return slice.rows ?? [];
}

export function contextQuotes(
  projection: MarketContextProjectionDTO | null | undefined,
): MarketQuoteDTO[] {
  return sliceRows<MarketQuoteDTO>(projection, "quotes");
}

export function contextNormalizedRows(
  projection: MarketContextProjectionDTO | null | undefined,
): NormalizedMarketObsDTO[] {
  return sliceRows<NormalizedMarketObsDTO>(projection, "normalized_quotes");
}

export function contextObservations(
  projection: MarketContextProjectionDTO | null | undefined,
): MarketObsDTO[] {
  return sliceRows<MarketObsDTO>(projection, "market_observations");
}

export function contextOpportunities(
  projection: MarketContextProjectionDTO | null | undefined,
): IntradayOpportunityDTO[] {
  return sliceRows<IntradayOpportunityDTO>(projection, "intraday_opportunities");
}

export function contextAlerts(
  projection: MarketContextProjectionDTO | null | undefined,
): MonitoringAlertDTO[] {
  return sliceRows<MonitoringAlertDTO>(projection, "monitoring");
}

/** The single as-of instant the whole payload shares. */
export function contextAsOf(
  projection: MarketContextProjectionDTO | null | undefined,
): string | null {
  return projection?.as_of_utc ?? null;
}

/** The declared time basis, as the backend stated it (gas day, basis id, zone). */
export function contextTimeBasis(
  projection: MarketContextProjectionDTO | null | undefined,
): Record<string, unknown> | null {
  return projection?.time_basis ?? null;
}

/**
 * Whether the payload may be used as the market surface's coherent source. An
 * absent projection, or one whose quotes slice the backend did not serve, means the
 * surface must fall back to the per-endpoint reads it used before - explicitly, and
 * never by treating missing rows as an empty market.
 */
export function contextIsUsable(
  projection: MarketContextProjectionDTO | null | undefined,
): boolean {
  if (!projection) return false;
  return projection.slices.quotes?.available === true;
}
