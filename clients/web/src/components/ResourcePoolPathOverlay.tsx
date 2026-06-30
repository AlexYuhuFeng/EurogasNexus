type Translate = (key: string) => string;

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
  routeGeometryState: "source_derived_leg_sequence" | "source_derived_corridor" | "directLineFallback";
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

export function ResourcePoolPathOverlay({ paths, blockers, t }: ResourcePoolPathOverlayProps) {
  const visiblePaths = paths.slice(0, 4);

  return (
    <div className="resource-pool-map-overlay" aria-label={t("home.resource_paths")}>
      <div className="resource-path-heading">
        <span>{t("home.resource_paths")}</span>
        <strong>{visiblePaths.length}</strong>
      </div>
      {visiblePaths.length > 0 ? (
        <div className="resource-path-list">
          {visiblePaths.map((path) => (
            <div key={path.pathId} className={`resource-path-card ${path.routeState}`}>
              <div className="resource-path-flow">
                <span>{path.sourcePointName}</span>
                <i aria-hidden="true" />
                <strong>{path.targetPointName}</strong>
              </div>
              <div className="resource-path-meta">
                <span>{path.resourceName}</span>
                <strong>{formatQuantity(path.allocatedQuantityMwhPerDay ?? path.availableQuantityMwhPerDay)}</strong>
              </div>
              <div className="resource-path-metrics">
                <span>{t("home.capacity_limit")}: {formatQuantity(path.capacityLimitMwhPerDay)}</span>
                <span>{t("home.route_cost")}: {formatMoney(path.routeCostGbpMwh)}</span>
                <span>{t("home.sale_price")}: {formatMoney(path.salePriceGbpMwh)}</span>
                <span>{t("home.net_margin")}: {formatMoney(path.netMarginGbpMwh)}</span>
              </div>
              <div className="resource-path-geometry">
                <span>{t("home.route_geometry")}: {path.routeGeometryState}</span>
                {path.routeLegSummary.length > 0 && (
                  <small>{t("home.route_legs")}: {path.routeLegSummary.slice(0, 4).join(" -> ")}</small>
                )}
              </div>
              {(path.warnings.length > 0 || path.routeState === "blocked") && (
                <small>{path.warnings[0] ?? t("home.route_blocked")}</small>
              )}
            </div>
          ))}
        </div>
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
