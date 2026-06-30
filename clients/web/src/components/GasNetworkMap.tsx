import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl, { GeoJSONSource, Map as MapLibreMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { EdgeDTO, NodeDTO, RouteEligibilityDTO } from "@/api/client";

interface GasNetworkMapProps {
  nodes: NodeDTO[];
  edges: EdgeDTO[];
  routes: RouteEligibilityDTO[];
  themeMode: "light" | "dark" | "system";
  activeLayers: string[];
  searchTerm: string;
  highlightedRoute?: {
    fromNodeId: string;
    toNodeId: string;
    routeId: string;
    label: string;
    pnlGbp: number | null;
    routeGeometryState: "source_derived_leg_sequence" | "source_derived_corridor" | "directLineFallback";
    routeLegSummary: string[];
  };
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

function metadataNumber(metadata: Record<string, unknown> | null | undefined, key: string, fallback = 0): number {
  const value = metadata?.[key];
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return fallback;
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

const MAX_FALLBACK_LABELS = 28;

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
  routes,
  themeMode,
  activeLayers,
  searchTerm,
  highlightedRoute,
}: GasNetworkMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const [mapReady, setMapReady] = useState(false);
  const effectiveTheme = resolveEffectiveTheme(themeMode);
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
  const filteredNodes = useMemo(() => {
    const term = searchTerm.trim().toLowerCase();
    return nodes.filter((node) => {
      const layerMatch =
        (activeLayers.includes("hubs") && node.node_type === "hub") ||
        (activeLayers.includes("lng") && node.node_type === "lng") ||
        (activeLayers.includes("ips") && node.node_type === "interconnection") ||
        (activeLayers.includes("network") && !["hub", "lng", "interconnection"].includes(node.node_type));
      const searchMatch = !term ||
        node.name.toLowerCase().includes(term) ||
        node.country.toLowerCase().includes(term) ||
        node.node_type.toLowerCase().includes(term);
      return layerMatch && searchMatch;
    });
  }, [activeLayers, nodes, searchTerm]);
  const nodeLookup = useMemo(() => new globalThis.Map(nodes.map((node) => [node.id, node])), [nodes]);
  const visibleEdges = useMemo(() => {
    const visibleNodeIds = new Set(filteredNodes.map((node) => node.id));
    return edges
      .map((edge) => {
        const from = nodeLookup.get(edge.from_node_id);
        const to = nodeLookup.get(edge.to_node_id);
        if (!from || !to) return null;
        if (!visibleNodeIds.has(from.id) && !visibleNodeIds.has(to.id)) return null;
        return { ...edge, from, to };
      })
      .filter((edge): edge is NonNullable<typeof edge> => edge !== null);
  }, [edges, filteredNodes, nodeLookup]);
  const routeIds = useMemo(
    () => new Set(routes.map((route) => `${route.from_node_id}:${route.to_node_id}`)),
    [routes],
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
    return visibleEdges
      .filter((edge) => {
        const metadata = edge.metadata_json ?? {};
        return (
          edge.source_record_id === highlightedRoutePoints.routeId ||
          metadataString(metadata, "route_id") === highlightedRoutePoints.routeId
        );
      })
      .sort(
        (left, right) =>
          metadataNumber(left.metadata_json, "route_leg_sequence") -
          metadataNumber(right.metadata_json, "route_leg_sequence"),
      );
  }, [highlightedRoutePoints?.routeId, visibleEdges]);
  const directLineFallback = Boolean(highlightedRoutePoints && routeSegmentsForHighlight.length === 0);
  const geometryWarning = directLineFallback
    ? "Route geometry unavailable; showing direct source-derived corridor, not surveyed pipeline geometry."
    : highlightedRoutePoints?.routeGeometryState === "source_derived_leg_sequence"
      ? "Using source_derived_leg_sequence route geometry from leg-level route-candidate edges."
      : "Using source-derived route geometry.";
  const highlightedRouteSegmentFeatures = useMemo(
    () =>
      routeSegmentsForHighlight.map((edge) => {
        const metadata = edge.metadata_json ?? {};
        return {
          type: "Feature" as const,
          properties: {
            id: edge.id,
            route_id: metadataString(metadata, "route_id", highlightedRoutePoints?.routeId ?? ""),
            route_leg_sequence: metadataNumber(metadata, "route_leg_sequence"),
            route_geometry_state: metadataString(
              metadata,
              "route_geometry_state",
              highlightedRoutePoints?.routeGeometryState ?? "source_derived_leg_sequence",
            ),
          },
          geometry: {
            type: "LineString" as const,
            coordinates: [
              [edge.from.lon, edge.from.lat],
              [edge.to.lon, edge.to.lat],
            ],
          },
        };
      }),
    [highlightedRoutePoints?.routeGeometryState, highlightedRoutePoints?.routeId, routeSegmentsForHighlight],
  );
  const normalizedSearchTerm = searchTerm.trim().toLowerCase();
  const fallbackLabelPriorityIds = useMemo(() => {
    const priorityIds = new Set<string>();
    if (highlightedRoutePoints) {
      priorityIds.add(highlightedRoutePoints.from.id);
      priorityIds.add(highlightedRoutePoints.to.id);
    }

    const addWithinBudget = (node: NodeDTO) => {
      if (priorityIds.has(node.id) || priorityIds.size >= MAX_FALLBACK_LABELS) return;
      priorityIds.add(node.id);
    };

    filteredNodes
      .filter((node) => isSearchLabelMatch(node, normalizedSearchTerm))
      .forEach(addWithinBudget);
    filteredNodes
      .filter((node) => node.node_type === "hub")
      .forEach(addWithinBudget);
    filteredNodes
      .filter((node) => node.node_type !== "hub" && Boolean(node.metadata_json?.market_code))
      .forEach(addWithinBudget);

    return priorityIds;
  }, [filteredNodes, highlightedRoutePoints, normalizedSearchTerm]);

  function shouldShowFallbackNodeLabel(node: NodeDTO, index: number): boolean {
    return index >= 0 && fallbackLabelPriorityIds.has(node.id);
  }

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      center: [7.8, 51.2],
      zoom: 4.0,
      minZoom: 3,
      maxZoom: 9,
      attributionControl: false,
      style: {
        version: 8,
        sources: {
          osm: {
            type: "raster",
            tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: "OpenStreetMap contributors",
          },
        },
        layers: [
          {
            id: "background",
            type: "background",
            paint: { "background-color": mapColors.background },
          },
          {
            id: "osm-raster",
            type: "raster",
            source: "osm",
            paint: {
              "raster-opacity": effectiveTheme === "dark" ? 0.38 : 0.64,
              "raster-saturation": -1,
              "raster-contrast": effectiveTheme === "dark" ? 0.14 : 0.24,
              "raster-brightness-min": effectiveTheme === "dark" ? 0.08 : 0.16,
              "raster-brightness-max": effectiveTheme === "dark" ? 0.62 : 0.92,
            },
          },
        ],
      },
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
    if (map.getLayer("osm-raster")) {
      map.setPaintProperty("osm-raster", "raster-opacity", effectiveTheme === "dark" ? 0.38 : 0.64);
      map.setPaintProperty("osm-raster", "raster-saturation", -1);
      map.setPaintProperty("osm-raster", "raster-contrast", effectiveTheme === "dark" ? 0.14 : 0.24);
      map.setPaintProperty("osm-raster", "raster-brightness-min", effectiveTheme === "dark" ? 0.08 : 0.16);
      map.setPaintProperty("osm-raster", "raster-brightness-max", effectiveTheme === "dark" ? 0.62 : 0.92);
    }
    if (!mapReady) return;

    if (map.getLayer("edges-line")) {
      map.setPaintProperty("edges-line", "line-color", ["case", ["get", "route_candidate"], mapColors.route, mapColors.edge]);
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
  }, [effectiveTheme, mapColors, mapReady]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady || !map.isStyleLoaded()) return;

    const visibleNodeIds = new Set(filteredNodes.map((node) => node.id));
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
      geometry: { type: "Point" as const, coordinates: [node.lon, node.lat] },
    }));
    const edgeFeatures = visibleEdges
      .map((edge) => {
        const from = edge.from;
        const to = edge.to;
        const metadata = edge.metadata_json ?? {};
        const routeCandidate =
          routeIds.has(`${edge.from_node_id}:${edge.to_node_id}`) ||
          edge.source_system === "route_candidate" ||
          metadata.materialization === "route_candidate_edge";
        const capacity = Number(metadata.capacity_mwh_d ?? metadata.firm_capacity_mwh_d ?? 0);
        const flow = Number(metadata.live_physical_flow_mwh_d ?? 0);
        const utilization = Number(metadata.utilization_pct ?? (capacity > 0 ? flow / capacity : 0));
        return {
          type: "Feature" as const,
          properties: {
            id: edge.id,
            from_node_id: edge.from_node_id,
            to_node_id: edge.to_node_id,
            operator: String(metadata.operator ?? ""),
            tariff_gbp_mwh: Number(metadata.tariff_gbp_mwh ?? 0),
            capacity_mwh_d: capacity,
            live_flow_mwh_d: flow,
            utilization_pct: utilization,
            route_candidate: routeCandidate,
          },
          geometry: {
            type: "LineString" as const,
            coordinates: [
              [from.lon, from.lat],
              [to.lon, to.lat],
            ],
          },
        };
      })

    if (!map.getSource("edges")) {
      map.addSource("edges", {
        type: "geojson",
        data: { type: "FeatureCollection", features: edgeFeatures },
      });
      map.addLayer({
        id: "edges-line",
        type: "line",
        source: "edges",
        paint: {
          "line-color": ["case", ["get", "route_candidate"], mapColors.route, mapColors.edge],
          "line-width": ["case", ["get", "route_candidate"], 4.2, ["interpolate", ["linear"], ["get", "utilization_pct"], 0, 1.2, 0.65, 2.4, 0.9, 3.4]],
          "line-opacity": 0.9,
        },
      });
    } else {
      (map.getSource("edges") as GeoJSONSource).setData({
        type: "FeatureCollection",
        features: edgeFeatures,
      });
    }

    if (!map.getSource("highlighted-route-segments")) {
      map.addSource("highlighted-route-segments", {
        type: "geojson",
        data: { type: "FeatureCollection", features: highlightedRouteSegmentFeatures },
      });
      map.addLayer({
        id: "highlighted-route-segments",
        type: "line",
        source: "highlighted-route-segments",
        paint: {
          "line-color": mapColors.route,
          "line-width": 6,
          "line-opacity": 0.96,
          "line-dasharray": [1.4, 1.2],
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
      });
      map.addLayer({
        id: "nodes-circle",
        type: "circle",
        source: "nodes",
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
      map.on("click", "nodes-circle", (event) => {
        const feature = event.features?.[0];
        if (!feature) return;
        const props = feature.properties ?? {};
        const coordinateQuality = propertyText(props.coordinate_quality, "unknown");
        const source = propertyText(props.source_system, "unknown");
        new maplibregl.Popup({ closeButton: false })
          .setLngLat(event.lngLat)
          .setHTML(
            `<div class="node-popup">
              <strong>${escapeHtml(props.name)}</strong>
              <span>${escapeHtml(props.node_type)} / ${escapeHtml(props.country)}</span>
              <small>Source ${escapeHtml(source)}</small>
              <small>Coordinate quality ${escapeHtml(coordinateQuality)}</small>
              ${coordinateQuality === "display_approximation"
                ? "<em>Approximate display coordinate, not surveyed WGS84 geometry.</em>"
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
  }, [filteredNodes, highlightedRouteSegmentFeatures, mapColors, mapReady, routeIds, visibleEdges]);

  function project(lon: number, lat: number): [number, number] {
    const x = ((lon + 12) / 47) * 1000;
    const y = ((63 - lat) / 29) * 620;
    return [Math.max(0, Math.min(1000, x)), Math.max(0, Math.min(620, y))];
  }

  return (
    <div className="gas-map" aria-label="Gas network map">
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
        {visibleEdges.map((edge) => {
          const [x1, y1] = project(edge.from.lon, edge.from.lat);
          const [x2, y2] = project(edge.to.lon, edge.to.lat);
          const metadata = edge.metadata_json ?? {};
          const capacity = Number(metadata.capacity_mwh_d ?? metadata.firm_capacity_mwh_d ?? 0);
          const flow = Number(metadata.live_physical_flow_mwh_d ?? 0);
          const utilization = Number(metadata.utilization_pct ?? (capacity > 0 ? flow / capacity : 0));
          const pressureClass = utilization >= 0.75 ? " hot" : utilization >= 0.5 ? " warm" : "";
          const routeCandidate =
            routeIds.has(`${edge.from_node_id}:${edge.to_node_id}`) ||
            edge.source_system === "route_candidate" ||
            metadata.materialization === "route_candidate_edge";
          return (
            <line
              key={edge.id}
              className={routeCandidate ? `fallback-edge route${pressureClass}` : `fallback-edge${pressureClass}`}
              x1={x1}
              y1={y1}
              x2={x2}
              y2={y2}
            />
          );
        })}
        {highlightedRoutePoints && (() => {
          const [x1, y1] = project(highlightedRoutePoints.from.lon, highlightedRoutePoints.from.lat);
          const [x2, y2] = project(highlightedRoutePoints.to.lon, highlightedRoutePoints.to.lat);
          const pnlText = highlightedRoutePoints.pnlGbp === null
            ? ""
            : `GBP ${Math.round(highlightedRoutePoints.pnlGbp).toLocaleString()}`;
          if (routeSegmentsForHighlight.length > 0) {
            const segmentPoints = routeSegmentsForHighlight.map((edge) => {
              const [fromX, fromY] = project(edge.from.lon, edge.from.lat);
              const [toX, toY] = project(edge.to.lon, edge.to.lat);
              return { edge, fromX, fromY, toX, toY };
            });
            const labelSegment = segmentPoints[Math.floor(segmentPoints.length / 2)];
            const labelX = (labelSegment.fromX + labelSegment.toX) / 2 + 12;
            const labelY = (labelSegment.fromY + labelSegment.toY) / 2 - 12;
            return (
              <g className="fallback-flow segmented" aria-hidden="true">
                <desc>{geometryWarning}</desc>
                {segmentPoints.map(({ edge, fromX, fromY, toX, toY }) => (
                  <g key={`highlighted-fallback-segment-${edge.id}`}>
                    <line
                      className="fallback-flow-shadow"
                      x1={fromX}
                      y1={fromY}
                      x2={toX}
                      y2={toY}
                    />
                    <line
                      className="fallback-flow-segment"
                      x1={fromX}
                      y1={fromY}
                      x2={toX}
                      y2={toY}
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
          }

          const controlX = (x1 + x2) / 2;
          const controlY = Math.min(y1, y2) - 90;
          const path = `M ${x1} ${y1} Q ${controlX} ${controlY} ${x2} ${y2}`;
          return (
            <g className="fallback-flow" aria-hidden="true">
              <desc>{geometryWarning}</desc>
              <path className="fallback-flow-shadow" d={path} />
              <path className="fallback-flow-path direct-corridor" d={path} />
              <circle className="fallback-flow-pulse" r="7">
                <animateMotion dur="3.8s" repeatCount="indefinite" path={path} />
              </circle>
              <text className="fallback-flow-label" x={controlX + 12} y={controlY - 14}>
                {highlightedRoutePoints.label}
              </text>
              {pnlText && (
                <text className="fallback-flow-value" x={controlX + 12} y={controlY + 4}>
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
            Loading network layers
          </text>
        )}
      </svg>
    </div>
  );
}
