/**
 * Which lines the network map may draw, and with what shape. Kept free of app imports so it
 * can be tested directly.
 *
 * A gas trader reads the map as a network: pipelines and interconnectors where they run. Three
 * rules follow from that.
 *
 * - **A trading point is a market area, not a place.** TTF, THE or NBP is not physically
 *   connected to the points of its zone. A zone-membership link (``edge_type = virtual``,
 *   ``connection_basis = entry_exit_zone``, or any unsurveyed link with a hub at one end) is
 *   data the map uses for selection and checks; it is never drawn. Drawing it put a star of
 *   lines on every hub, one to each point of the zone.
 * - **One quiet segment per real connection.** A link between two located physical points
 *   without a surveyed route is one straight segment between them, never a curve whose bend
 *   depends on a leg number; several records for the same pair are one line.
 * - **One line per origin and destination for the book.** Allocations between the same two
 *   places are summed into a single line whose width encodes the volume.
 */

export type LineCoordinate = [number, number];

export interface LineEndpoint {
  id: string;
  node_type: string;
  lon: number;
  lat: number;
}

export interface LineEdgeLike {
  id: string;
  from_node_id: string;
  to_node_id: string;
  edge_type?: string | null;
  metadata_json?: Record<string, unknown> | null;
}

/** A virtual trading point (hub) stands for a market area. */
export function isVirtualPoint(node: Pick<LineEndpoint, "node_type"> | null | undefined): boolean {
  return node?.node_type === "hub";
}

/** Market-area adjacency the route pricing walks (reference bundle, from ENTSOG). */
export const MARKET_AREA_LINK = "market_area_link";
export const INTERCONNECTOR = "interconnector";

/**
 * Whether an edge is commercial adjacency: an interconnection point joined to a market area it
 * connects (``market_area_link``), or the two ends of a two-point pipeline such as IUK or BBL
 * (``interconnector``). These are what route pricing walks and what the map draws.
 */
export function isAdjacencyEdge(edge: Pick<LineEdgeLike, "edge_type">): boolean {
  return edge.edge_type === MARKET_AREA_LINK || edge.edge_type === INTERCONNECTOR;
}

/**
 * Whether the map draws an adjacency edge by default: every pipeline, and for each pair of
 * market areas the one interconnection point the bundle marks representative. The other points
 * of a pair show when either hub is selected; pricing uses them all.
 */
export function isDrawnAdjacency(edge: LineEdgeLike): boolean {
  if (edge.edge_type === INTERCONNECTOR) return true;
  return edge.edge_type === MARKET_AREA_LINK && edge.metadata_json?.representative === true;
}

/**
 * Whether an edge only says which market area a point belongs to. Such an edge has no
 * physical meaning on the map: it is used for hub selection and topology checks, never drawn.
 */
export function isZoneMembershipEdge(
  edge: LineEdgeLike,
  from?: Pick<LineEndpoint, "node_type"> | null,
  to?: Pick<LineEndpoint, "node_type"> | null,
): boolean {
  if (isAdjacencyEdge(edge)) return false;
  if (edge.edge_type === "virtual") return true;
  if (edge.metadata_json?.connection_basis === "entry_exit_zone") return true;
  return isVirtualPoint(from) || isVirtualPoint(to);
}

/**
 * One straight segment between two located endpoints. A few intermediate vertices keep it
 * smooth on the globe projection; there is no bend, so records for the same pair coincide
 * instead of fanning out.
 */
export function straightSegment(from: LineEndpoint, to: LineEndpoint): LineCoordinate[] {
  const steps = 8;
  return Array.from({ length: steps + 1 }, (_, index) => {
    const t = index / steps;
    return [from.lon + (to.lon - from.lon) * t, from.lat + (to.lat - from.lat) * t];
  });
}

/**
 * A drawn connection's path along the open reference trunk lines (SciGRID_gas IGGIELGN,
 * ``metadata_json.presentation_path``): the general direction pipes run. Presentation only -
 * the line stays schematic and nothing is priced from it.
 */
export function presentationPath(edge: Pick<LineEdgeLike, "metadata_json">): LineCoordinate[] | null {
  const raw = edge.metadata_json?.presentation_path;
  if (!Array.isArray(raw) || raw.length < 2) return null;
  const out: LineCoordinate[] = [];
  for (const point of raw) {
    if (!Array.isArray(point) || point.length !== 2) return null;
    const [lon, lat] = point;
    if (typeof lon !== "number" || typeof lat !== "number" || !Number.isFinite(lon) || !Number.isFinite(lat)) return null;
    out.push([lon, lat]);
  }
  return out;
}

/** A leg's drawn path between two places, in the order asked, when an edge carries one. */
export type LegPath = (fromId: string, toId: string) => LineCoordinate[] | null;

export function legPaths(edges: readonly LineEdgeLike[]): LegPath {
  const byPair = new Map<string, LineCoordinate[]>();
  for (const edge of edges) {
    const path = presentationPath(edge);
    if (path) byPair.set(`${edge.from_node_id}|${edge.to_node_id}`, path);
  }
  return (fromId, toId) => {
    const forward = byPair.get(`${fromId}|${toId}`);
    if (forward) return forward;
    const backward = byPair.get(`${toId}|${fromId}`);
    return backward ? [...backward].reverse() : null;
  };
}

/** An order-free key for the pair of places a line joins. */
export function pairKey(fromId: string, toId: string): string {
  return fromId < toId ? `${fromId}|${toId}` : `${toId}|${fromId}`;
}

/**
 * Collapse schematic lines that join the same pair of places into one. Surveyed lines are kept
 * as they are: two real pipes between the same places are two lines on the ground.
 */
export function collapseSchematicPairs<
  T extends { from: { id: string }; to: { id: string }; schematic: boolean; kind: string },
>(lines: readonly T[]): T[] {
  const seen = new Set<string>();
  const out: T[] = [];
  for (const line of lines) {
    if (!line.schematic) {
      out.push(line);
      continue;
    }
    const key = `${line.kind}|${pairKey(line.from.id, line.to.id)}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(line);
  }
  return out;
}

/** Members of a market area: the points a hub's zone-membership edges name. */
export function zoneMemberIds(hubId: string, edges: readonly LineEdgeLike[]): Set<string> {
  const members = new Set<string>();
  for (const edge of edges) {
    if (edge.edge_type !== "virtual" && edge.metadata_json?.connection_basis !== "entry_exit_zone") continue;
    if (edge.to_node_id === hubId) members.add(edge.from_node_id);
    else if (edge.from_node_id === hubId) members.add(edge.to_node_id);
  }
  members.delete(hubId);
  return members;
}

/** Line widths for book flows, in px: a few steps, capped, so a big deal never shouts. */
export const BOOK_FLOW_WIDTH_STEPS: ReadonlyArray<readonly [number, number]> = [
  [5_000, 2],
  [15_000, 3],
  [40_000, 4.5],
];
export const BOOK_FLOW_MAX_WIDTH = 6;

export function bookFlowWidth(mwhPerDay: number): number {
  for (const [upTo, width] of BOOK_FLOW_WIDTH_STEPS) if (mwhPerDay < upTo) return width;
  return BOOK_FLOW_MAX_WIDTH;
}

/** "18k MWh/d", "950 MWh/d", "1.2k MWh/d". */
export function compactMwhPerDay(value: number): string {
  if (value >= 1000) {
    const thousands = value / 1000;
    const text = thousands >= 10 ? Math.round(thousands).toString() : (Math.round(thousands * 10) / 10).toString();
    return `${text}k MWh/d`;
  }
  return `${Math.round(value)} MWh/d`;
}

export interface BookFlowPathInput {
  routeId: string;
  /** The node ids hub -> interconnection point(s) -> hub the route was priced along. */
  pathNodeIds?: string[] | null;
  sourcePointName: string;
  targetPointName: string;
  routeState: string;
  routeTopologyKind?: string;
  allocatedQuantityMwhPerDay: number | null;
}

export interface BookFlowLine {
  id: string;
  fromId: string;
  toId: string;
  mwhPerDay: number;
  width: number;
  label: string;
  routeIds: string[];
  pathCount: number;
  /**
   * "priced_path" when it follows the hub -> interconnection point -> hub path the route was
   * priced along, "surveyed" along a surveyed pipeline route, else one straight segment.
   */
  geometryBasis: "priced_path" | "surveyed" | "segment";
  coordinates: LineCoordinate[];
}

interface BuildBookFlowsParams {
  paths: readonly BookFlowPathInput[];
  /** Normalised point name to node id. */
  resolvePoint: (name: string) => string | undefined;
  nodes: ReadonlyMap<string, LineEndpoint>;
  /** The surveyed path of a route from origin to destination, when one exists. */
  surveyedRoute?: (routeId: string) => LineCoordinate[] | null;
  /** A connection leg's drawn path (``legPaths``), so a flow follows the same lines. */
  legPath?: LegPath;
}

/**
 * The book's flows as one line per origin and destination. Only volume the decision allocated
 * is a flow; candidates and blocked options are not. A sale at the place the gas already is
 * (a local disposition) has no line. A delivery at a hub with no physical origin is a badge
 * at the hub, which the caller draws.
 */
export function buildBookFlows({ paths, resolvePoint, nodes, surveyedRoute, legPath }: BuildBookFlowsParams): BookFlowLine[] {
  const byPair = new Map<string, BookFlowLine>();
  for (const path of paths) {
    const volume = path.allocatedQuantityMwhPerDay ?? 0;
    if (path.routeState !== "allocated" || !(volume > 0)) continue;
    if (path.routeTopologyKind === "LOCAL_MARKET_DISPOSITION") continue;
    const fromId = resolvePoint(path.sourcePointName);
    const toId = resolvePoint(path.targetPointName);
    if (!fromId || !toId || fromId === toId) continue;
    const from = nodes.get(fromId);
    const to = nodes.get(toId);
    if (!from || !to || !located(from) || !located(to)) continue;
    const pricedPath = (path.pathNodeIds ?? []).map((id) => nodes.get(id));
    const followsPricedPath = pricedPath.length >= 2 && pricedPath.every((node) => node && located(node));
    const key = `${fromId}->${toId}`;
    const existing = byPair.get(key);
    if (existing) {
      existing.mwhPerDay += volume;
      existing.pathCount += 1;
      if (path.routeId && !existing.routeIds.includes(path.routeId)) existing.routeIds.push(path.routeId);
      continue;
    }
    byPair.set(key, {
      id: `book-flow-${key}`,
      fromId,
      toId,
      mwhPerDay: volume,
      width: 0,
      label: "",
      routeIds: path.routeId ? [path.routeId] : [],
      pathCount: 1,
      geometryBasis: followsPricedPath ? "priced_path" : "segment",
      coordinates: followsPricedPath ? polyline(pricedPath as LineEndpoint[], legPath) : straightSegment(from, to),
    });
  }
  return [...byPair.values()].map((flow) => {
    if (flow.geometryBasis === "priced_path") {
      return { ...flow, width: bookFlowWidth(flow.mwhPerDay), label: compactMwhPerDay(flow.mwhPerDay) };
    }
    const surveyed = flow.routeIds.map((routeId) => surveyedRoute?.(routeId) ?? null).find((coords) => coords && coords.length > 1);
    return {
      ...flow,
      width: bookFlowWidth(flow.mwhPerDay),
      label: compactMwhPerDay(flow.mwhPerDay),
      geometryBasis: surveyed ? "surveyed" as const : "segment" as const,
      coordinates: surveyed ?? flow.coordinates,
    };
  });
}

/**
 * Through a sequence of places (hub -> point -> hub): each leg along its drawn path when the
 * connection carries one (``legPath``), else a straight segment.
 */
export function polyline(points: readonly LineEndpoint[], legPath?: LegPath): LineCoordinate[] {
  const out: LineCoordinate[] = [];
  points.forEach((point, index) => {
    if (index === 0) return;
    const segment = legPath?.(points[index - 1].id, point.id) ?? straightSegment(points[index - 1], point);
    out.push(...(out.length ? segment.slice(1) : segment));
  });
  return out;
}

/** The points a hub's adjacency edges join (all of them, drawn when the hub is selected). */
export function hubAdjacencyEdges<T extends LineEdgeLike>(hubId: string, edges: readonly T[]): T[] {
  const points = new Set(
    edges
      .filter((edge) => edge.edge_type === MARKET_AREA_LINK && (edge.from_node_id === hubId || edge.to_node_id === hubId))
      .map((edge) => (edge.from_node_id === hubId ? edge.to_node_id : edge.from_node_id)),
  );
  return edges.filter((edge) =>
    edge.edge_type === MARKET_AREA_LINK && (edge.from_node_id === hubId || edge.to_node_id === hubId)
    || edge.edge_type === INTERCONNECTOR && (points.has(edge.from_node_id) || points.has(edge.to_node_id)));
}

function located(node: LineEndpoint): boolean {
  return Number.isFinite(node.lon) && Number.isFinite(node.lat) && Math.abs(node.lon) <= 180 && Math.abs(node.lat) <= 90;
}
