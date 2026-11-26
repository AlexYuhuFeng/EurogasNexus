import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ComponentProps } from "react";
import { useApiStore } from "@/stores/api";
import { api, type EdgeDTO, type NodeDTO, type RouteEligibilityDTO, type TodayNeedsMeItemDTO } from "@/api/client";
import { buildVisibleMapNetworkLines } from "@/app/networkMapLines";
import { legPaths, zoneMemberIds } from "@/app/mapLineGeometry";
import { corridorFlowDay, corridorFlowText } from "@/app/mapCorridors";
import { readKey, useCachedRead } from "@/app/data/readCache";
import { INTENSITY_METRICS, rankIntensity, intensityPoints, type IntensityDatum, type IntensityMetric } from "@/app/mapIntensity";
import type { SupplyCorridorDTO } from "@/api/client";
import { normalizePointName } from "@/app/routeMetadata";
import { isMapEligibleNode, type NetworkGeometryState } from "@/app/workspaceDerivedData";
import {
  bookEmphasis,
  bookReasonLines,
  contractPathLines,
  disruptionCallout,
  disruptionMarks,
  opportunityPathLines,
  periodFraction,
  periodLine,
  pointAtFraction,
  proposalLines,
  reachablePathLines,
  windowClosed,
  windowLeft,
} from "@/app/mapBookRelevance";
import { MapBookRelevance, OpportunityCard, type NeedsYouRow } from "@/components/MapBookRelevance";
import { GasNetworkMap, type MapCallout } from "@/components/GasNetworkMap";
import { NETWORK_LAYERS, SITUATION_LAYERS, situationSummary } from "@/app/mapSituation";
import { flowDayOptions } from "@/app/mapScene";
import { formatGasDay } from "@/app/time/timeFormat";
import { buildSites, topologyIssues, type MapSelection } from "@/app/mapSelection";
import { MAP_SITUATION_REFRESH_MS, useMapSituation } from "@/app/hooks/useMapSituation";
import { useExpandedView } from "@/app/hooks/useExpandedView";
import { useNetworkSheetLayout } from "@/app/hooks/useNetworkSheetLayout";
import { bookItems, bookSituation, liveSituation, replayTrack, type BookItem } from "@/app/mapBook";
import { MapBookPanel, MapReplayBar, useReplay } from "@/components/MapBookPanel";
import { MapDetailPanel } from "@/components/MapDetailPanel";
import { NetworkInfoPanel, useOutageEvents, type PanelRowRef, type PanelRowTarget } from "@/components/NetworkInfoPanel";
import type { CapacityWorkspaceProps } from "@/components/CapacityWorkspace";
import {
  networkPanelFromSearch,
  networkPanelToSearch,
  inScope,
  networkPlaceFromSearch,
  outageListRows,
  selectionScope,
  type LonLat,
  type MapBounds,
  type NetworkPanelTab,
} from "@/app/model/networkPanelModel";
import type { MapCargoDTO } from "@/api/client";
import { inspectorSubjectFor } from "@/app/model/inspectorDetail";
import { useInspectorStore } from "@/stores/inspector";
import { Popover, Segmented } from "@/components/ui";
import { Icon } from "@/components/ui/Icon";

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
  onToggleLayer: (layer: string) => void;
  /** Back to the first view's layers (hubs, our positions and cargoes, outages on our book). */
  onDefaultLayers: () => void;
  /** The reads behind the panel's Capacity tab (the retired "Outages & capacity" board). */
  capacity: Omit<CapacityWorkspaceProps, "t" | "scope" | "selectedKey" | "onSelectPoint">;
  language: string;
  /**
   * Whether the Network task is the one on screen. The task stays mounted while another Desk
   * task shows; while hidden, nothing it opened may stay above other pages (full screen, the
   * Inspector it opened, the panel drawer, open popovers).
   */
  active?: boolean;
  /**
   * Today's "What needs me" (CP-19). Those with a place on the map (an outage touching us, an
   * opportunity with a path, a limit with a hub) are listed beside the map in the Our book tab.
   */
  needsMe?: TodayNeedsMeItemDTO[];
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
  onToggleLayer,
  onDefaultLayers,
  capacity,
  language,
  active = true,
  needsMe = [],
}: NetworkWorkspaceProps) {
  // The sheet layout's width, the stylesheet's (app/hooks/useNetworkSheetLayout.ts).
  const compactLayout = useNetworkSheetLayout();
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
  // Cache-first; kept current while on screen, paused while parked (app/hooks/useMapSituation.ts).
  const { situation: rawSituation, facilities, error: situationError, readAt } =
    useMapSituation(true, mapView === "book" ? 120 : 0, active);
  const nowMs = readAt?.getTime() ?? Date.now();
  const situation = useMemo(
    () => (mapView === "book" ? bookSituation(rawSituation, nowMs) : liveSituation(rawSituation, nowMs)),
    [mapView, nowMs, rawSituation],
  );
  const book = useMemo(() => bookItems(rawSituation, nowMs), [nowMs, rawSituation]);
  const [focus, setFocus] = useState<{ refId?: string | null; cargoId?: string; at?: [number, number] | null; path?: Array<[number, number]> | null; nonce: number } | null>(null);
  const [replayCargo, setReplayCargo] = useState<MapCargoDTO | null>(null);
  // An address that names a place (`place=<node id>`) opens the map on it once the network has
  // loaded; Back and Forward between such addresses move the map again.
  const [linkedPlace, setLinkedPlace] = useState<string | null>(() =>
    typeof window === "undefined" ? null : networkPlaceFromSearch(window.location.search),
  );
  useEffect(() => {
    const sync = () => setLinkedPlace(networkPlaceFromSearch(window.location.search));
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, []);
  const hasPlace = Boolean(linkedPlace && nodes.some((node) => node.id === linkedPlace));
  useEffect(() => {
    if (hasPlace && linkedPlace) setFocus({ refId: linkedPlace, nonce: Date.now() });
  }, [hasPlace, linkedPlace]);
  const replayPath = useMemo(() => (replayCargo ? replayTrack(replayCargo) : null), [replayCargo]);
  const replay = useReplay(replayPath);
  const focusItem = (item: BookItem) => {
    setReplayCargo(null);
    if (item.kind === "cargo" && item.phase !== "completed") setFocus({ cargoId: item.id, nonce: Date.now() });
    else if (item.cargo && item.phase === "completed") setReplayCargo(item.cargo);
    else setFocus({ refId: item.refId, nonce: Date.now() });
  };
  // The data-maintenance line (for those who run the sources) still counts what is placed.
  const summary = situationSummary(liveSituation(rawSituation, nowMs));
  // The book view always draws our positions, our cargoes and the outages that can stop them.
  const mapLayers = useMemo(
    () => (mapView === "book" ? [...new Set([...activeLayers, "positions", "cargoes", "outages"])] : activeLayers),
    [activeLayers, mapView],
  );
  // Expanded: the whole Network instrument (toolbar, map, panel as a drawer) fills the app
  // window by CSS; the situation keeps refreshing. Never the browser's Fullscreen API
  // (app/hooks/useExpandedView.ts).
  const shellRef = useRef<HTMLDivElement | null>(null);
  const mapColumnRef = useRef<HTMLElement | null>(null);
  const expandedView = useExpandedView();
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
    if (!expandedView.expanded) setDrawerOpen(false);
  }, [expandedView.expanded]);
  // Escape: an open drawer closes first, then a selected object's card (its own handler), and
  // only then does the expanded map restore. Escape typed in a field (the finder) stays there.
  const escapeStateRef = useRef({ drawerOpen, hasSelection: false });
  useEffect(() => {
    if (!drawerOpen && !expandedView.expanded) return undefined;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || event.defaultPrevented) return;
      const target = event.target as HTMLElement | null;
      if (target?.closest("input, textarea, select, [contenteditable=true], [popover]")) return;
      if (escapeStateRef.current.drawerOpen) {
        setDrawerOpen(false);
        return;
      }
      if (escapeStateRef.current.hasSelection) return;
      expandedView.exit();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawerOpen, expandedView]);
  // A read that keeps failing leaves the last good picture up; say so once it is old.
  const situationStale = Boolean(situationError) && readAt !== null
    && Date.now() - readAt.getTime() > 2 * MAP_SITUATION_REFRESH_MS;
  // What netbacks rely on: every connection ends at known points and crosses a border only
  // at an entry or interconnection point. Problems are named here, not silently drawn.
  const topology = useMemo(() => topologyIssues(nodes, edges), [edges, nodes]);
  const openNodeInspector = (nodeId: string, label: string) => {
    const subject = inspectorSubjectFor("network-node", nodeId, label, "network");
    if (!subject) return;
    // The Inspector is a page-level drawer: the expanded map steps back so it is not covered.
    expandedView.exit();
    inspector.open(subject);
  };
  // Nothing this page opened stays above another page: when the Network task is hidden (another
  // Desk task shows) or leaves (another mode), full screen ends, the drawer and the popovers
  // close and an Inspector opened from the map closes. The selection itself is kept for coming
  // back; its card lives in the panel, which is hidden with the page.
  const closeTransientRef = useRef<() => void>(() => undefined);
  closeTransientRef.current = () => {
    expandedView.exit();
    setDrawerOpen(false);
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
  const tr = t as (key: string, options?: Record<string, unknown>) => string;
  // A clock for the windows to act: an opportunity whose window closed leaves the map.
  const [clockMs, setClockMs] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return undefined;
    setClockMs(Date.now());
    const id = window.setInterval(() => setClockMs(Date.now()), 30_000);
    return () => window.clearInterval(id);
  }, [active]);
  // Opportunities dismissed here leave the map at once (the server hides them on its next read),
  // and so do those whose window closed.
  const [dismissedIds, setDismissedIds] = useState<ReadonlySet<string>>(new Set());
  const hiddenIds = useMemo(() => {
    const out = new Set(dismissedIds);
    for (const item of relevance?.opportunities ?? []) if (windowClosed(item, clockMs)) out.add(item.opportunity_id);
    return out;
  }, [clockMs, dismissedIds, relevance]);
  // Re-route and locational alternatives: the current way against the proposed one.
  const proposals = useMemo(
    () => proposalLines(relevance, nodeById, tr, legPath).filter((line) => !hiddenIds.has(line.opportunityId)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [hiddenIds, legPath, nodeById, relevance, language],
  );
  // The opportunity class (CP-21): the core's opportunities with a path, and the one opened. One
  // drawn as a proposal is not drawn twice.
  const opportunityLines = useMemo(() => {
    const proposed = new Set(proposals.map((line) => line.opportunityId));
    return opportunityPathLines(relevance, nodeById, legPath, new Set([...hiddenIds, ...proposed]));
  }, [hiddenIds, legPath, nodeById, proposals, relevance]);
  const [openOpportunityId, setOpenOpportunityId] = useState<string | null>(null);
  const openOpportunity = relevance?.opportunities?.find((item) => item.opportunity_id === openOpportunityId) ?? null;
  // Disruptions touching the book, and the mark the trader opened (a disruption or a contract's
  // window): its callout shows on the map and its row is highlighted in "Needs you".
  const disruptions = useMemo(() => relevance?.disruptions ?? [], [relevance]);
  const disruptionPlaces = useMemo(() => disruptionMarks(relevance), [relevance]);
  const [openMark, setOpenMark] = useState<{ kind: "disruption" | "contract"; id: string } | null>(null);
  const pathOf = (opportunityId: string) => {
    const proposed = proposals.find((line) => line.opportunityId === opportunityId)?.proposed;
    if (proposed) return proposed;
    // A member of a grouped line shares its lead's path.
    const item = relevance?.opportunities?.find((entry) => entry.opportunity_id === opportunityId);
    const lead = item
      ? relevance?.opportunities?.find(
          (entry) => opportunityLines.some((line) => line.opportunityId === entry.opportunity_id)
            && entry.path_node_ids.join(">") === item.path_node_ids.join(">"),
        )
      : null;
    return opportunityLines.find((line) => line.opportunityId === (lead?.opportunity_id ?? opportunityId))?.coordinates ?? null;
  };
  const openOpportunityOnMap = (id: string) => {
    setOpenOpportunityId(id);
    setOpenMark(null);
    setSelection(null);
    const path = pathOf(id);
    if (path) setFocus({ path, nonce: Date.now() });
    if (compactLayout) setSheetRaised(false);
  };
  const openDisruption = (id: string, fly = true) => {
    setOpenMark({ kind: "disruption", id });
    setOpenOpportunityId(null);
    const item = disruptions.find((entry) => entry.event_id === id);
    if (fly && item) setFocus({ at: [item.location.lon, item.location.lat], nonce: Date.now() });
    if (compactLayout) setSheetRaised(false);
  };
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
  // Intensity: one metric from the Layers menu (flat encodings), and the mark the trader opened.
  const [intensity, setIntensity] = useState<IntensityMetric | null>(null);
  const [intensityPick, setIntensityPick] = useState<{ metric: IntensityMetric; datum: IntensityDatum } | null>(null);
  const chooseIntensity = (next: IntensityMetric | null) => {
    setIntensity(next);
    setIntensityPick(null);
  };
  // Europe's import supply corridors: shipped reference data with the store's latest flows,
  // read once per session (they change with a gas day, not by the minute).
  const corridorsRead = useCachedRead<SupplyCorridorDTO[]>(
    readKey("/reference-network/supply-corridors", {}),
    (signal) => api.supplyCorridors({ signal }).then((response) => response.data?.corridors ?? []),
    { freshMs: 30 * 60_000 },
  );
  const corridors = useMemo(() => corridorsRead.data ?? [], [corridorsRead.data]);
  const [corridorPick, setCorridorPick] = useState<string | null>(null);
  escapeStateRef.current = { drawerOpen, hasSelection: selection !== null };
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
    setIntensityPick(null);
    setCorridorPick(null);
    if (next) setOpenOpportunityId(null);
    if (next) setOpenMark(null);
    if (!next) setSelectedRow(null);
  };
  const intensityCard = intensityPick ? (
    // A column's figure: what it is, the value and unit, the gas day and the source.
    <aside className="map-detail-panel" aria-label={t("map.detail.title")}>
      <button type="button" className="map-detail-close link-button" onClick={() => setIntensityPick(null)} aria-label={t("map.detail.close")} title={t("map.detail.close")}><Icon name="close" /></button>
      <header className="map-detail-header">
        <h3>{intensityPick.datum.name}</h3>
        <p className="muted">
          {t(`map.intensity.metric.${intensityPick.metric}`)}
        </p>
      </header>
      <div className="map-detail-figures">
        <div className="map-detail-figure">
          <span>{t("map.intensity.card.value")}</span>
          <strong>{Math.round(intensityPick.datum.value).toLocaleString("en-GB")}<small> GWh/d</small></strong>
          {intensityPick.datum.direction && (
            <small className="muted">{t(`map.intensity.card.direction_${intensityPick.datum.direction}`)}</small>
          )}
        </div>
      </div>
      {intensityPick.datum.ratio !== null && (
        <p className="muted">{tr("map.intensity.card.utilisation", { pct: Math.round(intensityPick.datum.ratio * 100) })}</p>
      )}
      <p className="muted">
        {intensityPick.datum.gasDay ? tr("map.intensity.gas_day", { day: intensityPick.datum.gasDay }) : null}
        {intensityPick.datum.gasDay && intensityPick.datum.source ? " · " : null}
        {intensityPick.datum.source ? tr("map.intensity.card.source", { source: intensityPick.datum.source }) : null}
      </p>
    </aside>
  ) : null;
  // A corridor's card: where it comes from, who runs it, where it lands, capacity, the latest
  // flow with its gas day, its status with its date, and the source.
  const pickedCorridor = corridorPick ? corridors.find((item) => item.id === corridorPick) ?? null : null;
  const corridorCard = pickedCorridor ? (
    <aside className="map-detail-panel" aria-label={t("map.detail.title")}>
      <button type="button" className="map-detail-close link-button" onClick={() => setCorridorPick(null)} aria-label={t("map.detail.close")} title={t("map.detail.close")}><Icon name="close" /></button>
      <header className="map-detail-header">
        <h3>{pickedCorridor.name}</h3>
        <p className="muted">{tr("map.corridor.card.from", { country: pickedCorridor.source_country, place: pickedCorridor.source.place })}</p>
      </header>
      <dl className="map-corridor-facts">
        <dt>{t("map.corridor.card.operator")}</dt>
        <dd>{pickedCorridor.operator?.name ?? "–"}</dd>
        <dt>{t("map.corridor.card.landing")}</dt>
        <dd>{pickedCorridor.landing_points.map((point) => point.name).join(", ") || "–"}{pickedCorridor.into_market_areas.length ? ` → ${pickedCorridor.into_market_areas.join(", ")}` : ""}</dd>
        <dt>{t("map.corridor.card.capacity")}</dt>
        <dd>
          {pickedCorridor.capacity?.firm_technical_kwh_d
            ? `${Math.round(pickedCorridor.capacity.firm_technical_kwh_d / 1e6).toLocaleString("en-GB")} GWh/d`
            : t("map.corridor.not_published")}
          {pickedCorridor.capacity?.gas_day ? <small className="muted"> · {tr("map.intensity.gas_day", { day: pickedCorridor.capacity.gas_day })}</small> : null}
        </dd>
        <dt>{t("map.corridor.card.flow")}</dt>
        <dd>
          {corridorFlowText(pickedCorridor, tr)}
          {pickedCorridor.latest_flow_gwh_d !== null && corridorFlowDay(pickedCorridor)
            ? <small className="muted"> · {tr("map.intensity.gas_day", { day: corridorFlowDay(pickedCorridor) })}</small>
            : null}
        </dd>
        <dt>{t("map.corridor.card.status")}</dt>
        <dd>
          {pickedCorridor.status === "out_of_service"
            ? (pickedCorridor.since ? tr("map.corridor.out_since_date", { date: pickedCorridor.since }) : t("map.corridor.out_of_service"))
            : t(`map.corridor.status.${pickedCorridor.status}`)}
        </dd>
      </dl>
      <p className="muted map-corridor-source">
        {[pickedCorridor.status_source?.citation, pickedCorridor.capacity?.citation].filter(Boolean).join(" · ")}
      </p>
    </aside>
  ) : null;
  // The chosen metric's ten largest figures: exact comparison is a table's job, not the map's.
  // A row flies the map to the point and opens its figure.
  const intensityRanking = useMemo(
    () => (intensity && intensity !== "flow" ? rankIntensity(intensityPoints(intensity, { situation: rawSituation, nodes, edges, flowDay: null })) : []),
    [edges, intensity, nodes, rawSituation],
  );
  const rankingPanel = intensity && intensity !== "flow" ? (
    <section className="map-intensity-ranking" aria-label={t("map.intensity.ranking")}>
      <h4>{tr("map.intensity.ranking_title", { metric: t(`map.intensity.metric.${intensity}`) })}</h4>
      {intensityRanking.length === 0 ? (
        <p className="muted">{t("map.intensity.no_data")}</p>
      ) : (
        <ol>
          {intensityRanking.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                className="map-intensity-rank-row"
                onClick={() => {
                  setFocus({ at: item.at, nonce: Date.now() });
                  setIntensityPick({ metric: intensity, datum: item });
                }}
              >
                <span>{item.name}</span>
                <strong>{Math.round(item.value).toLocaleString("en-GB")}<small> GWh/d</small></strong>
              </button>
            </li>
          ))}
        </ol>
      )}
    </section>
  ) : null;
  const detail = corridorCard ?? intensityCard ?? rankingPanel ?? (openOpportunity && mapView === "book" ? (
    <OpportunityCard
      item={openOpportunity}
      t={tr}
      language={language}
      windowLeft={windowLeft(openOpportunity.window_closes_utc, clockMs)}
      onClose={() => setOpenOpportunityId(null)}
      onOpenCase={async () => {
        const response = await api.openOpportunityCase(openOpportunity.opportunity_id);
        return response.data?.case?.case_id ?? null;
      }}
      onDismiss={async (reason) => {
        await api.setOpportunityState(openOpportunity.opportunity_id, { action: "dismiss", reason });
        setDismissedIds((held) => new Set([...held, openOpportunity.opportunity_id]));
        setOpenOpportunityId(null);
      }}
    />
  ) : selection ? (
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
  ) : null);
  // Phone width: the panel is a sheet under the map; its handle moves the split.
  const [sheetRaised, setSheetRaised] = useState(false);
  const dragRef = useRef<{ startY: number; raised: boolean } | null>(null);

  // "Needs you" beside the map: Today's items that have a place on it.
  const needsYou = useMemo<NeedsYouRow[]>(() => {
    const rows: NeedsYouRow[] = [];
    for (const item of needsMe) {
      const title = language.startsWith("zh") && item.title_zh ? item.title_zh : item.title;
      if (item.kind === "outage") {
        const place = disruptions.find((entry) => entry.event_id === item.id);
        if (!place) continue;
        rows.push({ key: `outage:${item.id}`, kind: "outage", id: item.id, title, line: disruptionCallout(place, tr, language).lines.join(" · "), simulated: item.simulated });
      } else if (item.kind === "opportunity") {
        if (!pathOf(item.id)) continue;
        const opportunity = relevance?.opportunities?.find((entry) => entry.opportunity_id === item.id);
        rows.push({ key: `opportunity:${item.id}`, kind: "opportunity", id: item.id, title, line: opportunity ? `${opportunity.from_hub} → ${opportunity.to_hub} · ${opportunity.period}` : item.period ?? "", simulated: item.simulated });
      } else if (item.kind === "limit" && item.hub) {
        const hub = nodes.find((node) => node.node_type === "hub" && node.name.toUpperCase() === item.hub!.toUpperCase());
        if (!hub) continue;
        rows.push({ key: `limit:${item.id}`, kind: "limit", id: item.id, title, line: item.hub, simulated: item.simulated, refId: hub.id });
      }
    }
    return rows;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [disruptions, language, needsMe, nodes, opportunityLines, proposals, relevance]);
  const activeNeed = openMark?.kind === "disruption"
    ? `outage:${openMark.id}`
    : openOpportunityId ? `opportunity:${openOpportunityId}` : null;
  const selectNeed = (row: NeedsYouRow) => {
    if (row.kind === "outage") openDisruption(row.id);
    else if (row.kind === "opportunity") openOpportunityOnMap(row.id);
    else if (row.refId) {
      const hub = nodeById.get(row.refId);
      if (hub) selectOnMap({ kind: "hub", id: hub.name.toUpperCase() });
      setFocus({ refId: row.refId, nonce: Date.now() });
      if (compactLayout) setSheetRaised(false);
    }
  };
  // The callouts on the map: only for what the trader opened (a disruption, a contract's window),
  // one at a time. A pulsing disruption is its pulse, not a box over the map; a selected cargo's
  // card is in the panel, not floating over the map (owner review 2026-11-26).
  const callouts = useMemo<MapCallout[]>(() => {
    const out: MapCallout[] = [];
    if (mapView === "book") {
      for (const item of disruptions) {
        if (!(openMark?.kind === "disruption" && openMark.id === item.event_id)) continue;
        const { title, lines } = disruptionCallout(item, tr, language);
        out.push({ id: `disruption:${item.event_id}`, at: [item.location.lon, item.location.lat], title, lines, tone: "alert" });
      }
    }
    if (openMark?.kind === "contract") {
      const line = bookFlows.find((entry) => entry.id === openMark.id);
      const at = line ? pointAtFraction(line.coordinates, 0.5) : null;
      if (line && at) {
        const names = (relevance?.contract_paths ?? []).filter((path) => line.routeIds.includes(path.contract_id)).map((path) => path.contract);
        const period = line.period ?? null;
        out.push({
          id: `contract:${line.id}`,
          at,
          title: names.join(" · ") || line.label,
          lines: period ? [periodLine(period, tr, language)] : [tr("map.book.progress_no_window")],
          progress: periodFraction(period),
          tone: "own",
        });
      }
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bookFlows, disruptions, language, mapView, openMark, relevance]);

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
        needsYou={needsYou}
        activeNeed={activeNeed}
        activeOpportunity={openOpportunityId}
        onSelectNeed={selectNeed}
        // Fly the map to the opportunity's path and open its card.
        onSelectOpportunity={openOpportunityOnMap}
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
    </>
  );

  // Phone width: the map is the page. Its controls live in the bottom sheet (view switch,
  // reset, full screen, then the layer chips in one row that scrolls sideways), never as
  // a second row of chrome above the map. Full screen keeps the toolbar over the map.
  const controlsInSheet = compactLayout && !expandedView.expanded;
  const layerChips = (
    <>
        {NETWORK_LAYERS.map((layer) => (
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
  );
  // Desktop: the layers are one menu, not a row of chips. The map is what the page shows; the
  // toolbar names the view and keeps its choices one click away.
  const shownLayerCount = [...NETWORK_LAYERS, ...SITUATION_LAYERS].filter((layer) => activeLayers.includes(layer)).length;
  const layerOption = (layer: string, hint: string) => (
    <label key={layer} className="map-layer-option" title={t(hint)}>
      <input type="checkbox" checked={activeLayers.includes(layer)} onChange={() => onToggleLayer(layer)} />
      <i className={`map-layer-swatch layer-${layer}`} aria-hidden="true" />
      <span>{t(`map.layer.${layer}`)}</span>
    </label>
  );
  // Intensity: one entry per metric (and off), each drawn flat by size and colour.
  const intensityChoice = (
    <>
      {[null, ...INTENSITY_METRICS].map((metric) => (
        <label key={metric ?? "off"} className="map-layer-option">
          <input
            type="radio"
            name="map-intensity"
            checked={intensity === metric}
            onChange={() => chooseIntensity(metric)}
          />
          <span>{t(metric ? `map.intensity.metric.${metric}` : "map.intensity.off")}</span>
        </label>
      ))}
    </>
  );
  const layerMenu = (
    <Popover
      label={t("map.layers_panel")}
      placement="bottom-start"
      width="sm"
      className="map-layer-menu"
      trigger={(props) => (
        <button {...props} type="button" className="chip map-layer-menu-trigger">
          <Icon name="layers" />
          <span>{t("map.layers_panel")}</span>
          <span className="map-layer-menu-count">{shownLayerCount}</span>
        </button>
      )}
    >
      {/* What touches the book first (on by default), then the rest of the system. */}
      <fieldset className="map-layer-group">
        <legend>{t("map.layers.group_situation")}</legend>
        {SITUATION_LAYERS.map((layer) => layerOption(layer, `map.layer.${layer}_hint`))}
      </fieldset>
      <fieldset className="map-layer-group">
        <legend>{t("map.layers.group_network")}</legend>
        {NETWORK_LAYERS.map((layer) =>
          layerOption(layer, layer === "routes" ? "map.layer.routes_hint" : layer === "network" ? "map.layer.network_hint" : `map.layer.${layer}`))}
      </fieldset>
      <fieldset className="map-layer-group">
        <legend title={t("map.intensity.hint")}>{t("map.intensity.layer")}</legend>
        {intensityChoice}
      </fieldset>
      <button type="button" className="link-button map-layer-default" onClick={() => { onDefaultLayers(); chooseIntensity(null); }}>
        {t("map.layers.default")}
      </button>
    </Popover>
  );
  // The flows' gas day: in the toolbar while flows (or a flow intensity) are drawn (latest by default),
  // never as a bar over the map's bottom edge, where the attribution lives.
  const [flowDay, setFlowDay] = useState<string | null>(null);
  const flowDays = useMemo(() => flowDayOptions(rawSituation), [rawSituation]);
  const flowDayPicker = (mapLayers.includes("flows") || intensity === "flow" || intensity === "utilisation") && flowDays.length > 0 ? (
    <label className="map-flow-day-select">
      <span>{t("map.scene.flow_day")}</span>
      <select
        value={flowDay && flowDays.includes(flowDay) ? flowDay : ""}
        onChange={(event) => setFlowDay(event.target.value || null)}
      >
        <option value="">{t("map.scene.flow_day_latest")}</option>
        {[...flowDays].reverse().map((day) => (
          <option key={day} value={day}>{formatGasDay(day, language, true)}</option>
        ))}
      </select>
    </label>
  ) : null;
  const toolbar = (
      <div className={controlsInSheet ? "map-toolbar network-desk-toolbar is-in-sheet" : "map-toolbar network-desk-toolbar"}>
        <Segmented
          className="map-view-switch"
          label={t("map.view.label")}
          options={(["network", "book"] as const).map((option) => ({ value: option, label: t(`map.view.${option}`), title: t(`map.view.${option}_hint`) }))}
          value={mapView}
          onChange={chooseMapViewAndTab}
        />
        {!controlsInSheet && (compactLayout ? layerChips : layerMenu)}
        {flowDayPicker}
        {/* The rest of the row is the map's; the view's own actions sit at its end. */}
        <span className="map-toolbar-spacer" aria-hidden="true" />
        {/* Phone width: one compact row, an icon with its name for assistive technology. The
            map's own view controls (fit, key) are in its corner; nothing here repeats them. */}
        <button
          type="button"
          className={compactLayout ? "chip map-fullscreen-chip map-icon-chip" : "chip map-fullscreen-chip"}
          aria-pressed={expandedView.expanded}
          aria-label={compactLayout ? t(expandedView.expanded ? "map.expand.exit" : "map.expand.enter") : undefined}
          title={t(expandedView.expanded ? "map.expand.exit_hint" : "map.expand.enter_hint")}
          onClick={expandedView.toggle}
          data-map-expand={expandedView.expanded ? "on" : "off"}
        >
          {compactLayout ? (
            <Icon name={expandedView.expanded ? "exit-full-screen" : "full-screen"} />
          ) : (
            <>
              <Icon name={expandedView.expanded ? "exit-full-screen" : "full-screen"} />
              <span>{t(expandedView.expanded ? "map.expand.exit" : "map.expand.enter")}</span>
            </>
          )}
        </button>
        {expandedView.expanded && (
          // Expanded, the map is alone; the panel opens over it as a drawer.
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
  );

  // The one map key: symbology only, for what is drawn (owner review 2026-11-26). Counts, the
  // list of sites and the explanation of how flows are drawn are not the key's job.
  const showsOwnCargo = mapLayers.includes("cargoes") && (situation?.cargoes ?? []).some((item) => item.own);
  const keyExtra = (
    <div className="map-key-extra">
      <div className="map-visual-legend" aria-label={t("map.visual_legend")}>
        {displayedHubCount > 0 && mapLayers.includes("hubs") && <span><i className="node-swatch hubs" />{t("map.key.hub_area")}</span>}
        {mapLayers.includes("hubs") && nodes.some((node) => node.metadata_json?.zone_only === true) && (
          <span><i className="node-swatch zone" />{t("map.key.zone_only")}</span>
        )}
        {mapLayers.includes("positions") && <span><i className="situation-dot own ring" />{t("map.key.own_position")}</span>}
        {showsOwnCargo && <span><i className="map-key-vessel" />{t("map.key.own_cargo")}</span>}
        {showsOwnCargo && <span><i className="line-swatch sailed" />{t("map.key.sailed")}</span>}
        {showsOwnCargo && <span><i className="line-swatch ahead" />{t("map.key.ahead")}</span>}
        {(mapLayers.includes("outages") || mapLayers.includes("outages_all")) && (
          <span><i className="situation-dot outage-active" />{t("map.key.outage_active")}</span>
        )}
        {(mapLayers.includes("outages") || mapLayers.includes("outages_all")) && (
          <span><i className="situation-dot outage-scheduled" />{t("map.key.outage_scheduled")}</span>
        )}
        {mapLayers.includes("corridors") && <span><i className="line-swatch corridor" />{t("map.key.corridor")}</span>}
        {surveyedPipelineCount > 0 && <span><i className="line-swatch verified" />{t("map.key.pipeline")}</span>}
        {connectionLinkCount > 0 && <span><i className="line-swatch link" />{t("map.key.connection")}</span>}
        {mapLayers.includes("routes") && mapView === "network" && (
          <span><i className="line-swatch context" />{t("map.key.context_pipelines")}</span>
        )}
        {indicativeRouteCount > 0 && <span><i className="line-swatch indicative" />{t("map.indicative_route_lines")}</span>}
        {bookFlows.length > 0 && mapLayers.includes("positions") && <span><i className="line-swatch flow" />{t("map.key.book_flow")}</span>}
        {mapView === "book" && <span className="map-book-legend-line">{t("map.book.legend")}</span>}
        {mapLayers.includes("vessels") && situation?.vessel_feed?.entitled === false && (
          // A licensed feed the caller does not hold: said where the vessels would be drawn.
          <span className="is-alert">{t("map.situation.vessels_unentitled")}</span>
        )}
      </div>
    </div>
  );

  return (
    <div
      ref={shellRef}
      className={`network-workspace-shell network-desk${expandedView.expanded ? " is-fullscreen" : ""}${expandedView.expanded ? " is-expanded" : ""}${sheetRaised ? " is-sheet-raised" : ""}${panelCollapsed && !expandedView.expanded && !compactLayout ? " is-panel-collapsed" : ""}${drawerOpen ? " is-drawer-open" : ""}`}
      data-map-view={mapView}
    >
      {!controlsInSheet && toolbar}
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
          bookOpportunities={opportunityLines}
          onSelectOpportunity={(id) => {
            setOpenOpportunityId(id);
            setOpenMark(null);
            setSelection(null);
          }}
          bookDisruptions={disruptionPlaces}
          onSelectDisruption={(id) => openDisruption(id, false)}
          bookProposals={proposals}
          // The proposed line draws in when it first shows and again when it is opened.
          drawInKey={openOpportunityId ?? "shown"}
          onSelectContractLine={(id) => {
            setOpenMark({ kind: "contract", id });
            setOpenOpportunityId(null);
          }}
          callouts={callouts}
          flowDay={flowDay}
          intensity={intensity}
          onSelectIntensity={(pick) => {
            setIntensityPick(pick);
            setCorridorPick(null);
            setSelection(null);
            if (compactLayout) setSheetRaised(true);
          }}
          corridors={corridors}
          onSelectCorridor={(id) => {
            setCorridorPick(id);
            setIntensityPick(null);
            setSelection(null);
            if (compactLayout) setSheetRaised(true);
          }}
          keyExtra={keyExtra}
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
        {/* No status chip over the map: the outage counts are the panel's, and the page's one
            freshness indicator is in its context line. Only a map read that keeps failing is
            said here, because the picture on screen is then older than the page claims. */}
        {situationStale && readAt && (
          <p className="map-basemap-state is-fallback map-situation-stale" role="status">
            <strong>{tr("map.situation.stale_since", { time: readAt.toISOString().slice(11, 16) })}</strong>
          </p>
        )}
        {!mapHasVisibleEvidence && (
          <div className="map-empty-state" role="status">
            <strong>{t("map.empty_title")}</strong>
            <span>{t(geometryMessageKey(networkGeometryState))}</span>
            <small>{t("map.empty_help")}</small>
          </div>
        )}
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
        {controlsInSheet && toolbar}
        {controlsInSheet && (
          <div className="map-layer-row" role="group" aria-label={t("map.layers_panel")}>
            {layerChips}
            <label className="map-flow-day-select">
              <span>{t("map.intensity.layer")}</span>
              <select value={intensity ?? ""} onChange={(event) => chooseIntensity((event.target.value || null) as IntensityMetric | null)}>
                {[null, ...INTENSITY_METRICS].map((metric) => (
                  <option key={metric ?? "off"} value={metric ?? ""}>{t(metric ? `map.intensity.metric.${metric}` : "map.intensity.off")}</option>
                ))}
              </select>
            </label>
          </div>
        )}
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
          // A phone lowers the sheet with its handle instead.
          collapsed={panelCollapsed && !expandedView.expanded && !compactLayout}
          onCollapse={expandedView.expanded ? () => setDrawerOpen(false) : () => choosePanelCollapsed(true)}
          onExpand={(tab) => {
            setPanelTab(tab);
            choosePanelCollapsed(false);
          }}
        />
      </div>
    </div>
  );
}
