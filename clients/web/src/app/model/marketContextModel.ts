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
} from "@/api/client";
import {
  degradedReadings,
  projectionSliceIsAvailable,
  projectionSliceRows,
  projectionSliceReadings,
  type SliceReading,
} from "./projectionModel.ts";

export type { SliceReading };

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

/** One row per slice, in reading order, for the surface's status strip. */
export function sliceReadings(
  projection: MarketContextProjectionDTO | null | undefined,
): SliceReading[] {
  return projectionSliceReadings(projection?.slices, MARKET_CONTEXT_SLICE_ORDER);
}

/** Slices that are stale, missing or unavailable, so a surface can qualify a value. */
export function degradedSlices(
  projection: MarketContextProjectionDTO | null | undefined,
): SliceReading[] {
  return degradedReadings(sliceReadings(projection));
}

/**
 * The rows a slice carries, or an empty list when the backend did not make it
 * available. Callers that need to tell an unavailable slice apart from an empty one
 * must use `sliceReadings`/`degradedSlices`; this helper is for rendering tables.
 */
export function sliceRows<Row>(
  projection: MarketContextProjectionDTO | null | undefined,
  key: ProjectionSliceKey,
): Row[] {
  return projectionSliceRows<Row, MarketContextProjectionDTO["slices"], ProjectionSliceKey>(
    projection?.slices,
    key,
  );
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

/**
 * The declared time basis, as the backend stated it: the basis of every value (`time_basis.basis`),
 * the gas day and the frozen gas-day calendar version that encoded that day's boundaries.
 */
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
  return projectionSliceIsAvailable(projection.slices, "quotes");
}
