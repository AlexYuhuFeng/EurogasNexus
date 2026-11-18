import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ComponentProps } from "react";
import { useApiStore } from "@/stores/api";
import { useShellLayout } from "@/app/shell/useShellLayout";
import type { EdgeDTO, NodeDTO, RouteEligibilityDTO } from "@/api/client";
import { buildVisibleMapNetworkLines } from "@/app/networkMapLines";
import { legPaths, zoneMemberIds } from "@/app/mapLineGeometry";
import { normalizePointName } from "@/app/routeMetadata";
import { isMapEligibleNode, type NetworkGeometryState } from "@/app/workspaceDerivedData";
import {
  bookEmphasis,
  bookReasonLines,
  contractPathLines,
  reachablePathLines,
} from "@/app/mapBookRelevance";
import { MapBookRelevance } from "@/components/MapBookRelevance";
import { GasNetworkMap } from "@/components/GasNetworkMap";
import { SITUATION_LAYERS, situationSummary } from "@/app/mapSituation";
import { buildSites, topologyIssues, type MapSelection } from "@/app/mapSelection";
import { MAP_SITUATION_REFRESH_MS, useMapSituation } from "@/app/hooks/useMapSituation";
import { useFullscreen } from "@/app/hooks/useFullscreen";
import { bookItems, bookSituation, liveSituation, replayTrack, type BookItem } from "@/app/mapBook";
import { MapBookPanel, MapReplayBar, useReplay } from "@/components/MapBookPanel";
import { MapDetailPanel } from "@/components/MapDetailPanel";
import { NetworkInfoPanel, useOutageEvents, type PanelRowRef, type PanelRowTarget } from "@/components/NetworkInfoPanel";
import { ReferenceNetworkCatalogue } from "@/components/ReferenceNetworkCatalogue";
import type { CapacityWorkspaceProps } from "@/components/CapacityWorkspace";
import {
  networkPanelFromSearch,
  networkPanelToSearch,
  inScope,
  outageListRows,
  selectionScope,
  type LonLat,
  type MapBounds,
  type NetworkPanelTab,
} from "@/app/model/networkPanelModel";
import type { MapCargoDTO } from "@/api/client";
import { inspectorSubjectFor } from "@/app/model/inspectorDetail";
import { useInspectorStore } from "@/stores/inspector";
import { Segmented } from "@/components/ui";

type Translate = (key: string) => string;

interface NetworkWorkspaceProps {
  t: Translate;
  nodes: NodeDTO[];
  edges: EdgeDTO[];
  routes: RouteEligibilityDTO[];
  mode: ComponentProps<typeof GasNetworkMap>["themeMode"];
  activeLayers: string[];
  searchTerm: string;
  networkGeometryState: NetworkGeometryState;
  onResetSearch: () => void;
  onToggleLayer: (layer: string) => void;
  /** The reads behind the panel's Capacity tab (the retired "Outages & capacity" board). */
  capacity: Omit<CapacityWorkspaceProps, "t" | "scope" | "selectedKey" | "onSelectPoint">;
  language: string;
  /**
   * Whether the Network task is the one on screen. The task stays mounted while another Desk
   * task shows; while hidden, nothing it opened may stay above other pages (full screen, the
   * Inspector it opened, the panel drawer, open popovers).
   */
  active?: boolean;
}

/** The panel's tab, held in the URL (`panel=`), following Back and Forward. */
function useNetworkPanelTab(): [NetworkPanelTab, (tab: NetworkPanelTab) => void] {
  const read = () =>
    typeof window === "undefined"
      ? "outages"
      : networkPanelFromSearch(window.location.search, new URLSearchParams(window.location.search).get("workspace") ?? "");
  const [tab, setTab] = useState<NetworkPanelTab>(read);
  useEffect(() => {
    const sync = () => setTab(read());
    window.addEventListener("popstate", sync);
    // A retired address (`?workspace=capacity`, `task=capacity`) is rewritten to the
    // canonical Network one with its tab, so a copied link names the page it shows.
    const params = new URLSearchParams(window.location.search);
    if (params.get("workspace") === "capacity" || params.get("task") === "capacity") {
      const url = `${window.location.pathname}?${networkPanelToSearch(window.location.search, read())}${window.location.hash}`;
      window.history.replaceState(window.history.state, "", url);
    }
    return () => window.removeEventListener("popstate", sync);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const choose = useCallback((next: NetworkPanelTab) => {
    setTab(next);
    const search = networkPanelToSearch(window.location.search, next);
    if (`?${search}` !== window.location.search) {
      window.history.replaceState(window.history.state, "", `${window.location.pathname}?${search}${window.location.hash}`);
    }
  }, []);
  return [tab, choose];
}

/** Whether the caller may see the book's panel (a role without book reads never gets the tab). */
function canReadBook(permissions: readonly string[] | undefined): boolean {
  return !Array.isArray(permissions) || permissions.includes("portfolio.read");
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
  networkGeometryState,
  onResetSearch,
  onToggleLayer,
  capacity,
  language,
  active = true,
}: NetworkWorkspaceProps) {
  const compactLayout = useShellLayout().widthClass === "compact";
  const [statusOpen, setStatusOpen] = useState(false);
  const [legendOpen, setLegendOpen] = useState(false);
  const [attributionText, setAttributionText] = useState("");
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
  const [focus, setFocus] = useState<{ refId?: string | null; cargoId?: string; at?: [number, number] | null; nonce: number } | null>(null);
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
  // "Live" only when the read carries something in force now; a reachable server with nothing
  // to show is not live data (#35).
  const isLive = Boolean(summary) && (
    summary!.outagesNow + summary!.outagesScheduled + summary!.contracts + summary!.cargoesAtSea
      + summary!.slots > 0 || summary!.entryGwhD !== null
  );
  // The book view always draws our positions and the outages that can stop them.
  const mapLayers = useMemo(
    () => (mapView === "book" ? [...new Set([...activeLayers, "positions", "outages"])] : activeLayers),
    [activeLayers, mapView],
  );
  // Full screen: the map column (chips, map, live strip, card, key) as a wall or
  // second-monitor view; the situation keeps refreshing while it is up.
  // Full screen takes the whole Network instrument (toolbar, map and panel) edge to edge.
  const shellRef = useRef<HTMLDivElement | null>(null);
  const mapColumnRef = useRef<HTMLElement | null>(null);
  const fullscreen = useFullscreen(shellRef);
  // The right-hand panel collapses to a rail so the map takes the full width; remembered per
  // user on this device. In full screen the map is alone and the panel opens as a drawer.
  const principalId = useApiStore((state) => state.currentUser?.principal_id ?? "anonymous");
  const panelKey = `egn.network.panel.${principalId}`;
  const [panelCollapsed, setPanelCollapsed] = useState<boolean>(() => {
    try {
      return window.localStorage.getItem(panelKey) === "collapsed";
    } catch {
      return false;
    }
  });
  useEffect(() => {
    try {
      setPanelCollapsed(window.localStorage.getItem(panelKey) === "collapsed");
    } catch {
      // Not readable: the panel stays as it is.
    }
  }, [panelKey]);
  const choosePanelCollapsed = (collapsed: boolean) => {
    setPanelCollapsed(collapsed);
    try {
      window.localStorage.setItem(panelKey, collapsed ? "collapsed" : "open");
    } catch {
      // Not remembered; the choice still holds for this visit.
    }
  };
  const [drawerOpen, setDrawerOpen] = useState(false);
  useEffect(() => {
    if (!fullscreen.active) setDrawerOpen(false);
  }, [fullscreen.active]);
  useEffect(() => {
    if (!drawerOpen) return undefined;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setDrawerOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawerOpen]);
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
  // Nothing this page opened stays above another page: when the Network task is hidden (another
  // Desk task shows) or leaves (another mode), full screen ends, the drawer and the popovers
  // close and an Inspector opened from the map closes. The selection itself is kept for coming
  // back; its card lives in the panel, which is hidden with the page.
  const closeTransientRef = useRef<() => void>(() => undefined);
  closeTransientRef.current = () => {
    fullscreen.exit();
    setDrawerOpen(false);
    setLegendOpen(false);
    setStatusOpen(false);
    setHoverAt(null);
    const open = useInspectorStore.getState();
    if (open.subject?.originPage === "network" && open.subject.kind === "network-node") open.close();
  };
  useEffect(() => {
    if (!active) closeTransientRef.current();
  }, [active]);
  useEffect(() => () => closeTransientRef.current(), []);
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
  // Our book (design basis 2, J.5): the deals' places, hubs and priced paths ("ours") and
  // the neighbouring market areas they reach ("reachable"), derived by the server.
  const relevance = rawSituation?.book_relevance ?? null;
  const nodeById = useMemo(() => new Map(nodes.map((node) => [node.id, node])), [nodes]);
  const legPath = useMemo(() => legPaths(edges), [edges]);
  const emphasis = useMemo(() => bookEmphasis(relevance), [relevance]);
  // Our contracts' priced paths, width by contract volume, along the drawn legs.
  const bookFlows = useMemo(() => contractPathLines(relevance, nodeById, legPath), [legPath, nodeById, relevance]);
  const reachableLines = useMemo(() => reachablePathLines(relevance, nodeById, legPath), [legPath, nodeById, relevance]);
  // Our book: the book's own panels, in the panel's fourth tab, only in the "Our book" view
  // and only for a caller who may read the book. They belong to the book, not to the network.
  const currentUser = useApiStore((state) => state.currentUser);
  // Data-operations information (topology checks, point coverage, geometry state) is for those
  // who run the sources or administer the installation, not for the trader's map.
  const dataOps = Boolean(
    currentUser?.permissions.includes("source.run") || currentUser?.permissions.includes("identity.manage"),
  );
  const showBookTab = mapView === "book" && canReadBook(currentUser?.permissions);
  const [panelTab, setPanelTab] = useNetworkPanelTab();
  const activePanelTab: NetworkPanelTab = panelTab === "book" && !showBookTab ? "outages" : panelTab;
  const chooseMapViewAndTab = (next: "network" | "book") => {
    chooseMapView(next);
    if (next === "book" && canReadBook(currentUser?.permissions)) setPanelTab("book");
    else if (panelTab === "book") setPanelTab("outages");
  };

  /* ---------------------------------------------------------------- one selection */
  const [selection, setSelection] = useState<MapSelection | null>(null);
  const [selectedRow, setSelectedRow] = useState<PanelRowRef | null>(null);
  const [hoverAt, setHoverAt] = useState<LonLat | null>(null);
  const [bounds, setBounds] = useState<MapBounds | null>(null);
  const [followMap, setFollowMap] = useState<boolean>(() => {
    try {
      return window.localStorage.getItem("egn.network.follow") !== "off";
    } catch {
      return true;
    }
  });
  const chooseFollowMap = (on: boolean) => {
    setFollowMap(on);
    try {
      window.localStorage.setItem("egn.network.follow", on ? "on" : "off");
    } catch {
      // Not remembered; the choice still holds for this visit.
    }
  };
  const sites = useMemo(() => buildSites(nodes, facilities), [facilities, nodes]);
  const scope = useMemo(
    () => selectionScope(selection, { sites, nodes, zoneMemberIds: (hubId) => zoneMemberIds(hubId, edges) }),
    [edges, nodes, selection, sites],
  );
  const marketRows = useApiStore((state) => state.normalizedMarkets);
  // One read of the outage events: the panel's list and a selected hub's card count the same.
  const outageEvents = useOutageEvents();
  const zoneOutages = useMemo(() => {
    if (selection?.kind !== "hub" || !scope || !outageEvents.events) return null;
    const rows = outageListRows(outageEvents.events, rawSituation).filter((row) =>
      inScope(scope, { refId: row.refId, name: row.asset, country: row.country, zone: row.zone }),
    );
    const now = rows.filter((row) => row.state === "active");
    return {
      outagesNow: now.length,
      outagesPlanned: rows.filter((row) => row.state === "scheduled").length,
      unavailableGwhD: now.reduce((sum, row) => sum + (row.gwhD ?? 0), 0),
    };
  }, [outageEvents.events, rawSituation, scope, selection]);
  const nodeByName = useMemo(() => {
    const byName = new Map<string, (typeof nodes)[number]>();
    for (const node of nodes) byName.set(normalizePointName(node.name), node);
    return byName;
  }, [nodes]);
  const locatePoint = useCallback(
    (pointId: string, pointName: string) => {
      const flow = rawSituation?.flows.find((item) => item.point_id === pointId);
      if (flow) return { at: [flow.location.lon, flow.location.lat] as LonLat, refId: flow.location.ref_id ?? null, country: flow.location.country ?? null };
      const node = nodes.find((item) => item.id === pointId) ?? nodeByName.get(normalizePointName(pointName));
      return node ? { at: [node.lon, node.lat] as LonLat, refId: node.id, country: node.country } : { at: null, refId: null, country: null };
    },
    [nodeByName, nodes, rawSituation],
  );
  const selectRow = (row: PanelRowRef | null, target: PanelRowTarget | null) => {
    setSelectedRow(row);
    if (!row || !target) return;
    setFocus({ refId: target.refId, at: target.at ? [target.at[0], target.at[1]] : null, nonce: Date.now() });
    // At phone width the map sits above the list: bring it back into view.
    if (compactLayout) shellRef.current?.scrollIntoView({ block: "start", behavior: "smooth" });
  };
  const selectOnMap = (next: MapSelection | null) => {
    setSelection(next);
    if (!next) setSelectedRow(null);
  };
  const detail = selection ? (
    <MapDetailPanel
      selection={selection}
      sites={sites}
      edges={edges}
      situation={situation}
      marketRows={marketRows}
      nodes={nodes}
      onClose={() => selectOnMap(null)}
      onInspect={openNodeInspector}
      t={t as (key: string, options?: Record<string, unknown>) => string}
      outagesListed
      zoneOutages={zoneOutages}
      bookReasons={mapView === "book" ? bookReasonLines(
        relevance,
        {
          nodeIds: selection.kind === "site"
            ? (sites.find((item) => item.id === selection.id)?.members.map((member) => member.id) ?? [])
            : selection.kind === "hub"
              ? nodes.filter((node) => node.node_type === "hub" && node.name.toUpperCase() === selection.id).map((node) => node.id)
              : [],
          cargoId: selection.kind === "cargo" ? selection.id : null,
        },
        t as (key: string, options?: Record<string, unknown>) => string,
        language,
      ) : undefined}
      onSelect={(next) => {
        // A related object (a cargo's destination terminal): select it and bring it into view.
        selectOnMap(next);
        const site = next.kind === "site" ? sites.find((item) => item.id === next.id) : null;
        if (site) setFocus({ refId: site.members[0]?.id ?? null, at: [site.lon, site.lat], nonce: Date.now() });
      }}
    />
  ) : null;
  // Phone width: the panel is a sheet under the map; its handle moves the split.
  const [sheetRaised, setSheetRaised] = useState(false);
  const dragRef = useRef<{ startY: number; raised: boolean } | null>(null);

  const bookPanels = (
    <section className="network-book-tab" aria-label={t("network.panel.tab.book")}>
      <MapBookPanel
        items={book}
        t={t as (key: string, options?: Record<string, unknown>) => string}
        onFocus={focusItem}
        onReplay={setReplayCargo}
        replayingId={replayCargo?.cargo_id ?? null}
      />
      <MapBookRelevance
        relevance={relevance}
        language={language}
        t={t as (key: string, options?: Record<string, unknown>) => string}
        onSelectHub={(hubNodeId) => {
          const hub = nodeById.get(hubNodeId);
          if (!hub) return;
          selectOnMap({ kind: "hub", id: hub.name.toUpperCase() });
          setFocus({ refId: hub.id, nonce: Date.now() });
        }}
        onSelectPlace={(refId) => {
          const site = sites.find((item) => item.members.some((member) => member.id === refId));
          if (site) selectOnMap({ kind: "site", id: site.id });
          setFocus({ refId, nonce: Date.now() });
        }}
      />
    </section>
  );
  const footer = (
    <>
      {dataOps && <details className="network-panel-fold">
        <summary>{t("network.panel.map_data")}</summary>
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
                        ? t("map.schematic_connections_title")
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
              {/* The maintenance line, for those who run the sources: topology checks, point
                  coverage and what could not be placed. The map's status line stays the same
                  for everyone. */}
              {summary && (
                <div className="map-data-maintenance" data-network-points={summary.networkPoints ?? undefined}>
                  {topology.length > 0 && (
                    <span className="is-alert" title={topology.map((issue) => `${t(`map.topology.${issue.kind}`)}: ${issue.detail}`).join("\n")}>
                      {t("map.topology.count").replace("{{count}}", String(topology.length))}
                    </span>
                  )}
                  {summary.networkPoints != null && summary.networkPoints > 0 && (
                    <span
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
                  {summary.unlocated > 0 && (
                    <span title={t("map.situation.unlocated_hint")}>{t("map.situation.unlocated")} {summary.unlocated}</span>
                  )}
                </div>
              )}
            </div>
      </details>}
      {/* The register the map's topology is drawn against: what the deployment declares,
          including the rows the map does not place (slice D), one line until opened. */}
      <details className="network-panel-fold">
        <summary>{t("network.reference.title")}</summary>
        <ReferenceNetworkCatalogue t={t} />
      </details>
    </>
  );

  return (
    <div
      ref={shellRef}
      className={`network-workspace-shell network-desk${fullscreen.active ? " is-fullscreen" : ""}${fullscreen.expanded ? " is-expanded" : ""}${sheetRaised ? " is-sheet-raised" : ""}${panelCollapsed && !fullscreen.active ? " is-panel-collapsed" : ""}${drawerOpen ? " is-drawer-open" : ""}`}
      data-map-view={mapView}
    >
      <div className="map-toolbar network-desk-toolbar">
        <Segmented
          className="map-view-switch"
          label={t("map.view.label")}
          options={(["network", "book"] as const).map((option) => ({ value: option, label: t(`map.view.${option}`), title: t(`map.view.${option}_hint`) }))}
          value={mapView}
          onChange={chooseMapViewAndTab}
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
        {fullscreen.active && (
          // Full screen is the map alone; the panel opens over it as a drawer.
          <button
            type="button"
            className="chip map-drawer-chip"
            aria-expanded={drawerOpen}
            aria-controls="network-panel-column"
            onClick={() => setDrawerOpen((open) => !open)}
          >
            {t(drawerOpen ? "network.panel.drawer_close" : "network.panel.drawer_open")}
          </button>
        )}
      </div>
      <section
        ref={mapColumnRef}
        className="network-map-column"
        aria-label={t("network.map_column_label")}
      >
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
          onInspectNode={openNodeInspector}
          situation={situation}
          facilities={facilities}
          view={mapView}
          focus={focus}
          bookFlows={bookFlows}
          bookEmphasis={emphasis}
          bookReachable={reachableLines}
          // The page holds the selection: the panel lists what the selected object relates
          // to and shows its card, so the map draws no card of its own.
          selection={selection}
          onSelectionChange={selectOnMap}
          detailCard={false}
          onViewChange={setBounds}
          hoverAt={hoverAt ? [hoverAt[0], hoverAt[1]] : null}
          replay={
            replayCargo && replayPath && replay.frame
              ? { path: replayPath.coords, sailed: replay.frame.sailed, at: replay.frame.at, label: replayCargo.vessel_name }
              : null
          }
        />
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
        {summary && compactLayout && (
          // Phone width: the map shows the map. One compact line (Live · Out now N) that
          // opens the full status on tap.
          <button
            type="button"
            className="map-situation-compact"
            aria-expanded={statusOpen}
            onClick={() => setStatusOpen((open) => !open)}
          >
            <span className={isLive ? "map-situation-live" : "map-situation-live is-empty"}>
              {t(isLive ? "map.situation.live" : "map.situation.no_live_data")}
            </span>
            {summary.outagesNow > 0 && (
              <span className="is-alert">· {t("map.situation.outages_now")} <b>{summary.outagesNow}</b></span>
            )}
          </button>
        )}
        {summary && (!compactLayout || statusOpen) && (
          <div className="map-situation-strip" role="status" aria-live="polite">
            {/* "Live" only when the read carries something in force now; a reachable
                server with nothing to show is not live data (#35). */}
            {isLive
              ? <span className="map-situation-live">{t("map.situation.live")}</span>
              : <span className="map-situation-live is-empty">{t("map.situation.no_live_data")}</span>}
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
            {summary.entryGwhD != null && (
              <span>{t("map.situation.entry_flow")} <b>{Math.round(summary.entryGwhD).toLocaleString()}</b> GWh/d</span>
            )}
            {mapLayers.includes("vessels") && situation?.vessel_feed?.entitled === false && (
              // A licensed feed the caller does not hold: say so rather than show an empty sea.
              <span className="is-alert">{t("map.situation.vessels_unentitled")}</span>
            )}
            {mapLayers.includes("vessels") && (situation?.vessel_feed?.market_cargoes ?? 0) > 0 && (
              <span>
                <i className="situation-dot market" />{t("map.situation.vessels")}{" "}
                <b>{situation!.vessel_feed!.market_cargoes}</b>
                {situation!.vessel_feed!.simulated > 0 ? <small> sim</small> : null}
              </span>
            )}
            {situationStale && <span className="is-alert">{t("map.situation.stale")}</span>}
            <small>
              {t("map.situation.as_of")} {summary.asOf.slice(11, 16)} UTC
              {readAt ? ` · ${t("map.situation.read_at")} ${readAt.toISOString().slice(11, 16)} UTC` : ""}
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
        {/* The line key (and, on a phone, the basemap credit) opens from one info button, so it
            never covers the map or the zoom card. */}
        {mapHasVisibleEvidence && (
          <button
            type="button"
            className="map-info-chip"
            aria-expanded={legendOpen}
            aria-label={t("map.visual_legend")}
            title={t("map.visual_legend")}
            onClick={() => {
              // The basemap's own attribution, read from the map, goes behind this button too.
              const credit = mapColumnRef.current?.querySelector(".maplibregl-ctrl-attrib-inner");
              setAttributionText(credit?.textContent?.trim() ?? "");
              setLegendOpen((open) => !open);
            }}
          >
            <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" focusable="false">
              <circle cx="8" cy="8" r="6.2" fill="none" stroke="currentColor" strokeWidth="1.4" />
              <path d="M8 7.2v4M8 4.8v.1" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
            </svg>
          </button>
        )}
        {mapHasVisibleEvidence && legendOpen && <div className="map-visual-legend" aria-label={t("map.visual_legend")}>
          {surveyedPipelineCount > 0 && <span><i className="line-swatch verified" />{t("map.key.pipeline")}</span>}
          {connectionLinkCount > 0 && <span><i className="line-swatch link" />{t("map.key.connection")}</span>}
          {mapLayers.includes("routes") && mapView === "network" && (
            <span><i className="line-swatch context" />{t("map.key.context_pipelines")}</span>
          )}
          {indicativeRouteCount > 0 && <span><i className="line-swatch indicative" />{t("map.indicative_route_lines")}</span>}
          {bookFlows.length > 0 && mapLayers.includes("positions") && <span><i className="line-swatch flow" />{t("map.key.book_flow")}</span>}
          {displayedHubCount > 0 && <span><i className="node-swatch hubs" />{t("map.key.hub_area")}</span>}
          {compactLayout && attributionText && <small className="map-legend-attribution">{attributionText}</small>}
        </div>}
      </div>
      </section>

      <div className="network-panel-column" id="network-panel-column">
        {/* Phone width: the handle raises or lowers the sheet (drag, or press). */}
        <button
          type="button"
          className="network-sheet-handle"
          aria-label={t(sheetRaised ? "network.panel.sheet_lower" : "network.panel.sheet_raise")}
          aria-expanded={sheetRaised}
          onClick={() => setSheetRaised((raised) => !raised)}
          onPointerDown={(event) => {
            dragRef.current = { startY: event.clientY, raised: sheetRaised };
            event.currentTarget.setPointerCapture(event.pointerId);
          }}
          onPointerUp={(event) => {
            const drag = dragRef.current;
            dragRef.current = null;
            if (!drag) return;
            const moved = event.clientY - drag.startY;
            if (Math.abs(moved) < 12) return;
            event.preventDefault();
            setSheetRaised(moved < 0);
          }}
        >
          <span aria-hidden="true" />
        </button>
        <NetworkInfoPanel
          t={t as (key: string, options?: Record<string, unknown>) => string}
          outages={outageEvents}
          language={language}
          tab={activePanelTab}
          onTab={setPanelTab}
          showBookTab={showBookTab}
          situation={rawSituation}
          locatePoint={locatePoint}
          scope={scope}
          onClearScope={() => selectOnMap(null)}
          followMap={followMap}
          onFollowMap={chooseFollowMap}
          bounds={bounds}
          detail={detail}
          selectedRow={selectedRow}
          onSelectRow={selectRow}
          onHoverRow={setHoverAt}
          capacity={capacity}
          book={bookPanels}
          footer={footer}
          collapsed={panelCollapsed && !fullscreen.active}
          onCollapse={fullscreen.active ? () => setDrawerOpen(false) : () => choosePanelCollapsed(true)}
          onExpand={(tab) => {
            setPanelTab(tab);
            choosePanelCollapsed(false);
          }}
        />
      </div>
    </div>
  );
}
