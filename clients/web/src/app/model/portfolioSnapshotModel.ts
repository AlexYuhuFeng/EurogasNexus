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
  PortfolioResourceDTO,
  PortfolioSnapshotProjectionDTO,
  ResourcePoolOptionsDTO,
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
 * The resource-pool block the projection composed, rebuilt into the shape the
 * surfaces already read.
 *
 * The `resources` slice carries the pool payload (scope, data source, portfolio
 * resources, blockers, warnings) with the executable sale options as its rows, so the
 * client can read the pool from the same coherent payload instead of asking the route
 * for a second composition of the same thing. The slice is strictly narrower than the
 * route: where the route applies no row filter, the projection filters both
 * contributing reads (route candidates and market observations) by entitlement, so a
 * withheld option is absent rather than re-derived on the client.
 *
 * Returns `null` when the backend did not serve the slice, or when it did not carry
 * the pool's identifying fields - the surface then keeps what it read before rather
 * than showing an empty pool.
 */
export function snapshotResourcePoolOptions(
  projection: PortfolioSnapshotProjectionDTO | null | undefined,
): ResourcePoolOptionsDTO | null {
  const payload = projectionSlicePayload<
    Record<string, unknown>,
    PortfolioSnapshotProjectionDTO["slices"],
    PortfolioSliceKey
  >(projection?.slices, "resources");
  if (!payload) return null;

  const scope = typeof payload.scope === "string" ? payload.scope : null;
  const dataSource = typeof payload.data_source === "string" ? payload.data_source : null;
  if (!scope || !dataSource) return null;

  const stringList = (value: unknown): string[] =>
    Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];

  return {
    scope,
    data_source: dataSource,
    portfolio_resources: Array.isArray(payload.portfolio_resources)
      ? (payload.portfolio_resources as PortfolioResourceDTO[])
      : [],
    sale_options: projectionSliceRows<
      ResourcePoolOptionsDTO["sale_options"][number],
      PortfolioSnapshotProjectionDTO["slices"],
      PortfolioSliceKey
    >(projection?.slices, "resources"),
    blockers: stringList(payload.blockers),
    warnings: stringList(payload.warnings),
  };
}

/**
 * What the backend says about the resource-pool slice it served.
 *
 * The slice is composed for real by the same application code the route calls, so the
 * note explains the slice's own boundaries: that entitlement filtering runs before the
 * composition, that a `*_MISSING` blocker may therefore mean "not entitled" rather than
 * "absent", and - when the runtime store could not serve it - that the block is the
 * route's identical degraded answer rather than a fabricated empty resource list.
 */
export function snapshotResourceNote(
  projection: PortfolioSnapshotProjectionDTO | null | undefined,
): string | null {
  const reading = portfolioReadings(projection).find((item) => item.key === "resources");
  if (!reading) return null;
  return reading.notes.length > 0 ? reading.notes[0] : null;
}
