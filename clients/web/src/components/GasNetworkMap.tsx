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
}

export function GasNetworkMap({ nodes, edges, routes, themeMode, activeLayers, searchTerm }: GasNetworkMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const [mapReady, setMapReady] = useState(false);
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

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const dark = themeMode === "dark" || (themeMode === "system" && prefersDark);
    const map = new maplibregl.Map({
      container: containerRef.current,
      center: [7.8, 51.2],
      zoom: 4.0,
      minZoom: 3,
      maxZoom: 9,
      attributionControl: false,
      style: {
        version: 8,
        sources: {},
        layers: [
          {
            id: "background",
            type: "background",
            paint: { "background-color": dark ? "#101820" : "#eef4f7" },
          },
        ],
      },
    });

    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-left");
    map.on("load", () => setMapReady(true));
    mapRef.current = map;
    return () => {
      setMapReady(false);
      map.remove();
      mapRef.current = null;
    };
  }, [themeMode]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !mapReady) return;

    const visibleNodeIds = new Set(filteredNodes.map((node) => node.id));
    const nodeFeatures = filteredNodes.map((node) => ({
      type: "Feature" as const,
      properties: {
        id: node.id,
        name: node.name,
        node_type: node.node_type,
        country: node.country,
        capacity_boe_d: node.capacity_boe_d,
      },
      geometry: { type: "Point" as const, coordinates: [node.lon, node.lat] },
    }));
    const edgeFeatures = visibleEdges
      .map((edge) => {
        const from = edge.from;
        const to = edge.to;
        return {
          type: "Feature" as const,
          properties: {
            id: edge.id,
            from_node_id: edge.from_node_id,
            to_node_id: edge.to_node_id,
            route_candidate: routeIds.has(`${edge.from_node_id}:${edge.to_node_id}`),
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
          "line-color": ["case", ["get", "route_candidate"], "#f59e0b", "#3b82f6"],
          "line-width": ["case", ["get", "route_candidate"], 3.5, 1.8],
          "line-opacity": 0.84,
        },
      });
    } else {
      (map.getSource("edges") as GeoJSONSource).setData({
        type: "FeatureCollection",
        features: edgeFeatures,
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
          "circle-color": ["case", ["==", ["get", "node_type"], "hub"], "#0f766e", "#2563eb"],
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 1.5,
        },
      });
      map.on("click", "nodes-circle", (event) => {
        const feature = event.features?.[0];
        if (!feature) return;
        new maplibregl.Popup({ closeButton: false })
          .setLngLat(event.lngLat)
          .setHTML(
            `<strong>${feature.properties?.name}</strong><br/>${feature.properties?.node_type}`
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
  }, [filteredNodes, mapReady, routeIds, visibleEdges]);

  function project(lon: number, lat: number): [number, number] {
    const x = ((lon + 12) / 47) * 1000;
    const y = ((63 - lat) / 29) * 620;
    return [Math.max(0, Math.min(1000, x)), Math.max(0, Math.min(620, y))];
  }

  return (
    <div className="gas-map" aria-label="Gas network map">
      <div ref={containerRef} className="maplibre-canvas" />
      <svg className="fallback-network-map" viewBox="0 0 1000 620" role="presentation">
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
          const routeCandidate = routeIds.has(`${edge.from_node_id}:${edge.to_node_id}`);
          return (
            <line
              key={edge.id}
              className={routeCandidate ? "fallback-edge route" : "fallback-edge"}
              x1={x1}
              y1={y1}
              x2={x2}
              y2={y2}
            />
          );
        })}
        {filteredNodes.map((node) => {
          const [x, y] = project(node.lon, node.lat);
          return (
            <g key={node.id} className={`fallback-node ${node.node_type}`}>
              <circle cx={x} cy={y} r={node.node_type === "hub" ? 7 : 5} />
              <text x={x + 9} y={y - 8}>{node.name}</text>
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
