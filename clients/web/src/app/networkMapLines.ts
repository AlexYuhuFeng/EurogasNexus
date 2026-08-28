import type { EdgeDTO, NodeDTO } from "@/api/client";
import { routeEdgeRouteId } from "@/app/routeMetadata";
import {
  isMapEligibleNode,
  verifiedEdgeGeometryCoordinates,
} from "@/app/workspaceDerivedData";
import type { RouteGeometryState } from "@/components/ResourcePoolPathOverlay";

export type LineCoordinate = [number, number];
export type NetworkLineDisplayKind = "verified_pipeline" | "indicative_route";
export type NetworkLineGeometryBasis =
  | "verified_geometry"
  | "backend_route_geometry_coordinates"
  | "schematic_endpoint_curve";

export interface NetworkHighlightedRoute {
  fromNodeId: string;
  toNodeId: string;
  routeId: string;
  label: string;
  pnlGbp: number | null;
  routeGeometryState: RouteGeometryState;
  routeLegSummary: string[];
}

export interface RenderableNetworkLine {
  id: string;
  edge: EdgeDTO | null;
  from: NodeDTO;
  to: NodeDTO;
  geometryCoordinates: LineCoordinate[];
  displayKind: NetworkLineDisplayKind;
  routeCandidate: boolean;
  geometryBasis: NetworkLineGeometryBasis;
  routeId: string;
  routeLegSequence: number;
  routeGeometryState: RouteGeometryState;
}

interface MapNetworkLinesParams {
  nodes: NodeDTO[];
  edges: EdgeDTO[];
  activeLayers: string[];
  searchTerm: string;
  highlightedRoute?: NetworkHighlightedRoute;
}

function metadataString(
  metadata: Record<string, unknown> | null | undefined,
  key: string,
  fallback = "",
): string {
  const value = metadata?.[key];
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function metadataNumber(
  metadata: Record<string, unknown> | null | undefined,
  key: string,
  fallback = 0,
): number {
  const value = metadata?.[key];
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return fallback;
}

export function isRouteCandidateEdge(edge: EdgeDTO): boolean {
  const metadata = edge.metadata_json ?? {};
  return (
    edge.source_system === "route_candidate" ||
    metadata.materialization === "route_candidate_edge"
  );
}

export function validLineCoordinates(value: unknown): LineCoordinate[] | null {
  if (!Array.isArray(value) || value.length < 2) return null;
  const coordinates = value.filter(
    (coordinate): coordinate is LineCoordinate =>
      Array.isArray(coordinate) &&
      coordinate.length >= 2 &&
      typeof coordinate[0] === "number" &&
      Number.isFinite(coordinate[0]) &&
      coordinate[0] >= -180 &&
      coordinate[0] <= 180 &&
      typeof coordinate[1] === "number" &&
      Number.isFinite(coordinate[1]) &&
      coordinate[1] >= -90 &&
      coordinate[1] <= 90,
  );
  return coordinates.length === value.length ? coordinates : null;
}

export function buildSchematicRouteCoordinates(
  from: NodeDTO,
  to: NodeDTO,
  routeLegSequence = 1,
): LineCoordinate[] {
  const deltaLon = to.lon - from.lon;
  const deltaLat = to.lat - from.lat;
  const distance = Math.hypot(deltaLon, deltaLat);
  if (!Number.isFinite(distance) || distance < 0.01) {
    return [[from.lon, from.lat], [to.lon, to.lat]];
  }

  const bendDirection = routeLegSequence % 2 === 0 ? -1 : 1;
  const bend = Math.min(Math.max(distance * 0.09, 0.08), 0.55) * bendDirection;
  const normalLon = -deltaLat / distance;
  const normalLat = deltaLon / distance;
  return Array.from({ length: 9 }, (_, index) => {
    const t = index / 8;
    const arc = Math.sin(Math.PI * t) * bend;
    const lon = Math.min(180, Math.max(-180, from.lon + deltaLon * t + normalLon * arc));
    const lat = Math.min(90, Math.max(-90, from.lat + deltaLat * t + normalLat * arc));
    return [lon, lat];
  });
}

export function isUsableEndpointCoordinate(node: NodeDTO): boolean {
  return (
    Number.isFinite(node.lon) &&
    node.lon >= -180 &&
    node.lon <= 180 &&
    Number.isFinite(node.lat) &&
    node.lat >= -90 &&
    node.lat <= 90
  );
}

function routeGeometryStateFromMetadata(
  edge: EdgeDTO,
  fallback: RouteGeometryState,
): RouteGeometryState {
  const state = metadataString(edge.metadata_json, "route_geometry_state");
  return state === "surveyed_pipeline_route" ||
    state === "source_derived_leg_sequence" ||
    state === "source_derived_corridor" ||
    state === "directLineFallback"
    ? state
    : fallback;
}

export function buildRenderableNetworkLine(
  edge: EdgeDTO,
  nodeLookup: Map<string, NodeDTO>,
): RenderableNetworkLine | null {
  const from = nodeLookup.get(edge.from_node_id);
  const to = nodeLookup.get(edge.to_node_id);
  if (!from || !to || !isUsableEndpointCoordinate(from) || !isUsableEndpointCoordinate(to)) {
    return null;
  }

  const verifiedCoordinates = verifiedEdgeGeometryCoordinates(edge);
  if (verifiedCoordinates) {
    return {
      id: edge.id,
      edge,
      from,
      to,
      geometryCoordinates: verifiedCoordinates,
      displayKind: "verified_pipeline",
      routeCandidate: false,
      geometryBasis: "verified_geometry",
      routeId: routeEdgeRouteId(edge) ?? edge.source_record_id ?? "",
      routeLegSequence: metadataNumber(edge.metadata_json, "route_leg_sequence"),
      routeGeometryState: routeGeometryStateFromMetadata(edge, "surveyed_pipeline_route"),
    };
  }

  if (!isRouteCandidateEdge(edge)) return null;

  const metadata = edge.metadata_json ?? {};
  const explicitCoordinates = validLineCoordinates(metadata.geometry_coordinates);
  const routeLegSequence = metadataNumber(metadata, "route_leg_sequence", 1);
  return {
    id: edge.id,
    edge,
    from,
    to,
    geometryCoordinates: explicitCoordinates ??
      buildSchematicRouteCoordinates(from, to, routeLegSequence),
    displayKind: "indicative_route",
    routeCandidate: true,
    geometryBasis: explicitCoordinates
      ? "backend_route_geometry_coordinates"
      : "schematic_endpoint_curve",
    routeId: routeEdgeRouteId(edge) ?? edge.source_record_id ?? "",
    routeLegSequence,
    routeGeometryState: routeGeometryStateFromMetadata(edge, "source_derived_corridor"),
  };
}

export function buildRenderableNetworkLines(
  nodes: NodeDTO[],
  edges: EdgeDTO[],
): RenderableNetworkLine[] {
  const nodeLookup = new globalThis.Map(nodes.map((node) => [node.id, node]));
  return edges
    .map((edge) => buildRenderableNetworkLine(edge, nodeLookup))
    .filter((line): line is RenderableNetworkLine => line !== null);
}

export function buildSyntheticSelectedRouteLine(
  highlightedRoute: NetworkHighlightedRoute,
  from: NodeDTO,
  to: NodeDTO,
): RenderableNetworkLine | null {
  if (!isUsableEndpointCoordinate(from) || !isUsableEndpointCoordinate(to)) return null;
  const geometryState: RouteGeometryState =
    highlightedRoute.routeGeometryState === "surveyed_pipeline_route"
      ? "source_derived_corridor"
      : highlightedRoute.routeGeometryState;
  return {
    id: `selected-route-${highlightedRoute.routeId}-schematic`,
    edge: null,
    from,
    to,
    geometryCoordinates: buildSchematicRouteCoordinates(from, to, 1),
    displayKind: "indicative_route",
    routeCandidate: true,
    geometryBasis: "schematic_endpoint_curve",
    routeId: highlightedRoute.routeId,
    routeLegSequence: 1,
    routeGeometryState: geometryState,
  };
}

export function networkLineMatchesRoute(line: RenderableNetworkLine, routeId: string): boolean {
  return Boolean(routeId && line.routeId === routeId);
}

export function buildVisibleNetworkNodes({
  nodes,
  edges,
  activeLayers,
  searchTerm,
  highlightedRoute,
}: MapNetworkLinesParams): NodeDTO[] {
  const term = searchTerm.trim().toLowerCase();
  const highlightedRouteNodeIds = new Set<string>();
  if (highlightedRoute) {
    highlightedRouteNodeIds.add(highlightedRoute.fromNodeId);
    highlightedRouteNodeIds.add(highlightedRoute.toNodeId);
    edges.forEach((edge) => {
      if (
        edge.source_record_id === highlightedRoute.routeId ||
        metadataString(edge.metadata_json, "route_id") === highlightedRoute.routeId
      ) {
        highlightedRouteNodeIds.add(edge.from_node_id);
        highlightedRouteNodeIds.add(edge.to_node_id);
      }
    });
  }

  return nodes.filter(isMapEligibleNode).filter((node) => {
    const layerMatch =
      (activeLayers.includes("hubs") && node.node_type === "hub") ||
      (activeLayers.includes("lng") && node.node_type === "lng") ||
      (activeLayers.includes("ips") && node.node_type === "interconnection") ||
      (activeLayers.includes("network") && !["hub", "lng", "interconnection"].includes(node.node_type));
    const searchMatch = !term ||
      node.name.toLowerCase().includes(term) ||
      node.country.toLowerCase().includes(term) ||
      node.node_type.toLowerCase().includes(term);
    const routeContextMatch = highlightedRouteNodeIds.has(node.id) && !term;
    return (layerMatch || routeContextMatch) && searchMatch;
  });
}

export function buildVisibleMapNetworkLines(params: MapNetworkLinesParams): RenderableNetworkLine[] {
  const visibleNodeIds = new Set(buildVisibleNetworkNodes(params).map((node) => node.id));
  const baseLines = buildRenderableNetworkLines(params.nodes, params.edges).filter((line) => {
    if (line.displayKind === "indicative_route") return true;
    return (
      params.activeLayers.includes("network") ||
      visibleNodeIds.has(line.from.id) ||
      visibleNodeIds.has(line.to.id)
    );
  });
  if (!params.highlightedRoute) return baseLines;

  const hasMatchingReferenceLine = baseLines.some(
    (line) => line.edge !== null && networkLineMatchesRoute(line, params.highlightedRoute!.routeId),
  );
  if (hasMatchingReferenceLine) return baseLines;

  const nodeLookup = new globalThis.Map(params.nodes.map((node) => [node.id, node]));
  const from = nodeLookup.get(params.highlightedRoute.fromNodeId);
  const to = nodeLookup.get(params.highlightedRoute.toNodeId);
  const syntheticLine = from && to
    ? buildSyntheticSelectedRouteLine(params.highlightedRoute, from, to)
    : null;
  return syntheticLine ? [...baseLines, syntheticLine] : baseLines;
}
