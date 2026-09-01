import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl, { GeoJSONSource, Map as MapLibreMap, Marker } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { EdgeDTO, NodeDTO, RouteEligibilityDTO } from "@/api/client";
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
  transformCoordinate,
} from "@/app/mapTileProviders";
import type { RouteGeometryState } from "@/components/ResourcePoolPathOverlay";

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
}: GasNetworkMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const labelMarkersRef = useRef<Marker[]>([]);
  const [mapReady, setMapReady] = useState(false);
  const effectiveTheme = resolveEffectiveTheme(themeMode);
  const mapTileProvider = useMemo(configuredMapTileProvider, []);
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
        priorityIds.has(node.id) ||
        priorityNodes.length >= MAX_MAP_LABELS
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
    return priorityNodes;
  }, [filteredNodes, highlightedRoutePoints, normalizedSearchTerm]);

  const fallbackLabelPriorityIds = useMemo(
    () => new Set(priorityLabelNodes.map((node) => node.id)),
    [priorityLabelNodes],
  );

  function shouldShowFallbackNodeLabel(node: NodeDTO, index: number): boolean {
    return index >= 0 && fallbackLabelPriorityIds.has(node.id);
  }

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const mapTileProvider = configuredMapTileProvider();
    const mapTileToken = configuredMapTileToken();
    const map = new maplibregl.Map({
      container: containerRef.current,
      center: toMapCoordinates(7.8, 51.2),
      zoom: 4.0,
      minZoom: 3,
      maxZoom: 9,
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
      ),
    });

    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
    map.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-left");
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
        new maplibregl.Popup({ closeButton: false })
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
  }, [filteredNodes, highlightedRouteSegmentFeatures, indicativeRouteLines, mapColors, mapReady, t, verifiedPipelineLines]);

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
      priorityLabelNodes.forEach((node) => {
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
        const element = document.createElement("div");
        element.className = `map-node-label map-node-label-${node.node_type}${isHighlighted ? " highlighted" : ""}`;
        element.textContent = fallbackNodeLabel(node);
        element.title = node.name;
        labelMarkersRef.current.push(
          new maplibregl.Marker({ element, anchor: "left", offset: [9, -7] })
            .setLngLat(toMapCoordinates(node.lon, node.lat))
            .addTo(map),
        );
      });
    };

    renderLabels();
    map.on("moveend", renderLabels);
    return () => {
      map.off("moveend", renderLabels);
      clearLabels();
    };
  }, [highlightedRoutePoints, mapReady, priorityLabelNodes]);

  function project(lon: number, lat: number): [number, number] {
    const x = ((lon + 12) / 47) * 1000;
    const y = ((63 - lat) / 29) * 620;
    return [Math.max(0, Math.min(1000, x)), Math.max(0, Math.min(620, y))];
  }

  return (
    <div className="gas-map" aria-label={t("map.gas_network_map")}>
      <div ref={containerRef} className="maplibre-canvas" />
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
