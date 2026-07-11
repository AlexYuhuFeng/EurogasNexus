import type { ComponentProps } from "react";
import type {
  EdgeDTO,
  NodeDTO,
  PortfolioLiveSummaryDTO,
  PortfolioOptimizationResultDTO,
  PortfolioResourceDTO,
  ResourcePoolOptionsDTO,
  RouteEligibilityDTO,
  RouteRecommendationResultDTO,
  StrategyLabResultDTO,
} from "@/api/client";
import {
  hasVerifiedNodeCoordinate,
  verifiedEdgeGeometryCoordinates,
  type NetworkGeometryState,
} from "@/app/workspaceDerivedData";
import { GasNetworkMap } from "@/components/GasNetworkMap";
import {
  ResourcePoolPathOverlay,
  type ResourcePoolMapPath,
} from "@/components/ResourcePoolPathOverlay";

type Translate = (key: string) => string;
type SaleOption = ResourcePoolOptionsDTO["sale_options"][number];
type PoolAllocation = PortfolioOptimizationResultDTO["allocations"][number];
type RouteAllocation = RouteRecommendationResultDTO["allocations"][number];
type StrategyTarget = StrategyLabResultDTO["allocation_targets"][number];

interface ReviewEvidenceItem {
  kind: string;
  text: string;
}

interface SourceStats {
  total: number;
  active: number;
  issues: number;
  records: number;
  missingCredentials: number;
}

interface NetworkWorkspaceProps {
  t: Translate;
  nodes: NodeDTO[];
  edges: EdgeDTO[];
  routes: RouteEligibilityDTO[];
  mode: ComponentProps<typeof GasNetworkMap>["themeMode"];
  activeLayers: string[];
  searchTerm: string;
  highlightedRoute: ComponentProps<typeof GasNetworkMap>["highlightedRoute"];
  resourcePoolMapPaths: ResourcePoolMapPath[];
  poolInputBlockers: string[];
  error: string | null;
  loading: boolean;
  saleOptions: SaleOption[];
  canRunPoolOptimizer: boolean;
  portfolioResources: PortfolioResourceDTO[];
  totalPoolVolume: number;
  portfolioSummary: PortfolioLiveSummaryDTO | null;
  screenOrderCount: number;
  upstreamContractCount: number;
  networkGeometryState: NetworkGeometryState;
  routeRecommendation: RouteRecommendationResultDTO | null;
  decisionPnl: number | null;
  resourcePoolResult: PortfolioOptimizationResultDTO | null;
  poolAllocations: PoolAllocation[];
  saleOptionById: Map<string, SaleOption>;
  hasPortfolioResources: boolean;
  selectedAllocation: RouteAllocation | null;
  purchasePrice: number | null;
  salePrice: number | null;
  routeCharge: number | null;
  firstPoolAllocation: PoolAllocation | null;
  firstStrategyTarget: StrategyTarget | undefined;
  strategyResult: StrategyLabResultDTO | null;
  activeWarning: string | null;
  reviewEvidenceItems: ReviewEvidenceItem[];
  gasDay: string;
  deliveryProduct: string;
  marketLastUpdatedAtUtc: string | null;
  sourceStats: SourceStats;
  onResetSearch: () => void;
  onToggleLayer: (layer: string) => void;
  onOptimizePool: () => void;
  onOpenReview: () => void;
}

function geometryMessageKey(state: NetworkGeometryState): string {
  if (state === "runtime_missing") return "map.runtime_missing_body";
  if (state === "nodes_missing") return "map.nodes_missing_body";
  if (state === "edges_missing") return "map.network_warning_body";
  if (state === "corridors_only") return "map.route_corridors_only_body";
  if (state === "unverified_geometry") return "map.unverified_geometry_body";
  return "map.network_ready_body";
}

function warningLabel(warning: string, t: Translate): string {
  const separator = warning.indexOf(":");
  const code = (separator >= 0 ? warning.slice(0, separator) : warning).trim().toLowerCase();
  const detail = separator >= 0 ? warning.slice(separator + 1).trim() : "";
  const key = `warning.${code}`;
  const translated = t(key);
  const label = translated === key ? code.replaceAll("_", " ") : translated;
  return detail ? `${label}: ${detail}` : label;
}

export function NetworkWorkspace({
  t,
  nodes,
  edges,
  routes,
  mode,
  activeLayers,
  searchTerm,
  highlightedRoute,
  resourcePoolMapPaths,
  poolInputBlockers,
  error,
  loading,
  saleOptions,
  canRunPoolOptimizer,
  portfolioResources,
  totalPoolVolume,
  portfolioSummary,
  screenOrderCount,
  upstreamContractCount,
  networkGeometryState,
  routeRecommendation,
  decisionPnl,
  resourcePoolResult,
  poolAllocations,
  saleOptionById,
  hasPortfolioResources,
  selectedAllocation,
  purchasePrice,
  salePrice,
  routeCharge,
  firstPoolAllocation,
  firstStrategyTarget,
  strategyResult,
  activeWarning,
  reviewEvidenceItems,
  gasDay,
  deliveryProduct,
  marketLastUpdatedAtUtc,
  sourceStats,
  onResetSearch,
  onToggleLayer,
  onOptimizePool,
  onOpenReview,
}: NetworkWorkspaceProps) {
  const verifiedGeometryCount = edges.filter(
    (edge) => verifiedEdgeGeometryCoordinates(edge) !== null,
  ).length;
  const verifiedLngCount = nodes.filter(
    (node) => node.node_type === "lng" && hasVerifiedNodeCoordinate(node),
  ).length;
  const verifiedIpCount = nodes.filter(
    (node) => node.node_type === "interconnection" && hasVerifiedNodeCoordinate(node),
  ).length;
  return (
    <>
      <section className="map-container map-stage" id="map">
        <div className="map-toolbar">
          <button className="chip reset-chip" type="button" onClick={onResetSearch}>
            {t("map.reset")}
          </button>
          {["network", "lng", "ips", "hubs"].map((layer) => (
            <button
              key={layer}
              type="button"
              className={
                activeLayers.includes(layer)
                  ? `chip map-layer-chip compact layer-${layer} active`
                  : `chip map-layer-chip compact layer-${layer}`
              }
              aria-pressed={activeLayers.includes(layer)}
              aria-label={t(`map.layer.${layer}`)}
              title={t(`map.layer.${layer}`)}
              onClick={() => onToggleLayer(layer)}
            >
              <span className="layer-label">{t(`map.layer.${layer}`)}</span>
            </button>
          ))}
        </div>
        <GasNetworkMap
          nodes={nodes}
          edges={edges}
          routes={routes}
          themeMode={mode}
          activeLayers={activeLayers}
          searchTerm={searchTerm}
          highlightedRoute={highlightedRoute}
        />
        <ResourcePoolPathOverlay
          paths={resourcePoolMapPaths}
          blockers={poolInputBlockers}
          t={t}
        />
      </section>

      <aside className="scenario-rail">
        {error && <div className="panel alert">{error}</div>}
        {loading && <div className="panel">{t("status.loading")}</div>}

        <div className="panel scenario-intro">
          <span className="eyebrow">{t("home.resource_pool")}</span>
          <h2>{t("home.pool_cockpit")}</h2>
          <p>{t("home.pool_description")}</p>
          <div className="home-context-strip">
            <span><small>{t("context.gas_day")}</small><strong>{gasDay}</strong></span>
            <span>
              <small>{t("context.product")}</small>
              <strong>{deliveryProduct === "all" ? t("context.all_products") : t(`context.${deliveryProduct.replaceAll("-", "_")}`)}</strong>
            </span>
            <span className={sourceStats.issues > 0 ? "issue" : "ready"}>
              <small>{t("context.source_posture")}</small>
              <strong>{sourceStats.active}/{sourceStats.total} {t("context.active")}</strong>
            </span>
          </div>
          <div className="home-freshness-line">
            <span className={marketLastUpdatedAtUtc ? "freshness-dot ready" : "freshness-dot issue"} />
            <span>
              {marketLastUpdatedAtUtc
                ? `${t("context.market_updated")} ${new Date(marketLastUpdatedAtUtc).toLocaleString()}`
                : t("context.no_market_update")}
            </span>
          </div>
        </div>

        <div className="panel home-portfolio-panel">
          <div className="section-heading">
            <span className="eyebrow">{t("home.portfolio")}</span>
            <strong>{portfolioResources.length} {t("home.resources")}</strong>
          </div>
          <div className="metric-grid two-column compact-metrics">
            <div>
              <span>{t("home.pool_volume")}</span>
              <strong>{totalPoolVolume.toLocaleString()} MWh/d</strong>
            </div>
            <div>
              <span>{t("portfolio.open_orders")}</span>
              <strong>{portfolioSummary?.open_order_count ?? screenOrderCount}</strong>
            </div>
          </div>
          <div className="route-list compact-route-list resource-contract-list">
            {portfolioResources.map((resource) => (
              <div key={`home-resource-${resource.resource_id}`} className="route-row route-candidate">
                <span>{resource.resource_name}</span>
                <strong>{resource.available_quantity_mwh_per_day.toLocaleString()} MWh/d</strong>
                <small>{resource.location_point_name} / {resource.resource_type}</small>
                <div className="resource-constraint-line">
                  <span>{t("home.all_in_cost")}: {(resource.contract_cost_gbp_mwh + (resource.variable_cost_gbp_mwh ?? 0)).toFixed(2)} GBP/MWh</span>
                  <span>{t("home.required_access")}: {resource.required_tso_access?.join(", ") || t("home.none_declared")}</span>
                </div>
              </div>
            ))}
            {upstreamContractCount === 0 && (
              <div className="route-row route-candidate blocked-route">
                <span>{t("home.no_db_contracts")}</span>
                <strong>{t("data.partial")}</strong>
                <small>{t("home.draft_contract_note")}</small>
              </div>
            )}
          </div>
        </div>

        <div className="panel optimizer-control-panel">
          <div className="section-heading">
            <span className="eyebrow">{t("home.optimization")}</span>
            <strong>{saleOptions.length} {t("home.sale_markets")}</strong>
          </div>
          <p className="panel-copy">{t("home.optimization_scope")}</p>
          <div className="action-row">
            <button type="button" disabled={!canRunPoolOptimizer} onClick={onOptimizePool}>
              {t("home.optimize_pool")}
            </button>
          </div>
          {poolInputBlockers.length > 0 && (
            <div className="runtime-blocker-list">
              <strong>{t("home.optimizer_blocked")}</strong>
              {poolInputBlockers.map((blocker) => <span key={`home-blocker-${blocker}`}>{blocker}</span>)}
            </div>
          )}
        </div>

        <div className="panel map-data-panel">
          <div className="section-heading">
            <span className="eyebrow">{t("map.topology_status")}</span>
            <strong>
              {networkGeometryState === "loaded"
                ? t("data.runtime")
                : ["corridors_only", "unverified_geometry"].includes(networkGeometryState)
                  ? t("data.partial")
                  : t("data.unavailable")}
            </strong>
          </div>
          <div className={networkGeometryState === "loaded" ? "map-network-state ready" : "map-network-state blocked"}>
            <strong>
              {networkGeometryState === "loaded"
                ? t("map.network_dataset")
                : networkGeometryState === "corridors_only"
                  ? t("map.route_corridors_only")
                  : networkGeometryState === "unverified_geometry"
                    ? t("map.network_warning_title")
                  : t("map.network_warning_title")}
            </strong>
            <span>{t(geometryMessageKey(networkGeometryState))}</span>
          </div>
          <div className="node-color-legend">
            <span><i className="node-swatch network" />{t("map.layer.network")}<strong>{verifiedGeometryCount}</strong></span>
            <span><i className="node-swatch lng" />{t("map.layer.lng")}<strong>{verifiedLngCount}</strong></span>
            <span><i className="node-swatch ips" />{t("map.layer.ips")}<strong>{verifiedIpCount}</strong></span>
            <span><i className="node-swatch hubs" />{t("map.layer.hubs")}<strong>{nodes.filter((node) => node.node_type === "hub").length}</strong></span>
          </div>
          <p className="coordinate-quality-note">{t("map.coordinate_quality_note")}</p>
        </div>
      </aside>

      <aside className="decision-rail">
        <div className="panel trade-result-panel">
          <div className="panel-title-row">
            <div>
              <span className="eyebrow">{t("result.eyebrow")}</span>
              <h3>{t("result.title")}</h3>
            </div>
            <span className="status-pill">{routeRecommendation ? t("result.live") : t("result.snapshot")}</span>
          </div>
          <div className="net-pnl-card">
            <span>{t("result.net_pnl")}</span>
            <strong>
              {decisionPnl === null ? t("home.pending") : `GBP ${Math.round(decisionPnl).toLocaleString()}`}
            </strong>
            <small>
              {t("home.allocated")} {resourcePoolResult?.total_allocated_mwh_per_day?.toLocaleString() ?? "n/a"} MWh/d / {t("home.unallocated")} {resourcePoolResult?.total_unallocated_mwh_per_day?.toLocaleString() ?? "n/a"} MWh/d
            </small>
          </div>
        </div>

        <div className="panel route-alpha-panel">
          <div className="panel-title-row">
            <h3>{t("result.route_alpha")}</h3>
            <span>{t("result.pool_decision")}</span>
          </div>
          {poolAllocations.length > 0 ? poolAllocations.map((allocation, index) => {
            const option = saleOptionById.get(allocation.option_id);
            return (
              <details key={`pool-allocation-${allocation.resource_id}-${allocation.option_id}`} className="route-decision-card" open={index === 0}>
                <summary>
                  <span>
                    <small>{option?.target_point_name ?? allocation.option_id}</small>
                    <strong>{option?.label ?? allocation.option_id}</strong>
                  </span>
                  <span className="route-decision-value">
                    <strong>GBP {Math.round(allocation.net_pnl_gbp_per_day).toLocaleString()}</strong>
                    <small>{allocation.allocated_quantity_mwh_per_day.toLocaleString()} MWh/d</small>
                  </span>
                </summary>
                <div className="route-decision-metrics">
                  <span><small>{t("result.sale")}</small><strong>{allocation.gross_sale_price_gbp_mwh.toFixed(2)} GBP/MWh</strong></span>
                  <span><small>{t("result.route_cost")}</small><strong>{(option?.route_cost_gbp_mwh ?? 0).toFixed(2)} GBP/MWh</strong></span>
                  <span><small>{t("result.net_margin")}</small><strong>{allocation.net_margin_gbp_mwh.toFixed(2)} GBP/MWh</strong></span>
                  <span><small>{t("result.cash_value")}</small><strong>{allocation.early_cash_value_gbp_mwh.toFixed(3)} GBP/MWh</strong></span>
                  <span><small>{t("home.capacity_limit")}</small><strong>{option?.capacity_limit_mwh_per_day?.toLocaleString() ?? t("home.unlimited")} MWh/d</strong></span>
                  <span><small>{t("home.required_access")}</small><strong>{option?.required_tso_access?.join(", ") || t("home.none_declared")}</strong></span>
                </div>
                <div className="route-decision-evidence">
                  <span>{t("home.price_source")}: {option?.sale_price_simulated ? t("market.simulated_source") : option?.sale_price_source_system ?? "n/a"}</span>
                  <span>{t("context.updated")}: {option?.sale_price_observed_at_utc ? new Date(option.sale_price_observed_at_utc).toLocaleString() : "n/a"}</span>
                  <span>{t("home.source_refs")}: {option?.source_refs?.join(" / ") || t("data.unavailable")}</span>
                  {allocation.warnings.map((warning) => (
                    <strong key={`${allocation.option_id}-${warning}`}>{warningLabel(warning, t)}</strong>
                  ))}
                </div>
              </details>
            );
          }) : (
            <div className="route-alpha-card">
              <span>{t("result.optimal")}</span>
              <strong>{hasPortfolioResources ? selectedAllocation?.route_name ?? saleOptions[0]?.label ?? t("home.pending") : t("home.no_db_contracts")}</strong>
              <small>{hasPortfolioResources ? routeRecommendation ? t("result.no_route") : t("home.run_pool_optimizer") : t("home.draft_contract_note")}</small>
            </div>
          )}
        </div>

        <div className="panel economics-snapshot">
          <h3>{t("result.economics_snapshot")}</h3>
          <div className="metric-grid two-column">
            <div>
              <span>{t("result.purchase")}</span>
              <strong>{purchasePrice === null ? "n/a" : `GBP ${purchasePrice.toFixed(2)}/MWh`}</strong>
            </div>
            <div>
              <span>{t("result.sale")}</span>
              <strong>{salePrice === null ? "n/a" : `GBP ${salePrice.toFixed(2)}/MWh`}</strong>
            </div>
            <div>
              <span>{t("result.route_cost")}</span>
              <strong>{routeCharge === null ? "n/a" : `GBP ${routeCharge.toFixed(2)}/MWh`}</strong>
            </div>
            <div>
              <span>{t("result.cash_value")}</span>
              <strong>{firstPoolAllocation ? `GBP ${firstPoolAllocation.early_cash_value_gbp_mwh.toFixed(2)}/MWh` : "n/a"}</strong>
            </div>
          </div>
        </div>

        <div className="panel decision-signal-panel">
          <div className="panel-title-row">
            <h3>{t("home.signal")}</h3>
            <span>{firstStrategyTarget ? t("data.live") : t("result.snapshot")}</span>
          </div>
          <div className="net-pnl-card">
            <span>{t("home.strategy_process")}</span>
            <strong>
              {firstStrategyTarget ? `${firstStrategyTarget.market_bucket} ${firstStrategyTarget.target_allocation_pct.toFixed(1)}%` : t("home.not_running")}
            </strong>
            <small>{strategyResult?.candidate_action_for_review ?? t("home.signal_idle")}</small>
          </div>
          <div className="signal-warning">
            <span>{t("home.warning")}</span>
            <strong>{activeWarning ? warningLabel(activeWarning, t) : t("home.warning_clear")}</strong>
          </div>
        </div>

        <div className="panel evidence-stack-panel">
          <div className="panel-title-row">
            <h3>{t("home.evidence_stack")}</h3>
            <button type="button" className="text-action" onClick={onOpenReview}>
              {t("home.review_warnings")}
            </button>
          </div>
          <div className="review-warning-list compact">
            {reviewEvidenceItems.length > 0
              ? reviewEvidenceItems.map((item) => (
                  <span key={`evidence-${item.kind}-${item.text}`}>
                    <strong>{item.kind}</strong> {item.text}
                  </span>
                ))
              : <span>{t("home.no_evidence_warnings")}</span>}
          </div>
        </div>
      </aside>
    </>
  );
}
