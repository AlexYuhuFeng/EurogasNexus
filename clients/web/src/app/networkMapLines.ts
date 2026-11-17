import type { EdgeDTO, NodeDTO } from "@/api/client";
import { routeEdgeRouteId } from "@/app/routeMetadata";
import {
  isMapEligibleNode,
  verifiedEdgeGeometryCoordinates,
} from "@/app/workspaceDerivedData";
import type { RouteGeometryState } from "@/components/ResourcePoolPathOverlay";
import {
  collapseSchematicPairs,
  isAdjacencyEdge,
  isDrawnAdjacency,
  isZoneMembershipEdge,
  legPaths,
  polyline,
  presentationPath,
  straightSegment,
  type LegPath,
  type LineCoordinate,
} from "@/app/mapLineGeometry";

export type { LineCoordinate };
/**
 * - verified_pipeline: a reference connection with surveyed geometry, drawn as it runs;
 * - network_link: a physical connection between two located points without surveyed
 *   geometry, drawn as one quiet straight dashed segment between them;
 * - indicative_route: a route candidate's schematic corridor (one straight segment).
 *
 * Zone-membership links (a point to its zone's trading point) are never lines: a trading
 * point is a market area, not a place wired to its points (see mapLineGeometry.ts).
 */
export type NetworkLineDisplayKind = "verified_pipeline" | "network_link" | "indicative_route";
export type NetworkLineGeometryBasis =
  | "verified_geometry"
  | "backend_route_geometry_coordinates"
  | "schematic_endpoint_segment"
  /** Schematic, drawn along the open reference trunk lines (general direction; never priced). */
  | "reference_pipeline_direction";

export interface NetworkHighlightedRoute {
  fromNodeId: string;
  toNodeId: string;
  routeId: string;
  label: string;
  pnlGbp: number | null;
  routeGeometryState: RouteGeometryState;
  routeLegSummary: string[];
  /** The hub -> interconnection point(s) -> hub path the route was priced along, if known. */
  pathNodeIds?: string[] | null;
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

/**
 * The schematic shape of a connection without surveyed geometry: one straight segment between
 * its endpoints. It used to bend by leg number, which drew parallel records for the same pair
 * as offset arcs fanning out from one origin.
 */
export function buildSchematicRouteCoordinates(from: NodeDTO, to: NodeDTO): LineCoordinate[] {
  return straightSegment(from, to);
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

  if (edge.from_node_id === edge.to_node_id) return null;
  if (!isRouteCandidateEdge(edge)) {
    // A point's zone link is membership of a market area, not a connection on the ground.
    if (isZoneMembershipEdge(edge, from, to)) return null;
    // Of the interconnection points joining two market areas the map draws one by default;
    // the others show when a hub is selected (GasNetworkMap's selection layer).
    if (isAdjacencyEdge(edge) && !isDrawnAdjacency(edge)) return null;
    const sequence = metadataNumber(edge.metadata_json, "route_leg_sequence", 1);
    const along = presentationPath(edge);
    return {
      id: edge.id,
      edge,
      from,
      to,
      geometryCoordinates: along ?? buildSchematicRouteCoordinates(from, to),
      displayKind: "network_link",
      routeCandidate: false,
      geometryBasis: along ? "reference_pipeline_direction" : "schematic_endpoint_segment",
      routeId: routeEdgeRouteId(edge) ?? edge.source_record_id ?? "",
      routeLegSequence: sequence,
      routeGeometryState: routeGeometryStateFromMetadata(edge, "directLineFallback"),
    };
  }

  const metadata = edge.metadata_json ?? {};
  const explicitCoordinates = validLineCoordinates(metadata.geometry_coordinates);
  const routeLegSequence = metadataNumber(metadata, "route_leg_sequence", 1);
  return {
    id: edge.id,
    edge,
    from,
    to,
    geometryCoordinates: explicitCoordinates ??
      buildSchematicRouteCoordinates(from, to),
    displayKind: "indicative_route",
    routeCandidate: true,
    geometryBasis: explicitCoordinates
      ? "backend_route_geometry_coordinates"
      : "schematic_endpoint_segment",
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
  const lines = edges
    .map((edge) => buildRenderableNetworkLine(edge, nodeLookup))
    .filter((line): line is RenderableNetworkLine => line !== null);
  // Several records for the same pair of places (both directions, a leg per route) are one
  // schematic line; surveyed pipelines stay as they run.
  return collapseSchematicPairs(
    lines.map((line) => ({
      ...line,
      schematic: line.geometryBasis === "schematic_endpoint_segment" || line.geometryBasis === "reference_pipeline_direction",
      kind: line.displayKind,
    })),
  ).map(({ schematic: _schematic, kind: _kind, ...line }) => line);
}

export function buildSyntheticSelectedRouteLine(
  highlightedRoute: NetworkHighlightedRoute,
  from: NodeDTO,
  to: NodeDTO,
  nodeLookup?: Map<string, NodeDTO>,
  legPath?: LegPath,
): RenderableNetworkLine | null {
  if (
    from.id === to.id ||
    !isUsableEndpointCoordinate(from) ||
    !isUsableEndpointCoordinate(to)
  ) return null;
  const geometryState: RouteGeometryState =
    highlightedRoute.routeGeometryState === "surveyed_pipeline_route"
      ? "source_derived_corridor"
      : highlightedRoute.routeGeometryState;
  return {
    id: `selected-route-${highlightedRoute.routeId}-schematic`,
    edge: null,
    from,
    to,
    // Along the path the route was priced on (hub -> point -> hub), so the map shows what was
    // priced; one segment between the ends when no path is known.
    geometryCoordinates: pricedPathCoordinates(highlightedRoute.pathNodeIds, nodeLookup, legPath)
      ?? buildSchematicRouteCoordinates(from, to),
    displayKind: "indicative_route",
    routeCandidate: true,
    geometryBasis: "schematic_endpoint_segment",
    routeId: highlightedRoute.routeId,
    routeLegSequence: 1,
    routeGeometryState: geometryState,
  };
}

function pricedPathCoordinates(
  ids: string[] | null | undefined,
  nodeLookup: Map<string, NodeDTO> | undefined,
  legPath?: LegPath,
): LineCoordinate[] | null {
  if (!ids || ids.length < 2 || !nodeLookup) return null;
  const nodes = ids.map((id) => nodeLookup.get(id));
  if (nodes.some((node) => !node || !isUsableEndpointCoordinate(node))) return null;
  return polyline(nodes as NodeDTO[], legPath);
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
      // Entry points and interconnection points are where gas crosses into a zone: one layer.
      (activeLayers.includes("ips") && (node.node_type === "interconnection" || node.node_type === "entry_point")) ||
      (activeLayers.includes("network") && !["hub", "lng", "interconnection", "entry_point"].includes(node.node_type));
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
    ? buildSyntheticSelectedRouteLine(params.highlightedRoute, from, to, nodeLookup, legPaths(params.edges))
    : null;
  return syntheticLine ? [...baseLines, syntheticLine] : baseLines;
}

