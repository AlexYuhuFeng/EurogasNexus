import type { EdgeDTO, MapSituationDTO, NodeDTO } from "@/api/client";
import { flowsForDay } from "./mapScene.ts";

/**
 * Intensity on the flat map (owner review 2026-11-26): one metric at a time, each an entry in the
 * Layers menu with a small legend, each from stored data (rule 19), and a point with no figure
 * draws nothing. Exact comparison is the side panel's ranked list, not the map.
 *
 * - Flow: line width by GWh/d with an arrowhead for direction; at Europe zoom one net figure per
 *   border between market areas (`borderFlows`), point by point from regional zoom.
 * - Utilisation: the point's colour on a sequential ramp of flow / firm technical capacity
 *   (placeholder capacities skipped).
 * - Outage impact: a circle whose area is the capacity offline now.
 * - Storage and LNG: a circle whose area is the flow, coloured into the grid (withdrawal,
 *   send-out) or out of it (injection).
 */

export type IntensityMetric = "flow" | "utilisation" | "outage" | "storage";
export const INTENSITY_METRICS: readonly IntensityMetric[] = ["flow", "utilisation", "outage", "storage"];

/** Into the system (entry, withdrawal from storage, LNG send-out) or out of it (exit, injection). */
export type IntensityDirection = "in" | "out";

export interface IntensityDatum {
  id: string;
  name: string;
  at: [number, number];
  /** The figure in GWh/d (height). */
  value: number;
  direction: IntensityDirection | null;
  /** Flow against firm technical capacity (utilisation only). */
  ratio: number | null;
  gasDay: string | null;
  source: string;
}

/** Above this a published firm capacity for one point is a placeholder, not a figure
 * (application/map_assets.py, PLAUSIBLE_POINT_CAPACITY_GWH_D). */
export const PLAUSIBLE_POINT_CAPACITY_GWH_D = 3_000;

/** Below this zoom flow reads as one net figure per border; from it, point by point. */
export const BORDER_FLOWS_BELOW_ZOOM = 5;

const join = (items: Iterable<string>) => [...new Set(items)].filter(Boolean).sort().join(", ");

/** Firm technical capacity per point in GWh/d: the market-area links' published figure. */
function pointCapacities(edges: readonly EdgeDTO[]): Map<string, number> {
  const out = new Map<string, number>();
  for (const edge of edges) {
    const kwh = edge.metadata_json?.firm_technical_kwh_d;
    if (typeof kwh !== "number" || !(kwh > 0)) continue;
    const gwh = kwh / 1e6;
    if (gwh > PLAUSIBLE_POINT_CAPACITY_GWH_D) continue;
    out.set(edge.from_node_id, Math.max(out.get(edge.from_node_id) ?? 0, gwh));
  }
  return out;
}

/** One column per point and metric, from what the situation holds. */
export function intensityPoints(
  metric: IntensityMetric,
  input: { situation: MapSituationDTO | null; nodes: readonly NodeDTO[]; edges: readonly EdgeDTO[]; flowDay: string | null },
): IntensityDatum[] {
  const { situation, nodes, edges, flowDay } = input;
  if (!situation) return [];
  const byId = new Map(nodes.map((node) => [node.id, node]));
  if (metric === "flow" || metric === "utilisation") {
    // Entry and exit reported at one point are the same gas seen from each side: the larger is
    // the point's flow, and its side the direction.
    const sums = new Map<string, { entry: number; exit: number; name: string; day: string | null; sources: Set<string> }>();
    for (const flow of flowsForDay(situation, flowDay)) {
      const item = sums.get(flow.refId) ?? { entry: 0, exit: 0, name: flow.pointName, day: flow.gasDay, sources: new Set<string>() };
      if (flow.direction === "exit") item.exit += flow.gwhD;
      else if (flow.direction === "entry") item.entry += flow.gwhD;
      else continue;
      item.sources.add(flow.sourceSystem);
      sums.set(flow.refId, item);
    }
    const capacities = metric === "utilisation" ? pointCapacities(edges) : null;
    const out: IntensityDatum[] = [];
    for (const [refId, item] of sums) {
      const node = byId.get(refId);
      if (!node || !Number.isFinite(node.lon) || !Number.isFinite(node.lat)) continue;
      const value = Math.max(item.entry, item.exit);
      if (!(value > 0)) continue;
      let ratio: number | null = null;
      if (capacities) {
        const capacity = capacities.get(refId);
        if (!capacity) continue;
        ratio = value / capacity;
      }
      out.push({
        id: refId,
        name: node.name,
        at: [node.lon, node.lat],
        value,
        direction: item.entry >= item.exit ? "in" : "out",
        ratio,
        gasDay: item.day ?? flowDay,
        source: join(item.sources),
      });
    }
    return out;
  }
  if (metric === "outage") {
    return situation.outages
      .filter((outage) => outage.status === "active" && (outage.unavailable_gwh_d ?? 0) > 0)
      .map((outage) => ({
        id: outage.event_id,
        name: outage.facility_name,
        at: [outage.location.lon, outage.location.lat] as [number, number],
        value: outage.unavailable_gwh_d as number,
        direction: null,
        ratio: null,
        gasDay: outage.start_utc ? outage.start_utc.slice(0, 10) : null,
        source: outage.source_system,
      }));
  }
  // Storage and LNG: the site's newest closed day. ENTSOG's entry at a storage or LNG point is
  // gas into the grid (withdrawal, send-out); exit is gas out of it (injection).
  const out: IntensityDatum[] = [];
  for (const asset of situation.assets ?? []) {
    const entry = asset.flow.filter((flow) => flow.direction === "entry").reduce((sum, flow) => sum + flow.gwh_d, 0);
    const exit = asset.flow.filter((flow) => flow.direction === "exit").reduce((sum, flow) => sum + flow.gwh_d, 0);
    const value = Math.max(entry, exit);
    if (!(value > 0)) continue;
    out.push({
      id: asset.asset_id,
      name: asset.name,
      at: [asset.location.lon, asset.location.lat],
      value,
      direction: entry >= exit ? "in" : "out",
      ratio: null,
      gasDay: asset.flow.find((flow) => flow.gas_day)?.gas_day ?? null,
      source: join(asset.flow.map((flow) => flow.source_system)),
    });
  }
  return out;
}

/** One net flow across a border between two market areas, in GWh/d, from `fromId` to `toId`. */
export interface BorderFlow {
  id: string;
  fromId: string;
  toId: string;
  value: number;
  points: number;
  gasDay: string | null;
  source: string;
}

/**
 * The net flow across each border between market areas: each point's larger reported flow,
 * oriented by its operator's side (a market-area link lists the operators on its area's side),
 * summed per pair of areas and netted. A point whose operator is on no listed side adds nothing.
 */
export function borderFlows(
  input: { situation: MapSituationDTO | null; edges: readonly EdgeDTO[]; flowDay: string | null },
): BorderFlow[] {
  const { situation, edges, flowDay } = input;
  if (!situation) return [];
  const sides = new Map<string, Array<{ area: string; operators: Set<string> }>>();
  for (const edge of edges) {
    if (edge.edge_type !== "market_area_link") continue;
    const operators = new Set(Array.isArray(edge.metadata_json?.operators) ? (edge.metadata_json!.operators as unknown[]).map(String) : []);
    sides.set(edge.from_node_id, [...(sides.get(edge.from_node_id) ?? []), { area: edge.to_node_id, operators }]);
  }
  const strongest = new Map<string, ReturnType<typeof flowsForDay>[number]>();
  for (const flow of flowsForDay(situation, flowDay)) {
    const held = strongest.get(flow.refId);
    if (!held || flow.gwhD > held.gwhD) strongest.set(flow.refId, flow);
  }
  const borders = new Map<string, { a: string; b: string; net: number; points: number; days: Set<string>; sources: Set<string> }>();
  for (const flow of strongest.values()) {
    const pointSides = sides.get(flow.refId) ?? [];
    const own = pointSides.filter((side) => flow.operatorKey && side.operators.has(flow.operatorKey));
    const other = pointSides.filter((side) => !(flow.operatorKey && side.operators.has(flow.operatorKey)));
    if (own.length !== 1 || other.length !== 1 || own[0].area === other[0].area) continue;
    if (flow.direction !== "entry" && flow.direction !== "exit") continue;
    const [from, to] = flow.direction === "entry" ? [other[0].area, own[0].area] : [own[0].area, other[0].area];
    const [a, b] = [from, to].sort();
    const key = `${a}|${b}`;
    const item = borders.get(key) ?? { a, b, net: 0, points: 0, days: new Set<string>(), sources: new Set<string>() };
    item.net += from === a ? flow.gwhD : -flow.gwhD;
    item.points += 1;
    if (flow.gasDay) item.days.add(flow.gasDay);
    item.sources.add(flow.sourceSystem);
    borders.set(key, item);
  }
  return [...borders.entries()]
    .filter(([, item]) => Math.abs(item.net) > 0)
    .map(([key, item]) => ({
      id: key,
      fromId: item.net >= 0 ? item.a : item.b,
      toId: item.net >= 0 ? item.b : item.a,
      value: Math.abs(item.net),
      points: item.points,
      gasDay: [...item.days].sort().pop() ?? flowDay,
      source: join(item.sources),
    }));
}

/** A circle's radius in px whose area is the figure against the largest shown (4 to 22 px). */
export function intensityRadius(value: number, max: number): number {
  if (!(max > 0) || !(value > 0)) return 0;
  return Math.round((4 + 18 * Math.sqrt(Math.min(1, value / max))) * 10) / 10;
}

/** The colour of a mark: its direction, its utilisation band, or an outage. */
export function intensityColour(
  metric: IntensityMetric,
  datum: Pick<IntensityDatum, "direction" | "ratio">,
  palette: { into: string; out: string; outage: string; ramp: readonly string[] },
): string {
  if (metric === "outage") return palette.outage;
  if (metric === "utilisation") {
    const ratio = datum.ratio ?? 0;
    const band = ratio >= 0.9 ? 3 : ratio >= 0.7 ? 2 : ratio >= 0.4 ? 1 : 0;
    return palette.ramp[Math.min(band, palette.ramp.length - 1)];
  }
  return datum.direction === "out" ? palette.out : palette.into;
}

/** The ten largest figures of the metric, for the side panel's ranked list. */
export function rankIntensity(data: readonly IntensityDatum[], limit = 10): IntensityDatum[] {
  return [...data].sort((a, b) => b.value - a.value || a.name.localeCompare(b.name)).slice(0, limit);
}
