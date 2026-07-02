type Translate = (key: string) => string;
type RouteState = ResourcePoolMapPath["routeState"];
export type RouteGeometryState =
  | "surveyed_pipeline_route"
  | "source_derived_leg_sequence"
  | "source_derived_corridor"
  | "directLineFallback";

export interface ResourcePoolMapPath {
  pathId: string;
  routeId: string;
  resourceName: string;
  sourcePointName: string;
  targetPointName: string;
  availableQuantityMwhPerDay: number;
  allocatedQuantityMwhPerDay: number | null;
  capacityLimitMwhPerDay: number | null;
  routeCostGbpMwh: number | null;
  salePriceGbpMwh: number | null;
  netMarginGbpMwh: number | null;
  routeState: "allocated" | "candidate" | "blocked";
  routeGeometryState: RouteGeometryState;
  routeGeometryWarning: string | null;
  routeLegSummary: string[];
  warnings: string[];
}

interface ResourcePoolPathOverlayProps {
  paths: ResourcePoolMapPath[];
  blockers: string[];
  t: Translate;
}

function formatQuantity(value: number | null): string {
  if (value === null || Number.isNaN(value)) return "n/a";
  return `${Math.round(value).toLocaleString()} MWh/d`;
}

function formatMoney(value: number | null): string {
  if (value === null || Number.isNaN(value)) return "n/a";
  return `${value.toFixed(2)} GBP/MWh`;
}

function formatPnl(value: number | null): string {
  if (value === null || Number.isNaN(value)) return "n/a";
  const sign = value > 0 ? "+" : "";
  return `${sign}${Math.round(value).toLocaleString()} GBP`;
}

function formatPct(value: number | null): string {
  if (value === null || Number.isNaN(value)) return "n/a";
  return `${value.toFixed(1)}%`;
}

function routeGeometryLabel(state: RouteGeometryState): string {
  if (state === "surveyed_pipeline_route") return "Surveyed pipeline route";
  if (state === "source_derived_leg_sequence") return "Source-derived leg sequence";
  if (state === "source_derived_corridor") return "Source-derived corridor";
  return "Direct display fallback";
}

function routeGeometryWarning(path: ResourcePoolMapPath): string | null {
  if (path.routeGeometryWarning) return path.routeGeometryWarning;
  if (path.routeGeometryState === "surveyed_pipeline_route") return null;
  if (path.routeGeometryState === "source_derived_leg_sequence") {
    return "Matched route legs are shown as a corridor, not surveyed pipeline geometry.";
  }
  if (path.routeGeometryState === "source_derived_corridor") {
    return "Only source and target corridor geometry is available.";
  }
  return "No materialized route geometry is available; map uses direct display fallback.";
}

function routeStateLabelKey(state: RouteState): string {
  return `home.route_state.${state}`;
}

function summarizeResourcePool(paths: ResourcePoolMapPath[]) {
  const resourceVolumes = new Map<string, number>();
  paths.forEach((path) => {
    const key = `${path.resourceName}:${path.sourcePointName}`;
    resourceVolumes.set(key, Math.max(resourceVolumes.get(key) ?? 0, path.availableQuantityMwhPerDay));
  });
  const totalAvailableMwhPerDay = Array.from(resourceVolumes.values()).reduce((total, value) => total + value, 0);
  const totalAllocatedMwhPerDay = paths.reduce(
    (total, path) => total + (path.allocatedQuantityMwhPerDay ?? 0),
    0,
  );
  const totalUnallocatedMwhPerDay = Math.max(totalAvailableMwhPerDay - totalAllocatedMwhPerDay, 0);
  const weightedMarginNumerator = paths.reduce((total, path) => {
    const allocation = path.allocatedQuantityMwhPerDay ?? 0;
    return path.netMarginGbpMwh === null ? total : total + path.netMarginGbpMwh * allocation;
  }, 0);
  const weightedNetMargin = totalAllocatedMwhPerDay > 0
    ? weightedMarginNumerator / totalAllocatedMwhPerDay
    : null;
  const stateCounts: Record<RouteState, number> = {
    allocated: paths.filter((path) => path.routeState === "allocated").length,
    candidate: paths.filter((path) => path.routeState === "candidate").length,
    blocked: paths.filter((path) => path.routeState === "blocked").length,
  };
  return {
    totalAvailableMwhPerDay,
    totalAllocatedMwhPerDay,
    totalUnallocatedMwhPerDay,
    weightedNetMargin,
    stateCounts,
  };
}

function allocationEvidenceForPath(path: ResourcePoolMapPath, totalAvailableMwhPerDay: number) {
  const allocatedQuantityMwhPerDay = path.allocatedQuantityMwhPerDay ?? 0;
  const displayedQuantityMwhPerDay = path.allocatedQuantityMwhPerDay ?? path.availableQuantityMwhPerDay;
  const poolSharePct = totalAvailableMwhPerDay > 0
    ? (displayedQuantityMwhPerDay / totalAvailableMwhPerDay) * 100
    : null;
  const capacityHeadroomMwhPerDay = path.capacityLimitMwhPerDay === null
    ? null
    : path.capacityLimitMwhPerDay - displayedQuantityMwhPerDay;
  const pnlGbpPerDay = path.netMarginGbpMwh === null
    ? null
    : path.netMarginGbpMwh * displayedQuantityMwhPerDay;
  const capacityBottleneck =
    path.capacityLimitMwhPerDay !== null &&
    path.capacityLimitMwhPerDay < path.availableQuantityMwhPerDay;
  return {
    allocatedQuantityMwhPerDay,
    capacityHeadroomMwhPerDay,
    poolSharePct,
    pnlGbpPerDay,
    capacityBottleneck,
  };
}

export function ResourcePoolPathOverlay({ paths, blockers, t }: ResourcePoolPathOverlayProps) {
  const visiblePaths = paths.slice(0, 3);
  const poolSummary = summarizeResourcePool(paths);
  const hiddenPathCount = Math.max(paths.length - visiblePaths.length, 0);

  return (
    <div className="resource-pool-map-overlay" aria-label={t("home.resource_paths")}>
      <div className="resource-path-heading">
        <span>{t("home.resource_paths")}</span>
        <strong>{visiblePaths.length}/{paths.length}</strong>
      </div>
      {visiblePaths.length > 0 ? (
        <>
          <div className="resource-pool-allocation-summary" aria-label={t("home.pool_allocation")}>
            <div><span>{t("home.pool_volume")}</span><strong>{formatQuantity(poolSummary.totalAvailableMwhPerDay)}</strong></div>
            <div><span>{t("home.allocated")}</span><strong>{formatQuantity(poolSummary.totalAllocatedMwhPerDay)}</strong></div>
            <div><span>{t("home.unallocated")}</span><strong>{formatQuantity(poolSummary.totalUnallocatedMwhPerDay)}</strong></div>
            <div><span>{t("home.net_margin")}</span><strong>{formatMoney(poolSummary.weightedNetMargin)}</strong></div>
          </div>
          <div className="resource-route-status-legend" aria-label={t("home.route_status_legend")}>
            {(["allocated", "candidate", "blocked"] as RouteState[]).map((state) => (
              <span key={`route-state-${state}`} className={`route-state-item ${state}`}>
                <i aria-hidden="true" />
                {t(routeStateLabelKey(state))}
                <strong>{poolSummary.stateCounts[state]}</strong>
              </span>
            ))}
          </div>
          <div className="resource-path-list">
            {visiblePaths.map((path) => {
              const evidence = allocationEvidenceForPath(path, poolSummary.totalAvailableMwhPerDay);
              return (
                <div key={path.pathId} className={`resource-path-card ${path.routeState}`}>
                  <div className="resource-path-flow">
                    <span>{path.sourcePointName}</span>
                    <i aria-hidden="true" />
                    <strong>{path.targetPointName}</strong>
                  </div>
                  <div className="resource-path-meta">
                    <span>{path.resourceName}</span>
                    <strong>{formatQuantity(path.allocatedQuantityMwhPerDay ?? path.availableQuantityMwhPerDay)}</strong>
                    <em className={`resource-route-state-pill ${path.routeState}`}>
                      {t(routeStateLabelKey(path.routeState))}
                    </em>
                  </div>
                  <div className="resource-path-metrics">
                    <span>{t("home.capacity_limit")}: {formatQuantity(path.capacityLimitMwhPerDay)}</span>
                    <span>{t("home.route_cost")}: {formatMoney(path.routeCostGbpMwh)}</span>
                    <span>{t("home.sale_price")}: {formatMoney(path.salePriceGbpMwh)}</span>
                    <span>{t("home.net_margin")}: {formatMoney(path.netMarginGbpMwh)}</span>
                  </div>
                  <div className="resource-path-allocation-evidence">
                    <span>{t("home.pool_share")}: {formatPct(evidence.poolSharePct)}</span>
                    <span>{t("home.capacity_headroom")}: {formatQuantity(evidence.capacityHeadroomMwhPerDay)}</span>
                    <span>{t("home.pnl_per_day")}: {formatPnl(evidence.pnlGbpPerDay)}</span>
                  </div>
                  {evidence.capacityBottleneck && (
                    <div className="resource-path-capacity-warning">
                      {t("home.capacity_bottleneck")}: {formatQuantity(path.capacityLimitMwhPerDay)}
                    </div>
                  )}
                  <div className={`resource-path-geometry ${path.routeGeometryState === "surveyed_pipeline_route" ? "" : "warning"}`}>
                    <span title={routeGeometryWarning(path) ?? undefined}>
                      {t("home.route_geometry")}: {routeGeometryLabel(path.routeGeometryState)}
                    </span>
                    {path.routeLegSummary.length > 0 && (
                      <small>{t("home.route_legs")}: {path.routeLegSummary.slice(0, 3).join(" -> ")}</small>
                    )}
                  </div>
                  {(path.warnings.length > 0 || path.routeState === "blocked") && (
                    <small>{path.warnings[0] ?? t("home.route_blocked")}</small>
                  )}
                </div>
              );
            })}
          </div>
          {hiddenPathCount > 0 && (
            <div className="resource-path-more">+{hiddenPathCount} {t("home.more_route_paths")}</div>
          )}
        </>
      ) : (
        <div className="resource-path-empty">
          <strong>{t("home.path_unavailable")}</strong>
          {(blockers.length > 0 ? blockers : [t("home.draft_contract_note")]).slice(0, 3).map((blocker) => (
            <span key={`path-blocker-${blocker}`}>{blocker}</span>
          ))}
        </div>
      )}
    </div>
  );
}
