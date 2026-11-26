import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
// maplibre-gl v6 is ESM-only and has no default export: every symbol the map uses is imported by
// name. (The upgrade from v5 to v6.10.0 is a security fix - see the package note in
// `clients/web/package.json` and `docs/operations/VALIDATION.md`.)
import {
  AttributionControl,
  GeoJSONSource,
  Map as MapLibreMap,
  Marker,
  NavigationControl,
  Popup,
  setWorkerUrl,
} from "maplibre-gl";
import type { ExpressionSpecification } from "maplibre-gl";
import mapLibreWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import "maplibre-gl/dist/maplibre-gl.css";
import { EdgeDTO, FacilityDTO, MapCargoDTO, MapSituationDTO, NodeDTO, RouteEligibilityDTO, type SupplyCorridorDTO } from "@/api/client";
import {
  OVERVIEW_MAX_ZOOM,
  SITUATION_COLOURS,
  type ZoomTier,
  cargoFeatures,
  detailLabel,
  zoomTier,
  contractFeatures,
  facilityFeatures,
  flowFeatures,
  outageFeatures,
  situationCardHtml,
  slotTerminalFeatures,
} from "@/app/mapSituation";
import {
  buildVisibleMapNetworkLines,
  buildVisibleNetworkNodes,
  networkLineMatchesRoute,
  type NetworkHighlightedRoute,
} from "@/app/networkMapLines";
import { lineMatters, NO_ROUTES_MATTER, type RoutesThatMatter } from "@/app/routeEmphasis";
import { warmMapAssets } from "@/app/mapAssetWarmup";
import { periodFraction, splitAtFraction, type DisruptionMark, type ProposalLine } from "@/app/mapBookRelevance";
import { cameraMotion, drawInDuration, easeOut, prefersReducedMotion } from "@/app/mapMotion";
import {
  type BookFlowLine,
  compactMwhPerDay,
  hubAdjacencyEdges,
  presentationPath,
  isDrawnAdjacency,
  isZoneMembershipEdge,
  zoneMemberIds,
} from "@/app/mapLineGeometry";
import i18n from "@/i18n";
import {
  OSM_ATTRIBUTION,
  buildMapStyle,
  configuredMapTileProvider,
  labelFont,
  mapTileProviderById,
  mapZoomRange,
  muteVectorBasemap,
  outlinePalette,
  transformCoordinate,
} from "@/app/mapTileProviders";
import type { RouteGeometryState } from "@/components/ResourcePoolPathOverlay";
import { FACILITY_ICON, drawFacilityIcon, drawVesselIcon, vesselIconId } from "@/app/mapIcons";
import { hubDeskName, isZoneOnly, labelFeatures, mapLabels, type MapLabel } from "@/app/mapLabels";
import { cargoEta, cargoMapLabel } from "@/app/mapCargo";
import { basemapNameExpression } from "@/app/basemapLabels";
import { corridorLabel, corridorLines } from "@/app/mapCorridors";
import { MapFinder, type MapFinderPlace } from "@/components/MapFinder";
import { MapDetailPanel } from "@/components/MapDetailPanel";
import {
  CONTEXT_PIPELINES_ATTRIBUTION,
  loadContextPipelines,
  projectContextPipelines,
  type ContextPipelineCollection,
} from "@/app/contextPipelines";
import { buildSites, siteOf, sitePipelines, siteSituation, type MapSelection, type Site } from "@/app/mapSelection";
import { useApiStore } from "@/stores/api";
import { useShellLayout } from "@/app/shell/useShellLayout";
import { plainDecimal } from "@/app/time/valueFormat";
import { useInstantFormatter } from "@/app/time/useInstant";
import { Icon } from "@/components/ui/Icon";
import { useMapScene } from "@/components/mapScene/useMapScene";
import {
  BORDER_FLOWS_BELOW_ZOOM,
  borderFlows,
  intensityColour,
  intensityPoints,
  intensityRadius,
  type IntensityDatum,
  type IntensityMetric,
} from "@/app/mapIntensity";
import { MapSceneControls } from "@/components/mapScene/MapSceneControls";
import { chevronAt, flowDayOptions, pointIndex, tweenPoints, type FC } from "@/app/mapScene";

// Let Vite resolve and bundle the module worker and its shared imports in both dev and build.
// MapLibre's default relative URL otherwise points inside Vite's optimized dependency cache.
setWorkerUrl(mapLibreWorkerUrl);


// Landing on the map itself: its own files start at once (app/mapAssetWarmup.ts).
if (typeof window !== "undefined" && /[?&]task=network(&|$)/.test(window.location.search)) warmMapAssets();

type Translate = (key: string, options?: Record<string, unknown>) => string;

interface GasNetworkMapProps {
  nodes: NodeDTO[];
  edges: EdgeDTO[];
  routes: RouteEligibilityDTO[];
  themeMode: "light" | "dark" | "system";
  activeLayers: string[];
  searchTerm: string;
  t: Translate;
  highlightedRoute?: NetworkHighlightedRoute;
  /** Routes the decision's allocations flow on (by route and pipeline segment): drawn bright. */
  routesInUse?: { routeIds: string[]; edgeIds: string[] };
  /**
   * Hand a clicked node to the canonical Inspector. Omitted where the page's composition
   * does not declare `network-node` as an inspectable subject, so no surface promises
   * detail it has no contract for.
   */
  onInspectNode?: (nodeId: string, label: string) => void;
  /** Live situation (outages, flows, own positions) from `/api/portfolio/map-situation`. */
  situation?: MapSituationDTO | null;
  /** Located infrastructure (platforms, storage, plants) from the reference facilities. */
  facilities?: FacilityDTO[];
  /**
   * "network": infrastructure is quiet context (small muted points, faint lines) under the
   * live situation. "book": the firm's own deals carry the picture and the network steps
   * further back. Either way everything stays clickable.
   */
  view?: "network" | "book";
  /** A completed deal being replayed: the whole path faint, the part sailed so far and the vessel. */
  replay?: { path: Array<[number, number]>; sailed: Array<[number, number]>; at: [number, number]; label: string } | null;
  /**
   * A preview (the Market overview's mini-map): no place finder and no zoom-tier card, which
   * would cover most of a small map; the full map is one click away (#12).
   */
  compact?: boolean;
  /**
   * Select and fly to a place or a cargo from outside the map (the book list, the Network
   * panel); `nonce` re-fires it. `at` (longitude, latitude) flies there when the item names no
   * network point or facility of its own.
   */
  focus?: {
    refId?: string | null;
    cargoId?: string;
    at?: [number, number] | null;
    /** A path to frame (an opportunity's): the map fits it in view. */
    path?: Array<[number, number]> | null;
    nonce: number;
  } | null;
  /**
   * The selection, when the page holds it (the Network panel lists what the selected object
   * relates to). Omitted, the map keeps its own. Either way every change is reported through
   * `onSelectionChange`.
   */
  selection?: MapSelection | null;
  onSelectionChange?: (selection: MapSelection | null) => void;
  /** false: the page shows the selected object's card (the Network panel), not the map. */
  detailCard?: boolean;
  /** The visible area after each move, in longitude and latitude (the panel's "Follow map"). */
  onViewChange?: (bounds: { west: number; south: number; east: number; north: number }) => void;
  /** A quiet ring where a hovered list row is (longitude, latitude); null for none. */
  hoverAt?: [number, number] | null;
  /**
   * The book's allocated flows, one per origin and destination (see mapLineGeometry.ts):
   * width by volume, the volume at the destination, one arrowhead for direction.
   */
  bookFlows?: BookFlowLine[];
  /**
   * The "Our book" view's emphasis (design basis 2, J.5; see app/mapBookRelevance.ts): node ids
   * that are ours (full), on a reachable path (medium); everything else dims in the book view.
   */
  bookEmphasis?: { ours: ReadonlySet<string>; reachable: ReadonlySet<string> };
  /** Paths to reachable neighbouring market areas, drawn at medium emphasis in the book view. */
  bookReachable?: Array<{ id: string; toHub: string; coordinates: Array<[number, number]> }>;
  /**
   * The caller's opportunity paths in the book view (app/mapBookRelevance.ts): actionable ones
   * pop out with their headline on the far hub, a watch-state one is a thin outline.
   */
  bookOpportunities?: Array<{
    id: string;
    opportunityId: string;
    emphasis: "pop" | "outline";
    coordinates: Array<[number, number]>;
    labelAt: [number, number];
    label: string;
  }>;
  /** Selecting an opportunity path or its label opens the opportunity. */
  onSelectOpportunity?: (opportunityId: string) => void;
  /**
   * Disruptions touching the book (book view): a quiet mark each; one active and touching our
   * contracts pulses slowly (a ring, no pulse, under reduced motion). Selecting opens it.
   */
  bookDisruptions?: DisruptionMark[];
  onSelectDisruption?: (eventId: string) => void;
  /**
   * Re-route and locational alternatives (book view): the current way dimmed, the proposed
   * one highlighted with its benefit on the line, drawn in once when `drawInKey` changes.
   */
  bookProposals?: ProposalLine[];
  drawInKey?: string | number | null;
  /** Selecting a contract's path (its done or to-go part) opens its window. */
  onSelectContractLine?: (lineId: string) => void;
  /** Callouts anchored on the map: what, until when, how much of ours, progress. */
  callouts?: MapCallout[];
  /** The page's own key lines, shown first in the map's one key. */
  keyExtra?: ReactNode;
  /** The stored gas day the flows show (null: each point's latest closed day); the page's toolbar picks it. */
  flowDay?: string | null;
  /** The intensity view's metric (the Layers menu), or null for the flat map. */
  intensity?: IntensityMetric | null;
  /** A clicked intensity column: its figure, unit, gas day and source go to the side panel. */
  onSelectIntensity?: (pick: { metric: IntensityMetric; datum: IntensityDatum }) => void;
  /** Europe's import supply corridors (the "Supply corridors" layer). */
  corridors?: SupplyCorridorDTO[];
  /** A clicked corridor: its facts go to the side panel. */
  onSelectCorridor?: (corridorId: string) => void;
}

/** A callout on the map: a title, short lines and an optional progress bar (0..1). */
export interface MapCallout {
  id: string;
  at: [number, number];
  title: string;
  lines: string[];
  progress?: number | null;
  tone: "alert" | "own" | "opportunity";
}

/**
 * How strongly the reference layers draw in each view. The network is the stage, not the
 * subject: points are small and muted and lines faint, so the live situation and the firm's
 * own positions read first. Layers not listed keep their own opacity.
 */
const VIEW_EMPHASIS: Record<"network" | "book", Record<string, unknown>> = {
  network: {
    "nodes-circle": ["case", ["==", ["get", "node_type"], "hub"], 0.85, 0.5],
    "node-clusters": 0.45,
    // Context routes dimmed; a route the book uses at full strength. Lines stay quieter
    // than the points they join.
    "verified-pipeline-lines": ["case", ["==", ["get", "matters"], true], 0.95, 0.32],
    "network-link-lines": ["case", ["==", ["get", "matters"], true], 0.95, 0.85],
    "adjacency-points": 0.9,
    "indicative-route-lines": ["case", ["==", ["get", "matters"], true], 0.9, 0.24],
    "book-flow-lines": 0.85,
    "situation-facilities": 0.55,
  },
  book: {
    "nodes-circle": ["case", ["==", ["get", "node_type"], "hub"], 0.55, 0.22],
    "node-clusters": 0.2,
    "verified-pipeline-lines": ["case", ["==", ["get", "matters"], true], 0.95, 0.12],
    "network-link-lines": ["case", ["==", ["get", "matters"], true], 0.9, 0.3],
    "adjacency-points": 0.35,
    "indicative-route-lines": ["case", ["==", ["get", "matters"], true], 0.9, 0.12],
    "book-flow-lines": 0.95,
    "situation-facilities": 0.2,
  },
};

/** Context pipelines in the neutral edge colour, routes the book uses in the route colour. */
function routeLineColor(colors: { edge: string; route: string }): ExpressionSpecification {
  return ["case", ["==", ["get", "matters"], true], colors.route, colors.edge];
}

/** Connections between market areas in the link colour; one the book uses in the route colour. */
function linkLineColor(colors: { link: string; route: string }): ExpressionSpecification {
  return ["case", ["==", ["get", "matters"], true], colors.route, colors.link];
}

/** The HTML overlays drawn over the map canvas; names keep clear of them (see the blockers). */
export const OVERLAY_SELECTOR = [
  ".map-finder",
  ".map-finder-toggle",
  ".map-control-stack",
  ".maplibregl-ctrl-top-right .maplibregl-ctrl",
  ".maplibregl-ctrl-bottom-left .maplibregl-ctrl",
  ".map-basemap-state",
  ".map-scene-key",
  ".map-intensity-legend",
].join(", ");

const SITUATION_HOVER_LAYERS = [
  "situation-outages",
  "situation-contracts",
  "situation-regas",
  "situation-cargo-positions",
  "situation-flows",
  "situation-facilities",
] as const;

/** Fly to a point (or jump, under reduced motion), never past the map's own zoom limit. */
/** MapLibre instances created in this page's life (see `data-map-instance`). */
let MAP_INSTANCES = 0;

/**
 * Frame our cargo: the vessel and the terminal it is going to in one view, so "where is it and
 * how far to go" reads at a glance; the vessel alone when no destination is located.
 */
function frameCargo(map: MapLibreMap, cargo: MapCargoDTO | undefined, project: (lon: number, lat: number) => [number, number]): boolean {
  const at = cargo?.position ?? cargo?.origin ?? cargo?.destination;
  if (!cargo || !at) return false;
  const points = [at, cargo.destination].filter(Boolean).map((place) => project(place!.lon, place!.lat));
  if (points.length < 2 || (points[0][0] === points[1][0] && points[0][1] === points[1][1])) {
    focusOn(map, points[0], Math.max(map.getZoom(), 5));
    return true;
  }
  const { clientWidth: width, clientHeight: height } = map.getContainer();
  const pad = Math.max(24, Math.min(90, Math.round(Math.min(width, height) * 0.15)));
  map.fitBounds(
    [[Math.min(points[0][0], points[1][0]), Math.min(points[0][1], points[1][1])], [Math.max(points[0][0], points[1][0]), Math.max(points[0][1], points[1][1])]],
    { padding: pad, maxZoom: 7, ...(prefersReducedMotion() ? { duration: 0 } : cameraMotion()) },
  );
  return true;
}

function focusOn(map: MapLibreMap, center: [number, number], zoom: number): void {
  const target = { center, zoom: Math.min(zoom, map.getMaxZoom()) };
  if (prefersReducedMotion()) map.jumpTo(target);
  // The design system's map motion (--ds-duration-map, --ds-ease-out).
  else map.flyTo({ ...target, ...cameraMotion(), essential: false });
}

type FeatureCollectionData = Parameters<GeoJSONSource["setData"]>[0];

/** What each source last drew, so an update that changes nothing sends nothing to the map. */
const drawnSources = new WeakMap<MapLibreMap, Map<string, string>>();

/**
 * Add a source, or update it in place: a diff applied to the existing source (no layer
 * teardown, so selection, camera and open cards stay). A source whose data did not change is
 * not touched: a revalidation that found nothing new redraws nothing.
 */
function upsertSource(map: MapLibreMap, id: string, data: FeatureCollectionData): boolean {
  const drawn = drawnSources.get(map) ?? new Map<string, string>();
  drawnSources.set(map, drawn);
  const text = typeof data === "string" ? data : JSON.stringify(data);
  const source = map.getSource(id) as GeoJSONSource | undefined;
  if (source) {
    if (drawn.get(id) !== text) source.setData(data);
    drawn.set(id, text);
    return false;
  }
  map.addSource(id, { type: "geojson", data });
  drawn.set(id, text);
  return true;
}

function resolveEffectiveTheme(themeMode: GasNetworkMapProps["themeMode"]): "light" | "dark" {
  if (themeMode === "dark") return "dark";
  if (themeMode === "light") return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function propertyText(value: unknown, fallback = "n/a"): string {
  if (value === null || value === undefined || value === "") return fallback;
  return String(value);
}

function metadataString(metadata: Record<string, unknown> | null | undefined, key: string, fallback = ""): string {
  const value = metadata?.[key];
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function escapeHtml(value: unknown): string {
  return propertyText(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    "\"": "&quot;",
    "'": "&#39;",
  }[char] ?? char));
}

function routeGeometryStateLabel(state: RouteGeometryState, t: Translate): string {
  if (state === "not_applicable_local_disposition") {
    return t("map.geometry_not_applicable_local_sale");
  }
  if (state === "surveyed_pipeline_route") return t("map.geometry_surveyed_pipeline");
  if (state === "source_derived_leg_sequence") return t("map.geometry_source_derived_sequence");
  if (state === "source_derived_corridor") return t("map.geometry_source_derived_corridor");
  return t("map.geometry_indicative_corridor");
}

function routeGeometryStateClass(state: RouteGeometryState): string {
  if (state === "surveyed_pipeline_route") return "surveyed";
  if (state === "source_derived_leg_sequence") return "leg-sequence";
  if (state === "source_derived_corridor") return "corridor";
  return "corridor";
}

const MAX_MAP_LABELS = 12;
const MAJOR_HUB_PRIORITY = [
  "TTF",
  "NBP",
  "THE",
  "ZTP",
  "PEG",
  "PSV",
  "CEGH",
  "PVB",
  "VTP",
  "IBP",
];

/** The desk's short name for a point: its market code, else the name's own code part
 * ("ZTP (Zeebrugge Trading Point)" is ZTP, "VTP - Gas Exchange Point" VTP); the full name is
 * the label's tooltip. */
export function fallbackNodeLabel(node: NodeDTO): string {
  const metadata = node.metadata_json ?? {};
  const code = metadata.market_code;
  if (typeof code === "string" && code.trim()) return code.trim();
  const head = node.name.split(/\s+\(|\s+[-–]\s+/)[0].trim();
  // A generic code (VTP, VIP) names several places: it carries its country (VTP CZ, VTP SK).
  if (/^(VTP|VIP|PVB|VHP)$/i.test(head) && node.country) return `${head} ${node.country}`;
  return head.length > 14 ? `${head.slice(0, 13)}…` : head || node.name;
}

function isSearchLabelMatch(node: NodeDTO, searchTerm: string): boolean {
  if (!searchTerm) return false;
  return [
    node.name,
    node.country,
    node.node_type,
    fallbackNodeLabel(node),
    node.source_system ?? "",
  ].some((value) => value.toLowerCase().includes(searchTerm));
}

/**
 * The full map's camera and selection outlive the component: leaving the Network page (a mode
 * switch unmounts it) and coming back restores them at once instead of starting over. The
 * Market overview's mini-map (``compact``) keeps its own.
 */
const remembered: {
  camera: { center: [number, number]; zoom: number } | null;
  selection: MapSelection | null;
} = { camera: null, selection: null };


export function GasNetworkMap({
  nodes,
  edges,
  themeMode,
  activeLayers,
  searchTerm,
  t,
  highlightedRoute,
  routesInUse,
  onInspectNode,
  situation = null,
  facilities = [],
  view = "network",
  compact = false,
  replay = null,
  focus = null,
  bookFlows = [],
  bookEmphasis,
  bookReachable = [],
  bookOpportunities = [],
  onSelectOpportunity,
  bookDisruptions = [],
  onSelectDisruption,
  bookProposals = [],
  drawInKey = null,
  onSelectContractLine,
  callouts = [],
  keyExtra,
  selection: selectionProp,
  onSelectionChange,
  detailCard = true,
  onViewChange,
  hoverAt = null,
  flowDay = null,
  intensity = null,
  onSelectIntensity,
  corridors = [],
  onSelectCorridor,
}: GasNetworkMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  /** The basemap's own place-name layers (named in the app language). */
  const basemapSymbolIdsRef = useRef<string[]>([]);
  const [mapReady, setMapReady] = useState(false);
  // MapLibre needs WebGL. On a machine without it (remote desktop, locked-down browser, old
  // GPU driver) the constructor throws; without this the throw took the whole page down to a
  // white screen. The page now says why the map is missing and keeps the network lists.
  const [mapStartError, setMapStartError] = useState<string | null>(null);
  const [tier, setTier] = useState<ZoomTier>("overview");
  /** The whole zoom level, for the labels that appear as the view narrows. */
  const [labelZoom, setLabelZoom] = useState(3);
  /** The outages the map draws: those touching our book, or every one with "All outages". */
  const outageIds = useMemo(() => {
    if (!situation) return new Set<string>();
    if (activeLayers.includes("outages_all")) return new Set(situation.outages.map((item) => item.event_id));
    if (!activeLayers.includes("outages")) return new Set<string>();
    return new Set(situation.book_relevance?.outages_touching ?? []);
  }, [activeLayers, situation]);
  // The "control tower" selection: one object at a time, its card docked on the right, the
  // object and what it relates to highlighted and the rest dimmed.
  // Uncontrolled, the selection is remembered across a remount (a mode switch), as the camera is.
  const [ownSelection, setOwnSelection] = useState<MapSelection | null>(
    () => (compact ? null : remembered.selection),
  );
  const selectionControlled = selectionProp !== undefined;
  const selection = selectionControlled ? selectionProp : ownSelection;
  useEffect(() => {
    if (!compact) remembered.selection = selection ?? null;
  }, [compact, selection]);
  // Stable for the handlers the map registers once: they always reach the current owner.
  const selectionOwnerRef = useRef({ controlled: selectionControlled, report: onSelectionChange });
  selectionOwnerRef.current = { controlled: selectionControlled, report: onSelectionChange };
  const setSelection = useCallback((next: MapSelection | null) => {
    if (!selectionOwnerRef.current.controlled) setOwnSelection(next);
    selectionOwnerRef.current.report?.(next);
  }, []);
  const viewChangeRef = useRef(onViewChange);
  viewChangeRef.current = onViewChange;
  const sites = useMemo(() => buildSites(nodes, facilities), [facilities, nodes]);
  const tsoTariffs = useApiStore((state) => state.tsoTariffs);
  // The hover card of a connection between market areas: the two sides, every point on that
  // border with its firm technical capacity, and whether the register holds its tariffs.
  const borderCard = (props: Record<string, unknown>): string => {
    const byId = new globalThis.Map(nodes.map((node) => [node.id, node]));
    const nameOfKey = (key: string) =>
      key.startsWith("pipeline:")
        ? key.slice("pipeline:".length)
        : byId.get(`entsog-${key.toLowerCase()}`)?.name ?? key;
    const held = (pointKey: string) => tsoTariffs.filter((row) => row.point_id === pointKey).length;
    if (props.edge_type === "interconnector") {
      const from = byId.get(String(props.from_node_id))?.name ?? "";
      const to = byId.get(String(props.to_node_id))?.name ?? "";
      return `<div class="node-popup situation-card"><strong>${escapeHtml(props.name)}</strong>`
        + `<small>${escapeHtml(t("map.border.pipeline"))}: ${escapeHtml(from)} – ${escapeHtml(to)}</small></div>`;
    }
    let joins: string[] = [];
    try {
      joins = JSON.parse(String(props.joins ?? "[]"));
    } catch {
      joins = [];
    }
    const pair = JSON.stringify(joins);
    const points = new globalThis.Map<string, { name: string; capacity: number | null; drawn: boolean }>();
    for (const edge of edges) {
      const meta = edge.metadata_json ?? {};
      if (edge.edge_type !== "market_area_link" || JSON.stringify([...(Array.isArray(meta.joins) ? meta.joins : [])].sort()) !== pair) continue;
      const key = String(meta.point_key ?? "");
      const capacity = typeof meta.firm_technical_kwh_d === "number" ? meta.firm_technical_kwh_d : null;
      points.set(key, { name: byId.get(edge.from_node_id)?.name ?? key, capacity, drawn: meta.representative === true });
    }
    const rows = [...points.entries()]
      .sort((a, b) => Number(b[1].drawn) - Number(a[1].drawn) || (b[1].capacity ?? 0) - (a[1].capacity ?? 0))
      .map(([key, point]) => {
        const capacity = point.capacity !== null ? `${Math.round(point.capacity / 1e6).toLocaleString()} GWh/d` : t("map.border.capacity_unpublished");
        const tariffs = held(key) > 0 ? t("map.border.tariff_held") : t("map.border.tariff_not_held");
        return `<span><b>${escapeHtml(point.name)}</b><small>${escapeHtml(capacity)} · ${escapeHtml(tariffs)}</small></span>`;
      })
      .join("");
    const title = joins.map(nameOfKey).join(" – ");
    return `<div class="node-popup situation-card"><strong>${escapeHtml(title)}</strong>`
      + `<small>${escapeHtml(t("map.border.points", { count: points.size }))}</small>${rows}`
      // Drawn along the open reference trunk lines: the general direction, not a surveyed route.
      + (props.geometry_basis === "reference_pipeline_direction"
        ? `<small class="muted">${escapeHtml(t("map.border.drawn_along"))}</small>`
        : "")
      + "</div>";
  };
  const borderCardRef = useRef(borderCard);
  borderCardRef.current = borderCard;
  const phoneWidth = useShellLayout().widthClass === "compact";
  const sitesRef = useRef<Site[]>(sites);
  sitesRef.current = sites;
  const marketRows = useApiStore((state) => state.normalizedMarkets);
  /** The selection a clicked network point, facility or located item stands for. */
  const selectFor = (refId: string, nodeType = ""): MapSelection | null => {
    // Anything located at a hub (a contract delivering "at NBP") selects the hub.
    const hub = nodes.find((node) => node.id === refId && (nodeType === "hub" || node.node_type === "hub"));
    if (hub) return { kind: "hub", id: hub.name.toUpperCase() };
    const site = siteOf(sitesRef.current, refId);
    return site ? { kind: "site", id: site.id } : null;
  };
  const selectForRef = useRef(selectFor);
  selectForRef.current = selectFor;
  const effectiveTheme = resolveEffectiveTheme(themeMode);
  // The deployment profile names the installation's default basemap; it can arrive after the
  // map first mounts, so the provider follows it. A vector basemap that cannot be reached (an
  // office proxy, an air-gapped network) falls back to the bundled outline and says so.
  const deploymentMapDefault = useApiStore((state) => state.runtimeRelease?.deployment?.map_default_provider ?? null);
  const [unreachableBasemap, setUnreachableBasemap] = useState<string | null>(null);
  const configuredProvider = useMemo(configuredMapTileProvider, [deploymentMapDefault]);
  const basemapFellBack = unreachableBasemap === configuredProvider.id;
  const mapTileProvider = basemapFellBack ? mapTileProviderById("outline")! : configuredProvider;
  // The outline is said only when it stands in for OpenStreetMap (offline, unreachable); a China
  // installation draws it by design and says nothing.
  const showingOfflineOutline = mapTileProvider.id === "outline" && deploymentMapDefault !== "outline";
  const toMapCoordinates = (lon: number, lat: number): [number, number] =>
    transformCoordinate(mapTileProvider.id, lon, lat);
  const mapColors = useMemo(
    () => effectiveTheme === "dark"
      ? {
          background: "#0b1220",
          edge: "#737373",
          // Connections between market areas: legible on the dark land, still under markers.
          link: "#b4bcc8",
          route: "#50e3c2",
          // Generic points are neutral: blue on this map means the firm's own positions.
          node: "#94a3b8",
          zone: "#71717a",
          hub: "#50e3c2",
          lng: "#b978ff",
          interconnection: "#f5a623",
          stroke: "#0a0a0a",
        }
      : {
          // Water: a quiet blue, so land (white) and sea read apart at a glance.
          background: "#e3ebf3",
          edge: "#6b7280",
          link: "#4b5563",
          route: "#00b871",
          node: "#64748b",
          zone: "#a1a1aa",
          hub: "#50e3c2",
          lng: "#7928ca",
          interconnection: "#f5a623",
          stroke: "#ffffff",
        },
    [effectiveTheme],
  );
  const nodeLookup = useMemo(() => new globalThis.Map(nodes.map((node) => [node.id, node])), [nodes]);
  const filteredNodes = useMemo(
    () => buildVisibleNetworkNodes({ nodes, edges, activeLayers, searchTerm, highlightedRoute }),
    [activeLayers, edges, highlightedRoute, nodes, searchTerm],
  );
  const visibleLines = useMemo(
    () => buildVisibleMapNetworkLines({ nodes, edges, activeLayers, searchTerm, highlightedRoute }),
    [activeLayers, edges, highlightedRoute, nodes, searchTerm],
  );
  // Routes are context, drawn dimmed so a trader sees there is a way through. A route that
  // carries the book (an allocation's route, or a pipeline landing gas where the book has a
  // live contract, slot or cargo) is drawn bright. "Routes" off hides the context routes.
  const routesMatter = useMemo<RoutesThatMatter>(() => {
    const pointIds = new Set<string>();
    // A delivery at a hub is a market position, not a use of the hub's connections: only a
    // physical point a contract names lights the lines that reach it.
    const isHub = (refId: string) => nodeLookup.get(refId)?.node_type === "hub";
    for (const contract of situation?.contracts ?? []) {
      if (contract.location.ref_id && !isHub(contract.location.ref_id)) pointIds.add(contract.location.ref_id);
    }
    for (const slot of situation?.regas_slots ?? []) if (slot.location.ref_id) pointIds.add(slot.location.ref_id);
    for (const cargo of situation?.cargoes ?? []) {
      if (cargo.own && cargo.status !== "delivered" && cargo.status !== "ballast" && cargo.destination?.ref_id) {
        pointIds.add(cargo.destination.ref_id);
      }
    }
    if (!routesInUse && pointIds.size === 0) return NO_ROUTES_MATTER;
    return {
      routeIds: new Set(routesInUse?.routeIds ?? []),
      edgeIds: new Set(routesInUse?.edgeIds ?? []),
      pointIds,
    };
  }, [nodeLookup, routesInUse, situation]);
  const showContextRoutes = activeLayers.includes("routes");
  const matteringLineIds = useMemo(
    () => new Set(visibleLines.filter((line) => lineMatters(line, routesMatter)).map((line) => line.id)),
    [routesMatter, visibleLines],
  );
  const verifiedPipelineLines = useMemo(
    // Surveyed pipelines and topology links share one layer: both are the network; a link is
    // drawn thinner and its card says the path is schematic.
    () => visibleLines.filter((line) =>
      (line.displayKind === "verified_pipeline" || line.displayKind === "network_link")
      && (showContextRoutes || matteringLineIds.has(line.id))),
    [matteringLineIds, showContextRoutes, visibleLines],
  );
  // A route candidate is a trade route, not a pipe: drawn when the book uses it, or as context
  // only when the server gives its path. Candidates from one hub to every other hub drawn as
  // schematic segments would be a star again.
  const indicativeRouteLines = useMemo(
    () => visibleLines.filter((line) =>
      line.displayKind === "indicative_route" && (
        matteringLineIds.has(line.id) ||
        (showContextRoutes && line.geometryBasis === "backend_route_geometry_coordinates")
      )),
    [matteringLineIds, showContextRoutes, visibleLines],
  );
  const highlightedRoutePoints = useMemo(() => {
    if (!highlightedRoute) return null;
    const from = nodeLookup.get(highlightedRoute.fromNodeId);
    const to = nodeLookup.get(highlightedRoute.toNodeId);
    if (!from || !to) return null;
    return { ...highlightedRoute, from, to };
  }, [highlightedRoute, nodeLookup]);
  const routeSegmentsForHighlight = useMemo(() => {
    if (!highlightedRoutePoints?.routeId) return [];
    return visibleLines
      .filter((line) => networkLineMatchesRoute(line, highlightedRoutePoints.routeId))
      .sort((left, right) => left.routeLegSequence - right.routeLegSequence);
  }, [highlightedRoutePoints?.routeId, visibleLines]);
  const highlightedRouteIsVerified = routeSegmentsForHighlight.length > 0 &&
    routeSegmentsForHighlight.every((line) => line.displayKind === "verified_pipeline");
  const geometryWarning = highlightedRouteIsVerified
    ? `${routeGeometryStateLabel(highlightedRoutePoints?.routeGeometryState ?? "surveyed_pipeline_route", t)} ${t("map.geometry_from_verified_metadata")}`
    : highlightedRoutePoints?.routeGeometryState === "surveyed_pipeline_route"
      ? `${routeGeometryStateLabel(highlightedRoutePoints.routeGeometryState, t)}: ${t("map.geometry_surveyed_metadata_only")}`
      : `${routeGeometryStateLabel(highlightedRoutePoints?.routeGeometryState ?? "source_derived_corridor", t)}: ${t("map.geometry_indicative_warning")}`;
  const highlightedRouteSegmentFeatures = useMemo(
    () =>
      routeSegmentsForHighlight.map((line) => {
        const metadata = line.edge?.metadata_json ?? {};
        return {
          type: "Feature" as const,
          properties: {
            id: line.id,
            route_id: line.routeId || highlightedRoutePoints?.routeId || "",
            route_leg_sequence: line.routeLegSequence,
            route_geometry_state: line.routeGeometryState,
            geometry_quality: metadataString(metadata, "geometry_quality", line.geometryBasis),
            geometry_basis: line.geometryBasis,
            display_kind: line.displayKind,
            geometry_verification: line.displayKind === "verified_pipeline" ? "verified" : "unverified",
            is_schematic_corridor: line.displayKind === "indicative_route",
            geometry_warning: geometryWarning,
          },
          geometry: {
            type: "LineString" as const,
            coordinates: line.geometryCoordinates.map(([lon, lat]) => toMapCoordinates(lon, lat)),
          },
        };
      }),
    [geometryWarning, highlightedRoutePoints, routeSegmentsForHighlight, t],
  );
  const normalizedSearchTerm = searchTerm.trim().toLowerCase();
  const priorityLabelNodes = useMemo(() => {
    const priorityNodes: NodeDTO[] = [];
    const priorityIds = new Set<string>();
    const visibleNodeIds = new Set(filteredNodes.map((node) => node.id));
    const addWithinBudget = (node: NodeDTO | undefined) => {
      if (
        !node ||
        !visibleNodeIds.has(node.id) ||
        priorityIds.has(node.id)
      ) return;
      priorityIds.add(node.id);
      priorityNodes.push(node);
    };

    if (highlightedRoutePoints) {
      addWithinBudget(highlightedRoutePoints.from);
      addWithinBudget(highlightedRoutePoints.to);
    }
    filteredNodes
      .filter((node) => isSearchLabelMatch(node, normalizedSearchTerm))
      .forEach(addWithinBudget);
    MAJOR_HUB_PRIORITY.forEach((marketCode) => addWithinBudget(
      filteredNodes.find((node) => fallbackNodeLabel(node).toUpperCase() === marketCode),
    ));
    filteredNodes.filter((node) => node.node_type === "hub").forEach(addWithinBudget);
    // Then terminals and interconnection points, then the rest: the label pass shows as many
    // as the zoom's budget allows, so names appear progressively as the view narrows.
    filteredNodes.filter((node) => node.node_type === "lng").forEach(addWithinBudget);
    filteredNodes.filter((node) => node.node_type === "interconnection").forEach(addWithinBudget);
    filteredNodes.forEach(addWithinBudget);
    return priorityNodes;
  }, [filteredNodes, highlightedRoutePoints, normalizedSearchTerm]);

  const fallbackLabelPriorityIds = useMemo(
    () => new Set(priorityLabelNodes.slice(0, MAX_MAP_LABELS).map((node) => node.id)),
    [priorityLabelNodes],
  );

  function shouldShowFallbackNodeLabel(node: NodeDTO, index: number): boolean {
    return index >= 0 && fallbackLabelPriorityIds.has(node.id);
  }

  // OpenStreetMap has its own light and dark style, so the map is rebuilt when the theme
  // changes; the outline is recoloured in place (below).
  const basemapStyleKey = `${mapTileProvider.id}:${mapTileProvider.styleUrl ? effectiveTheme : "any"}`;
  const lastViewRef = useRef<{ center: [number, number]; zoom: number } | null>(
    compact ? null : remembered.camera,
  );

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const view = lastViewRef.current;
    // Each MapLibre instance is numbered, so a measurement can tell a kept map from a rebuilt one.
    MAP_INSTANCES += 1;
    containerRef.current.dataset.mapInstance = String(MAP_INSTANCES);
    let map: MapLibreMap;
    try {
      map = new MapLibreMap({
        container: containerRef.current,
        // North-west Europe with the Norwegian shelf below the toolbar.
        center: view?.center ?? toMapCoordinates(6.5, 55.2),
        zoom: view?.zoom ?? 3.65,
        ...mapZoomRange(mapTileProvider.id),
        attributionControl: false,
        // Flat and north-up: no rotation, no tilt, by mouse, touch or keyboard.
        dragRotate: false,
        pitchWithRotate: false,
        touchPitch: false,
        maxPitch: 0,
        style: buildMapStyle(
          mapTileProvider.id,
          { background: mapColors.background },
          effectiveTheme === "dark" ? "dark" : "light",
        ),
      });
    } catch (error) {
      console.error("The network map could not start", error);
      setMapStartError(error instanceof Error ? error.message : String(error));
      return;
    }
    setMapStartError(null);

    // Zoom sits bottom-right: the top of the map belongs to the finder, the bar above to the
    // toolbar, so no two control groups can meet at any width.
    // Flat and north-up (owner, 2026-11-26): zoom only, no compass, no rotation, no pitch.
    map.addControl(new NavigationControl({ showCompass: false }), "top-right");
    map.dragRotate.disable();
    map.touchZoomRotate.disableRotation();
    map.keyboard.disableRotation();
    map.addControl(new AttributionControl({ compact: true }), "bottom-left");
    let loaded = false;
    map.on("load", () => {
      loaded = true;
      // OpenStreetMap, muted: the network, our positions and prices are the content.
      if (mapTileProvider.styleUrl) muteVectorBasemap(map);
      setMapReady(true);
    });
    let unreachable: ReturnType<typeof setTimeout> | undefined;
    if (mapTileProvider.styleUrl) {
      // Reachable means the provider's style arrived; a slow or failed tile afterwards is
      // not a reason to drop the basemap. Only a style that never loads falls back.
      let styleArrived = false;
      map.on("style.load", () => {
        styleArrived = true;
        clearTimeout(unreachable);
      });
      // The ODbL credit in the words the licence asks for, once (OpenFreeMap's own line says the
      // same less plainly): the attribution control reads each source's text, which a vector
      // source sets when its TileJSON (metadata) arrives.
      map.on("sourcedata", (event) => {
        if (event.sourceDataType !== "metadata") return;
        const source = map.getSource(event.sourceId) as { attribution?: string } | undefined;
        if (source && typeof source.attribution === "string" && /openstreetmap|openmaptiles/i.test(source.attribution)
          && source.attribution !== OSM_ATTRIBUTION) {
          source.attribution = OSM_ATTRIBUTION;
        }
      });
      const fallBack = () => {
        if (!loaded && !styleArrived) setUnreachableBasemap(mapTileProvider.id);
      };
      map.on("error", fallBack);
      unreachable = setTimeout(fallBack, 20_000);
    }
    // Clicking empty map clears the selection; clicking an object selects it (below).
    map.on("click", (event) => {
      const interactive = ["nodes-circle", "node-clusters", ...SITUATION_HOVER_LAYERS, "situation-cargo-sailed", "situation-cargo-ahead"]
        .filter((layerId) => map.getLayer(layerId));
      if (!map.queryRenderedFeatures(event.point, { layers: interactive }).length) setSelection(null);
    });
    // Semantic zoom: the tier decides what the map shows, not only how big it is.
    const syncTier = () => {
      setTier(zoomTier(map.getZoom()));
      setLabelZoom(Math.floor(map.getZoom()));
    };
    syncTier();
    map.on("zoomend", syncTier);
    mapRef.current = map;
    // For measurement in a real browser (scripts/uat/map_overlap_check.mjs): the map instance on
    // its own container element, read-only use. Nothing in the product reads it.
    (containerRef.current as HTMLElement & { egnMap?: MapLibreMap }).egnMap = map;
    // A map kept mounted while its page is hidden (MarketCockpit) has no size there; it takes
    // its size again the moment the page shows, with no rebuild.
    const resizeObserver = typeof ResizeObserver === "function"
      ? new ResizeObserver(() => {
          const element = containerRef.current;
          if (element && element.clientWidth > 0 && element.clientHeight > 0) map.resize();
        })
      : null;
    if (containerRef.current) resizeObserver?.observe(containerRef.current);
    return () => {
      clearTimeout(unreachable);
      const center = map.getCenter();
      lastViewRef.current = { center: [center.lng, center.lat], zoom: map.getZoom() };
      if (!compact) remembered.camera = lastViewRef.current;
      resizeObserver?.disconnect();
      setMapReady(false);
      basemapSymbolIdsRef.current = [];
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [basemapStyleKey]);

  // Intensity on the flat map (app/mapIntensity.ts): one metric from the Layers menu. Flow is the
  // flow lines (width, arrowhead) from regional zoom and one net figure per border below it;
  // utilisation, outage impact and storage are circles (area, colour). No figure, no mark.
  const intensityData = useMemo(() => {
    if (!intensity || compact) return null;
    return {
      points: intensity === "flow" ? [] : intensityPoints(intensity, { situation, nodes, edges, flowDay }),
      borders: intensity === "flow" ? borderFlows({ situation, edges, flowDay }) : [],
    };
  }, [compact, edges, flowDay, intensity, nodes, situation]);
  const intensityPalette = useMemo(() => effectiveTheme === "dark"
    ? { into: "#60a5fa", out: "#fbbf24", outage: "#f87171", ramp: ["#134e4a", "#0f766e", "#14b8a6", "#99f6e4"] }
    : { into: "#1d4ed8", out: "#b45309", outage: "#b91c1c", ramp: ["#ccfbf1", "#5eead4", "#0d9488", "#134e4a"] }, [effectiveTheme]);
  const intensityMax = useMemo(() => {
    if (!intensityData) return 0;
    return Math.max(0, ...intensityData.points.map((item) => item.value), ...intensityData.borders.map((item) => item.value));
  }, [intensityData]);
  const intensityDataRef = useRef(intensityData);
  intensityDataRef.current = intensityData;
  const intensityPickRef = useRef(onSelectIntensity);
  intensityPickRef.current = onSelectIntensity;
  const intensityMetricRef = useRef(intensity);
  intensityMetricRef.current = intensity;
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const byId = new globalThis.Map(nodes.map((node) => [node.id, node]));
    const metric = intensity;
    const points = intensityData?.points ?? [];
    const borders = intensityData?.borders ?? [];
    const pointData = {
      type: "FeatureCollection" as const,
      features: metric ? points.map((item) => ({
        type: "Feature" as const,
        properties: {
          id: item.id,
          radius: metric === "utilisation" ? 6 : intensityRadius(item.value, intensityMax),
          colour: intensityColour(metric, item, intensityPalette),
        },
        geometry: { type: "Point" as const, coordinates: toMapCoordinates(item.at[0], item.at[1]) },
      })) : [],
    };
    const borderLines: Array<{ id: string; coords: Array<[number, number]>; width: number }> = [];
    for (const border of borders) {
      const from = byId.get(border.fromId);
      const to = byId.get(border.toId);
      if (!from || !to) continue;
      const width = Math.round((1.2 + 4.8 * Math.sqrt(border.value / (intensityMax || 1))) * 10) / 10;
      borderLines.push({ id: border.id, coords: [[from.lon, from.lat], [to.lon, to.lat]], width });
    }
    const borderData = {
      type: "FeatureCollection" as const,
      features: borderLines.flatMap((line) => {
        const chevron = chevronAt(line.coords, 40);
        return [
          { type: "Feature" as const, properties: { id: line.id, width: line.width, part: "line" }, geometry: { type: "LineString" as const, coordinates: line.coords.map(([lon, lat]) => toMapCoordinates(lon, lat)) } },
          ...(chevron ? [{ type: "Feature" as const, properties: { id: line.id, width: line.width, part: "arrow" }, geometry: { type: "LineString" as const, coordinates: chevron.map(([lon, lat]) => toMapCoordinates(lon, lat)) } }] : []),
        ];
      }),
    };
    const flowColour = SITUATION_COLOURS[effectiveTheme].flow;
    const before = map.getLayer("map-labels") ? "map-labels" : undefined;
    if (upsertSource(map, "intensity-points", pointData)) {
      map.addLayer({
        id: "intensity-points",
        type: "circle",
        source: "intensity-points",
        paint: {
          "circle-radius": ["get", "radius"],
          "circle-color": ["get", "colour"],
          "circle-opacity": 0.55,
          "circle-stroke-color": ["get", "colour"],
          "circle-stroke-width": 1.2,
        },
      }, before);
      map.on("click", "intensity-points", (event) => {
        const id = String(event.features?.[0]?.properties?.id ?? "");
        const datum = intensityDataRef.current?.points.find((item) => item.id === id);
        const current = intensityMetricRef.current;
        if (datum && current) intensityPickRef.current?.({ metric: current, datum });
      });
      map.on("mouseenter", "intensity-points", () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", "intensity-points", () => {
        map.getCanvas().style.cursor = "";
      });
    }
    if (upsertSource(map, "intensity-borders", borderData)) {
      map.addLayer({
        id: "intensity-borders",
        type: "line",
        source: "intensity-borders",
        maxzoom: BORDER_FLOWS_BELOW_ZOOM,
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": flowColour, "line-width": ["case", ["==", ["get", "part"], "arrow"], 2, ["get", "width"]], "line-opacity": 0.85 },
      }, before);
    }
    map.setPaintProperty("intensity-borders", "line-color", flowColour);
    map.setLayoutProperty("intensity-points", "visibility", metric && metric !== "flow" ? "visible" : "none");
    map.setLayoutProperty("intensity-borders", "visibility", metric === "flow" ? "visible" : "none");
    // Flow, point by point, from regional zoom; below it the borders carry the picture.
    if (map.getLayer("scene-flow-lines")) {
      const from = metric === "flow" ? BORDER_FLOWS_BELOW_ZOOM : 0;
      map.setLayerZoomRange("scene-flow-lines", from, 24);
      map.setLayerZoomRange("scene-flow-chevrons", from, 24);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [effectiveTheme, intensity, intensityData, intensityMax, intensityPalette, mapReady, nodes]);

  // The map's overlays (finder, zoom, control stack, attribution, notices) are HTML over the
  // canvas, which MapLibre's label placement cannot see. Each is mirrored as invisible collision
  // squares in the map's own placement, above every label layer, so a name never sits under an
  // overlay: it moves to a free side or drops out, like any colliding label (owner review
  // 2026-11-26: "nothing overlaps").
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return undefined;
    if (!map.hasImage("overlay-blocker")) {
      map.addImage("overlay-blocker", { width: 16, height: 16, data: new Uint8Array(16 * 16 * 4) }, { pixelRatio: 1 });
    }
    const container = map.getContainer();
    let frame = 0;
    const update = () => {
      frame = 0;
      const box = container.getBoundingClientRect();
      const root = container.closest(".gas-map") ?? container.parentElement;
      const overlays = [...(root?.querySelectorAll(OVERLAY_SELECTOR) ?? [])];
      const features: Array<{ type: "Feature"; properties: { size: number }; geometry: { type: "Point"; coordinates: [number, number] } }> = [];
      for (const element of overlays) {
        const rect = element.getBoundingClientRect();
        if (rect.width <= 0 || rect.height <= 0) continue;
        const left = Math.max(rect.left, box.left) - box.left;
        const right = Math.min(rect.right, box.right) - box.left;
        const top = Math.max(rect.top, box.top) - box.top;
        const bottom = Math.min(rect.bottom, box.bottom) - box.top;
        if (right <= left || bottom <= top) continue;
        // Squares of the overlay's height (with a small margin) along its width.
        const side = bottom - top + 6;
        for (let x = left + side / 2 - 3; x < right + side / 2 - 3; x += side - 2) {
          const at = map.unproject([Math.min(x, right - 1), (top + bottom) / 2]);
          features.push({ type: "Feature", properties: { size: side / 16 }, geometry: { type: "Point", coordinates: [at.lng, at.lat] } });
        }
      }
      const data = { type: "FeatureCollection" as const, features };
      const source = map.getSource("overlay-blockers") as GeoJSONSource | undefined;
      if (source) source.setData(data);
      else {
        map.addSource("overlay-blockers", { type: "geojson", data });
        map.addLayer({
          id: "overlay-blockers",
          type: "symbol",
          source: "overlay-blockers",
          layout: {
            "icon-image": "overlay-blocker",
            "icon-size": ["get", "size"],
            "icon-allow-overlap": true,
            "icon-ignore-placement": false,
            "icon-pitch-alignment": "viewport",
            "icon-rotation-alignment": "viewport",
          },
        });
      }
      // Placed first: the topmost symbol layer.
      if (map.getLayer("overlay-blockers")) map.moveLayer("overlay-blockers");
    };
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(update);
    };
    update();
    map.on("move", schedule);
    map.on("resize", schedule);
    // An overlay that opens, closes or changes size (the key, a notice) moves the blockers too.
    const observer = typeof MutationObserver === "function" ? new MutationObserver(schedule) : null;
    const root = container.closest(".gas-map") ?? container.parentElement;
    if (root) observer?.observe(root, { childList: true, subtree: false, attributes: false });
    const resize = typeof ResizeObserver === "function" ? new ResizeObserver(schedule) : null;
    for (const element of root?.querySelectorAll(OVERLAY_SELECTOR) ?? []) resize?.observe(element);
    return () => {
      cancelAnimationFrame(frame);
      map.off("move", schedule);
      map.off("resize", schedule);
      observer?.disconnect();
      resize?.disconnect();
    };
  }, [mapReady]);

  // OpenStreetMap names places in the app language where OSM holds the name (Chinese or
  // English), else in Latin script: a Chinese desk reads 荷兰, not Nederland. Chinese prefers
  // name:zh-Hans and never shows a joined "simplified/traditional" string (basemapLabels.ts).
  useEffect(() => {
    const apply = (language: string) => {
      const map = mapRef.current;
      if (!map || !mapReady || !mapTileProvider.styleUrl) return;
      if (!basemapSymbolIdsRef.current.length) {
        basemapSymbolIdsRef.current = (map.getStyle().layers ?? [])
          .filter((layer) => layer.type === "symbol" && JSON.stringify(layer.layout?.["text-field"] ?? "").includes("name"))
          .map((layer) => layer.id);
      }
      for (const id of basemapSymbolIdsRef.current) {
        if (!map.getLayer(id)) continue;
        map.setLayoutProperty(id, "text-field", basemapNameExpression(language) as never);
      }
    };
    apply(i18n.language);
    i18n.on("languageChanged", apply);
    return () => {
      i18n.off("languageChanged", apply);
    };
  }, [mapReady]);

  useEffect(() => {
    const map = mapRef.current;
    // "load" (mapReady) means the style can be edited. isStyleLoaded() is also false while a
    // vector basemap's tiles are still arriving, which skipped this update for good.
    if (!map || !mapReady) return;

    // A vector basemap's own "background" layer is its land colour; leave it to the style.
    if (!mapTileProvider.styleUrl && map.getLayer("background")) {
      map.setPaintProperty("background", "background-color", mapColors.background);
    }
    if (map.getLayer("outline-land")) {
      const palette = outlinePalette(effectiveTheme === "dark" ? "dark" : "light");
      map.setPaintProperty("outline-land", "fill-color", palette.land);
      map.setPaintProperty("outline-coast", "line-color", palette.coast);
    }

    if (map.getLayer("verified-pipeline-lines")) {
      map.setPaintProperty("verified-pipeline-lines", "line-color", routeLineColor(mapColors));
    }
    if (map.getLayer("network-link-lines")) {
      map.setPaintProperty("network-link-lines", "line-color", linkLineColor(mapColors));
    }
    if (map.getLayer("adjacency-points")) {
      map.setPaintProperty("adjacency-points", "circle-color", mapColors.link);
      map.setPaintProperty("adjacency-points", "circle-stroke-color", mapColors.stroke);
    }
    if (map.getLayer("indicative-route-lines")) {
      map.setPaintProperty("indicative-route-lines", "line-color", mapColors.route);
    }
    if (map.getLayer("highlighted-route-verified")) {
      map.setPaintProperty("highlighted-route-verified", "line-color", mapColors.edge);
    }
    if (map.getLayer("highlighted-route-indicative")) {
      map.setPaintProperty("highlighted-route-indicative", "line-color", mapColors.route);
    }
    if (map.getLayer("nodes-circle")) {
      map.setPaintProperty("nodes-circle", "circle-color", [
        "case",
        ["get", "zone_only"],
        mapColors.zone,
        ["match", ["get", "node_type"], "hub", mapColors.hub, "lng", mapColors.lng, "interconnection", mapColors.interconnection, "entry_point", mapColors.interconnection, mapColors.node],
      ]);
      map.setPaintProperty("nodes-circle", "circle-stroke-color", mapColors.stroke);
      map.setPaintProperty("nodes-circle", "circle-opacity", [
        "case",
        ["==", ["get", "coordinate_quality"], "display_approximation"],
        0.74,
        0.96,
      ]);
    }
    if (map.getLayer("node-clusters")) {
      map.setPaintProperty("node-clusters", "circle-color", mapColors.node);
      map.setPaintProperty("node-clusters", "circle-stroke-color", mapColors.stroke);
    }
    if (map.getLayer("node-cluster-count")) {
      map.setPaintProperty("node-cluster-count", "text-color", mapColors.stroke);
    }
  }, [effectiveTheme, mapColors, mapReady]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;

    const nodeFeatures = filteredNodes.map((node) => ({
      type: "Feature" as const,
      properties: {
        id: node.id,
        name: node.name,
        node_type: node.node_type,
        // A balancing zone with no trading point: a small grey dot, never a hub's mark.
        zone_only: isZoneOnly(node),
        country: node.country,
        capacity_boe_d: node.capacity_boe_d,
        source_system: node.source_system ?? "",
        source_reference: node.source_reference ?? "",
        data_quality: node.data_quality ?? "",
        coordinate_quality: propertyText(node.metadata_json?.coordinate_quality, node.data_quality ?? "unknown"),
        coordinate_source: propertyText(node.metadata_json?.coordinate_source, "unknown"),
      },
      geometry: {
        type: "Point" as const,
        coordinates: toMapCoordinates(node.lon, node.lat),
      },
    }));
    const verifiedEdgeFeatures = verifiedPipelineLines.map((line) => {
      const metadata = line.edge?.metadata_json ?? {};
      const capacity = Number(metadata.capacity_mwh_d ?? metadata.firm_capacity_mwh_d ?? 0);
      const flow = Number(metadata.live_physical_flow_mwh_d ?? 0);
      const utilization = Number(metadata.utilization_pct ?? (capacity > 0 ? flow / capacity : 0));
      return {
        type: "Feature" as const,
        properties: {
          id: line.id,
          from_node_id: line.from.id,
          to_node_id: line.to.id,
          display_kind: line.displayKind,
          geometry_basis: line.geometryBasis,
          geometry_verification: line.displayKind === "verified_pipeline" ? "verified" : "schematic",
          name: String(metadata.name ?? ""),
          is_schematic_corridor: false,
          operator: String(metadata.operator ?? ""),
          capacity_mwh_d: capacity,
          live_flow_mwh_d: flow,
          utilization_pct: utilization,
          matters: matteringLineIds.has(line.id),
          edge_type: line.edge?.edge_type ?? "",
          // The pair of market areas (or market area and pipeline) a market-area link joins:
          // the hover card lists every point on that border.
          joins: JSON.stringify(Array.isArray(metadata.joins) ? [...metadata.joins].sort() : []),
          point_key: String(metadata.point_key ?? ""),
        },
        geometry: {
          type: "LineString" as const,
          coordinates: line.geometryCoordinates.map(([lon, lat]) => toMapCoordinates(lon, lat)),
        },
      };
    });
    // The interconnection point of each drawn connection, as a small node on the line.
    const adjacencyPointFeatures = [...new Map(
      verifiedPipelineLines
        .filter((line) => line.displayKind === "network_link")
        .flatMap((line) => [line.from, line.to])
        .filter((node) => node.node_type !== "hub")
        .map((node) => [node.id, node]),
    ).values()].map((node) => ({
      type: "Feature" as const,
      properties: { id: node.id, name: node.name },
      geometry: { type: "Point" as const, coordinates: toMapCoordinates(node.lon, node.lat) },
    }));
    const indicativeEdgeFeatures = indicativeRouteLines.map((line) => {
      const metadata = line.edge?.metadata_json ?? {};
      return {
        type: "Feature" as const,
        properties: {
          id: line.id,
          from_node_id: line.from.id,
          to_node_id: line.to.id,
          route_id: line.routeId,
          route_leg_sequence: line.routeLegSequence,
          route_geometry_state: line.routeGeometryState,
          matters: matteringLineIds.has(line.id),
          display_kind: "indicative_route",
          geometry_basis: line.geometryBasis,
          geometry_verification: "unverified",
          is_schematic_corridor: true,
          geometry_classification: "indicative_schematic_corridor",
          geometry_warning: line.edge
            ? metadataString(metadata, "geometry_warning", t("map.indicative_route_warning"))
            : t("map.indicative_route_warning"),
        },
        geometry: {
          type: "LineString" as const,
          coordinates: line.geometryCoordinates.map(([lon, lat]) => toMapCoordinates(lon, lat)),
        },
      };
    });

    if (!map.getSource("verified-pipeline-lines")) {
      map.addSource("verified-pipeline-lines", {
        type: "geojson",
        data: { type: "FeatureCollection", features: verifiedEdgeFeatures },
      });
      map.addLayer({
        id: "verified-pipeline-lines",
        type: "line",
        source: "verified-pipeline-lines",
        filter: ["==", ["get", "display_kind"], "verified_pipeline"],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": routeLineColor(mapColors),
          // Thin context lines: utilisation still widens a busy pipe, but nothing shouts. A
          // route the book uses is drawn wider in the route colour.
          "line-width": [
            "case",
            ["==", ["get", "matters"], true],
            3,
            ["interpolate", ["linear"], ["get", "utilization_pct"], 0, 1.1, 0.65, 1.8, 0.9, 2.6],
          ],
          "line-opacity": 0.94,
        },
      });
      // A physical connection between two located points with no surveyed route: one quiet
      // straight dashed segment, so it never reads as a pipeline's path.
      map.addLayer({
        id: "network-link-lines",
        type: "line",
        source: "verified-pipeline-lines",
        filter: ["==", ["get", "display_kind"], "network_link"],
        layout: { "line-cap": "butt", "line-join": "round" },
        paint: {
          "line-color": linkLineColor(mapColors),
          "line-width": ["case", ["==", ["get", "matters"], true], 2.6, 1.6],
          "line-opacity": 0.85,
          "line-dasharray": [2.2, 1.6],
        },
      });
      // A wide transparent band over the dashes makes a connection easy to hover.
      map.addLayer({
        id: "network-link-hit",
        type: "line",
        source: "verified-pipeline-lines",
        filter: ["==", ["get", "display_kind"], "network_link"],
        paint: { "line-color": "rgba(0,0,0,0)", "line-width": 12 },
      });
      const hover = new Popup({ closeButton: false, closeOnClick: false, offset: 8, maxWidth: "320px" });
      map.on("mousemove", "network-link-hit", (event) => {
        const props = event.features?.[0]?.properties;
        if (!props) return;
        map.getCanvas().style.cursor = "pointer";
        hover.setLngLat(event.lngLat).setHTML(borderCardRef.current(props)).addTo(map);
      });
      map.on("mouseleave", "network-link-hit", () => {
        map.getCanvas().style.cursor = "";
        hover.remove();
      });
    } else {
      (map.getSource("verified-pipeline-lines") as GeoJSONSource).setData({
        type: "FeatureCollection",
        features: verifiedEdgeFeatures,
      });
    }
    if (upsertSource(map, "adjacency-points", { type: "FeatureCollection", features: adjacencyPointFeatures })) {
      map.addLayer({
        id: "adjacency-points",
        type: "circle",
        source: "adjacency-points",
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 2.5, 7, 4],
          "circle-color": mapColors.link,
          "circle-stroke-color": mapColors.stroke,
          "circle-stroke-width": 1,
          "circle-opacity": 0.9,
        },
      });
    }

    if (!map.getSource("indicative-route-lines")) {
      map.addSource("indicative-route-lines", {
        type: "geojson",
        data: { type: "FeatureCollection", features: indicativeEdgeFeatures },
      });
      map.addLayer({
        id: "indicative-route-lines",
        type: "line",
        source: "indicative-route-lines",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": mapColors.route,
          "line-width": 3.2,
          "line-opacity": 0.62,
          "line-dasharray": [2.2, 2.4],
        },
      });
    } else {
      (map.getSource("indicative-route-lines") as GeoJSONSource).setData({
        type: "FeatureCollection",
        features: indicativeEdgeFeatures,
      });
    }

    if (!map.getSource("highlighted-route-segments")) {
      map.addSource("highlighted-route-segments", {
        type: "geojson",
        data: { type: "FeatureCollection", features: highlightedRouteSegmentFeatures },
      });
      map.addLayer({
        id: "highlighted-route-verified",
        type: "line",
        source: "highlighted-route-segments",
        filter: ["==", ["get", "display_kind"], "verified_pipeline"],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": mapColors.edge,
          "line-width": 6,
          "line-opacity": 0.98,
        },
      });
      map.addLayer({
        id: "highlighted-route-indicative",
        type: "line",
        source: "highlighted-route-segments",
        filter: ["==", ["get", "display_kind"], "indicative_route"],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": mapColors.route,
          "line-width": 5,
          "line-opacity": 0.78,
          "line-dasharray": [2.4, 2.6],
        },
      });
    } else {
      (map.getSource("highlighted-route-segments") as GeoJSONSource).setData({
        type: "FeatureCollection",
        features: highlightedRouteSegmentFeatures,
      });
    }

    if (!map.getSource("nodes")) {
      map.addSource("nodes", {
        type: "geojson",
        data: { type: "FeatureCollection", features: nodeFeatures },
        cluster: true,
        clusterMaxZoom: 6,
        clusterRadius: 34,
      });
      map.addLayer({
        id: "node-clusters",
        type: "circle",
        source: "nodes",
        filter: ["has", "point_count"],
        paint: {
          "circle-color": mapColors.node,
          "circle-radius": ["step", ["get", "point_count"], 9, 25, 12, 100, 15],
          "circle-stroke-color": mapColors.stroke,
          "circle-stroke-width": 2,
          "circle-opacity": 0.88,
        },
      });
      map.addLayer({
        id: "node-cluster-count",
        type: "symbol",
        source: "nodes",
        filter: ["has", "point_count"],
        layout: {
          "text-field": ["get", "point_count_abbreviated"],
          "text-size": 11,
          "text-font": labelFont(mapTileProvider.id),
          // A count always shows inside its circle, and never pushes a basemap name away.
          "text-allow-overlap": true,
          "text-ignore-placement": true,
        },
        paint: { "text-color": mapColors.stroke },
      });
      map.addLayer({
        id: "nodes-circle",
        type: "circle",
        source: "nodes",
        filter: ["!", ["has", "point_count"]],
        paint: {
          "circle-radius": ["case", ["get", "zone_only"], 3, ["==", ["get", "node_type"], "hub"], 6, 3.5],
          "circle-color": [
            "case",
            ["get", "zone_only"],
            mapColors.zone,
            ["match",
            ["get", "node_type"],
            "hub",
            mapColors.hub,
            "lng",
            mapColors.lng,
            "interconnection",
            mapColors.interconnection,
            "entry_point",
            mapColors.interconnection,
            mapColors.node],
          ],
          "circle-stroke-color": mapColors.stroke,
          "circle-stroke-width": [
            "case",
            ["==", ["get", "coordinate_quality"], "display_approximation"],
            2.2,
            1.5,
          ],
          "circle-opacity": [
            "case",
            ["==", ["get", "coordinate_quality"], "display_approximation"],
            0.74,
            0.96,
          ],
        },
      });
      map.on("click", "node-clusters", (event) => {
        const feature = event.features?.[0];
        const clusterId = Number(feature?.properties?.cluster_id);
        if (!feature || !Number.isFinite(clusterId)) return;
        const coordinates = (feature.geometry as { coordinates?: [number, number] }).coordinates;
        if (!coordinates) return;
        const source = map.getSource("nodes") as GeoJSONSource;
        void source.getClusterExpansionZoom(clusterId).then((zoom) => {
          focusOn(map, coordinates, zoom);
        });
      });
      map.on("mouseenter", "node-clusters", () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", "node-clusters", () => {
        map.getCanvas().style.cursor = "";
      });
      map.on("click", "nodes-circle", (event) => {
        const feature = event.features?.[0];
        if (!feature) return;
        const props = feature.properties ?? {};
        const nodeId = propertyText(props.id, "");
        const pointAt = (feature.geometry as { coordinates?: [number, number] }).coordinates;
        if (pointAt) focusOn(map, pointAt, Math.max(map.getZoom(), 7));
        // The docked card is the map's quick context; it hands the point to the canonical
        // Inspector for full detail (see MapDetailPanel's "Inspect").
        setSelection(selectForRef.current(nodeId, propertyText(props.node_type, "")));
      });
      map.on("mouseenter", "nodes-circle", () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", "nodes-circle", () => {
        map.getCanvas().style.cursor = "";
      });
    } else {
      (map.getSource("nodes") as GeoJSONSource).setData({
        type: "FeatureCollection",
        features: nodeFeatures,
      });
    }
  }, [filteredNodes, highlightedRouteSegmentFeatures, indicativeRouteLines, mapColors, mapReady, onInspectNode, t, verifiedPipelineLines]);

  // The open reference trunk lines (SciGRID_gas), faint, under the connections: the general
  // direction pipes run. Network view with Routes on; never selectable, never priced.
  const [contextPipes, setContextPipes] = useState<ContextPipelineCollection | null>(null);
  useEffect(() => {
    let live = true;
    void loadContextPipelines().then((data) => {
      if (live) setContextPipes(data);
    });
    return () => {
      live = false;
    };
  }, []);
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !contextPipes) return;
    const data = projectContextPipelines(contextPipes, toMapCoordinates);
    const source = map.getSource("context-pipelines") as GeoJSONSource | undefined;
    if (source) source.setData(data);
    else {
      map.addSource("context-pipelines", { type: "geojson", data, attribution: CONTEXT_PIPELINES_ATTRIBUTION });
      map.addLayer(
        {
          id: "context-pipelines",
          type: "line",
          source: "context-pipelines",
          layout: { "line-cap": "round", "line-join": "round" },
          paint: {
            "line-color": linkLineColor(mapColors),
            "line-width": ["interpolate", ["linear"], ["zoom"], 3, 0.5, 6, 0.9, 9, 1.4],
            // Context, not content: quieter than the priced routes and our positions.
            "line-opacity": effectiveTheme === "dark" ? 0.24 : 0.16,
          },
        },
        map.getLayer("verified-pipeline-lines") ? "verified-pipeline-lines" : undefined,
      );
    }
    map.setLayoutProperty(
      "context-pipelines",
      "visibility",
      showContextRoutes && view === "network" ? "visible" : "none",
    );
    map.setPaintProperty("context-pipelines", "line-color", linkLineColor(mapColors));
    map.setPaintProperty("context-pipelines", "line-opacity", effectiveTheme === "dark" ? 0.24 : 0.16);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contextPipes, effectiveTheme, mapColors, mapReady, showContextRoutes, view]);

  // Our book view: the paths to the neighbouring market areas our hubs reach, at medium
  // emphasis (dashed, thinner than our own paths), only in that view.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const accent = SITUATION_COLOURS[effectiveTheme].own;
    const data = {
      type: "FeatureCollection" as const,
      features: bookReachable.map((line) => ({
        type: "Feature" as const,
        properties: { id: line.id, to_hub: line.toHub },
        geometry: {
          type: "LineString" as const,
          coordinates: line.coordinates.map(([lon, lat]) => toMapCoordinates(lon, lat)),
        },
      })),
    };
    if (upsertSource(map, "book-reachable-lines", data)) {
      map.addLayer({
        id: "book-reachable-lines",
        type: "line",
        source: "book-reachable-lines",
        layout: { "line-cap": "butt", "line-join": "round" },
        paint: { "line-color": accent, "line-width": 1.8, "line-opacity": 0.55, "line-dasharray": [1.4, 1.4] },
      }, map.getLayer("node-clusters") ? "node-clusters" : undefined);
    }
    map.setPaintProperty("book-reachable-lines", "line-color", accent);
    map.setLayoutProperty("book-reachable-lines", "visibility", view === "book" ? "visible" : "none");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bookReachable, effectiveTheme, mapReady, view]);

  // Our book view: the opportunities' paths. An actionable one pops out (wide, the opportunity
  // colour) with its headline on the far hub; a watch-state one is a thin outline. Selecting
  // either opens the opportunity.
  const selectOpportunityRef = useRef(onSelectOpportunity);
  selectOpportunityRef.current = onSelectOpportunity;
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const colour = SITUATION_COLOURS[effectiveTheme].opportunity;
    const data = {
      type: "FeatureCollection" as const,
      features: bookOpportunities.map((line) => ({
        type: "Feature" as const,
        properties: { id: line.id, opportunity_id: line.opportunityId, emphasis: line.emphasis },
        geometry: {
          type: "LineString" as const,
          coordinates: line.coordinates.map(([lon, lat]) => toMapCoordinates(lon, lat)),
        },
      })),
    };
    if (upsertSource(map, "book-opportunity-lines", data)) {
      map.addLayer({
        id: "book-opportunity-lines",
        type: "line",
        source: "book-opportunity-lines",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": colour,
          "line-width": ["case", ["==", ["get", "emphasis"], "pop"], 4, 1.4],
          "line-opacity": ["case", ["==", ["get", "emphasis"], "pop"], 0.95, 0.7],
        },
      }, map.getLayer("node-clusters") ? "node-clusters" : undefined);
      map.addLayer({
        id: "book-opportunity-hit",
        type: "line",
        source: "book-opportunity-lines",
        paint: { "line-color": "rgba(0,0,0,0)", "line-width": 14 },
      });
      map.on("click", "book-opportunity-hit", (event) => {
        const id = event.features?.[0]?.properties?.opportunity_id;
        if (id) selectOpportunityRef.current?.(String(id));
      });
      map.on("mouseenter", "book-opportunity-hit", () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", "book-opportunity-hit", () => {
        map.getCanvas().style.cursor = "";
      });
    }
    map.setPaintProperty("book-opportunity-lines", "line-color", colour);
    const visible = view === "book" ? "visible" : "none";
    map.setLayoutProperty("book-opportunity-lines", "visibility", visible);
    map.setLayoutProperty("book-opportunity-hit", "visibility", visible);
    // Each opportunity's headline is a label in the map's one label layer (selecting it opens it).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bookOpportunities, effectiveTheme, mapReady, view]);

  // The book's flows: one line per origin and destination, width by volume, the volume at the
  // destination and a single arrowhead for direction. Drawn under the points.
  const bookFlowMarkersRef = useRef<Marker[]>([]);
  const selectContractLineRef = useRef(onSelectContractLine);
  selectContractLineRef.current = onSelectContractLine;
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const accent = SITUATION_COLOURS[effectiveTheme].own;
    // In the book view a contract's path reads as its delivery window: the part delivered
    // solid, the part to go dashed (split along the line at the share of days delivered).
    const parts = bookFlows.flatMap((flow) => {
      const fraction = view === "book" ? periodFraction(flow.period) : null;
      if (fraction === null || fraction >= 1) return [{ flow, part: "done", coordinates: flow.coordinates }];
      const { done, toGo } = splitAtFraction(flow.coordinates, fraction);
      return [
        ...(done.length > 1 ? [{ flow, part: "done", coordinates: done }] : []),
        ...(toGo.length > 1 ? [{ flow, part: "to_go", coordinates: toGo }] : []),
      ];
    });
    const data = {
      type: "FeatureCollection" as const,
      features: parts.map(({ flow, part, coordinates }) => ({
        type: "Feature" as const,
        properties: {
          id: flow.id,
          from_node_id: flow.fromId,
          to_node_id: flow.toId,
          width: flow.width,
          mwh_d: flow.mwhPerDay,
          geometry_basis: flow.geometryBasis,
          part,
        },
        geometry: {
          type: "LineString" as const,
          coordinates: coordinates.map(([lon, lat]) => toMapCoordinates(lon, lat)),
        },
      })),
    };
    if (upsertSource(map, "book-flow-lines", data)) {
      map.addLayer({
        id: "book-flow-lines",
        type: "line",
        source: "book-flow-lines",
        filter: ["!=", ["get", "part"], "to_go"],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": accent,
          "line-width": ["get", "width"],
          "line-opacity": VIEW_EMPHASIS[view]["book-flow-lines"] as number,
        },
      }, map.getLayer("node-clusters") ? "node-clusters" : undefined);
      map.addLayer({
        id: "book-flow-ahead",
        type: "line",
        source: "book-flow-lines",
        filter: ["==", ["get", "part"], "to_go"],
        layout: { "line-cap": "butt", "line-join": "round" },
        paint: {
          "line-color": accent,
          "line-width": ["max", 1.5, ["*", 0.6, ["get", "width"]]],
          "line-opacity": 0.8,
          "line-dasharray": [1.6, 1.2],
        },
      }, map.getLayer("node-clusters") ? "node-clusters" : undefined);
      for (const layerId of ["book-flow-lines", "book-flow-ahead"]) {
        map.on("click", layerId, (event) => {
          const id = event.features?.[0]?.properties?.id;
          if (id) selectContractLineRef.current?.(String(id));
        });
      }
    }
    map.setPaintProperty("book-flow-lines", "line-color", accent);
    map.setPaintProperty("book-flow-ahead", "line-color", accent);
    map.setLayoutProperty("book-flow-lines", "visibility", activeLayers.includes("positions") ? "visible" : "none");
    map.setLayoutProperty("book-flow-ahead", "visibility", activeLayers.includes("positions") ? "visible" : "none");
    const clear = () => {
      bookFlowMarkersRef.current.forEach((marker) => marker.remove());
      bookFlowMarkersRef.current = [];
    };
    const place = () => {
      clear();
      if (!activeLayers.includes("positions")) return;
      for (const flow of bookFlows) {
        if (flow.coordinates.length < 2) continue;
        const end = toMapCoordinates(...flow.coordinates[flow.coordinates.length - 1]);
        const before = toMapCoordinates(...flow.coordinates[flow.coordinates.length - 2]);
        const tip = map.project(end);
        const tail = map.project(before);
        const length = Math.hypot(tip.x - tail.x, tip.y - tail.y) || 1;
        const ux = (tip.x - tail.x) / length;
        const uy = (tip.y - tail.y) / length;
        // The arrowhead sits just short of the destination's marker, pointing at it.
        const arrowAt = map.unproject([tip.x - ux * 16, tip.y - uy * 16]);
        const arrow = document.createElement("div");
        arrow.className = "map-flow-arrow";
        arrow.setAttribute("aria-hidden", "true");
        arrow.style.transform = `rotate(${Math.atan2(uy, ux)}rad)`;
        // The volume is the flow's label in the map's one label layer (decluttered).
        bookFlowMarkersRef.current.push(
          new Marker({ element: arrow, anchor: "center", rotationAlignment: "viewport" }).setLngLat(arrowAt).addTo(map),
        );
      }
    };
    place();
    map.on("moveend", place);
    return () => {
      map.off("moveend", place);
      clear();
    };
  }, [activeLayers, bookFlows, effectiveTheme, mapReady, view]);


  // Disruptions touching the book (book view only): a quiet mark each; the ones active and
  // touching our contracts pulse slowly (the map's only loop; a still ring under reduced
  // motion, in CSS). Selecting one opens its callout.
  const selectDisruptionRef = useRef(onSelectDisruption);
  selectDisruptionRef.current = onSelectDisruption;
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || view !== "book") return;
    const markers = bookDisruptions.map((mark) => {
      const element = document.createElement("button");
      element.type = "button";
      element.className = `map-disruption${mark.pulse ? " is-pulse" : ""}${mark.active ? " is-active" : " is-scheduled"}`;
      element.setAttribute("aria-label", t("map.book.disruption_mark"));
      element.dataset.eventId = mark.id;
      element.innerHTML = '<span class="map-disruption-ring" aria-hidden="true"></span><span class="map-disruption-dot" aria-hidden="true"></span>';
      element.addEventListener("click", (event) => {
        event.stopPropagation();
        selectDisruptionRef.current?.(mark.id);
      });
      return new Marker({ element, anchor: "center" }).setLngLat(toMapCoordinates(mark.at[0], mark.at[1])).addTo(map);
    });
    return () => markers.forEach((marker) => marker.remove());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bookDisruptions, mapReady, view]);

  // Re-route and locational alternatives (book view): the current way dimmed, the proposed
  // one highlighted, with its benefit on the line. The proposed line draws in once (at most
  // 600 ms, the map's motion tokens) when it first shows or is selected; at once under
  // reduced motion.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const colour = SITUATION_COLOURS[effectiveTheme].opportunity;
    const muted = effectiveTheme === "dark" ? "#a1a1aa" : "#71717a";
    const shown = view === "book" ? bookProposals : [];
    const lineData = (share: number) => ({
      type: "FeatureCollection" as const,
      features: shown.flatMap((line) => {
        const proposed = share >= 1 ? line.proposed : splitAtFraction(line.proposed, share).done;
        return [
          ...(line.current.length > 1
            ? [{
                type: "Feature" as const,
                properties: { id: line.id, opportunity_id: line.opportunityId, part: "current" },
                geometry: { type: "LineString" as const, coordinates: line.current.map(([lon, lat]) => toMapCoordinates(lon, lat)) },
              }]
            : []),
          ...(proposed.length > 1
            ? [{
                type: "Feature" as const,
                properties: { id: line.id, opportunity_id: line.opportunityId, part: "proposed" },
                geometry: { type: "LineString" as const, coordinates: proposed.map(([lon, lat]) => toMapCoordinates(lon, lat)) },
              }]
            : []),
        ];
      }),
    });
    if (upsertSource(map, "book-proposals", lineData(1))) {
      map.addLayer({
        id: "book-proposal-current",
        type: "line",
        source: "book-proposals",
        filter: ["==", ["get", "part"], "current"],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": muted, "line-width": 3, "line-opacity": 0.45 },
      }, map.getLayer("node-clusters") ? "node-clusters" : undefined);
      map.addLayer({
        id: "book-proposal-lines",
        type: "line",
        source: "book-proposals",
        filter: ["==", ["get", "part"], "proposed"],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": colour, "line-width": 4.5, "line-opacity": 0.95 },
      }, map.getLayer("node-clusters") ? "node-clusters" : undefined);
      map.on("click", "book-proposal-lines", (event) => {
        const id = event.features?.[0]?.properties?.opportunity_id;
        if (id) selectOpportunityRef.current?.(String(id));
      });
    }
    map.setPaintProperty("book-proposal-current", "line-color", muted);
    map.setPaintProperty("book-proposal-lines", "line-color", colour);
    const source = map.getSource("book-proposals") as GeoJSONSource;
    const duration = drawInDuration();
    let frame = 0;
    if (duration > 0 && shown.length) {
      const started = performance.now();
      const step = (time: number) => {
        const share = Math.min(1, (time - started) / duration);
        source.setData(lineData(easeOut(share)));
        if (share < 1) frame = requestAnimationFrame(step);
      };
      source.setData(lineData(0));
      frame = requestAnimationFrame(step);
    } else {
      source.setData(lineData(1));
    }
    // The benefit on the line is a label in the map's one label layer.
    return () => {
      cancelAnimationFrame(frame);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bookProposals, drawInKey, effectiveTheme, mapReady, view]);

  // Callouts: what, until when, how much of ours, and a progress bar for a window or voyage.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !callouts.length) return;
    const markers = callouts.map((callout) => {
      const element = document.createElement("div");
      element.className = `map-callout is-${callout.tone}`;
      element.dataset.callout = callout.id;
      const title = document.createElement("strong");
      title.textContent = callout.title;
      element.appendChild(title);
      for (const line of callout.lines) {
        const row = document.createElement("span");
        row.textContent = line;
        element.appendChild(row);
      }
      if (typeof callout.progress === "number") {
        const bar = document.createElement("span");
        bar.className = "map-callout-progress";
        bar.setAttribute("role", "progressbar");
        bar.setAttribute("aria-valuemin", "0");
        bar.setAttribute("aria-valuemax", "100");
        bar.setAttribute("aria-valuenow", String(Math.round(callout.progress * 100)));
        const fill = document.createElement("span");
        fill.style.width = `${Math.round(callout.progress * 100)}%`;
        bar.appendChild(fill);
        element.appendChild(bar);
      }
      const marker = new Marker({ element, anchor: "bottom", offset: [0, -16] })
        .setLngLat(toMapCoordinates(callout.at[0], callout.at[1]))
        .addTo(map);
      // A callout reads above the point labels it sits among.
      marker.getElement().style.zIndex = "6";
      return marker;
    });
    return () => markers.forEach((marker) => marker.remove());
  }, [callouts, mapReady]);

  // Live situation layers. Added once, then fed with setData; visibility follows the
  // layer chips. Hover shows a compact card; nothing here opens a second detail pane.
  const situationRef = useRef<MapSituationDTO | null>(situation);
  // Vessel dots that moved between two reads ease to their new place (none under reduced motion).
  const cargoDrawnRef = useRef<FC<{ type: "Point"; coordinates: [number, number] }> | null>(null);
  const cargoTweenRef = useRef(0);
  useEffect(() => () => cancelAnimationFrame(cargoTweenRef.current), []);
  situationRef.current = situation;
  useEffect(() => {
    const map = mapRef.current;
    // After "load" sources and layers can be added even while other sources are still
    // updating, so this does not wait for isStyleLoaded() (which would skip the update).
    if (!map || !mapReady) return;
    const palette = SITUATION_COLOURS[effectiveTheme];
    const empty = { type: "FeatureCollection" as const, features: [] };
    const cargo = situation ? cargoFeatures(situation.cargoes, toMapCoordinates) : null;

    for (const theme of ["light", "dark"] as const) {
      for (const facilityType of Object.keys(FACILITY_ICON)) {
        const id = `infra-${facilityType}-${theme}`;
        if (map.hasImage(id)) continue;
        const image = drawFacilityIcon(facilityType, theme);
        if (image) map.addImage(id, image, { pixelRatio: 2 });
      }
    }
    // Vessel marks, one per kind, owner and theme: an arrow turned to the reported heading, or a
    // dot where no heading is known.
    for (const theme of ["light", "dark"] as const) {
      const colours = SITUATION_COLOURS[theme];
      for (const kind of ["heading", "still"] as const) {
        for (const owner of ["own", "market"] as const) {
          const id = vesselIconId(kind, owner, theme);
          if (map.hasImage(id)) continue;
          const image = drawVesselIcon(kind, owner === "own" ? colours.own : colours.market, colours.halo);
          if (image) map.addImage(id, image, { pixelRatio: 2 });
        }
      }
    }
    const vesselImage = ["concat", "vessel-", ["get", "icon"], "-", ["case", ["get", "own"], "own", "market"], `-${effectiveTheme}`];
    const iconImage = ["concat", "infra-", ["get", "facility_type"], `-${effectiveTheme}`];
    if (upsertSource(map, "situation-facilities", facilityFeatures(facilities, toMapCoordinates))) {
      map.addLayer({
        id: "situation-facilities",
        type: "symbol",
        source: "situation-facilities",
        minzoom: 4,
        layout: {
          "icon-image": iconImage as never,
          "icon-size": ["interpolate", ["linear"], ["zoom"], 4, 0.45, 8, 0.7, 12, 0.95],
          // Thin out at regional zoom, show every asset once the view is local.
          "icon-allow-overlap": ["step", ["zoom"], false, 8, true] as never,
          "symbol-sort-key": ["match", ["get", "facility_type"], "lng_terminal", 0, "liquefaction", 0, "storage", 1, "production_platform", 2, 3],
        },
      }, map.getLayer("nodes-circle") ? "node-clusters" : undefined);
    } else if (map.getLayer("situation-facilities")) {
      map.setLayoutProperty("situation-facilities", "icon-image", iconImage as never);
    }
    // ENTSOG positions are transformed from a schematic map: once zoomed in, say so on the map
    // with a soft ring rather than let a precise-looking dot sit on the wrong street.
    if (map.getSource("nodes") && !map.getLayer("nodes-approx-halo")) {
      map.addLayer({
        id: "nodes-approx-halo",
        type: "circle",
        source: "nodes",
        minzoom: 7,
        filter: ["all", ["!", ["has", "point_count"]], ["==", ["get", "coordinate_quality"], "display_approximation"]],
        paint: {
          "circle-radius": ["interpolate", ["exponential", 2], ["zoom"], 7, 10, 12, 120],
          "circle-color": palette.facility,
          "circle-opacity": 0.06,
          "circle-stroke-color": palette.facility,
          "circle-stroke-width": 1,
          "circle-stroke-opacity": 0.35,
        },
      }, "nodes-circle");
    }
    if (map.getSource("verified-pipeline-lines") && !map.getLayer("situation-pipeline-flow")) {
      map.addLayer({
        id: "situation-pipeline-flow",
        type: "line",
        source: "verified-pipeline-lines",
        filter: [">", ["get", "live_flow_mwh_d"], 0],
        layout: { "line-cap": "butt", "line-join": "round" },
        paint: {
          "line-color": palette.flow,
          "line-width": ["interpolate", ["linear"], ["get", "utilization_pct"], 0, 1.5, 1, 3.5],
          "line-opacity": 0.9,
          "line-dasharray": [0, 4, 3],
        },
      });
    }
    if (upsertSource(map, "situation-flows", situation ? flowFeatures(situation.flows, toMapCoordinates) : empty)) {
      map.addLayer({
        id: "situation-flows",
        type: "circle",
        source: "situation-flows",
        paint: {
          // A metering point's flow: a small quiet dot, larger with the flow, never a ring
          // that covers its neighbours (2 to 7 px).
          "circle-radius": ["interpolate", ["linear"], ["sqrt", ["get", "gwh_d"]], 0, 2, 30, 7],
          "circle-color": palette.flow,
          "circle-opacity": 0.55,
          "circle-stroke-color": palette.flow,
          "circle-stroke-width": 0,
        },
      });
    }
    if (upsertSource(map, "situation-cargo-sailed", cargo?.sailed ?? empty)) {
      map.addLayer({
        id: "situation-cargo-sailed",
        type: "line",
        source: "situation-cargo-sailed",
        layout: { "line-cap": "round", "line-join": "round" },
        // The track already sailed: thin and solid.
        paint: {
          "line-color": ["case", ["get", "own"], palette.own, palette.market],
          "line-width": ["case", ["get", "own"], 1.6, 1],
          "line-opacity": 0.7,
        },
      });
    }
    if (upsertSource(map, "situation-cargo-ahead", cargo?.ahead ?? empty)) {
      map.addLayer({
        id: "situation-cargo-ahead",
        type: "line",
        source: "situation-cargo-ahead",
        layout: { "line-cap": "butt" },
        // The way still to go: a straight dashed line to the terminal, the direction and not a
        // route (no sea-lane routing is held, and a great circle can cross land).
        paint: {
          "line-color": ["case", ["get", "own"], palette.own, palette.market],
          "line-width": ["case", ["get", "own"], 1.4, 1],
          "line-opacity": 0.65,
          "line-dasharray": [3, 3],
        },
      });
    }
    if (upsertSource(map, "situation-regas", situation ? slotTerminalFeatures(situation.regas_slots, toMapCoordinates) : empty)) {
      map.addLayer({
        id: "situation-regas",
        type: "circle",
        source: "situation-regas",
        paint: {
          "circle-radius": 11,
          "circle-color": palette.own,
          "circle-opacity": ["case", ["get", "active"], 0.22, 0.1],
          "circle-stroke-color": palette.own,
          "circle-stroke-width": 2,
        },
      });
    }
    if (upsertSource(map, "situation-contracts", situation ? contractFeatures(situation.contracts, toMapCoordinates) : empty)) {
      map.addLayer({
        id: "situation-contracts",
        type: "circle",
        source: "situation-contracts",
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["get", "count"], 1, 6, 5, 9],
          "circle-color": palette.halo,
          "circle-stroke-color": palette.own,
          "circle-stroke-width": 3,
        },
      });
    }
    const cargoPositions = (cargo?.positions ?? empty) as FC<{ type: "Point"; coordinates: [number, number] }>;
    const cargoBefore = cargoDrawnRef.current;
    cargoDrawnRef.current = cargoPositions;
    const cargoCreated = upsertSource(map, "situation-cargo-positions", cargoPositions as FeatureCollectionData);
    if (!cargoCreated && cargoBefore && cargoBefore !== cargoPositions) {
      const was = pointIndex(cargoBefore);
      const moved = cargoPositions.features.some((feature) => {
        const at = was.get(`${String(feature.properties.id)}|${String(feature.properties.basis)}`);
        return at !== undefined && (at[0] !== feature.geometry.coordinates[0] || at[1] !== feature.geometry.coordinates[1]);
      });
      const duration = cameraMotion().duration;
      const source = map.getSource("situation-cargo-positions") as GeoJSONSource | undefined;
      if (moved && duration > 0 && source) {
        cancelAnimationFrame(cargoTweenRef.current);
        const start = performance.now();
        const step = (time: number) => {
          const k = Math.min(1, (time - start) / duration);
          source.setData(tweenPoints(was, cargoPositions, easeOut(k)) as FeatureCollectionData);
          if (k < 1) cargoTweenRef.current = requestAnimationFrame(step);
        };
        step(start);
      }
    }
    if (cargoCreated) {
      map.addLayer({
        id: "situation-cargo-positions",
        type: "symbol",
        source: "situation-cargo-positions",
        layout: {
          "icon-image": vesselImage as never,
          "icon-size": ["case", ["get", "own"], 1, 0.75] as never,
          "icon-rotate": ["get", "heading"],
          "icon-rotation-alignment": "map",
          // A vessel always shows; names give way around it.
          "icon-allow-overlap": true,
          "icon-ignore-placement": false,
          "symbol-sort-key": ["case", ["get", "own"], 0, 1] as never,
        },
      });
    } else if (map.getLayer("situation-cargo-positions")) {
      map.setLayoutProperty("situation-cargo-positions", "icon-image", vesselImage as never);
    }
    if (upsertSource(map, "situation-outages", situation ? outageFeatures(situation.outages, toMapCoordinates) : empty)) {
      map.addLayer({
        id: "situation-outage-halo",
        type: "circle",
        source: "situation-outages",
        filter: ["==", ["get", "status"], "active"],
        paint: {
          "circle-radius": ["+", 12, ["*", 14, ["get", "share"]]],
          "circle-color": palette.outageActive,
          "circle-opacity": 0.14,
        },
      });
      map.addLayer({
        id: "situation-outages",
        type: "circle",
        source: "situation-outages",
        paint: {
          "circle-radius": ["+", 5, ["*", 6, ["get", "share"]]],
          "circle-color": ["match", ["get", "status"], "active", palette.outageActive, palette.outageScheduled],
          "circle-stroke-color": palette.halo,
          "circle-stroke-width": 1.5,
        },
      });

      const hover = new Popup({ closeButton: false, closeOnClick: false, offset: 10, maxWidth: "300px" });
      const cardFor = (layerId: string, props: Record<string, unknown>): string => {
        const current = situationRef.current;
        if (layerId === "situation-facilities") {
          return `<div class="node-popup situation-card"><strong>${escapeHtml(props.name)}</strong><small>${escapeHtml(t(`map.situation.facility_${String(props.facility_type)}`))}</small></div>`;
        }
        return current ? situationCardHtml(String(props.kind), String(props.id), current, t, escapeHtml) : "";
      };
      for (const layerId of SITUATION_HOVER_LAYERS) {
        map.on("mousemove", layerId, (event) => {
          const feature = event.features?.[0];
          if (!feature) return;
          const html = cardFor(layerId, feature.properties ?? {});
          if (!html) return;
          map.getCanvas().style.cursor = "pointer";
          hover.setLngLat(event.lngLat).setHTML(html).addTo(map);
        });
        map.on("mouseleave", layerId, () => {
          map.getCanvas().style.cursor = "";
          hover.remove();
        });
        // Click selects: the map flies to the item and docks its card on the right.
        map.on("click", layerId, (event) => {
          const feature = event.features?.[0];
          if (!feature) return;
          const props = feature.properties ?? {};
          const coordinates = (feature.geometry as { coordinates?: [number, number] }).coordinates;
          const target = Array.isArray(coordinates) && typeof coordinates[0] === "number"
            ? coordinates
            : [event.lngLat.lng, event.lngLat.lat] as [number, number];
          hover.remove();
          if (props.kind === "cargo") {
            const cargo = situationRef.current?.cargoes.find((item) => item.cargo_id === String(props.id));
            if (!frameCargo(map, cargo, toMapCoordinates)) focusOn(map, target, Math.max(map.getZoom(), 7));
            setSelection({ kind: "cargo", id: String(props.id) });
            return;
          }
          focusOn(map, target, Math.max(map.getZoom(), layerId === "situation-facilities" ? 9 : 7));
          if (props.kind === "cargo") setSelection({ kind: "cargo", id: String(props.id) });
          else setSelection(selectForRef.current(String(layerId === "situation-facilities" ? props.id : props.ref ?? "")));
        });
      }
      for (const layerId of ["situation-cargo-sailed", "situation-cargo-ahead"]) {
        map.on("click", layerId, (event) => {
          const id = event.features?.[0]?.properties?.id;
          if (id) setSelection({ kind: "cargo", id: String(id) });
        });
      }
    }

    const visibility = (on: boolean) => (on ? "visible" : "none");
    // Individual assets appear from the region tier; the overview shows country totals.
    for (const layerId of [
      "situation-facilities",
      "situation-flows",
      "situation-cargo-sailed",
      "situation-cargo-ahead",
      "situation-regas",
      "situation-contracts",
      "situation-cargo-positions",
      "situation-outage-halo",
      "situation-outages",
    ]) {
      // What touches our book (our deals, our cargoes, the outages on the book) is the map's
      // subject and draws at every zoom; the rest of the system from regional zoom.
      const bookLayer = layerId.startsWith("situation-cargo") || layerId === "situation-regas"
        || layerId === "situation-contracts" || layerId.startsWith("situation-outage");
      if (map.getLayer(layerId)) map.setLayerZoomRange(layerId, bookLayer ? 0 : OVERVIEW_MAX_ZOOM, 24);
    }
    const show: Record<string, boolean> = {
      "situation-facilities": activeLayers.includes("infrastructure"),
      "situation-pipeline-flow": activeLayers.includes("flows"),
      "situation-flows": activeLayers.includes("flows"),
      // Our cargoes with "Our cargoes", market vessels with "LNG vessels" (filtered below).
      "situation-cargo-sailed": activeLayers.includes("cargoes") || activeLayers.includes("vessels"),
      "situation-cargo-ahead": activeLayers.includes("cargoes") || activeLayers.includes("vessels"),
      "situation-regas": activeLayers.includes("positions"),
      "situation-contracts": activeLayers.includes("positions"),
      "situation-cargo-positions": activeLayers.includes("cargoes") || activeLayers.includes("vessels"),
      "situation-outage-halo": outageIds.size > 0,
      "situation-outages": outageIds.size > 0,
    };
    for (const [layerId, on] of Object.entries(show)) {
      if (map.getLayer(layerId)) map.setLayoutProperty(layerId, "visibility", visibility(on));
    }
    const cargoFilter = [
      "any",
      ["all", ["==", ["get", "own"], true], activeLayers.includes("cargoes")],
      ["all", ["==", ["get", "own"], false], activeLayers.includes("vessels")],
    ];
    // Outages: by default those that touch our book; "All outages" shows every one.
    const outageFilter = ["in", ["get", "id"], ["literal", [...outageIds]]];
    for (const layerId of ["situation-outages"]) {
      if (map.getLayer(layerId)) map.setFilter(layerId, outageFilter as never);
    }
    if (map.getLayer("situation-outage-halo")) {
      map.setFilter("situation-outage-halo", ["all", ["==", ["get", "status"], "active"], outageFilter] as never);
    }
    for (const layerId of ["situation-cargo-sailed", "situation-cargo-positions"]) {
      if (map.getLayer(layerId)) map.setFilter(layerId, cargoFilter as never);
    }
    if (map.getLayer("situation-cargo-ahead")) {
      map.setFilter("situation-cargo-ahead", cargoFilter as never);
    }
    // Theme changes re-colour the layers in place.
    const ownOrMarket = ["case", ["get", "own"], palette.own, palette.market];
    const paints: Array<[string, string, unknown]> = [
      ["nodes-approx-halo", "circle-color", palette.facility],
      ["nodes-approx-halo", "circle-stroke-color", palette.facility],
      ["situation-pipeline-flow", "line-color", palette.flow],
      ["situation-flows", "circle-color", palette.flow],
      ["situation-flows", "circle-stroke-color", palette.flow],
      ["situation-cargo-sailed", "line-color", ownOrMarket],
      ["situation-cargo-ahead", "line-color", ownOrMarket],
      ["situation-regas", "circle-color", palette.own],
      ["situation-regas", "circle-stroke-color", palette.own],
      ["situation-contracts", "circle-color", palette.halo],
      ["situation-contracts", "circle-stroke-color", palette.own],
      ["situation-outage-halo", "circle-color", palette.outageActive],
      ["situation-outages", "circle-color", ["match", ["get", "status"], "active", palette.outageActive, palette.outageScheduled]],
      ["situation-outages", "circle-stroke-color", palette.halo],
    ];
    for (const [layerId, property, value] of paints) {
      if (map.getLayer(layerId)) map.setPaintProperty(layerId, property as never, value as never);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeLayers, effectiveTheme, facilities, mapReady, outageIds, situation, t, verifiedPipelineLines, view]);

  // Selection: draw the selected object and what it relates to on top, dim everything else.
  const dimmedRef = useRef<Map<string, unknown>>(new Map());
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const accent = SITUATION_COLOURS[effectiveTheme].own;
    type Coord = [number, number];
    const lines: Array<{ part: string; coords: Coord[] }> = [];
    const points: Array<{ part: string; at: Coord }> = [];
    const labels: Array<{ at: Coord; text: string }> = [];
    let hubMembers: Set<string> | null = null;
    if (selection?.kind === "cargo" && situation) {
      const cargo = situation.cargoes.find((item) => item.cargo_id === selection.id);
      if (cargo) {
        // The vessel where it was reported, the track it sailed (only from its position history)
        // and the direction to its terminal, with the terminal named; the card is in the panel.
        const at = cargo.position ?? (cargo.status === "loading" ? cargo.origin : null);
        if (cargo.track.length > 1) lines.push({ part: "sailed", coords: cargo.track.map(([lon, lat]) => [lon, lat] as Coord) });
        if (at && cargo.destination && cargo.status === "laden") {
          lines.push({ part: "ahead", coords: [[at.lon, at.lat], [cargo.destination.lon, cargo.destination.lat]] });
        }
        if (cargo.destination) {
          points.push({ part: "end", at: [cargo.destination.lon, cargo.destination.lat] });
          if (cargo.destination_terminal) labels.push({ at: [cargo.destination.lon, cargo.destination.lat], text: cargo.destination_terminal });
        }
        if (at) points.push({ part: "current", at: [at.lon, at.lat] });
      }
    } else if (selection?.kind === "site") {
      const site = sites.find((item) => item.id === selection.id);
      if (site) {
        const ids = new Set(site.members.map((member) => member.id));
        for (const node of nodes) if (ids.has(node.id)) points.push({ part: "current", at: [node.lon, node.lat] });
        for (const facility of facilities) if (ids.has(facility.id)) points.push({ part: "current", at: [facility.lon, facility.lat] });
        for (const line of verifiedPipelineLines) {
          if (ids.has(line.from.id) || ids.has(line.to.id)) lines.push({ part: "link", coords: line.geometryCoordinates as Coord[] });
        }
        // A point inside a market area (storage, LNG, production) shows its one link to the
        // hub of the zone it delivers into: membership, drawn only on selection.
        for (const edge of edges) {
          if (!ids.has(edge.from_node_id) && !ids.has(edge.to_node_id)) continue;
          const from = nodeLookup.get(edge.from_node_id);
          const to = nodeLookup.get(edge.to_node_id);
          if (!from || !to || !isZoneMembershipEdge(edge, from, to)) continue;
          if (![from.lon, from.lat, to.lon, to.lat].every(Number.isFinite)) continue;
          lines.push({ part: "ahead", coords: [[from.lon, from.lat], [to.lon, to.lat]] });
        }
        if (situation) {
          for (const cargo of siteSituation(site, situation).inbound) {
            const at = cargo.position ?? cargo.origin;
            if (at) {
              lines.push({ part: "ahead", coords: [[at.lon, at.lat], [site.lon, site.lat]] });
              points.push({ part: "end", at: [at.lon, at.lat] });
              labels.push({ at: [at.lon, at.lat], text: cargoMapLabel(cargo, cargoEta(cargo, Date.now()), t) });
            }
          }
        }
        if (!sitePipelines(site, edges).length && !points.length) points.push({ part: "current", at: [site.lon, site.lat] });
      }
    } else if (selection?.kind === "hub") {
      const hub = nodes.find((node) => node.node_type === "hub" && node.name.toUpperCase() === selection.id);
      if (hub) {
        points.push({ part: "current", at: [hub.lon, hub.lat] });
        // A hub is a market area: its points are marked, never wired to the hub.
        hubMembers = zoneMemberIds(hub.id, edges);
        // Its connections to neighbouring market areas are emphasised (one line per pair, as
        // drawn by default, and the pipelines leaving from them); every other interconnection
        // point joining it to a neighbour is ringed, not wired, so selection never fans out.
        for (const edge of hubAdjacencyEdges(hub.id, edges)) {
          hubMembers.add(edge.from_node_id === hub.id ? edge.to_node_id : edge.from_node_id);
          if (!isDrawnAdjacency(edge)) continue;
          const from = nodeLookup.get(edge.from_node_id);
          const to = nodeLookup.get(edge.to_node_id);
          if (!from || !to || ![from.lon, from.lat, to.lon, to.lat].every(Number.isFinite)) continue;
          lines.push({ part: "link", coords: presentationPath(edge) ?? [[from.lon, from.lat], [to.lon, to.lat]] });
        }
        for (const node of nodes) {
          if (hubMembers.has(node.id) && Number.isFinite(node.lon) && Number.isFinite(node.lat)) {
            points.push({ part: "member", at: [node.lon, node.lat] });
          }
        }
      }
    }
    const lineData = {
      type: "FeatureCollection" as const,
      features: lines.map((line) => ({
        type: "Feature" as const,
        properties: { part: line.part },
        geometry: { type: "LineString" as const, coordinates: line.coords.map(([lon, lat]) => toMapCoordinates(lon, lat)) },
      })),
    };
    const pointData = {
      type: "FeatureCollection" as const,
      features: points.map((item) => ({
        type: "Feature" as const,
        properties: { part: item.part },
        geometry: { type: "Point" as const, coordinates: toMapCoordinates(item.at[0], item.at[1]) },
      })),
    };
    if (upsertSource(map, "selection-lines", lineData)) {
      map.addLayer({
        id: "selection-lines",
        type: "line",
        source: "selection-lines",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": accent, "line-width": 3.4, "line-opacity": 0.95 },
      });
      map.addLayer({
        id: "selection-lines-ahead",
        type: "line",
        source: "selection-lines",
        filter: ["==", ["get", "part"], "ahead"],
        layout: { "line-cap": "round" },
        paint: { "line-color": accent, "line-width": 2.6, "line-dasharray": [1.5, 1.8] },
      });
      map.setFilter("selection-lines", ["!=", ["get", "part"], "ahead"]);
    }
    if (upsertSource(map, "selection-points", pointData)) {
      map.addLayer({
        id: "selection-points",
        type: "circle",
        source: "selection-points",
        paint: {
          "circle-radius": ["match", ["get", "part"], "current", 11, "member", 5, 7],
          "circle-color": "rgba(0,0,0,0)",
          "circle-stroke-color": accent,
          "circle-stroke-width": ["match", ["get", "part"], "current", 3, "member", 1.5, 2],
        },
      });
    }
    map.setPaintProperty("selection-lines", "line-color", accent);
    map.setPaintProperty("selection-lines-ahead", "line-color", accent);
    map.setPaintProperty("selection-points", "circle-stroke-color", accent);
    // Everything else steps back while something is selected.
    const dimmable: Array<[string, string]> = [
      ["nodes-circle", "circle-opacity"],
      ["node-clusters", "circle-opacity"],
      ["verified-pipeline-lines", "line-opacity"],
      ["network-link-lines", "line-opacity"],
      ["adjacency-points", "circle-opacity"],
      ["indicative-route-lines", "line-opacity"],
      ["book-flow-lines", "line-opacity"],
      ["situation-facilities", "icon-opacity"],
      ["situation-flows", "circle-opacity"],
      ["situation-pipeline-flow", "line-opacity"],
      ["situation-cargo-sailed", "line-opacity"],
      ["situation-cargo-ahead", "line-opacity"],
      ["situation-regas", "circle-opacity"],
      ["situation-contracts", "circle-opacity"],
      ["situation-cargo-positions", "icon-opacity"],
      ["situation-outages", "circle-opacity"],
    ];
    const emphasis: Record<string, unknown> = { ...VIEW_EMPHASIS[view] };
    if (view === "book" && bookEmphasis && (bookEmphasis.ours.size || bookEmphasis.reachable.size)) {
      // Our book: what relates to the deals stands out, everything else dims.
      const ours = ["literal", [...bookEmphasis.ours]];
      const related = ["literal", [...bookEmphasis.ours, ...bookEmphasis.reachable]];
      emphasis["nodes-circle"] = ["case", ["in", ["get", "id"], ours], 1, ["in", ["get", "id"], ["literal", [...bookEmphasis.reachable]]], 0.7, 0.12];
      emphasis["network-link-lines"] = [
        "case",
        ["all", ["in", ["get", "from_node_id"], related], ["in", ["get", "to_node_id"], related]],
        0.6,
        0.12,
      ];
      emphasis["adjacency-points"] = ["case", ["in", ["get", "id"], related], 0.9, 0.15];
    }
    for (const [layerId, property] of dimmable) {
      if (!map.getLayer(layerId)) continue;
      const key = `${layerId}|${property}`;
      // The layer's own opacity, read once before this effect ever changes it.
      if (!dimmedRef.current.has(key)) dimmedRef.current.set(key, map.getPaintProperty(layerId, property as never) ?? 1);
      const base = emphasis[layerId] ?? dimmedRef.current.get(key);
      // A selected hub keeps its zone's points at full strength and steps the rest back.
      const dimmed = hubMembers && layerId === "nodes-circle"
        ? ["case", ["in", ["get", "id"], ["literal", [...hubMembers]]], 0.95, 0.2]
        : 0.25;
      map.setPaintProperty(layerId, property as never, (selection || replay ? dimmed : base) as never);
    }
    // The selection's names: a symbol layer above the map's own labels, so they win a collision.
    const selectionLabelData = {
      type: "FeatureCollection" as const,
      features: labels.map((label) => ({
        type: "Feature" as const,
        properties: { text: label.text },
        geometry: { type: "Point" as const, coordinates: toMapCoordinates(label.at[0], label.at[1]) },
      })),
    };
    if (upsertSource(map, "selection-labels", selectionLabelData)) {
      map.addLayer({
        id: "selection-labels",
        type: "symbol",
        source: "selection-labels",
        layout: {
          "text-field": ["get", "text"],
          "text-font": labelFont(mapTileProvider.id, "bold"),
          "text-size": 12,
          "text-variable-anchor": ["left", "right", "top", "bottom"],
          "text-radial-offset": 1.1,
          "text-justify": "auto",
          "text-padding": 3,
        },
        paint: { "text-color": accent, "text-halo-color": SITUATION_COLOURS[effectiveTheme].halo, "text-halo-width": 1.4 },
      });
    }
    map.setPaintProperty("selection-labels", "text-color", accent);
    map.setPaintProperty("selection-labels", "text-halo-color", SITUATION_COLOURS[effectiveTheme].halo);
    map.moveLayer("selection-labels");
    if (map.getLayer("overlay-blockers")) map.moveLayer("overlay-blockers");
  }, [bookEmphasis, edges, effectiveTheme, facilities, mapReady, nodeLookup, nodes, selection, situation, sites, verifiedPipelineLines, view, Boolean(replay)]);

  // Replay of a completed deal: the whole voyage faint, the part sailed by the replay clock
  // drawn in the accent, the vessel where it was. Driven from outside (play, scrub).
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const accent = SITUATION_COLOURS[effectiveTheme].own;
    const project = (coords: Array<[number, number]>) => coords.map(([lon, lat]) => toMapCoordinates(lon, lat));
    const lines = {
      type: "FeatureCollection" as const,
      features: replay
        ? [
            { type: "Feature" as const, properties: { part: "path" }, geometry: { type: "LineString" as const, coordinates: project(replay.path) } },
            ...(replay.sailed.length > 1
              ? [{ type: "Feature" as const, properties: { part: "sailed" }, geometry: { type: "LineString" as const, coordinates: project(replay.sailed) } }]
              : []),
          ]
        : [],
    };
    const vessel = {
      type: "FeatureCollection" as const,
      features: replay
        ? [{ type: "Feature" as const, properties: { label: replay.label }, geometry: { type: "Point" as const, coordinates: toMapCoordinates(replay.at[0], replay.at[1]) } }]
        : [],
    };
    if (upsertSource(map, "replay-lines", lines)) {
      map.addLayer({
        id: "replay-lines",
        type: "line",
        source: "replay-lines",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": accent,
          "line-width": ["case", ["==", ["get", "part"], "sailed"], 3.2, 1.4],
          "line-opacity": ["case", ["==", ["get", "part"], "sailed"], 0.95, 0.3],
        },
      });
    }
    if (upsertSource(map, "replay-vessel", vessel)) {
      map.addLayer({
        id: "replay-vessel",
        type: "circle",
        source: "replay-vessel",
        paint: { "circle-radius": 7, "circle-color": accent, "circle-stroke-color": "#ffffff", "circle-stroke-width": 2 },
      });
    }
    map.setPaintProperty("replay-lines", "line-color", accent);
    map.setPaintProperty("replay-vessel", "circle-color", accent);
  }, [effectiveTheme, mapReady, replay]);

  // Focus requested from outside (the book list): select it and bring it into view.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !focus) return;
    if (focus.path && focus.path.length > 1) {
      const projected = focus.path.map(([lon, lat]) => toMapCoordinates(lon, lat));
      const lons = projected.map((point) => point[0]);
      const lats = projected.map((point) => point[1]);
      map.fitBounds(
        [[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]],
        { padding: 80, maxZoom: 7, ...cameraMotion() },
      );
      return;
    }
    if (focus.cargoId) {
      const cargo = situationRef.current?.cargoes.find((item) => item.cargo_id === focus.cargoId);
      setSelection({ kind: "cargo", id: focus.cargoId });
      frameCargo(map, cargo, toMapCoordinates);
      return;
    }
    if (focus.refId) {
      const next = selectForRef.current(focus.refId);
      if (next) setSelection(next);
      const node = nodes.find((item) => item.id === focus.refId);
      const facility = facilities.find((item) => item.id === focus.refId);
      const place = node ?? facility;
      if (place && place.lon != null && place.lat != null) {
        focusOn(map, toMapCoordinates(place.lon, place.lat), 7);
        return;
      }
    }
    if (focus.at) focusOn(map, toMapCoordinates(focus.at[0], focus.at[1]), 7);
    // Only a new request moves the map; data refreshes do not.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focus?.nonce, mapReady]);

  // The visible area, for a page list that follows the map.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return undefined;
    const report = () => {
      const bounds = map.getBounds();
      viewChangeRef.current?.({ west: bounds.getWest(), south: bounds.getSouth(), east: bounds.getEast(), north: bounds.getNorth() });
    };
    report();
    map.on("moveend", report);
    return () => {
      map.off("moveend", report);
    };
  }, [mapReady]);

  // A quiet ring where a hovered list row is: a hint, not a selection.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !hoverAt) return undefined;
    const element = document.createElement("div");
    element.className = "map-hover-ring";
    element.setAttribute("aria-hidden", "true");
    const ring = new Marker({ element }).setLngLat(toMapCoordinates(hoverAt[0], hoverAt[1])).addTo(map);
    return () => {
      ring.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hoverAt?.[0], hoverAt?.[1], mapReady]);

  // Motion rules (design system): nothing on the map loops except the pulse of a disruption
  // touching the book (CSS, `.map-disruption.is-pulse`). Flows and voyages are drawn still.

  // The map's names: one symbol layer MapLibre declutters (app/mapLabels.ts). A label that would
  // touch another is dropped, the less important first, and the basemap's names give way to
  // ours; nothing is an HTML box over the map.
  // Europe's import supply corridors (app/mapCorridors.ts): thin lines, solid on a SciGRID path
  // and dashed when schematic; in service with the flow width and an arrowhead at the landing,
  // out of service grey with none. On by default ("Supply corridors").
  const corridorSelectRef = useRef(onSelectCorridor);
  corridorSelectRef.current = onSelectCorridor;
  const corridorDrawn = useMemo(() => corridorLines(corridors), [corridors]);
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const features = corridorDrawn.flatMap((line) => {
      const props = { id: line.id, in_service: line.inService, schematic: line.schematic, width: line.width };
      const chevron = line.inService ? chevronAt(line.coordinates, 30) : null;
      return [
        { type: "Feature" as const, properties: { ...props, part: "line" }, geometry: { type: "LineString" as const, coordinates: line.coordinates.map(([lon, lat]) => toMapCoordinates(lon, lat)) } },
        ...(chevron ? [{ type: "Feature" as const, properties: { ...props, part: "arrow" }, geometry: { type: "LineString" as const, coordinates: chevron.map(([lon, lat]) => toMapCoordinates(lon, lat)) } }] : []),
      ];
    });
    const flowColour = SITUATION_COLOURS[effectiveTheme].flow;
    const grey = effectiveTheme === "dark" ? "#71717a" : "#a1a1aa";
    const colour = ["case", ["get", "in_service"], flowColour, grey];
    const before = map.getLayer("node-clusters") ? "node-clusters" : undefined;
    if (upsertSource(map, "supply-corridors", { type: "FeatureCollection", features })) {
      for (const [id, schematic] of [["supply-corridors", false], ["supply-corridors-schematic", true]] as const) {
        map.addLayer({
          id,
          type: "line",
          source: "supply-corridors",
          filter: ["all", ["==", ["get", "schematic"], schematic], ["==", ["get", "part"], "line"]],
          layout: { "line-cap": "butt", "line-join": "round" },
          paint: {
            "line-color": colour as never,
            "line-width": ["get", "width"],
            "line-opacity": ["case", ["get", "in_service"], 0.85, 0.6],
            ...(schematic ? { "line-dasharray": [2.5, 2] } : {}),
          },
        }, before);
      }
      map.addLayer({
        id: "supply-corridor-arrows",
        type: "line",
        source: "supply-corridors",
        filter: ["==", ["get", "part"], "arrow"],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": colour as never, "line-width": 2, "line-opacity": 0.9 },
      }, before);
      map.addLayer({
        id: "supply-corridor-hit",
        type: "line",
        source: "supply-corridors",
        filter: ["==", ["get", "part"], "line"],
        paint: { "line-color": "rgba(0,0,0,0)", "line-width": 12 },
      });
      map.on("click", "supply-corridor-hit", (event) => {
        const id = event.features?.[0]?.properties?.id;
        if (id) corridorSelectRef.current?.(String(id));
      });
      map.on("mouseenter", "supply-corridor-hit", () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", "supply-corridor-hit", () => {
        map.getCanvas().style.cursor = "";
      });
    }
    const visible = activeLayers.includes("corridors") ? "visible" : "none";
    for (const id of ["supply-corridors", "supply-corridors-schematic", "supply-corridor-arrows", "supply-corridor-hit"]) {
      if (!map.getLayer(id)) continue;
      map.setLayoutProperty(id, "visibility", visible);
      if (id !== "supply-corridor-hit") map.setPaintProperty(id, "line-color", colour as never);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeLayers, corridorDrawn, effectiveTheme, mapReady]);
  const extraLabels = useMemo<MapLabel[]>(() => {
    const base = { price: "", sim: "", action: "" };
    // Each corridor names itself and its flow (or its status) at its landing.
    const lines = new globalThis.Map(corridorDrawn.map((line) => [line.id, line]));
    const corridorLabels: MapLabel[] = activeLayers.includes("corridors")
      ? corridors.flatMap((corridor) => {
          const line = lines.get(corridor.id);
          return line ? [{ ...base, at: line.landing, text: corridorLabel(corridor, t), rank: 2, tone: "point" as const }] : [];
        })
      : [];
    // Flow intensity at Europe zoom: each border's net figure at its middle.
    const byId = new globalThis.Map(nodes.map((node) => [node.id, node]));
    const borderLabels: MapLabel[] = intensity === "flow" && labelZoom < BORDER_FLOWS_BELOW_ZOOM
      ? (intensityData?.borders ?? []).flatMap((border) => {
          const from = byId.get(border.fromId);
          const to = byId.get(border.toId);
          return from && to
            ? [{ ...base, at: [(from.lon + to.lon) / 2, (from.lat + to.lat) / 2] as [number, number], text: `${Math.round(border.value).toLocaleString("en-GB")}`, rank: 2, tone: "point" as const }]
            : [];
        })
      : [];
    if (view !== "book") return [...corridorLabels, ...borderLabels];
    const out: MapLabel[] = [...corridorLabels, ...borderLabels];
    if (activeLayers.includes("positions")) {
      for (const flow of bookFlows) {
        const end = flow.coordinates[flow.coordinates.length - 1];
        if (end) out.push({ ...base, at: end, text: flow.label, rank: 0, tone: "own" });
      }
    }
    for (const line of bookOpportunities) {
      out.push({ ...base, at: line.labelAt, text: line.label, rank: 0, tone: "opportunity", action: `opportunity:${line.opportunityId}` });
    }
    for (const line of bookProposals) {
      out.push({ ...base, at: line.labelAt, text: line.label, rank: 0, tone: "opportunity", action: `opportunity:${line.opportunityId}` });
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeLayers, bookFlows, bookOpportunities, bookProposals, corridorDrawn, corridors, intensity, intensityData, labelZoom, nodes, view]);
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const palette = SITUATION_COLOURS[effectiveTheme];
    const strong = effectiveTheme === "dark" ? "#f4f4f5" : "#18181b";
    const muted = effectiveTheme === "dark" ? "#a1a1aa" : "#52525b";
    const labels = mapLabels({
      nodes: filteredNodes,
      activeLayers,
      situation,
      marketRows,
      facilities,
      zoom: labelZoom,
      nowMs: Date.now(),
      t,
      outageIds,
      extra: extraLabels,
    });
    const regular = labelFont(mapTileProvider.id);
    const bold = labelFont(mapTileProvider.id, "bold");
    if (upsertSource(map, "map-labels", labelFeatures(labels, toMapCoordinates))) {
      map.addLayer({
        id: "map-labels",
        type: "symbol",
        source: "map-labels",
        layout: {
          "text-field": [
            "format",
            ["get", "text"], { "text-font": ["match", ["get", "tone"], "hub", ["literal", bold], ["literal", regular]] },
            ["get", "price"], { "text-font": ["literal", bold] },
            ["get", "sim"], { "font-scale": 0.8, "text-font": ["literal", regular] },
          ] as never,
          "text-font": regular,
          "text-size": ["match", ["get", "tone"], "hub", 12.5, "own", 12, "opportunity", 12, 11] as never,
          // A label sits beside its point, on whichever side is free; if none is, it is dropped.
          "text-variable-anchor": ["left", "right", "top", "bottom"],
          "text-radial-offset": 0.8,
          "text-justify": "auto",
          "text-max-width": 28,
          "text-padding": 3,
          "text-allow-overlap": false,
          "text-ignore-placement": false,
          "symbol-sort-key": ["get", "rank"],
        },
        paint: {
          "text-color": ["match", ["get", "tone"], "own", palette.own, "hub", strong, "outage", palette.outageActive, "opportunity", palette.opportunity, muted] as never,
          "text-halo-color": palette.halo,
          "text-halo-width": 1.4,
        },
      });
      map.on("click", "map-labels", (event) => {
        const action = String(event.features?.[0]?.properties?.action ?? "");
        if (action.startsWith("opportunity:")) selectOpportunityRef.current?.(action.slice("opportunity:".length));
      });
    } else {
      map.setPaintProperty("map-labels", "text-color", ["match", ["get", "tone"], "own", palette.own, "hub", strong, "outage", palette.outageActive, "opportunity", palette.opportunity, muted] as never);
      map.setPaintProperty("map-labels", "text-halo-color", palette.halo);
    }
    // Names above every line and mark drawn since (the scene, the selection).
    map.moveLayer("map-labels");
    if (map.getLayer("selection-labels")) map.moveLayer("selection-labels");
    // The overlays' blockers stay topmost, so names keep clear of the HTML over the map.
    if (map.getLayer("overlay-blockers")) map.moveLayer("overlay-blockers");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeLayers, effectiveTheme, extraLabels, facilities, filteredNodes, labelZoom, mapReady, marketRows, outageIds, situation, t]);

  // Overview tier: no per-country cards over the map (they collided with labels and each
  // other); the outage list groups by zone, and a click on the map selects what is there.

  /** Frame everything the firm holds: contracts, own cargoes and held slots. */
  function fitOurPositions() {
    const map = mapRef.current;
    if (!map || !situation) return;
    // The book list covers the left of the map in the book view. On a phone the padding is
    // scaled to the map: padding wider than the map leaves MapLibre no camera, and fitBounds
    // then throws (the book view went blank at phone width).
    const wanted = view === "book" ? { top: 90, bottom: 90, left: 340, right: 80 } : { top: 80, bottom: 80, left: 80, right: 80 };
    const { clientWidth: width, clientHeight: height } = map.getContainer();
    const scaleX = Math.min(1, (width * 0.6) / (wanted.left + wanted.right));
    const scaleY = Math.min(1, (height * 0.6) / (wanted.top + wanted.bottom));
    const padding = {
      top: Math.round(wanted.top * scaleY),
      bottom: Math.round(wanted.bottom * scaleY),
      left: Math.round(wanted.left * scaleX),
      right: Math.round(wanted.right * scaleX),
    };
    const points: Array<[number, number]> = [
      ...situation.contracts.map((item) => [item.location.lon, item.location.lat] as [number, number]),
      ...situation.regas_slots.map((item) => [item.location.lon, item.location.lat] as [number, number]),
      ...situation.cargoes.filter((item) => item.own && item.status !== "delivered" && item.status !== "ballast").flatMap((item) =>
        [item.position, item.destination].filter(Boolean).map((at) => [at!.lon, at!.lat] as [number, number])),
    ].map(([lon, lat]) => toMapCoordinates(lon, lat));
    if (!points.length) return;
    const lons = points.map(([lon]) => lon);
    const lats = points.map(([, lat]) => lat);
    map.fitBounds(
      [[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]],
      { padding, maxZoom: 7, duration: prefersReducedMotion() ? 0 : 900 },
    );
  }
  const fitOurPositionsRef = useRef(fitOurPositions);
  fitOurPositionsRef.current = fitOurPositions;

  // The first view is our footprint (owner review 2026-11-26): the map opens framed on what we
  // hold (contracts, slots, our cargoes and where they are going), once, unless the person had
  // a view of their own to come back to. Switching to the book frames the book, once per switch.
  const framedBookRef = useRef(false);
  const framedFootprintRef = useRef(compact || remembered.camera !== null);
  useEffect(() => {
    if (!mapReady || !situation) return;
    if (view !== "book") {
      framedBookRef.current = false;
      if (framedFootprintRef.current) return;
      framedFootprintRef.current = true;
      fitOurPositionsRef.current();
      return;
    }
    if (framedBookRef.current) return;
    framedBookRef.current = true;
    framedFootprintRef.current = true;
    fitOurPositionsRef.current();
  }, [mapReady, situation, view]);

  // A replay frames its whole voyage when it starts.
  const replayPathKey = replay ? `${replay.label}|${replay.path.length}` : "";
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !replay) return;
    const points = replay.path.map(([lon, lat]) => toMapCoordinates(lon, lat));
    const lons = points.map(([lon]) => lon);
    const lats = points.map(([, lat]) => lat);
    map.fitBounds(
      [[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]],
      { padding: { top: 140, bottom: 110, left: 340, right: 80 }, maxZoom: 6, duration: prefersReducedMotion() ? 0 : 900 },
    );
    // Only a new voyage reframes; the moving vessel does not.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mapReady, replayPathKey]);

  // MAP-1: terminal and storage columns, moving flows, voyages with estimated positions. Its
  // layers are added after the map's own (this hook's effects run after the ones above).
  // The stored gas day the flows show is chosen in the toolbar while flows are drawn (the page
  // holds it), never as a bar over the map's bottom edge.
  const flowDays = useMemo(() => flowDayOptions(situation), [situation]);
  // A stored day that has left the window falls back to the latest.
  const shownFlowDay = flowDay !== null && flowDays.includes(flowDay) ? flowDay : null;
  const sceneProject = useCallback(
    (lon: number, lat: number): [number, number] => transformCoordinate(mapTileProvider.id, lon, lat),
    [mapTileProvider.id],
  );
  const scene = useMapScene({
    map: mapRef.current,
    ready: mapReady,
    enabled: !compact,
    situation,
    nodes,
    edges,
    theme: effectiveTheme,
    flowColour: SITUATION_COLOURS[effectiveTheme].flow,
    project: sceneProject,
    flowDay: shownFlowDay,
    activeLayers,
    t: t as (key: string, options?: Record<string, unknown>) => string,
    onSelectRef: (refId) => {
      const next = selectForRef.current(refId);
      if (next) setSelection(next);
      // A clicked site point brings its site in, as a clicked dot does.
      const map = mapRef.current;
      const node = nodes.find((item) => item.id === refId);
      if (map && node) focusOn(map, toMapCoordinates(node.lon, node.lat), Math.max(map.getZoom(), 7));
    },
  });

  // Everything the map can locate, for the finder. Positions come from the same sources
  // as the layers, so the finder never lands somewhere the map would not draw.
  const finderPlaces = useMemo<MapFinderPlace[]>(() => {
    // Only what the active layers draw, so the map never flies to something it hides.
    const places: MapFinderPlace[] = filteredNodes.map((node) => ({
      id: node.id,
      name: node.name,
      kind: t(`map.find.kind_${node.node_type === "hub" || node.node_type === "lng" || node.node_type === "interconnection" ? node.node_type : "point"}`),
      lon: node.lon,
      lat: node.lat,
      zoom: node.node_type === "hub" ? 6 : 7,
    }));
    for (const facility of activeLayers.includes("infrastructure") ? facilities : []) {
      places.push({
        id: facility.id,
        name: facility.name,
        kind: t(`map.situation.facility_${facility.facility_type}`),
        lon: facility.lon,
        lat: facility.lat,
        zoom: 9,
      });
    }
    // Our cargoes with our positions, market vessels with the vessels layer (as drawn).
    for (const cargo of situation?.cargoes ?? []) {
      if (!activeLayers.includes(cargo.own ? "cargoes" : "vessels")) continue;
      const at = cargo.position ?? cargo.origin ?? cargo.destination;
      if (at) {
        places.push({
          id: cargo.cargo_id,
          name: cargo.vessel_name,
          kind: t(cargo.own ? "map.situation.own_cargo" : "map.situation.market_cargo"),
          lon: at.lon,
          lat: at.lat,
          zoom: 7,
          cargoId: cargo.cargo_id,
        });
      }
    }
    return places;
  }, [activeLayers, facilities, filteredNodes, situation, t]);

  function flyToPlace(place: MapFinderPlace) {
    const map = mapRef.current;
    if (!map) return;
    const at = toMapCoordinates(place.lon, place.lat);
    const cargo = place.cargoId ? situationRef.current?.cargoes.find((item) => item.cargo_id === place.cargoId) : undefined;
    if (!frameCargo(map, cargo, toMapCoordinates)) focusOn(map, at, place.zoom);
    // A short-lived pin marks the spot the map flew to.
    const element = document.createElement("div");
    element.className = "map-finder-pin";
    element.setAttribute("aria-hidden", "true");
    const pin = new Marker({ element }).setLngLat(at).addTo(map);
    window.setTimeout(() => pin.remove(), 4000);
    // A vessel opens its card (name, status, voyage, ETA, cargo, and its terminal's send-out).
    if (place.cargoId) setSelection({ kind: "cargo", id: place.cargoId });
  }

  function project(lon: number, lat: number): [number, number] {
    const x = ((lon + 12) / 47) * 1000;
    const y = ((63 - lat) / 29) * 620;
    return [Math.max(0, Math.min(1000, x)), Math.max(0, Math.min(620, y))];
  }

  return (
    <div
      className="gas-map"
      aria-label={t("map.gas_network_map")}
      // Read by scripts/uat/map_sync_measure.mjs: when the map drew, and the situation it shows.
      data-map-ready={mapReady ? "true" : undefined}
      data-map-situation-as-of={situation?.as_of_utc ?? undefined}
    >
      <div ref={containerRef} className="maplibre-canvas" />
      {mapReady && !compact && (
        <MapFinder places={finderPlaces} onPick={flyToPlace} t={t} collapsible={phoneWidth} />
      )}
      {/* Not at phone width: the network sheet covers the map's foot there, so the scene
          controls would sit under it, drawn but out of reach (browser acceptance, 390 px). */}
      {mapReady && !compact && !phoneWidth && (
        <MapSceneControls
          t={t as (key: string, options?: Record<string, unknown>) => string}
          activeLayers={activeLayers}
          onFitPositions={
            situation && (situation.contracts.length > 0 || situation.regas_slots.length > 0 || situation.cargoes.some((item) => item.own))
              ? fitOurPositions
              : undefined
          }
          keyExtra={keyExtra}
        />
      )}
      {/* Under the finder, one column of what the map says about itself: the offline notice and
          the intensity legend. Nothing in the bottom band, which is the attribution's. */}
      {(showingOfflineOutline || (mapReady && intensity && intensityData)) && !mapStartError && (
        <div className="map-top-left-stack">
          {showingOfflineOutline && (
            // OpenStreetMap could not be reached (offline, a proxy): the coastline outline stands in.
            <p className="map-basemap-state is-fallback" role="status">
              <strong>{t("map.basemap.offline")}</strong>
            </p>
          )}
          {mapReady && intensity && intensityData && (() => {
            // The metric's legend: what size and colour mean, the largest figure and its unit, the
            // scale, the gas day; or that the metric holds nothing for the day.
            const data = intensity === "flow" ? intensityData.borders : intensityData.points;
            const days = [...new Set(data.map((item) => item.gasDay).filter(Boolean))].sort();
            const swatch = (colour: string, label: string) => (
              <span className="map-intensity-swatch"><i style={{ background: colour }} aria-hidden="true" />{label}</span>
            );
            return (
              <div className="map-intensity-legend" role="note" aria-label={t("map.intensity.legend")}>
                <strong>{t(`map.intensity.metric.${intensity}`)}</strong>
                {data.length === 0 ? (
                  <span>{t("map.intensity.no_data")}</span>
                ) : (
                  <>
                    <span>
                      {t(`map.intensity.size.${intensity}`, { max: Math.round(intensityMax).toLocaleString("en-GB") })}
                    </span>
                    <span className="map-intensity-swatches">
                      {intensity === "outage" && swatch(intensityPalette.outage, t("map.intensity.colour.outage"))}
                      {intensity === "utilisation" && intensityPalette.ramp.map((colour, index) => (
                        <span key={colour} className="map-intensity-swatch"><i style={{ background: colour }} aria-hidden="true" />{t(`map.intensity.band.${index}`)}</span>
                      ))}
                      {(intensity === "flow" || intensity === "storage") && (
                        <>
                          {swatch(intensityPalette.into, t(intensity === "storage" ? "map.intensity.colour.into_grid" : "map.intensity.colour.entry"))}
                          {swatch(intensityPalette.out, t(intensity === "storage" ? "map.intensity.colour.out_of_grid" : "map.intensity.colour.exit"))}
                        </>
                      )}
                    </span>
                    {days.length > 0 && <small>{t("map.intensity.gas_day", { day: days.length === 1 ? days[0] : `${days[0]} – ${days[days.length - 1]}` })}</small>}
                  </>
                )}
              </div>
            );
          })()}
        </div>
      )}
      {selection && detailCard && (
        <MapDetailPanel
          selection={selection}
          sites={sites}
          edges={edges}
          situation={situation}
          marketRows={marketRows}
          nodes={nodes}
          onClose={() => setSelection(null)}
          onInspect={onInspectNode}
          onSelect={setSelection}
          t={t as (key: string, options?: Record<string, unknown>) => string}
        />
      )}
      {mapStartError && (
        <p className="map-basemap-state is-unavailable" role="alert">
          <strong>{t("map.start_failed.title")}</strong>
          <small>{t("map.start_failed.body")}</small>
        </p>
      )}
      <svg className={mapReady ? "fallback-network-map map-ready" : "fallback-network-map"} viewBox="0 0 1000 620" role="presentation">
        <path
          className="fallback-landmass"
          d="M100 180 C150 120 235 100 320 120 C390 80 505 90 610 135 C750 135 865 210 900 330 C850 455 720 520 560 500 C440 570 300 540 220 465 C105 445 60 340 100 180 Z"
        />
        {[-5, 5, 15, 25].map((lon) => {
          const [x] = project(lon, 50);
          return <line key={`lon-${lon}`} className="fallback-grid" x1={x} x2={x} y1={30} y2={590} />;
        })}
        {[40, 45, 50, 55, 60].map((lat) => {
          const [, y] = project(5, lat);
          return <line key={`lat-${lat}`} className="fallback-grid" x1={35} x2={960} y1={y} y2={y} />;
        })}
        {visibleLines.map((line) => {
          const metadata = line.edge?.metadata_json ?? {};
          const capacity = Number(metadata.capacity_mwh_d ?? metadata.firm_capacity_mwh_d ?? 0);
          const flow = Number(metadata.live_physical_flow_mwh_d ?? 0);
          const utilization = Number(metadata.utilization_pct ?? (capacity > 0 ? flow / capacity : 0));
          const pressureClass = utilization >= 0.75 ? " hot" : utilization >= 0.5 ? " warm" : "";
          const indicativeClass = line.displayKind === "indicative_route" ? " route indicative-route" : " verified";
          return (
            <polyline
              key={line.id}
              className={`fallback-edge${indicativeClass}${pressureClass}`}
              points={line.geometryCoordinates.map(([lon, lat]) => project(lon, lat).join(",")).join(" ")}
              fill="none"
            />
          );
        })}
        {highlightedRoutePoints && routeSegmentsForHighlight.length > 0 && (() => {
          const pnlText = highlightedRoutePoints.pnlGbp === null
            ? ""
            : `GBP ${Math.round(highlightedRoutePoints.pnlGbp).toLocaleString()}`;
          const segmentPoints = routeSegmentsForHighlight.map((line) => {
            const projected = line.geometryCoordinates.map(([lon, lat]) => project(lon, lat));
            return { line, projected };
          });
          const labelSegment = segmentPoints[Math.floor(segmentPoints.length / 2)];
          const labelPoint = labelSegment.projected[Math.floor(labelSegment.projected.length / 2)];
          const labelX = labelPoint[0] + 12;
          const labelY = labelPoint[1] - 12;
          const highlightClass = highlightedRouteIsVerified
            ? "verified-highlight"
            : `indicative-highlight ${routeGeometryStateClass(highlightedRoutePoints.routeGeometryState)}`;
          return (
            <g className={`fallback-flow segmented ${highlightClass}`} aria-hidden="true">
              <desc>{geometryWarning}</desc>
              {segmentPoints.map(({ line, projected }) => (
                <g key={`highlighted-fallback-segment-${line.id}`}>
                  <polyline
                    className="fallback-flow-shadow"
                    points={projected.map(([x, y]) => `${x},${y}`).join(" ")}
                    fill="none"
                  />
                  <polyline
                    className="fallback-flow-segment"
                    points={projected.map(([x, y]) => `${x},${y}`).join(" ")}
                    fill="none"
                  />
                </g>
              ))}
              <text className="fallback-flow-label" x={labelX} y={labelY}>
                {highlightedRoutePoints.label}
              </text>
              {pnlText && (
                <text className="fallback-flow-value" x={labelX} y={labelY + 18}>
                  {pnlText}
                </text>
              )}
            </g>
          );
        })()}
        {filteredNodes.map((node, index) => {
          const [x, y] = project(node.lon, node.lat);
          const metadata = node.metadata_json ?? {};
          const label = fallbackNodeLabel(node);
          const coordinateQuality = propertyText(metadata.coordinate_quality, node.data_quality ?? "unknown");
          return (
            <g key={node.id} className={`fallback-node ${node.node_type} ${coordinateQuality === "display_approximation" ? "approximate" : "official"}`}>
              <circle cx={x} cy={y} r={node.node_type === "hub" ? 7 : node.node_type === "lng" ? 6 : 4.8} />
              {shouldShowFallbackNodeLabel(node, index) && (
                <text className="fallback-node-label priority" x={x + 9} y={y - 8}>{label}</text>
              )}
            </g>
          );
        })}
        {filteredNodes.length === 0 && (
          <text className="fallback-empty" x="500" y="310" textAnchor="middle">
            {t("map.loading_network_layers")}
          </text>
        )}
      </svg>
    </div>
  );
}
