import { useMemo, useRef, useState } from "react";
import type { ComponentProps } from "react";
import { useShellLayout } from "@/app/shell/useShellLayout";
import type {
  EdgeDTO,
  IntradayOpportunityDTO,
  NodeDTO,
  PortfolioLiveSummaryDTO,
  PortfolioOptimizationResultDTO,
  PortfolioResourceDTO,
  ResourcePoolOptionsDTO,
  RouteEligibilityDTO,
  RouteRecommendationResultDTO,
  StrategyLabResultDTO,
} from "@/api/client";
import { buildVisibleMapNetworkLines } from "@/app/networkMapLines";
import { buildBookFlows, type LineCoordinate } from "@/app/mapLineGeometry";
import { buildNodeIdByPointName, buildRouteGeometryEdgesByRouteId } from "@/app/resourcePoolMapPaths";
import { normalizePointName } from "@/app/routeMetadata";
import {
  isMapEligibleNode,
  verifiedEdgeGeometryCoordinates,
  type NetworkGeometryState,
} from "@/app/workspaceDerivedData";
import { GasNetworkMap } from "@/components/GasNetworkMap";
import { Button } from "@/components/ui/Button";
import { SITUATION_LAYERS, situationSummary } from "@/app/mapSituation";
import { topologyIssues } from "@/app/mapSelection";
import { MAP_SITUATION_REFRESH_MS, useMapSituation } from "@/app/hooks/useMapSituation";
import { useFullscreen } from "@/app/hooks/useFullscreen";
import { bookItems, bookSituation, liveSituation, replayTrack, type BookItem } from "@/app/mapBook";
import { MapBookPanel, MapReplayBar, useReplay } from "@/components/MapBookPanel";
import type { MapCargoDTO } from "@/api/client";
import { inspectorSubjectFor } from "@/app/model/inspectorDetail";
import { useInspectorStore } from "@/stores/inspector";
import { IntradayDecisionFeed } from "@/components/IntradayDecisionFeed";
import { CommercialWarningList } from "@/components/CommercialWarningList";
import type { CommercialDiagnosticItem } from "@/app/model/commercialWarnings";
import { Segmented, WorkspaceTabs } from "@/components/ui";
import {
  ResourcePoolPathOverlay,
  type ResourcePoolMapPath,
} from "@/components/ResourcePoolPathOverlay";
import { warningCode, warningLabel } from "@/app/warningLabel";

type Translate = (key: string) => string;
type SaleOption = ResourcePoolOptionsDTO["sale_options"][number];
type PoolAllocation = PortfolioOptimizationResultDTO["allocations"][number];
type RouteAllocation = RouteRecommendationResultDTO["allocations"][number];
type StrategyTarget = StrategyLabResultDTO["allocation_targets"][number];

interface ReviewEvidenceItem {
  kind: string;
  text: string;
}

type DecisionRailView = "decision" | "pnl" | "warnings" | "evidence";

interface NetworkWorkspaceProps {
  t: Translate;
  nodes: NodeDTO[];
  edges: EdgeDTO[];
  routes: RouteEligibilityDTO[];
  mode: ComponentProps<typeof GasNetworkMap>["themeMode"];
  activeLayers: string[];
  searchTerm: string;
  highlightedRoute: ComponentProps<typeof GasNetworkMap>["highlightedRoute"];
  routesInUse?: ComponentProps<typeof GasNetworkMap>["routesInUse"];
  resourcePoolMapPaths: ResourcePoolMapPath[];
  poolInputBlockers: string[];
  commercialDiagnostics: CommercialDiagnosticItem[];
  error: string | null;
  loading: boolean;
  saleOptions: SaleOption[];
  /** The pool-optimiser run belongs to the Decision workspace's primary action; see below. */
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
  /** The held strategy result was not computed from the inputs the caller now knows. */
  strategyContextMismatch: boolean;
  activeWarning: string | null;
  reviewEvidenceItems: ReviewEvidenceItem[];
  intradayOpportunities: IntradayOpportunityDTO[];
  resultsContextMismatch: boolean;
  onResetSearch: () => void;
  onToggleLayer: (layer: string) => void;
  onOpenReview: () => void;
  onOpenScenario: () => void;
}

function geometryMessageKey(state: NetworkGeometryState): string {
  // The status read has not answered: the map states that, and never claims a disconnection it
  // has no reading for.
  if (state === "runtime_unknown") return "map.runtime_unknown_body";
  if (state === "runtime_missing") return "map.runtime_missing_body";
  if (state === "nodes_missing") return "map.nodes_missing_body";
  if (state === "edges_missing") return "map.network_warning_body";
  if (state === "corridors_only") return "map.route_corridors_only_body";
  if (state === "unverified_geometry") return "map.unverified_geometry_body";
  return "map.network_ready_body";
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
  routesInUse,
  resourcePoolMapPaths,
  poolInputBlockers,
  commercialDiagnostics,
  error,
  loading,
  saleOptions,
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
  strategyContextMismatch,
  activeWarning,
  reviewEvidenceItems,
  intradayOpportunities,
  resultsContextMismatch,
  onResetSearch,
  onToggleLayer,
  onOpenReview,
  onOpenScenario,
}: NetworkWorkspaceProps) {
  const compactLayout = useShellLayout().widthClass === "compact";
  // Wave 9: map nodes hand their detail to the canonical Inspector. This page declares
  // `network-node` as an inspectable subject, so the hand-over is legal here; the builder
  // refuses it everywhere the composition does not declare it.
  const inspector = useInspectorStore();
  // Network: the whole picture with the infrastructure as quiet context. Our book: only the
  // firm's deals still in play, prioritised, with completed ones kept for looking back.
  const [mapView, setMapView] = useState<"network" | "book">(() => {
    try {
      return window.localStorage.getItem("egn.map.view") === "book" ? "book" : "network";
    } catch {
      return "network";
    }
  });
  const chooseMapView = (next: "network" | "book") => {
    setMapView(next);
    try {
      window.localStorage.setItem("egn.map.view", next);
    } catch {
      // A blocked store only means the choice is not remembered.
    }
  };
  // The book view also reads 120 days of completed deals for its history.
  const { situation: rawSituation, facilities, error: situationError, readAt } = useMapSituation(true, mapView === "book" ? 120 : 0);
  const nowMs = readAt?.getTime() ?? Date.now();
  const situation = useMemo(
    () => (mapView === "book" ? bookSituation(rawSituation, nowMs) : liveSituation(rawSituation, nowMs)),
    [mapView, nowMs, rawSituation],
  );
  const book = useMemo(() => bookItems(rawSituation, nowMs), [nowMs, rawSituation]);
  const [focus, setFocus] = useState<{ refId?: string | null; cargoId?: string; nonce: number } | null>(null);
  const [replayCargo, setReplayCargo] = useState<MapCargoDTO | null>(null);
  const replayPath = useMemo(() => (replayCargo ? replayTrack(replayCargo) : null), [replayCargo]);
  const replay = useReplay(replayPath);
  const focusItem = (item: BookItem) => {
    setReplayCargo(null);
    if (item.kind === "cargo" && item.phase !== "completed") setFocus({ cargoId: item.id, nonce: Date.now() });
    else if (item.cargo && item.phase === "completed") setReplayCargo(item.cargo);
    else setFocus({ refId: item.refId, nonce: Date.now() });
  };
  const summary = situationSummary(liveSituation(rawSituation, nowMs));
  // The book view always draws our positions and the outages that can stop them.
  const mapLayers = useMemo(
    () => (mapView === "book" ? [...new Set([...activeLayers, "positions", "outages"])] : activeLayers),
    [activeLayers, mapView],
  );
  // Full screen: the map column (chips, map, live strip, card, key) as a wall or
  // second-monitor view; the situation keeps refreshing while it is up.
  const mapColumnRef = useRef<HTMLElement | null>(null);
  const fullscreen = useFullscreen(mapColumnRef);
  // A read that keeps failing leaves the last good picture up; say so once it is old.
  const situationStale = Boolean(situationError) && readAt !== null
    && Date.now() - readAt.getTime() > 2 * MAP_SITUATION_REFRESH_MS;
  // What netbacks rely on: every connection ends at known points and crosses a border only
  // at an entry or interconnection point. Problems are named here, not silently drawn.
  const topology = useMemo(() => topologyIssues(nodes, edges), [edges, nodes]);
  const openNodeInspector = (nodeId: string, label: string) => {
    const subject = inspectorSubjectFor("network-node", nodeId, label, "network");
    if (subject) inspector.open(subject);
  };
  const displayedNetworkCount = nodes.filter(
    (node) =>
      !["hub", "lng", "interconnection", "entry_point"].includes(node.node_type) &&
      isMapEligibleNode(node),
  ).length;
  const displayedLngCount = nodes.filter(
    (node) => node.node_type === "lng" && isMapEligibleNode(node),
  ).length;
  const displayedIpCount = nodes.filter(
    (node) => (node.node_type === "interconnection" || node.node_type === "entry_point") && isMapEligibleNode(node),
  ).length;
  const displayedHubCount = nodes.filter((node) => node.node_type === "hub").length;
  const visibleMapLines = buildVisibleMapNetworkLines({
    nodes,
    edges,
    activeLayers,
    searchTerm,
    highlightedRoute,
  });
  const surveyedPipelineCount = visibleMapLines.filter((line) => line.displayKind === "verified_pipeline").length;
  const connectionLinkCount = visibleMapLines.filter((line) => line.displayKind === "network_link").length;
  const verifiedPipelineCount = surveyedPipelineCount + connectionLinkCount;
  const indicativeRouteCount = visibleMapLines.filter(
    (line) => line.displayKind === "indicative_route",
  ).length;
  const mapHasVisibleEvidence =
    displayedNetworkCount +
      displayedLngCount +
      displayedIpCount +
      displayedHubCount +
      verifiedPipelineCount +
      indicativeRouteCount >
    0;
  const [activeRailView, setActiveRailView] = useState<DecisionRailView>("decision");
  // The book's allocated flows, one line per origin and destination, along the surveyed
  // pipeline route where every leg of it is surveyed.
  const bookFlows = useMemo(() => {
    const nodeIdByPointName = buildNodeIdByPointName(nodes);
    const edgesByRouteId = buildRouteGeometryEdgesByRouteId(edges);
    const surveyedRoute = (routeId: string): LineCoordinate[] | null => {
      const legs = [...(edgesByRouteId.get(routeId) ?? [])]
        .sort((a, b) => Number(a.metadata_json?.route_leg_sequence ?? 0) - Number(b.metadata_json?.route_leg_sequence ?? 0))
        .map(verifiedEdgeGeometryCoordinates);
      if (!legs.length || legs.some((leg) => leg === null)) return null;
      return legs.flatMap((leg) => leg as LineCoordinate[]);
    };
    return buildBookFlows({
      paths: resourcePoolMapPaths,
      resolvePoint: (name) => nodeIdByPointName.get(normalizePointName(name)),
      nodes: new Map(nodes.map((node) => [node.id, node])),
      surveyedRoute,
    });
  }, [edges, nodes, resourcePoolMapPaths]);

  return (
    <div className="network-workspace-shell">
      <aside className="scenario-rail network-resource-rail" aria-label={t("home.resource_pool")} tabIndex={0}>
        {error && <div className="panel alert">{error}</div>}
        {loading && <div className="panel">{t("status.loading")}</div>}

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
            <Button variant="secondary" disabled={!hasPortfolioResources} onClick={onOpenScenario}>
              {t("network.open_in_scenario")}
            </Button>
          </div>
          {/* One `compute` consequence, one control: the pool optimiser runs from the Decision
              workspace's primary action, so this panel hands the user over instead of running a
              second copy of the same act from the map. */}
          <p className="panel-copy">{t("network.optimizer_location")}</p>
          {/* Both decision results the map draws from - the pool allocation and the route
              recommendation - are only current for the trading context they were computed
              under, so either lane being stale is stated here. */}
          {resultsContextMismatch && (
            <div className="runtime-blocker-list compact">
              <strong>{t("context.result_mismatch")}</strong>
              <span>{t("context.result_mismatch_hint")}</span>
            </div>
          )}
          {poolInputBlockers.length > 0 && (
            <div className="runtime-blocker-list">
              <strong>{t("home.optimizer_blocked")}</strong>
              {poolInputBlockers.map((blocker) => <span key={`home-blocker-${blocker}`} title={blocker}>{warningLabel(blocker, t)}</span>)}
            </div>
          )}
        </div>

        <div className="panel map-data-panel">
          <div className="section-heading">
            <span className="eyebrow">{t("map.topology_status")}</span>
            <strong>
              {networkGeometryState === "loaded"
                ? t("data.ready")
                : ["corridors_only", "unverified_geometry"].includes(networkGeometryState)
                  ? t("data.partial")
                  : networkGeometryState === "runtime_unknown"
                    ? t("status.unknown")
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
            <span><i className="node-swatch network" />{t("map.layer.network")}<strong>{displayedNetworkCount}</strong></span>
            <span><i className="node-swatch lng" />{t("map.layer.lng")}<strong>{displayedLngCount}</strong></span>
            <span><i className="node-swatch ips" />{t("map.layer.ips")}<strong>{displayedIpCount}</strong></span>
            <span><i className="node-swatch hubs" />{t("map.layer.hubs")}<strong>{displayedHubCount}</strong></span>
          </div>
          <p className="coordinate-quality-note">{t("map.coordinate_quality_note")}</p>
        </div>
      </aside>

      <section
        ref={mapColumnRef}
        className={`network-map-column${fullscreen.active ? " is-fullscreen" : ""}${fullscreen.expanded ? " is-expanded" : ""}`}
        aria-label={t("network.map_column_label")}
      >
        <div className="map-toolbar">
          <Segmented
            className="map-view-switch"
            label={t("map.view.label")}
            options={(["network", "book"] as const).map((option) => ({ value: option, label: t(`map.view.${option}`), title: t(`map.view.${option}_hint`) }))}
            value={mapView}
            onChange={chooseMapView}
          />
          <span className="map-toolbar-divider" aria-hidden="true" />
          {/* Phone width: one compact row, icons with their names for assistive technology. */}
          <button
            className={compactLayout ? "chip reset-chip map-icon-chip" : "chip reset-chip"}
            type="button"
            onClick={onResetSearch}
            aria-label={compactLayout ? t("map.reset") : undefined}
            title={compactLayout ? t("map.reset") : undefined}
          >
            {compactLayout ? (
              <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
                <path d="M13 8a5 5 0 1 1-1.5-3.6M13 2.5v2.5h-2.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            ) : t("map.reset")}
          </button>
          {compactLayout ? (
            // Phone width (docs/product/ADAPTIVE_CLIENT.md): the layer switches live in one
            // labelled panel with the active count, so they never cover the map (#39).
            <details className="map-layers-panel">
              <summary>
                {t("map.layers_panel")} <span className="map-layers-count">{activeLayers.length}</span>
              </summary>
              <div className="map-layers-panel-body">
          {["routes", "network", "lng", "ips", "hubs"].map((layer) => (
            <button
              key={layer}
              type="button"
              className={
                activeLayers.includes(layer)
                  ? `chip map-layer-chip layer-${layer} active`
                  : `chip map-layer-chip layer-${layer}`
              }
              aria-pressed={activeLayers.includes(layer)}
              aria-label={t(`map.layer.${layer}`)}
              title={t(layer === "routes" ? "map.layer.routes_hint" : `map.layer.${layer}`)}
              onClick={() => onToggleLayer(layer)}
            >
              <span className="layer-label">{t(`map.layer.${layer}`)}</span>
            </button>
          ))}
          <span className="map-toolbar-divider" aria-hidden="true" />
          {SITUATION_LAYERS.map((layer) => (
            <button
              key={layer}
              type="button"
              className={
                activeLayers.includes(layer)
                  ? `chip map-layer-chip situation-chip layer-${layer} active`
                  : `chip map-layer-chip situation-chip layer-${layer}`
              }
              aria-pressed={activeLayers.includes(layer)}
              title={t(`map.layer.${layer}_hint`)}
              onClick={() => onToggleLayer(layer)}
            >
              <span className="layer-label">{t(`map.layer.${layer}`)}</span>
            </button>
          ))}
              </div>
            </details>
          ) : (
            <>
          {["routes", "network", "lng", "ips", "hubs"].map((layer) => (
            <button
              key={layer}
              type="button"
              className={
                activeLayers.includes(layer)
                  ? `chip map-layer-chip layer-${layer} active`
                  : `chip map-layer-chip layer-${layer}`
              }
              aria-pressed={activeLayers.includes(layer)}
              aria-label={t(`map.layer.${layer}`)}
              title={t(layer === "routes" ? "map.layer.routes_hint" : `map.layer.${layer}`)}
              onClick={() => onToggleLayer(layer)}
            >
              <span className="layer-label">{t(`map.layer.${layer}`)}</span>
            </button>
          ))}
          <span className="map-toolbar-divider" aria-hidden="true" />
          {SITUATION_LAYERS.map((layer) => (
            <button
              key={layer}
              type="button"
              className={
                activeLayers.includes(layer)
                  ? `chip map-layer-chip situation-chip layer-${layer} active`
                  : `chip map-layer-chip situation-chip layer-${layer}`
              }
              aria-pressed={activeLayers.includes(layer)}
              title={t(`map.layer.${layer}_hint`)}
              onClick={() => onToggleLayer(layer)}
            >
              <span className="layer-label">{t(`map.layer.${layer}`)}</span>
            </button>
          ))}
            </>
          )}
          <span className="map-toolbar-divider" aria-hidden="true" />
          <button
            type="button"
            className={compactLayout ? "chip map-fullscreen-chip map-icon-chip" : "chip map-fullscreen-chip"}
            aria-pressed={fullscreen.active}
            aria-label={compactLayout ? t(fullscreen.active ? "map.fullscreen.exit" : "map.fullscreen.enter") : undefined}
            title={t(fullscreen.active ? "map.fullscreen.exit_hint" : "map.fullscreen.enter_hint")}
            onClick={fullscreen.toggle}
          >
            {compactLayout ? (
              <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
                <path
                  d={fullscreen.active ? "M6 2v4H2M10 2v4h4M6 14v-4H2M10 14v-4h4" : "M2 6V2h4M14 6V2h-4M2 10v4h4M14 10v4h-4"}
                  fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"
                />
              </svg>
            ) : t(fullscreen.active ? "map.fullscreen.exit" : "map.fullscreen.enter")}
          </button>
        </div>
        <div className="map-container map-stage network-map-stage" id="map">
          <GasNetworkMap
            nodes={nodes}
            edges={edges}
            routes={routes}
            themeMode={mode}
            // The book view always draws our positions and the outages that can stop them.
            activeLayers={mapLayers}
            searchTerm={searchTerm}
            t={t}
            highlightedRoute={highlightedRoute}
            routesInUse={routesInUse}
            onInspectNode={openNodeInspector}
            situation={situation}
            facilities={facilities}
            view={mapView}
            focus={focus}
            bookFlows={bookFlows}
            replay={
              replayCargo && replayPath && replay.frame
                ? { path: replayPath.coords, sailed: replay.frame.sailed, at: replay.frame.at, label: replayCargo.vessel_name }
                : null
            }
          />
          {mapView === "book" && (
            <MapBookPanel
              items={book}
              t={t as (key: string, options?: Record<string, unknown>) => string}
              onFocus={focusItem}
              onReplay={setReplayCargo}
              replayingId={replayCargo?.cargo_id ?? null}
            />
          )}
          {replayCargo && replayPath && replay.moment !== null && (
            <MapReplayBar
              cargo={replayCargo}
              track={replayPath}
              moment={replay.moment}
              playing={replay.playing}
              onMoment={replay.setMoment}
              onPlaying={replay.setPlaying}
              onClose={() => setReplayCargo(null)}
              t={t as (key: string, options?: Record<string, unknown>) => string}
            />
          )}
          {summary && (
            <div className="map-situation-strip" role="status" aria-live="polite">
              {/* "Live" only when the read carries something in force now; a reachable
                  server with nothing to show is not live data (#35). */}
              {summary.outagesNow + summary.outagesScheduled + summary.contracts + summary.cargoesAtSea
                + summary.slots > 0 || summary.entryGwhD !== null
                ? <span className="map-situation-live">{t("map.situation.live")}</span>
                : <span className="map-situation-live is-empty">{t("map.situation.no_live_data")}</span>}
              {topology.length > 0 && (
                <span className="is-alert" title={topology.map((issue) => `${t(`map.topology.${issue.kind}`)}: ${issue.detail}`).join("\n")}>
                  <i className="situation-dot outage-scheduled" />{t("map.topology.count").replace("{{count}}", String(topology.length))}
                </span>
              )}
              {summary.outagesNow > 0 && (
                <span className="is-alert"><i className="situation-dot outage-active" />{t("map.situation.outages_now")} <b>{summary.outagesNow}</b></span>
              )}
              {summary.outagesScheduled > 0 && (
                <span><i className="situation-dot outage-scheduled" />{t("map.situation.outages_scheduled")} <b>{summary.outagesScheduled}</b></span>
              )}
              {summary.contracts > 0 && (
                <span><i className="situation-dot own" />{t("map.situation.contracts")} <b>{summary.contracts}</b></span>
              )}
              {summary.cargoesAtSea > 0 && (
                <span><i className="situation-dot own" />{t("map.situation.cargoes_at_sea")} <b>{summary.cargoesAtSea}</b></span>
              )}
              {summary.slots > 0 && (
                <span><i className="situation-dot own ring" />{t("map.situation.slots")} <b>{summary.slots}</b></span>
              )}
              {summary.regasNow > 0 && (
                <span><i className="situation-dot own" />{t("map.situation.regas_now")} <b>{summary.regasNow}</b></span>
              )}
              {summary.networkPoints != null && summary.networkPoints > 0 && (
                <span
                  data-network-points={summary.networkPoints}
                  title={summary.unlocatedPoints.length > 0
                    ? `${t("map.situation.points_not_located_hint")}\n${summary.unlocatedPoints.map((point) => `${point.point_name} (${point.point_key})`).join("\n")}`
                    : undefined}
                >
                  {t("map.situation.network_points")} <b>{summary.networkPoints.toLocaleString()}</b>
                  {summary.unlocatedPoints.length > 0
                    ? ` · ${t("map.situation.points_not_located").replace("{{count}}", String(summary.unlocatedPoints.length))}`
                    : ""}
                </span>
              )}
              {summary.entryGwhD != null && (
                <span>{t("map.situation.entry_flow")} <b>{Math.round(summary.entryGwhD).toLocaleString()}</b> GWh/d</span>
              )}
              {situationStale && <span className="is-alert">{t("map.situation.stale")}</span>}
              <small title={t("map.situation.unlocated_hint")}>
                {t("map.situation.as_of")} {summary.asOf.slice(11, 16)} UTC
                {readAt ? ` · ${t("map.situation.read_at")} ${readAt.toISOString().slice(11, 16)} UTC` : ""}
                {summary.unlocated > 0 ? ` · ${t("map.situation.unlocated")} ${summary.unlocated}` : ""}
              </small>
            </div>
          )}
          {!mapHasVisibleEvidence && (
            <div className="map-empty-state" role="status">
              <strong>{t("map.empty_title")}</strong>
              <span>{t(geometryMessageKey(networkGeometryState))}</span>
              <small>{t("map.empty_help")}</small>
            </div>
          )}
          {/* The chips are the key for points; this one line keys only the lines drawn. A hub
              is a market area, never wired to its points: the key says how to see its zone. */}
          {mapHasVisibleEvidence && <div className="map-visual-legend" aria-label={t("map.visual_legend")}>
            {surveyedPipelineCount > 0 && <span><i className="line-swatch verified" />{t("map.key.pipeline")}</span>}
            {connectionLinkCount > 0 && <span><i className="line-swatch link" />{t("map.key.connection")}</span>}
            {indicativeRouteCount > 0 && <span><i className="line-swatch indicative" />{t("map.indicative_route_lines")}</span>}
            {bookFlows.length > 0 && mapLayers.includes("positions") && <span><i className="line-swatch flow" />{t("map.key.book_flow")}</span>}
            {displayedHubCount > 0 && <span><i className="node-swatch hubs" />{t("map.key.hub_area")}</span>}
          </div>}
        </div>
      </section>

      <aside className="decision-rail network-decision-rail" aria-label={t("network.rail_tabs")}>
        <WorkspaceTabs
          idPrefix="network-rail-tab"
          label={t("network.rail_tabs")}
          tabs={(["decision", "pnl", "warnings", "evidence"] as DecisionRailView[]).map((view) => ({
            id: view,
            label: t(`network.rail_${view}`),
          }))}
          activeId={activeRailView}
          panelId="network-rail-panel"
          className="network-rail-tabs"
          onActivate={setActiveRailView}
        />
        <div
          id="network-rail-panel"
          className="network-rail-view"
          role="tabpanel"
          aria-labelledby={`network-rail-tab-${activeRailView}`}
          // Keep the text-only scroll region reachable by keyboard.
          tabIndex={0}
        >
          {activeRailView === "decision" && (
            <>
              <div className="panel intraday-home-panel">
                <IntradayDecisionFeed
                  opportunities={intradayOpportunities}
                  t={t}
                  compact
                />
              </div>
              <div className="panel route-alpha-panel">
                <div className="panel-title-row">
                  <h2>{t("result.route_alpha")}</h2>
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
                          <strong key={`${allocation.option_id}-${warning}`} title={warning} data-warning-code={warningCode(warning)}>{warningLabel(warning, t)}</strong>
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
            </>
          )}

          {activeRailView === "pnl" && (
            <>
              <div className="panel trade-result-panel">
                <div className="panel-title-row">
                  <div>
                    <span className="eyebrow">{t("result.eyebrow")}</span>
                    <h2>{t("result.title")}</h2>
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
              <div className="panel economics-snapshot">
                <h2>{t("result.economics_snapshot")}</h2>
                <div className="metric-grid two-column">
                  <div><span>{t("result.purchase")}</span><strong>{purchasePrice === null ? "n/a" : `GBP ${purchasePrice.toFixed(2)}/MWh`}</strong></div>
                  <div><span>{t("result.sale")}</span><strong>{salePrice === null ? "n/a" : `GBP ${salePrice.toFixed(2)}/MWh`}</strong></div>
                  <div><span>{t("result.route_cost")}</span><strong>{routeCharge === null ? "n/a" : `GBP ${routeCharge.toFixed(2)}/MWh`}</strong></div>
                  <div><span>{t("result.cash_value")}</span><strong>{firstPoolAllocation ? `GBP ${firstPoolAllocation.early_cash_value_gbp_mwh.toFixed(2)}/MWh` : "n/a"}</strong></div>
                </div>
              </div>
              <div className="panel decision-signal-panel">
                <div className="panel-title-row">
                  <h2>{t("home.signal")}</h2>
                  <span>
                    {strategyContextMismatch
                      ? t("data.stale")
                      : firstStrategyTarget
                        ? t("data.live")
                        : t("result.snapshot")}
                  </span>
                </div>
                <div className="net-pnl-card">
                  <span>{t("home.strategy_process")}</span>
                  <strong>
                    {firstStrategyTarget ? `${firstStrategyTarget.market_bucket} ${firstStrategyTarget.target_allocation_pct.toFixed(1)}%` : t("home.not_running")}
                  </strong>
                  <small>
                    {strategyContextMismatch
                      ? t("context.result_mismatch_hint")
                      : strategyResult?.candidate_action_for_review ?? t("home.signal_idle")}
                  </small>
                </div>
              </div>
            </>
          )}

          {activeRailView === "warnings" && (
            <div className="panel network-warning-panel">
              <div className="panel-title-row">
                <h2>{t("home.warning")}</h2>
                <span>{activeWarning ? t("data.live") : t("result.snapshot")}</span>
              </div>
              <div className="signal-warning">
                <span>{t("home.warning")}</span>
                <strong>{activeWarning ? warningLabel(activeWarning, t) : t("home.warning_clear")}</strong>
              </div>
              <CommercialWarningList
                items={commercialDiagnostics}
                t={t}
                limit={8}
                emptyLabel={t("home.warning_clear")}
              />
              {error && <div className="panel alert">{error}</div>}
              {loading && <div className="panel">{t("status.loading")}</div>}
            </div>
          )}

          {activeRailView === "evidence" && (
            <div className="panel evidence-stack-panel">
              <div className="panel-title-row">
                <h2>{t("home.evidence_stack")}</h2>
                <button type="button" className="link-button" onClick={onOpenReview}>
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
          )}
        </div>
      </aside>

      <section className="network-route-ladder" aria-label={t("home.resource_paths")}>
        <ResourcePoolPathOverlay
          paths={resourcePoolMapPaths}
          blockers={poolInputBlockers}
          t={t}
          defaultOpen
        />
      </section>
    </div>
  );
}
