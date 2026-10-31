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
import mapLibreWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import "maplibre-gl/dist/maplibre-gl.css";
import { EdgeDTO, FacilityDTO, MapSituationDTO, NodeDTO, RouteEligibilityDTO } from "@/api/client";
import {
  SITUATION_COLOURS,
  cargoFeatures,
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
import {
  buildMapStyle,
  configuredMapTileProvider,
  configuredMapTileToken,
  labelBudgetForZoom,
  mapTileBasemapState,
  mapZoomRange,
  transformCoordinate,
} from "@/app/mapTileProviders";
import type { RouteGeometryState } from "@/components/ResourcePoolPathOverlay";
import { FACILITY_ICON, drawFacilityIcon } from "@/app/mapIcons";
import { MapFinder, type MapFinderPlace } from "@/components/MapFinder";

// Let Vite resolve and bundle the module worker and its shared imports in both dev and build.
// MapLibre's default relative URL otherwise points inside Vite's optimized dependency cache.
setWorkerUrl(mapLibreWorkerUrl);

type Translate = (key: string) => string;

interface GasNetworkMapProps {
  nodes: NodeDTO[];
  edges: EdgeDTO[];
  routes: RouteEligibilityDTO[];
  themeMode: "light" | "dark" | "system";
  activeLayers: string[];
  searchTerm: string;
  t: Translate;
  highlightedRoute?: NetworkHighlightedRoute;
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
  onInspectNode,
  situation = null,
  facilities = [],
}: GasNetworkMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const labelMarkersRef = useRef<Marker[]>([]);
  const [mapReady, setMapReady] = useState(false);
  const effectiveTheme = resolveEffectiveTheme(themeMode);
  const mapTileProvider = useMemo(configuredMapTileProvider, []);
  const basemapState = useMemo(
    () => mapTileBasemapState(mapTileProvider, configuredMapTileToken()),
    [mapTileProvider],
  );
  const toMapCoordinates = (lon: number, lat: number): [number, number] =>
    transformCoordinate(mapTileProvider.id, lon, lat);
  const mapColors = useMemo(
    () => effectiveTheme === "dark"
      ? {
          background: "#080808",
          edge: "#737373",
          route: "#50e3c2",
          node: "#3291ff",
          hub: "#50e3c2",
          lng: "#b978ff",
          interconnection: "#f5a623",
          stroke: "#0a0a0a",
        }
      : {
          background: "#eeeeee",
          edge: "#6b7280",
          route: "#00b871",
          node: "#007cf0",
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
  const verifiedPipelineLines = useMemo(
    () => visibleLines.filter((line) => line.displayKind === "verified_pipeline"),
    [visibleLines],
  );
  const indicativeRouteLines = useMemo(
    () => visibleLines.filter((line) => line.displayKind === "indicative_route"),
    [visibleLines],
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

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const mapTileProvider = configuredMapTileProvider();
    const mapTileToken = configuredMapTileToken();
    const map = new MapLibreMap({
      container: containerRef.current,
      center: toMapCoordinates(7.8, 51.2),
      zoom: 4.0,
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

    map.addControl(new NavigationControl({ visualizePitch: true }), "top-right");
    map.addControl(new AttributionControl({ compact: true }), "bottom-left");
    map.on("load", () => setMapReady(true));
    mapRef.current = map;
    return () => {
      setMapReady(false);
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (!map.isStyleLoaded()) return;

    if (map.getLayer("background")) {
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
      map.setPaintProperty("verified-pipeline-lines", "line-color", mapColors.edge);
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
    if (!map || !mapReady || !map.isStyleLoaded()) return;

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
          display_kind: "verified_pipeline",
          geometry_basis: "verified_geometry",
          geometry_verification: "verified",
          is_schematic_corridor: false,
          operator: String(metadata.operator ?? ""),
          capacity_mwh_d: capacity,
          live_flow_mwh_d: flow,
          utilization_pct: utilization,
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
          "line-color": mapColors.edge,
          "line-width": ["interpolate", ["linear"], ["get", "utilization_pct"], 0, 1.4, 0.65, 2.6, 0.9, 3.6],
          "line-opacity": 0.94,
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
          "circle-radius": ["case", ["==", ["get", "node_type"], "hub"], 7, 5],
          "circle-color": [
            "match",
            ["get", "node_type"],
            "hub",
            mapColors.hub,
            "lng",
            mapColors.lng,
            "interconnection",
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
        const coordinateQuality = propertyText(props.coordinate_quality, t("data.unavailable"));
        const source = propertyText(props.source_system, t("data.unavailable"));
        const nodeId = propertyText(props.id, "");
        const nodeLabel = propertyText(props.name, nodeId);
        const pointAt = (feature.geometry as { coordinates?: [number, number] }).coordinates;
        if (pointAt) focusOn(map, pointAt, Math.max(map.getZoom(), 7));
        const popup = new Popup({ closeButton: false })
          .setLngLat(event.lngLat)
          .setHTML(
            `<div class="node-popup">
              <strong>${escapeHtml(props.name)}</strong>
              <span>${escapeHtml(props.node_type)} / ${escapeHtml(props.country)}</span>
              <small>${escapeHtml(t("map.node_popup_source"))} ${escapeHtml(source)}</small>
              <small>${escapeHtml(t("map.node_popup_coordinate_quality"))} ${escapeHtml(coordinateQuality)}</small>
              ${coordinateQuality === "display_approximation"
                ? `<em>${escapeHtml(t("map.node_popup_approximate_coordinate"))}</em>`
                : ""}
            </div>`
          )
          .addTo(map);
        // Wave 9: the popup stays the map's quick context, and the canonical Inspector
        // carries the object's detail. The map hands the node over rather than growing a
        // second detail pane of its own.
        if (onInspectNode && nodeId) {
          const container = popup.getElement()?.querySelector(".node-popup");
          if (container) {
            const inspect = document.createElement("button");
            inspect.type = "button";
            inspect.className = "node-popup-inspect";
            inspect.textContent = t("map.inspect_node");
            inspect.addEventListener("click", () => {
              onInspectNode(nodeId, nodeLabel);
              popup.remove();
            });
            container.appendChild(inspect);
          }
        }
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
        // Click focuses: the map flies to the item and pins its card until closed.
        map.on("click", layerId, (event) => {
          const feature = event.features?.[0];
          if (!feature) return;
          const html = cardFor(layerId, feature.properties ?? {});
          if (!html) return;
          const coordinates = (feature.geometry as { coordinates?: [number, number] }).coordinates;
          const target = Array.isArray(coordinates) && typeof coordinates[0] === "number"
            ? coordinates
            : [event.lngLat.lng, event.lngLat.lat] as [number, number];
          hover.remove();
          focusOn(map, target, Math.max(map.getZoom(), layerId === "situation-facilities" ? 11 : 8));
          new Popup({ closeButton: true, closeOnClick: true, offset: 12, maxWidth: "320px", className: "is-pinned" })
            .setLngLat(target)
            .setHTML(html)
            .addTo(map);
        });
      }
    }

    const visibility = (on: boolean) => (on ? "visible" : "none");
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
  }, [activeLayers, effectiveTheme, facilities, mapReady, situation, t, verifiedPipelineLines]);

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
  }, [activeLayers, facilities, highlightedRoutePoints, mapReady, priorityLabelNodes]);

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
      zoom: node.node_type === "hub" ? 6 : 9,
    }));
    for (const facility of activeLayers.includes("infrastructure") ? facilities : []) {
      places.push({
        id: facility.id,
        name: facility.name,
        kind: t(`map.situation.facility_${facility.facility_type}`),
        lon: facility.lon,
        lat: facility.lat,
        zoom: 12,
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
      {mapReady && <MapFinder places={finderPlaces} onPick={flyToPlace} t={t} />}
      {/*
        Owner decision D4: no third-party basemap is a default, so the map has to say which of the
        two honest states it is in. "No basemap configured" is a choice the deployment made and the
        geometry is unaffected; "the configured basemap cannot be drawn" is a deployment fault the
        operator has to see. Rendering neither would leave a blank map looking like a data failure.
      */}
      {basemapState !== "configured" && (
        <p className={`map-basemap-state is-${basemapState}`} role="status">
          <strong>
            {t(
              basemapState === "no-basemap"
                ? "map.basemap.none"
                : "map.basemap.unavailable",
            )}
          </strong>
          <small>
            {t(
              basemapState === "no-basemap"
                ? "map.basemap.none_detail"
                : "map.basemap.unavailable_detail",
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
