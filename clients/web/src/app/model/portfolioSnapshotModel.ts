/**
 * Portfolio snapshot presentation model (Architecture V2 Wave 5, client half).
 *
 * The portfolio surface used to join `/portfolio/live-summary`,
 * `/portfolio/screen-orders` and `/portfolio/pnl-snapshots` (plus upstream
 * contracts) and reconcile their timestamps itself. The projection gives it one
 * coherent read model instead: one as-of, one time basis, and per-slice freshness
 * and entitlement.
 *
 * The summary slice is an aggregate, not a row set, so it is read as a payload. A
 * summary that the backend could not build is `null` - never a zero-valued summary,
 * because "no exposure" and "not measured" are different answers.
 */

import type {
  PortfolioLiveSummaryDTO,
  PortfolioPnlSnapshotDTO,
  PortfolioSnapshotProjectionDTO,
  ScreenOrderObservationDTO,
  UpstreamContractDTO,
} from "@/api/client";
import {
  degradedReadings,
  projectionSliceIsAvailable,
  projectionSlicePayload,
  projectionSliceRows,
  projectionSliceReadings,
  type SliceReading,
} from "./projectionModel.ts";

export type { SliceReading };

export type PortfolioSliceKey = keyof PortfolioSnapshotProjectionDTO["slices"];

export const PORTFOLIO_SNAPSHOT_SLICE_ORDER: PortfolioSliceKey[] = [
  "summary",
  "screen_orders",
  "pnl_snapshots",
  "contracts",
  "resources",
  "data_sources",
];

/** Translation keys for the slice labels the surface renders. */
export const PORTFOLIO_SNAPSHOT_SLICE_LABEL_KEYS: Readonly<Record<PortfolioSliceKey, string>> = {
  summary: "portfolio_context.slice.summary",
  screen_orders: "portfolio_context.slice.screen_orders",
  pnl_snapshots: "portfolio_context.slice.pnl_snapshots",
  contracts: "portfolio_context.slice.contracts",
  resources: "portfolio_context.slice.resources",
  data_sources: "portfolio_context.slice.data_sources",
};

/** One row per slice, in reading order, for the surface's status strip. */
export function portfolioReadings(
  projection: PortfolioSnapshotProjectionDTO | null | undefined,
): SliceReading[] {
  return projectionSliceReadings(projection?.slices, PORTFOLIO_SNAPSHOT_SLICE_ORDER);
}

/** Slices that are stale, missing or unavailable. */
export function degradedPortfolioSlices(
  projection: PortfolioSnapshotProjectionDTO | null | undefined,
): SliceReading[] {
  return degradedReadings(portfolioReadings(projection));
}

/**
 * The live summary the projection measured, or `null` when the backend could not
 * build it. A caller must not substitute a zero summary for a missing one.
 */
export function snapshotSummary(
  projection: PortfolioSnapshotProjectionDTO | null | undefined,
): PortfolioLiveSummaryDTO | null {
  return projectionSlicePayload<
    PortfolioLiveSummaryDTO,
    PortfolioSnapshotProjectionDTO["slices"],
    PortfolioSliceKey
  >(projection?.slices, "summary");
}

export function snapshotScreenOrders(
  projection: PortfolioSnapshotProjectionDTO | null | undefined,
): ScreenOrderObservationDTO[] {
  return projectionSliceRows<
    ScreenOrderObservationDTO,
    PortfolioSnapshotProjectionDTO["slices"],
    PortfolioSliceKey
  >(projection?.slices, "screen_orders");
}

export function snapshotPnlSnapshots(
  projection: PortfolioSnapshotProjectionDTO | null | undefined,
): PortfolioPnlSnapshotDTO[] {
  return projectionSliceRows<
    PortfolioPnlSnapshotDTO,
    PortfolioSnapshotProjectionDTO["slices"],
    PortfolioSliceKey
  >(projection?.slices, "pnl_snapshots");
}

export function snapshotContracts(
  projection: PortfolioSnapshotProjectionDTO | null | undefined,
): UpstreamContractDTO[] {
  return projectionSliceRows<
    UpstreamContractDTO,
    PortfolioSnapshotProjectionDTO["slices"],
    PortfolioSliceKey
  >(projection?.slices, "contracts");
}

/** The single as-of instant the whole payload shares. */
export function snapshotAsOf(
  projection: PortfolioSnapshotProjectionDTO | null | undefined,
): string | null {
  return projection?.as_of_utc ?? null;
}

/** The declared time basis, as the backend stated it. */
export function snapshotTimeBasis(
  projection: PortfolioSnapshotProjectionDTO | null | undefined,
): Record<string, unknown> | null {
  return projection?.time_basis ?? null;
}

/**
 * Whether the payload may be used as the portfolio surface's coherent source. An
 * absent payload, or one whose summary slice the backend did not serve, means the
 * surface keeps what it read before rather than reading a missing portfolio as an
 * empty one.
 */
export function snapshotIsUsable(
  projection: PortfolioSnapshotProjectionDTO | null | undefined,
): boolean {
  if (!projection) return false;
  return projectionSliceIsAvailable(projection.slices, "summary");
}

/**
 * Why the resource-pool slice is not part of this read, when the backend says so.
 * The slice is declared rather than approximated: composing executable sale options
 * is a route-local read today, and a projection must not invent it.
 */
export function snapshotResourceNote(
  projection: PortfolioSnapshotProjectionDTO | null | undefined,
): string | null {
  const reading = portfolioReadings(projection).find((item) => item.key === "resources");
  if (!reading) return null;
  return reading.notes.length > 0 ? reading.notes[0] : null;
}
