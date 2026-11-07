import { useEffect, useMemo, useRef, useState } from "react";
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
import { EdgeDTO, FacilityDTO, MapSituationDTO, NodeDTO, RouteEligibilityDTO } from "@/api/client";
import {
  OVERVIEW_MAX_ZOOM,
  SITUATION_COLOURS,
  type ZoomTier,
  cargoFeatures,
  countrySummaries,
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
import {
  buildMapStyle,
  configuredMapTileProvider,
  mapTileProviderById,
  quietBasemapMinZoom,
  configuredMapTileToken,
  labelBudgetForZoom,
  mapTileBasemapState,
  mapZoomRange,
  transformCoordinate,
} from "@/app/mapTileProviders";
import type { RouteGeometryState } from "@/components/ResourcePoolPathOverlay";
import { FACILITY_ICON, drawFacilityIcon } from "@/app/mapIcons";
import { MapFinder, type MapFinderPlace } from "@/components/MapFinder";
import { MapDetailPanel } from "@/components/MapDetailPanel";
import { buildSites, siteOf, sitePipelines, siteSituation, type MapSelection, type Site } from "@/app/mapSelection";
import { useApiStore } from "@/stores/api";

// Let Vite resolve and bundle the module worker and its shared imports in both dev and build.
// MapLibre's default relative URL otherwise points inside Vite's optimized dependency cache.
setWorkerUrl(mapLibreWorkerUrl);

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
  /** Select and fly to a place or a cargo from outside the map (the book list); `nonce` re-fires it. */
  focus?: { refId?: string | null; cargoId?: string; nonce: number } | null;
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
    // Context routes dimmed; a route the book uses at full strength.
    "verified-pipeline-lines": ["case", ["==", ["get", "matters"], true], 0.95, ["==", ["get", "display_kind"], "network_link"], 0.16, 0.28],
    "indicative-route-lines": ["case", ["==", ["get", "matters"], true], 0.9, 0.24],
    "situation-facilities": 0.55,
  },
  book: {
    "nodes-circle": ["case", ["==", ["get", "node_type"], "hub"], 0.55, 0.22],
    "node-clusters": 0.2,
    "verified-pipeline-lines": ["case", ["==", ["get", "matters"], true], 0.95, 0.12],
    "indicative-route-lines": ["case", ["==", ["get", "matters"], true], 0.9, 0.12],
    "situation-facilities": 0.2,
  },
};

/** Context pipelines in the neutral edge colour, routes the book uses in the route colour. */
function routeLineColor(colors: { edge: string; route: string }): ExpressionSpecification {
  return ["case", ["==", ["get", "matters"], true], colors.route, colors.edge];
}

const SITUATION_HOVER_LAYERS = [
  "situation-outages",
  "situation-contracts",
  "situation-regas",
  "situation-cargo-positions",
  "situation-flows",
  "situation-facilities",
] as const;

/** Fly to a point (or jump, under reduced motion), never past the map's own zoom limit. */
function focusOn(map: MapLibreMap, center: [number, number], zoom: number): void {
  const target = { center, zoom: Math.min(zoom, map.getMaxZoom()) };
  if (prefersReducedMotion()) map.jumpTo(target);
  else map.flyTo({ ...target, speed: 1.4, curve: 1.42, essential: false });
}

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function"
    && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

type FeatureCollectionData = Parameters<GeoJSONSource["setData"]>[0];

function upsertSource(map: MapLibreMap, id: string, data: FeatureCollectionData): boolean {
  const source = map.getSource(id) as GeoJSONSource | undefined;
  if (source) {
    source.setData(data);
    return false;
  }
  map.addSource(id, { type: "geojson", data });
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

function fallbackNodeLabel(node: NodeDTO): string {
  const metadata = node.metadata_json ?? {};
  return String(metadata.market_code ?? node.name);
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
}: GasNetworkMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const labelMarkersRef = useRef<Marker[]>([]);
  const [mapReady, setMapReady] = useState(false);
  const [tier, setTier] = useState<ZoomTier>("overview");
  // The "control tower" selection: one object at a time, its card docked on the right, the
  // object and what it relates to highlighted and the rest dimmed.
  const [selection, setSelection] = useState<MapSelection | null>(null);
  const sites = useMemo(() => buildSites(nodes, facilities), [facilities, nodes]);
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
  const summaryMarkersRef = useRef<Marker[]>([]);
  const effectiveTheme = resolveEffectiveTheme(themeMode);
  // The deployment profile names the installation's default basemap; it can arrive after the
  // map first mounts, so the provider follows it. A vector basemap that cannot be reached (an
  // office proxy, an air-gapped network) falls back to the bundled outline and says so.
  const deploymentMapDefault = useApiStore((state) => state.runtimeRelease?.deployment?.map_default_provider ?? null);
  const [unreachableBasemap, setUnreachableBasemap] = useState<string | null>(null);
  const configuredProvider = useMemo(configuredMapTileProvider, [deploymentMapDefault]);
  const basemapFellBack = unreachableBasemap === configuredProvider.id;
  const mapTileProvider = basemapFellBack ? mapTileProviderById("outline")! : configuredProvider;
  const basemapState = useMemo(
    () => basemapFellBack ? "fallback" as const : mapTileBasemapState(mapTileProvider, configuredMapTileToken()),
    [basemapFellBack, mapTileProvider],
  );
  const toMapCoordinates = (lon: number, lat: number): [number, number] =>
    transformCoordinate(mapTileProvider.id, lon, lat);
  const mapColors = useMemo(
    () => effectiveTheme === "dark"
      ? {
          background: "#080808",
          edge: "#737373",
          route: "#50e3c2",
          // Generic points are neutral: blue on this map means the firm's own positions.
          node: "#94a3b8",
          hub: "#50e3c2",
          lng: "#b978ff",
          interconnection: "#f5a623",
          stroke: "#0a0a0a",
        }
      : {
          background: "#eeeeee",
          edge: "#6b7280",
          route: "#00b871",
          node: "#64748b",
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
    for (const contract of situation?.contracts ?? []) if (contract.location.ref_id) pointIds.add(contract.location.ref_id);
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
  }, [routesInUse, situation]);
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
  const indicativeRouteLines = useMemo(
    () => visibleLines.filter((line) =>
      line.displayKind === "indicative_route" && (showContextRoutes || matteringLineIds.has(line.id))),
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

  // A vector basemap has its own light and dark style, so the map is rebuilt when the theme
  // changes; a raster or outline basemap is recoloured in place (below).
  const basemapStyleKey = `${mapTileProvider.id}:${mapTileProvider.styleUrl ? effectiveTheme : "any"}`;
  const lastViewRef = useRef<{ center: [number, number]; zoom: number } | null>(null);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const mapTileToken = configuredMapTileToken();
    const view = lastViewRef.current;
    const map = new MapLibreMap({
      container: containerRef.current,
      // North-west Europe with the Norwegian shelf below the toolbar.
      center: view?.center ?? toMapCoordinates(6.5, 55.2),
      zoom: view?.zoom ?? 3.65,
      ...mapZoomRange(mapTileProvider.id),
      attributionControl: false,
      style: buildMapStyle(
        mapTileProvider.id,
        mapTileToken,
        {
          background: mapColors.background,
          rasterOpacity: effectiveTheme === "dark" ? 0.56 : 0.72,
          rasterSaturation: -1,
          rasterContrast: effectiveTheme === "dark" ? 0.2 : 0.28,
          rasterBrightnessMin: effectiveTheme === "dark" ? 0.12 : 0.2,
          rasterBrightnessMax: effectiveTheme === "dark" ? 0.76 : 0.96,
        },
        effectiveTheme === "dark" ? "dark" : "light",
      ),
    });

    // Zoom sits bottom-right: the top of the map belongs to the finder, the bar above to the
    // toolbar, so no two control groups can meet at any width.
    map.addControl(new NavigationControl({ visualizePitch: true }), "bottom-right");
    map.addControl(new AttributionControl({ compact: true }), "bottom-left");
    let loaded = false;
    map.on("load", () => {
      loaded = true;
      // At overview zoom the map is drawn as a globe, so the Norwegian shelf is not stretched
      // against the Mediterranean as on a flat Mercator map; MapLibre flattens it as the view
      // narrows to a region.
      map.setProjection({ type: "globe" });
      if (mapTileProvider.styleUrl) {
        for (const layer of map.getStyle().layers) {
          if (layer.type !== "symbol") continue;
          const from = quietBasemapMinZoom(layer.id, layer.minzoom);
          if (from !== null) map.setLayerZoomRange(layer.id, from, layer.maxzoom ?? 24);
          map.setPaintProperty(layer.id, "text-opacity", 0.72);
        }
      }
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
    const syncTier = () => setTier(zoomTier(map.getZoom()));
    syncTier();
    map.on("zoomend", syncTier);
    mapRef.current = map;
    return () => {
      clearTimeout(unreachable);
      const center = map.getCenter();
      lastViewRef.current = { center: [center.lng, center.lat], zoom: map.getZoom() };
      setMapReady(false);
      map.remove();
      mapRef.current = null;
    };
  }, [basemapStyleKey]);

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
      map.setPaintProperty("outline-land", "fill-color", effectiveTheme === "dark" ? "#18181b" : "#ffffff");
      map.setPaintProperty("outline-coast", "line-color", effectiveTheme === "dark" ? "#3f3f46" : "#d4d4d8");
    }
    for (const rasterLayerId of ["basemap-raster", "tianditu-vec-raster", "tianditu-label-raster"]) {
      if (!map.getLayer(rasterLayerId)) continue;
      map.setPaintProperty(rasterLayerId, "raster-opacity", effectiveTheme === "dark" ? 0.56 : 0.72);
      map.setPaintProperty(rasterLayerId, "raster-saturation", -1);
      map.setPaintProperty(rasterLayerId, "raster-contrast", effectiveTheme === "dark" ? 0.2 : 0.28);
      map.setPaintProperty(rasterLayerId, "raster-brightness-min", effectiveTheme === "dark" ? 0.12 : 0.2);
      map.setPaintProperty(rasterLayerId, "raster-brightness-max", effectiveTheme === "dark" ? 0.76 : 0.96);
    }
    if (!mapReady) return;

    if (map.getLayer("verified-pipeline-lines")) {
      map.setPaintProperty("verified-pipeline-lines", "line-color", routeLineColor(mapColors));
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
        "match",
        ["get", "node_type"],
        "hub",
        mapColors.hub,
        "lng",
        mapColors.lng,
        "interconnection",
        mapColors.interconnection,
        mapColors.node,
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
        },
        geometry: {
          type: "LineString" as const,
          coordinates: line.geometryCoordinates.map(([lon, lat]) => toMapCoordinates(lon, lat)),
        },
      };
    });
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
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": routeLineColor(mapColors),
          // Thin context lines: utilisation still widens a busy pipe, but nothing shouts. A
          // route the book uses is drawn wider in the route colour.
          "line-width": [
            "case",
            ["==", ["get", "matters"], true],
            3,
            ["==", ["get", "display_kind"], "network_link"],
            1,
            ["interpolate", ["linear"], ["get", "utilization_pct"], 0, 1.1, 0.65, 1.8, 0.9, 2.6],
          ],
          "line-opacity": ["case", ["==", ["get", "display_kind"], "network_link"], 0.7, 0.94],
        },
      });
    } else {
      (map.getSource("verified-pipeline-lines") as GeoJSONSource).setData({
        type: "FeatureCollection",
        features: verifiedEdgeFeatures,
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
          "circle-radius": ["step", ["get", "point_count"], 14, 25, 18, 100, 22],
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
        },
        paint: { "text-color": mapColors.stroke },
      });
      map.addLayer({
        id: "nodes-circle",
        type: "circle",
        source: "nodes",
        filter: ["!", ["has", "point_count"]],
        paint: {
          "circle-radius": ["case", ["==", ["get", "node_type"], "hub"], 6, 3.5],
          "circle-color": [
            "match",
            ["get", "node_type"],
            "hub",
            mapColors.hub,
            "lng",
            mapColors.lng,
            "interconnection",
            mapColors.interconnection,
            "entry_point",
            mapColors.interconnection,
            mapColors.node,
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
          map.easeTo({ center: coordinates, zoom });
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


  // Live situation layers. Added once, then fed with setData; visibility follows the
  // layer chips. Hover shows a compact card; nothing here opens a second detail pane.
  const situationRef = useRef<MapSituationDTO | null>(situation);
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
          "circle-radius": ["interpolate", ["linear"], ["sqrt", ["get", "gwh_d"]], 0, 3, 30, 16],
          "circle-color": palette.flow,
          "circle-opacity": 0.16,
          "circle-stroke-color": palette.flow,
          "circle-stroke-width": 1.2,
        },
      });
    }
    if (upsertSource(map, "situation-cargo-sailed", cargo?.sailed ?? empty)) {
      map.addLayer({
        id: "situation-cargo-sailed",
        type: "line",
        source: "situation-cargo-sailed",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": ["case", ["get", "own"], palette.own, palette.market],
          "line-width": ["case", ["get", "own"], 2, 1.2],
          "line-opacity": 0.55,
        },
      });
    }
    if (upsertSource(map, "situation-cargo-ahead", cargo?.ahead ?? empty)) {
      map.addLayer({
        id: "situation-cargo-ahead",
        type: "line",
        source: "situation-cargo-ahead",
        layout: { "line-cap": "butt" },
        paint: {
          "line-color": ["case", ["get", "own"], palette.own, palette.market],
          "line-width": ["case", ["get", "own"], 2, 1],
          "line-opacity": 0.8,
          "line-dasharray": [0, 4, 3],
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
    if (upsertSource(map, "situation-cargo-positions", cargo?.positions ?? empty)) {
      map.addLayer({
        id: "situation-cargo-positions",
        type: "circle",
        source: "situation-cargo-positions",
        paint: {
          "circle-radius": ["case", ["get", "own"], 6, 4],
          "circle-color": ["case", ["get", "own"], palette.own, palette.market],
          "circle-stroke-color": palette.halo,
          "circle-stroke-width": 1.5,
        },
      });
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
      // In the book view our own deals are the subject: drawn at every zoom, not folded
      // into country totals.
      const ownLayer = layerId.startsWith("situation-cargo") || layerId === "situation-regas" || layerId === "situation-contracts";
      if (map.getLayer(layerId)) map.setLayerZoomRange(layerId, view === "book" && ownLayer ? 0 : OVERVIEW_MAX_ZOOM, 24);
    }
    const show: Record<string, boolean> = {
      "situation-facilities": activeLayers.includes("infrastructure"),
      "situation-pipeline-flow": activeLayers.includes("flows"),
      "situation-flows": activeLayers.includes("flows"),
      "situation-cargo-sailed": activeLayers.includes("positions"),
      "situation-cargo-ahead": activeLayers.includes("positions"),
      "situation-regas": activeLayers.includes("positions"),
      "situation-contracts": activeLayers.includes("positions"),
      "situation-cargo-positions": activeLayers.includes("positions"),
      "situation-outage-halo": activeLayers.includes("outages"),
      "situation-outages": activeLayers.includes("outages"),
    };
    for (const [layerId, on] of Object.entries(show)) {
      if (map.getLayer(layerId)) map.setLayoutProperty(layerId, "visibility", visibility(on));
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
      ["situation-cargo-positions", "circle-color", ownOrMarket],
      ["situation-cargo-positions", "circle-stroke-color", palette.halo],
      ["situation-outage-halo", "circle-color", palette.outageActive],
      ["situation-outages", "circle-color", ["match", ["get", "status"], "active", palette.outageActive, palette.outageScheduled]],
      ["situation-outages", "circle-stroke-color", palette.halo],
    ];
    for (const [layerId, property, value] of paints) {
      if (map.getLayer(layerId)) map.setPaintProperty(layerId, property as never, value as never);
    }
  }, [activeLayers, effectiveTheme, facilities, mapReady, situation, t, verifiedPipelineLines, view]);

  // Selection: draw the selected object and what it relates to on top, dim everything else.
  const selectionMarkersRef = useRef<Marker[]>([]);
  const dimmedRef = useRef<Map<string, unknown>>(new Map());
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;
    const accent = SITUATION_COLOURS[effectiveTheme].own;
    type Coord = [number, number];
    const lines: Array<{ part: string; coords: Coord[] }> = [];
    const points: Array<{ part: string; at: Coord }> = [];
    const labels: Array<{ at: Coord; text: string }> = [];
    if (selection?.kind === "cargo" && situation) {
      const cargo = situation.cargoes.find((item) => item.cargo_id === selection.id);
      if (cargo) {
        const at = cargo.position ?? cargo.origin;
        const track: Coord[] = cargo.track.length > 1
          ? cargo.track.map(([lon, lat]) => [lon, lat] as Coord)
          : cargo.origin && cargo.position ? [[cargo.origin.lon, cargo.origin.lat], [cargo.position.lon, cargo.position.lat]] : [];
        if (track.length > 1) lines.push({ part: "sailed", coords: track });
        if (at && cargo.destination) lines.push({ part: "ahead", coords: [[at.lon, at.lat], [cargo.destination.lon, cargo.destination.lat]] });
        if (cargo.origin) {
          points.push({ part: "end", at: [cargo.origin.lon, cargo.origin.lat] });
          labels.push({ at: [cargo.origin.lon, cargo.origin.lat], text: cargo.load_port });
        }
        if (cargo.destination) {
          points.push({ part: "end", at: [cargo.destination.lon, cargo.destination.lat] });
          labels.push({ at: [cargo.destination.lon, cargo.destination.lat], text: `${cargo.destination_terminal ?? ""} · ETA ${(cargo.eta_utc ?? "").slice(5, 10)}` });
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
        if (situation) {
          for (const cargo of siteSituation(site, situation).inbound) {
            const at = cargo.position ?? cargo.origin;
            if (at) {
              lines.push({ part: "ahead", coords: [[at.lon, at.lat], [site.lon, site.lat]] });
              points.push({ part: "end", at: [at.lon, at.lat] });
              labels.push({ at: [at.lon, at.lat], text: `${cargo.vessel_name} · ETA ${(cargo.eta_utc ?? "").slice(5, 10)}` });
            }
          }
        }
        if (!sitePipelines(site, edges).length && !points.length) points.push({ part: "current", at: [site.lon, site.lat] });
      }
    } else if (selection?.kind === "hub") {
      const hub = nodes.find((node) => node.node_type === "hub" && node.name.toUpperCase() === selection.id);
      if (hub) points.push({ part: "current", at: [hub.lon, hub.lat] });
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
          "circle-radius": ["case", ["==", ["get", "part"], "current"], 11, 7],
          "circle-color": "rgba(0,0,0,0)",
          "circle-stroke-color": accent,
          "circle-stroke-width": ["case", ["==", ["get", "part"], "current"], 3, 2],
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
      ["indicative-route-lines", "line-opacity"],
      ["situation-facilities", "icon-opacity"],
      ["situation-flows", "circle-opacity"],
      ["situation-pipeline-flow", "line-opacity"],
      ["situation-cargo-sailed", "line-opacity"],
      ["situation-cargo-ahead", "line-opacity"],
      ["situation-regas", "circle-opacity"],
      ["situation-contracts", "circle-opacity"],
      ["situation-cargo-positions", "circle-opacity"],
      ["situation-outages", "circle-opacity"],
    ];
    const emphasis = VIEW_EMPHASIS[view];
    for (const [layerId, property] of dimmable) {
      if (!map.getLayer(layerId)) continue;
      const key = `${layerId}|${property}`;
      // The layer's own opacity, read once before this effect ever changes it.
      if (!dimmedRef.current.has(key)) dimmedRef.current.set(key, map.getPaintProperty(layerId, property as never) ?? 1);
      const base = emphasis[layerId] ?? dimmedRef.current.get(key);
      map.setPaintProperty(layerId, property as never, (selection || replay ? 0.25 : base) as never);
    }
    selectionMarkersRef.current.forEach((marker) => marker.remove());
    selectionMarkersRef.current = labels.map((label) => {
      const element = document.createElement("div");
      element.className = "map-node-label map-selection-label";
      element.textContent = label.text;
      return new Marker({ element, anchor: "left", offset: [12, 0] }).setLngLat(toMapCoordinates(label.at[0], label.at[1])).addTo(map);
    });
  }, [edges, effectiveTheme, facilities, mapReady, nodes, selection, situation, sites, verifiedPipelineLines, view, Boolean(replay)]);

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
    if (focus.cargoId) {
      const cargo = situationRef.current?.cargoes.find((item) => item.cargo_id === focus.cargoId);
      setSelection({ kind: "cargo", id: focus.cargoId });
      const at = cargo?.position ?? cargo?.origin ?? cargo?.destination;
      if (at) focusOn(map, toMapCoordinates(at.lon, at.lat), 5);
      return;
    }
    if (focus.refId) {
      const next = selectForRef.current(focus.refId);
      if (next) setSelection(next);
      const node = nodes.find((item) => item.id === focus.refId);
      const facility = facilities.find((item) => item.id === focus.refId);
      const place = node ?? facility;
      if (place && place.lon != null && place.lat != null) focusOn(map, toMapCoordinates(place.lon, place.lat), 7);
    }
    // Only a new request moves the map; data refreshes do not.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focus?.nonce, mapReady]);

  // Motion that carries meaning only: gas moving along flowing pipelines, the firm's laden
  // cargoes heading in, and a slow pulse on capacity that is out now. Off under
  // prefers-reduced-motion, where the same layers stay static.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || prefersReducedMotion()) return;
    const dashSteps: number[][] = [
      [0, 4, 3], [0.5, 4, 2.5], [1, 4, 2], [1.5, 4, 1.5], [2, 4, 1], [2.5, 4, 0.5], [3, 4, 0],
      [0, 0.5, 3, 3.5], [0, 1, 3, 3], [0, 1.5, 3, 2.5], [0, 2, 3, 2], [0, 2.5, 3, 1.5],
      [0, 3, 3, 1], [0, 3.5, 3, 0.5],
    ];
    let frame = 0;
    let step = -1;
    const tick = (time: number) => {
      const next = Math.floor(time / 70) % dashSteps.length;
      if (next !== step) {
        step = next;
        for (const layerId of ["situation-pipeline-flow", "situation-cargo-ahead"]) {
          if (map.getLayer(layerId)) map.setPaintProperty(layerId, "line-dasharray", dashSteps[step]);
        }
      }
      if (map.getLayer("situation-outage-halo")) {
        const phase = (Math.sin(time / 650) + 1) / 2;
        map.setPaintProperty("situation-outage-halo", "circle-opacity", 0.06 + phase * 0.16);
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [mapReady]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;

    const clearLabels = () => {
      labelMarkersRef.current.forEach((marker) => marker.remove());
      labelMarkersRef.current = [];
    };
    const renderLabels = () => {
      clearLabels();
      const occupied: Array<{ x: number; y: number }> = [];
      const budget = labelBudgetForZoom(map.getZoom());
      const bounds = map.getBounds();
      let shown = 0;
      // Detail tier: each situation asset carries its key numbers, ahead of plain names.
      const current = situationRef.current;
      if (current && zoomTier(map.getZoom()) === "detail") {
        const candidates: Array<{ kind: string; id: string; lon: number; lat: number }> = [
          ...current.outages.map((item) => ({ kind: "outage", id: item.event_id, ...item.location })),
          ...current.regas_slots.map((item) => ({ kind: "regas", id: item.terminal_name, ...item.location })),
          ...current.cargoes
            .filter((item) => item.position ?? item.origin)
            .map((item) => ({ kind: "cargo", id: item.cargo_id, ...(item.position ?? item.origin)! })),
          ...current.contracts.map((item) => ({ kind: "contract", id: item.contract_id, ...item.location })),
        ];
        const seen = new Set<string>();
        for (const item of candidates) {
          const key = `${item.kind}:${item.id}`;
          if (seen.has(key) || shown >= budget) continue;
          seen.add(key);
          const at = toMapCoordinates(item.lon, item.lat);
          if (!bounds.contains(at)) continue;
          const text = detailLabel(item.kind, item.id, current);
          if (!text) continue;
          const projected = map.project(at);
          // Assets at one place (an outage and a contract at the same terminal) stack
          // their labels instead of hiding each other.
          let dy = 0;
          while (occupied.some((point) => Math.abs(point.x - projected.x) < 150 && Math.abs(point.y - (projected.y + dy)) < 22) && dy < 88) {
            dy += 22;
          }
          if (dy >= 88) continue;
          occupied.push({ x: projected.x, y: projected.y + dy });
          shown += 1;
          const element = document.createElement("div");
          element.className = `map-node-label map-detail-label is-${item.kind}`;
          element.textContent = text;
          labelMarkersRef.current.push(
            new Marker({ element, anchor: "left", offset: [12, dy] }).setLngLat(at).addTo(map),
          );
        }
      }
      priorityLabelNodes.forEach((node) => {
        if (shown >= budget || !bounds.contains(toMapCoordinates(node.lon, node.lat))) return;
        const projected = map.project(toMapCoordinates(node.lon, node.lat));
        const isHighlighted = Boolean(
          highlightedRoutePoints &&
          [highlightedRoutePoints.from.id, highlightedRoutePoints.to.id].includes(node.id),
        );
        const collides = occupied.some(
          (point) => Math.abs(point.x - projected.x) < 76 && Math.abs(point.y - projected.y) < 24,
        );
        if (collides && !isHighlighted) return;
        occupied.push({ x: projected.x, y: projected.y });
        shown += 1;
        const element = document.createElement("div");
        element.className = `map-node-label map-node-label-${node.node_type}${isHighlighted ? " highlighted" : ""}`;
        element.textContent = fallbackNodeLabel(node);
        element.title = node.name;
        labelMarkersRef.current.push(
          new Marker({ element, anchor: "left", offset: [9, -7] })
            .setLngLat(toMapCoordinates(node.lon, node.lat))
            .addTo(map),
        );
      });
      // Close in, infrastructure gets names too, quieter than network points.
      if (map.getZoom() >= 7 && activeLayers.includes("infrastructure")) {
        for (const facility of facilities) {
          if (shown >= budget) break;
          const at = toMapCoordinates(facility.lon, facility.lat);
          if (!bounds.contains(at) || !FACILITY_ICON[facility.facility_type]) continue;
          const projected = map.project(at);
          if (occupied.some((point) => Math.abs(point.x - projected.x) < 76 && Math.abs(point.y - projected.y) < 24)) continue;
          occupied.push({ x: projected.x, y: projected.y });
          shown += 1;
          const element = document.createElement("div");
          element.className = "map-node-label map-facility-label";
          element.textContent = facility.name;
          labelMarkersRef.current.push(
            new Marker({ element, anchor: "left", offset: [10, 0] }).setLngLat(at).addTo(map),
          );
        }
      }
    };

    renderLabels();
    map.on("moveend", renderLabels);
    return () => {
      map.off("moveend", renderLabels);
      clearLabels();
    };
  }, [activeLayers, facilities, highlightedRoutePoints, mapReady, priorityLabelNodes, situation]);

  // Overview tier: one compact pill per country with the portfolio's headline there; the
  // full breakdown is in its tooltip. Pills that would overlap are pushed apart, and
  // clicking one zooms into that country, where the individual assets take over.
  useEffect(() => {
    const map = mapRef.current;
    const clear = () => {
      summaryMarkersRef.current.forEach((marker) => marker.remove());
      summaryMarkersRef.current = [];
    };
    clear();
    // Country totals summarise the market; the book view draws its deals themselves.
    if (!map || !mapReady || tier !== "overview" || view === "book") return;
    const showPositions = activeLayers.includes("positions");
    const showOutages = activeLayers.includes("outages");
    const compact = (value: number) =>
      value >= 1000 ? `${(value / 1000).toLocaleString(undefined, { maximumFractionDigits: 1 })}k` : `${Math.round(value)}`;
    const rows = countrySummaries(situation)
      .map((row) => {
        const headline: string[] = [];
        const details: string[] = [];
        if (showPositions && row.contracts) {
          headline.push(`${compact(row.contractedMwhD)} MWh/d`);
          details.push(`${row.contractedMwhD.toLocaleString()} MWh/d ${t("map.overview.contracted")} (${row.contracts})`);
        }
        if (showPositions && row.cargoesInbound) {
          headline.push(`${row.cargoesInbound} ⛴`);
          details.push(`${row.cargoesInbound} ${t("map.overview.cargoes_inbound")}${row.inboundGwh ? ` · ${Math.round(row.inboundGwh).toLocaleString()} GWh` : ""}`);
        }
        if (showPositions && row.slots) details.push(`${row.slots} ${t("map.overview.slots")}`);
        const alert = showOutages && row.outagesNow > 0;
        if (alert) {
          details.push(`${row.outagesNow} ${t("map.overview.outages_now")}${row.unavailableGwhD ? ` · −${Math.round(row.unavailableGwhD).toLocaleString()} GWh/d` : ""}`);
        }
        if (showOutages && row.outagesScheduled) details.push(`${row.outagesScheduled} ${t("map.overview.outages_scheduled")}`);
        return { row, headline, details, alert };
      })
      .filter((item) => item.details.length > 0);

    const place = () => {
      clear();
      const taken: Array<{ x: number; y: number }> = [];
      for (const { row, headline, details, alert } of rows) {
        const at = toMapCoordinates(row.lon, row.lat);
        const base = map.project(at);
        let dy = 0;
        // Simple label placement: step down until the pill clears the ones placed.
        while (taken.some((box) => Math.abs(box.x - base.x) < 150 && Math.abs(box.y - (base.y + dy)) < 26) && dy < 260) {
          dy += 28;
        }
        taken.push({ x: base.x, y: base.y + dy });
        const element = document.createElement("button");
        element.type = "button";
        element.className = `map-summary-card${alert ? " has-alert" : ""}`;
        element.title = details.join("\n");
        element.setAttribute("aria-label", `${row.country}: ${details.join("; ")}. ${t("map.overview.zoom_in")}`);
        element.innerHTML = `<strong>${escapeHtml(row.country)}</strong><span>${escapeHtml(headline.join(" · ") || details[0])}</span>${alert ? `<b class="is-alert">${row.outagesNow} ${escapeHtml(t("map.overview.outages_now"))}</b>` : ""}`;
        element.addEventListener("click", () => focusOn(map, at, 6));
        summaryMarkersRef.current.push(
          new Marker({ element, anchor: "bottom", offset: [0, dy - 6] }).setLngLat(at).addTo(map),
        );
      }
    };
    place();
    map.on("moveend", place);
    return () => {
      map.off("moveend", place);
      clear();
    };
  }, [activeLayers, mapReady, situation, t, tier, view]);

  /** Frame everything the firm holds: contracts, own cargoes and held slots. */
  function fitOurPositions() {
    const map = mapRef.current;
    if (!map || !situation) return;
    // The book list covers the left of the map in the book view.
    const padding = view === "book" ? { top: 90, bottom: 90, left: 340, right: 80 } : 80;
    const points: Array<[number, number]> = [
      ...situation.contracts.map((item) => [item.location.lon, item.location.lat] as [number, number]),
      ...situation.regas_slots.map((item) => [item.location.lon, item.location.lat] as [number, number]),
      ...situation.cargoes.filter((item) => item.own).flatMap((item) =>
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

  // Switching to the book frames the book; once per switch, not on every refresh.
  const framedBookRef = useRef(false);
  useEffect(() => {
    if (view !== "book") {
      framedBookRef.current = false;
      return;
    }
    if (!mapReady || !situation || framedBookRef.current) return;
    framedBookRef.current = true;
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
    for (const cargo of activeLayers.includes("positions") ? situation?.cargoes ?? [] : []) {
      const at = cargo.position ?? cargo.origin ?? cargo.destination;
      if (at) {
        places.push({
          id: cargo.cargo_id,
          name: cargo.vessel_name,
          kind: t(cargo.own ? "map.situation.own_cargo" : "map.situation.market_cargo"),
          lon: at.lon,
          lat: at.lat,
          zoom: 7,
        });
      }
    }
    return places;
  }, [activeLayers, facilities, filteredNodes, situation, t]);

  function flyToPlace(place: MapFinderPlace) {
    const map = mapRef.current;
    if (!map) return;
    const at = toMapCoordinates(place.lon, place.lat);
    focusOn(map, at, place.zoom);
    // A short-lived pin marks the spot the map flew to.
    const element = document.createElement("div");
    element.className = "map-finder-pin";
    element.setAttribute("aria-hidden", "true");
    const pin = new Marker({ element }).setLngLat(at).addTo(map);
    window.setTimeout(() => pin.remove(), 4000);
  }

  function project(lon: number, lat: number): [number, number] {
    const x = ((lon + 12) / 47) * 1000;
    const y = ((63 - lat) / 29) * 620;
    return [Math.max(0, Math.min(1000, x)), Math.max(0, Math.min(620, y))];
  }

  return (
    <div className="gas-map" aria-label={t("map.gas_network_map")}>
      <div ref={containerRef} className="maplibre-canvas" />
      {mapReady && !compact && <MapFinder places={finderPlaces} onPick={flyToPlace} t={t} />}
      {selection && (
        <MapDetailPanel
          selection={selection}
          sites={sites}
          edges={edges}
          situation={situation}
          marketRows={marketRows}
          nodes={nodes}
          onClose={() => setSelection(null)}
          onInspect={onInspectNode}
          t={t as (key: string, options?: Record<string, unknown>) => string}
        />
      )}
      {mapReady && !selection && !compact && (
        <div className="map-zoom-tier" role="status" aria-live="polite">
          {view === "network" && (
            <>
              <span className={`map-zoom-tier-name is-${tier}`}>{t(`map.tier.${tier}`)}</span>
              <small>{t(`map.tier.${tier}_hint`)}</small>
            </>
          )}
          {situation && (situation.contracts.length > 0 || situation.regas_slots.length > 0 || situation.cargoes.some((item) => item.own)) && (
            <button type="button" className="chip" onClick={fitOurPositions}>{t("map.tier.fit_positions")}</button>
          )}
        </div>
      )}
      {/*
        Owner decision D4 (amended 2026-11-05): a global installation defaults to OpenFreeMap, an
        open basemap licensed for commercial use; China installations to the bundled outline. The
        map says which state it is in when it draws no imagery: "no basemap" is the deployment's
        choice, "cannot be drawn" a configuration fault, and "fallback" a basemap the network
        could not reach, replaced by the outline. A blank map would look like a data failure.
      */}
      {basemapState !== "configured" && (
        <p className={`map-basemap-state is-${basemapState}`} role="status">
          <strong>
            {t(
              basemapState === "no-basemap"
                ? "map.basemap.none"
                : basemapState === "fallback" ? "map.basemap.fallback" : "map.basemap.unavailable",
              { provider: configuredProvider.label },
            )}
          </strong>
          <small>
            {t(
              basemapState === "no-basemap"
                ? "map.basemap.none_detail"
                : basemapState === "fallback" ? "map.basemap.fallback_detail" : "map.basemap.unavailable_detail",
            )}
          </small>
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
