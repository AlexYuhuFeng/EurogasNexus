import type {
  EdgeDTO,
  MapAssetDTO,
  MapFlowDayDTO,
  MapSituationDTO,
  NodeDTO,
} from "@/api/client";

/**
 * The map scene (MAP-1), flat: terminals and storage sites as points sized by their published
 * capacity, and gas flows moving along the network. Pure functions, no map or DOM, so each rule
 * is tested directly (tests/mapScene.test.ts). The map has no 3D (owner, 2026-11-26): a cargo is
 * drawn once, by the situation layers, at its reported position.
 *
 * Rules:
 * - **Real or labelled.** A site's point is sized by a capacity the publisher stated; a site
 *   with none is the smallest point and its card says "no published capacity". A GIE figure read
 *   by country is the country's, and the card says so.
 * - **Direction only where the data gives it.** ENTSOG reports a flow relative to the operator's
 *   own system; the operator's side of a border is the market-area link that lists it. A flow
 *   whose side cannot be found is drawn as a point (the map's existing circle), never as an arrow.
 * - **Motion is functional.** Flow dashes move in the gas's direction; under reduced motion the
 *   line is static with a chevron. Moves between reads ease over the map token.
 */

export type Project = (lon: number, lat: number) => [number, number];
export type LonLat = [number, number];

type Props = Record<string, string | number | boolean | null>;
interface Feature<G> {
  type: "Feature";
  properties: Props;
  geometry: G;
}
export interface FC<G> {
  type: "FeatureCollection";
  features: Array<Feature<G>>;
}
type Point = { type: "Point"; coordinates: LonLat };
type Line = { type: "LineString"; coordinates: LonLat[] };

const fc = <G>(features: Array<Feature<G>>): FC<G> => ({ type: "FeatureCollection", features });

/**
 * Colours for the scene's own marks: the design system's series tokens (tokens.css; MapLibre
 * cannot read CSS variables, so the values are repeated here and in the key's swatches by
 * token). LNG terminals `--ds-series-5` (violet), storage `--ds-series-6` (olive), apart from the
 * map's existing meanings (blue: our positions, red and amber: outages, teal: flows) and from
 * each other under the common colour-vision deficiencies.
 */
export const SCENE_COLOURS = {
  light: { lng: "#7c3aed", storage: "#4d7c0f", noCapacity: "#a1a1aa" },
  dark: { lng: "#a78bfa", storage: "#a3e635", noCapacity: "#71717a" },
} as const;

// ---------------------------------------------------------------------------------------------
// Geometry helpers

const RAD = Math.PI / 180;
const EARTH_KM = 6371;

/** Great-circle distance in km. */
export function distanceKm(a: LonLat, b: LonLat): number {
  const [lon1, lat1] = [a[0] * RAD, a[1] * RAD];
  const [lon2, lat2] = [b[0] * RAD, b[1] * RAD];
  const h = Math.sin((lat2 - lat1) / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin((lon2 - lon1) / 2) ** 2;
  return 2 * EARTH_KM * Math.asin(Math.min(1, Math.sqrt(h)));
}

/** The point a fraction of the way along the great circle from `a` to `b`. */
export function greatCirclePoint(a: LonLat, b: LonLat, fraction: number): LonLat {
  const f = Math.min(1, Math.max(0, fraction));
  const [lon1, lat1] = [a[0] * RAD, a[1] * RAD];
  const [lon2, lat2] = [b[0] * RAD, b[1] * RAD];
  const d = distanceKm(a, b) / EARTH_KM;
  if (d < 1e-9) return [a[0], a[1]];
  const A = Math.sin((1 - f) * d) / Math.sin(d);
  const B = Math.sin(f * d) / Math.sin(d);
  const x = A * Math.cos(lat1) * Math.cos(lon1) + B * Math.cos(lat2) * Math.cos(lon2);
  const y = A * Math.cos(lat1) * Math.sin(lon1) + B * Math.cos(lat2) * Math.sin(lon2);
  const z = A * Math.sin(lat1) + B * Math.sin(lat2);
  return [Math.atan2(y, x) / RAD, Math.atan2(z, Math.sqrt(x * x + y * y)) / RAD];
}

/** The first `km` of a path (or all of it when shorter), cut exactly at that length. */
export function pathPrefix(path: LonLat[], km: number): LonLat[] {
  if (path.length < 2) return [...path];
  const out: LonLat[] = [path[0]];
  let left = km;
  for (let i = 1; i < path.length; i += 1) {
    const step = distanceKm(path[i - 1], path[i]);
    if (step >= left) {
      out.push(step > 0 ? greatCirclePoint(path[i - 1], path[i], left / step) : path[i]);
      return out;
    }
    left -= step;
    out.push(path[i]);
  }
  return out;
}

export function pathLengthKm(path: LonLat[]): number {
  let total = 0;
  for (let i = 1; i < path.length; i += 1) total += distanceKm(path[i - 1], path[i]);
  return total;
}

// ---------------------------------------------------------------------------------------------
// Terminals and storage

/** The figures a site's point and card are drawn from, each with where it came from. */
export interface AssetFigures {
  /** Published firm technical capacity the point is sized by (GWh/d), or null when none held. */
  capacityGwhD: number | null;
  capacityDirection: string | null;
  capacityGasDay: string | null;
  /** The point's newest closed-day physical flow in that direction (GWh/d), or null. */
  flowGwhD: number | null;
  flowGasDay: string | null;
  /** flow / capacity, only when both are published at the point; never above 1.5 shown. */
  utilisation: number | null;
}

/**
 * Which capacity stands for the site: the LNG terminal's send-out into the grid (entry), a
 * storage site's larger direction. The flow shown is the same direction's, so the fill level
 * compares like with like.
 */
export function assetFigures(asset: MapAssetDTO): AssetFigures {
  const capacities = asset.capacity ?? [];
  const pick = asset.kind === "lng_terminal"
    ? capacities.find((item) => item.direction === "entry") ?? null
    : [...capacities].sort((a, b) => b.gwh_d - a.gwh_d)[0] ?? null;
  const flows = asset.flow ?? [];
  const flow = pick
    ? flows.find((item) => item.direction === pick.direction) ?? null
    : asset.kind === "lng_terminal"
      ? flows.find((item) => item.direction === "entry") ?? null
      : [...flows].sort((a, b) => b.gwh_d - a.gwh_d)[0] ?? null;
  const capacity = pick && pick.gwh_d > 0 ? pick.gwh_d : null;
  return {
    capacityGwhD: capacity,
    capacityDirection: pick?.direction ?? null,
    capacityGasDay: pick?.gas_day ?? null,
    flowGwhD: flow?.gwh_d ?? null,
    flowGasDay: flow?.gas_day ?? null,
    utilisation: capacity !== null && flow ? Math.min(1.5, Math.max(0, flow.gwh_d / capacity)) : null,
  };
}

/** One point per site, its radius on a square-root scale of published capacity (4 to 14 px). */
export function assetPoints(assets: MapAssetDTO[] | undefined, project: Project): FC<Point> {
  const list = assets ?? [];
  const figures = list.map(assetFigures);
  const largest = Math.max(0, ...figures.map((item) => item.capacityGwhD ?? 0));
  return fc(list.map((asset, index) => {
    const figure = figures[index];
    return {
      type: "Feature" as const,
      properties: {
        kind: "asset",
        id: asset.asset_id,
        asset_kind: asset.kind,
        name: asset.name,
        published: figure.capacityGwhD !== null,
        capacity_gwh_d: figure.capacityGwhD,
        flow_gwh_d: figure.flowGwhD,
        utilisation: figure.utilisation,
        radius: figure.capacityGwhD === null || largest <= 0 ? 4 : 4 + 10 * Math.sqrt(figure.capacityGwhD / largest),
      },
      geometry: { type: "Point" as const, coordinates: project(asset.location.lon, asset.location.lat) },
    };
  }));
}

/** How old a figure is, in hours, from when the platform received it; null when unknown. */
export function figureAgeHours(receivedAtUtc: string | null | undefined, now: Date): number | null {
  if (!receivedAtUtc) return null;
  const at = Date.parse(receivedAtUtc);
  if (!Number.isFinite(at)) return null;
  return Math.max(0, (now.getTime() - at) / 3_600_000);
}

/** A daily figure older than two gas days is stale: the card says so beside its age. */
export const STALE_AFTER_HOURS = 48;

// ---------------------------------------------------------------------------------------------
// Gas flows

export interface SceneFlow {
  refId: string;
  pointName: string;
  direction: string;
  gwhD: number;
  operatorKey: string | null;
  gasDay: string | null;
  sourceSystem: string;
}

/** The stored closed gas days the scrubber can show, oldest first. */
export function flowDayOptions(situation: Pick<MapSituationDTO, "flow_days"> | null | undefined): string[] {
  return (situation?.flow_days ?? []).map((day) => day.gas_day);
}

/**
 * The flows to draw: `null` is "latest" (each point's newest closed day, as the map's flows
 * show), a gas day is that day from the stored window. Flows with no located point are left out.
 */
export function flowsForDay(situation: MapSituationDTO | null | undefined, day: string | null): SceneFlow[] {
  if (!situation) return [];
  const names = new Map(situation.flows.map((flow) => [flow.location.ref_id ?? "", flow.point_name]));
  if (day === null) {
    return situation.flows
      .filter((flow) => flow.location.ref_id && (flow.gwh_d ?? 0) > 0)
      .map((flow) => ({
        refId: flow.location.ref_id as string,
        pointName: flow.point_name,
        direction: flow.direction,
        gwhD: flow.gwh_d as number,
        operatorKey: flow.operator_key ?? null,
        gasDay: flow.gas_day ?? null,
        sourceSystem: flow.source_system,
      }));
  }
  const stored: MapFlowDayDTO | undefined = (situation.flow_days ?? []).find((item) => item.gas_day === day);
  return (stored?.flows ?? [])
    .filter((flow) => flow.ref_id && flow.gwh_d > 0)
    .map((flow) => ({
      refId: flow.ref_id as string,
      pointName: names.get(flow.ref_id as string) ?? flow.point_id,
      direction: flow.direction,
      gwhD: flow.gwh_d,
      operatorKey: flow.operator_key,
      gasDay: day,
      sourceSystem: flow.source_system,
    }));
}

interface Side {
  /** The path from the point toward this side (point first). */
  path: LonLat[];
  operators: Set<string>;
}

/**
 * The two sides of each point that the network says it joins: a market-area link lists the
 * operators on its hub's side; a two-point pipeline is its operator's side, toward its far end.
 */
export function pointSides(nodes: NodeDTO[], edges: EdgeDTO[]): Map<string, Side[]> {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const sides = new Map<string, Side[]>();
  const add = (pointId: string, side: Side) => sides.set(pointId, [...(sides.get(pointId) ?? []), side]);
  const straight = (from: NodeDTO, to: NodeDTO): LonLat[] => [[from.lon, from.lat], [to.lon, to.lat]];
  const drawn = (edge: EdgeDTO): LonLat[] | null => {
    const raw = edge.metadata_json?.presentation_path;
    if (!Array.isArray(raw) || raw.length < 2) return null;
    const path = raw.filter((p): p is LonLat => Array.isArray(p) && p.length === 2 && p.every((v) => typeof v === "number" && Number.isFinite(v)));
    return path.length === raw.length ? path : null;
  };
  for (const edge of edges) {
    const from = byId.get(edge.from_node_id);
    const to = byId.get(edge.to_node_id);
    if (!from || !to) continue;
    const meta = edge.metadata_json ?? {};
    if (edge.edge_type === "market_area_link") {
      const operators = new Set(Array.isArray(meta.operators) ? meta.operators.map(String) : []);
      add(from.id, { path: drawn(edge) ?? straight(from, to), operators });
    } else if (edge.edge_type === "interconnector") {
      const pipelineOperator = typeof meta.operator_key === "string"
        ? meta.operator_key
        : typeof meta.pipeline === "string" ? meta.pipeline.replace(/^pipeline:/, "") : "";
      const operators = new Set(pipelineOperator ? [pipelineOperator] : []);
      const path = drawn(edge) ?? straight(from, to);
      add(from.id, { path, operators });
      add(to.id, { path: [...path].reverse(), operators });
    }
  }
  return sides;
}

export interface FlowLine {
  refId: string;
  /** Upstream to downstream, through the point: dashes move from start to end. */
  coordinates: LonLat[];
  gwhD: number;
}

/**
 * A flow's line through its point, oriented by the operator's side: entry flows into the
 * operator's side, exit out of it. Null when the operator is on no side the network lists, or
 * the other side is unknown: then no direction is claimed.
 */
export function orientFlow(flow: SceneFlow, at: LonLat, sides: Side[] | undefined, armKm = 60): FlowLine | null {
  if (!flow.operatorKey || !sides || sides.length < 2) return null;
  const own = sides.filter((side) => side.operators.has(flow.operatorKey as string));
  const other = sides.filter((side) => !side.operators.has(flow.operatorKey as string));
  if (own.length !== 1 || other.length < 1) return null;
  // Of several other sides, the one whose operators are listed (a real neighbour) first.
  const far = [...other].sort((a, b) => b.operators.size - a.operators.size)[0];
  const arm = (side: Side) => pathPrefix(side.path, Math.min(armKm, 0.45 * pathLengthKm(side.path)));
  const ownArm = arm(own[0]);
  const farArm = arm(far);
  if (ownArm.length < 2 || farArm.length < 2) return null;
  const into = flow.direction === "entry";
  const out = flow.direction === "exit";
  if (!into && !out) return null;
  const upstream = into ? farArm : ownArm;
  const downstream = into ? ownArm : farArm;
  return {
    refId: flow.refId,
    coordinates: [...[...upstream].reverse().slice(0, -1), at, ...downstream.slice(1)],
    gwhD: flow.gwhD,
  };
}

/** Line width in px from GWh/d: square root, 1 to 3.5 px against the largest flow drawn. A
 * flow is a thin moving line, never a band that hides the network under it. */
export function flowWidth(gwhD: number, largest: number): number {
  if (!(largest > 0) || !(gwhD > 0)) return 1;
  return Math.round((1 + 2.5 * Math.sqrt(gwhD / largest)) * 10) / 10;
}

export interface FlowLayers {
  lines: FC<Line>;
  /** A chevron at the downstream end of each line: the direction without motion. */
  chevrons: FC<Line>;
  /** Flows drawn with a direction, and those left as points because none could be found. */
  oriented: number;
  unoriented: number;
}

export function flowLayers(flows: SceneFlow[], nodes: NodeDTO[], edges: EdgeDTO[], project: Project): FlowLayers {
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const sides = pointSides(nodes, edges);
  // One line per point: the larger of its directions (an entry and an exit at one point net
  // to the larger; both are on the point's card).
  const strongest = new Map<string, SceneFlow>();
  for (const flow of flows) {
    const held = strongest.get(flow.refId);
    if (!held || flow.gwhD > held.gwhD) strongest.set(flow.refId, flow);
  }
  const oriented: Array<{ flow: SceneFlow; line: FlowLine }> = [];
  let unoriented = 0;
  for (const flow of strongest.values()) {
    const node = byId.get(flow.refId);
    const line = node ? orientFlow(flow, [node.lon, node.lat], sides.get(flow.refId)) : null;
    if (line) oriented.push({ flow, line });
    else unoriented += 1;
  }
  const largest = Math.max(0, ...oriented.map((item) => item.flow.gwhD));
  const lines: Array<Feature<Line>> = [];
  const chevrons: Array<Feature<Line>> = [];
  for (const { flow, line } of oriented) {
    const properties: Props = {
      kind: "flow",
      id: `${flow.refId}|${flow.direction}`,
      ref: flow.refId,
      name: flow.pointName,
      direction: flow.direction,
      gwh_d: flow.gwhD,
      gas_day: flow.gasDay,
      width: flowWidth(flow.gwhD, largest),
    };
    lines.push({ type: "Feature", properties, geometry: { type: "LineString", coordinates: line.coordinates.map(([lon, lat]) => project(lon, lat)) } });
    const chevron = chevronAt(line.coordinates);
    if (chevron) chevrons.push({ type: "Feature", properties, geometry: { type: "LineString", coordinates: chevron.map(([lon, lat]) => project(lon, lat)) } });
  }
  return { lines: fc(lines), chevrons: fc(chevrons), oriented: oriented.length, unoriented };
}

/** A small open arrowhead at a line's end, pointing along its last segment. */
export function chevronAt(line: LonLat[], sizeKm = 14): LonLat[] | null {
  if (line.length < 2) return null;
  const tip = line[line.length - 1];
  const before = line[line.length - 2];
  const kmX = 111.32 * Math.cos(tip[1] * RAD);
  const dx = (tip[0] - before[0]) * kmX;
  const dy = (tip[1] - before[1]) * 111.32;
  const length = Math.hypot(dx, dy);
  if (!(length > 0) || !(kmX > 0)) return null;
  const ux = dx / length;
  const uy = dy / length;
  const back = (angle: number): LonLat => {
    const cos = Math.cos(angle);
    const sin = Math.sin(angle);
    const rx = -(ux * cos - uy * sin) * sizeKm;
    const ry = -(ux * sin + uy * cos) * sizeKm;
    return [tip[0] + rx / kmX, tip[1] + ry / 111.32];
  };
  return [back(Math.PI / 6), tip, back(-Math.PI / 6)];
}

// ---------------------------------------------------------------------------------------------
// Motion

/**
 * The dash steps of a flow line: drawn in turn, the gap travels from the line's start to its
 * end, which is the gas's direction. MapLibre cannot offset a dash, so the pattern itself moves.
 */
export const FLOW_DASH_STEPS: number[][] = [
  [0, 4, 3],
  [0.5, 4, 2.5],
  [1, 4, 2],
  [1.5, 4, 1.5],
  [2, 4, 1],
  [2.5, 4, 0.5],
  [3, 4, 0],
  [0, 0.5, 3, 3.5],
  [0, 1, 3, 3],
  [0, 1.5, 3, 2.5],
  [0, 2, 3, 2],
  [0, 2.5, 3, 1.5],
  [0, 3, 3, 1],
  [0, 3.5, 3, 0.5],
];
/** The static pattern under reduced motion (and while the page is hidden). */
export const FLOW_DASH_STATIC = [3, 1.5];
/** One step per this many ms: a calm pace, about one dash cycle a second. */
export const FLOW_STEP_MS = 70;

export type FlowMotion = "animated" | "static";
export function flowMotion(reducedMotion: boolean, pageVisible = true): FlowMotion {
  return reducedMotion || !pageVisible ? "static" : "animated";
}

export function flowDashAt(elapsedMs: number, motion: FlowMotion): number[] {
  if (motion === "static") return FLOW_DASH_STATIC;
  return FLOW_DASH_STEPS[Math.floor(Math.max(0, elapsedMs) / FLOW_STEP_MS) % FLOW_DASH_STEPS.length];
}

/** Points moved between two reads ease from where they were: the share of the way at `t`. */
export function tweenPoints(
  from: ReadonlyMap<string, LonLat>,
  to: FC<Point>,
  t: number,
): FC<Point> {
  const k = Math.min(1, Math.max(0, t));
  return fc(
    to.features.map((feature) => {
      const before = from.get(String(feature.properties.id) + "|" + String(feature.properties.basis));
      if (!before || k >= 1) return feature;
      const [x, y] = feature.geometry.coordinates;
      return {
        ...feature,
        geometry: { type: "Point" as const, coordinates: [before[0] + (x - before[0]) * k, before[1] + (y - before[1]) * k] as LonLat },
      };
    }),
  );
}

/** Where each point of a layer is now, keyed as `tweenPoints` reads it. */
export function pointIndex(collection: FC<Point>): Map<string, LonLat> {
  return new Map(collection.features.map((feature) => [
    String(feature.properties.id) + "|" + String(feature.properties.basis),
    feature.geometry.coordinates,
  ]));
}
