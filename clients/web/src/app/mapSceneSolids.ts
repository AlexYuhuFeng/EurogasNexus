import type { MapAssetDTO, MapCargoDTO, NodeDTO } from "@/api/client";
import {
  assetFigures,
  cargoPositions,
  columnHeightM,
  squareAround,
  type FC,
  type LonLat,
  type Project,
} from "./mapScene.ts";

/**
 * The 3D scene's solid marks (MAP-1, refined): hubs and network points stand as small hexagonal
 * pillars, LNG carriers as low hulls pointing where they sail, and every solid (the terminal and
 * storage columns included) casts a soft ground shadow away from one fixed light. Pure functions,
 * no map or DOM (tests/mapSceneSolids.test.ts).
 *
 * - Marks, not models: a hull is drawn at a symbol's size (tens of km), never to scale, and the
 *   layers stop at regional zoom where the map's own dot and card take over.
 * - The light: MapLibre's light at `SCENE_LIGHT`, anchored to the map, so lit faces and the
 *   shadows on the ground agree whatever the bearing. Shadows fall toward `SHADOW_BEARING_DEG`.
 * - Nothing invented: a hull's heading is the reported track's last leg, else the way to its
 *   destination, else north; a ship with no position draws no hull.
 */

const RAD = Math.PI / 180;
const KM_PER_DEG = 111.32;

/** MapLibre's light (anchor map): from the north-west, 40 degrees off vertical, soft. */
export const SCENE_LIGHT = { anchor: "map" as const, position: [1.15, 135, 40] as [number, number, number], intensity: 0.4 };
/** Where the ground shadows fall: away from the light, to the south-east. */
export const SHADOW_BEARING_DEG = 135;

/** Pillar and hull sizes (km on the ground, metres high). */
export const HUB_PILLAR = { radiusKm: 8, heightM: 28_000 };
export const POINT_PILLAR = { radiusKm: 3.5, heightM: 10_000 };
export const HULL = { lengthKm: 24, beamKm: 6, heightM: 5_000 };

/** Initial great-circle bearing from a to b, degrees clockwise from north, in [0, 360). */
export function bearingDeg(a: LonLat, b: LonLat): number {
  const [lon1, lat1] = [a[0] * RAD, a[1] * RAD];
  const [lon2, lat2] = [b[0] * RAD, b[1] * RAD];
  const y = Math.sin(lon2 - lon1) * Math.cos(lat2);
  const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(lon2 - lon1);
  if (Math.abs(x) < 1e-12 && Math.abs(y) < 1e-12) return 0;
  return (Math.atan2(y, x) / RAD + 360) % 360;
}

/** A local offset (km east, km north) from a point, in degrees. */
function offset([lon, lat]: LonLat, eastKm: number, northKm: number): LonLat {
  return [lon + eastKm / (KM_PER_DEG * Math.max(0.05, Math.cos(lat * RAD))), lat + northKm / KM_PER_DEG];
}

/** A regular polygon of `sides` around a point, closed. */
export function polygonAround(at: LonLat, radiusKm: number, sides = 6): LonLat[] {
  const ring: LonLat[] = [];
  for (let i = 0; i < sides; i += 1) {
    const angle = (i / sides) * 2 * Math.PI;
    ring.push(offset(at, radiusKm * Math.sin(angle), radiusKm * Math.cos(angle)));
  }
  ring.push(ring[0]);
  return ring;
}

/** A hull's footprint: a pointed bow at `headingDeg`, square stern, closed. */
export function hullRing(at: LonLat, headingDeg: number, lengthKm = HULL.lengthKm, beamKm = HULL.beamKm): LonLat[] {
  const h = headingDeg * RAD;
  const half = lengthKm / 2;
  const local: Array<[number, number]> = [
    [half, 0],
    [half * 0.45, beamKm / 2],
    [-half, beamKm / 2],
    [-half, -beamKm / 2],
    [half * 0.45, -beamKm / 2],
  ];
  const ring = local.map(([along, across]) => offset(
    at,
    along * Math.sin(h) + across * Math.cos(h),
    along * Math.cos(h) - across * Math.sin(h),
  ));
  ring.push(ring[0]);
  return ring;
}

/** Convex hull (monotone chain), closed. */
export function convexHull(points: LonLat[]): LonLat[] {
  const sorted = [...points].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  if (sorted.length < 3) return [...sorted, ...(sorted[0] ? [sorted[0]] : [])];
  const cross = (o: LonLat, a: LonLat, b: LonLat) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lower: LonLat[] = [];
  for (const p of sorted) {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) lower.pop();
    lower.push(p);
  }
  const upper: LonLat[] = [];
  for (let i = sorted.length - 1; i >= 0; i -= 1) {
    const p = sorted[i];
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) upper.pop();
    upper.push(p);
  }
  const hull = [...lower.slice(0, -1), ...upper.slice(0, -1)];
  hull.push(hull[0]);
  return hull;
}

/** A shadow's length on the ground: a quarter of the solid's height, 1.5 to 18 km. */
export function shadowLengthKm(heightM: number): number {
  return Math.min(18, Math.max(1.5, (heightM / 1000) * 0.25));
}

/** The ground shadow of a solid: its footprint swept away from the light. */
export function shadowRing(footprint: LonLat[], heightM: number, bearing = SHADOW_BEARING_DEG): LonLat[] {
  const length = shadowLengthKm(heightM);
  const east = length * Math.sin(bearing * RAD);
  const north = length * Math.cos(bearing * RAD);
  const open = footprint.slice(0, -1);
  return convexHull([...open, ...open.map((point) => offset(point, east, north))]);
}

type Props = Record<string, string | number | boolean | null>;
type Polygon = { type: "Polygon"; coordinates: LonLat[][] };
type Feature = { type: "Feature"; properties: Props; geometry: Polygon };
const polygon = (properties: Props, ring: LonLat[], project: Project): Feature => ({
  type: "Feature",
  properties,
  geometry: { type: "Polygon", coordinates: [ring.map(([lon, lat]) => project(lon, lat))] },
});
const fc = (features: Feature[]): FC<Polygon> => ({ type: "FeatureCollection", features });

/** Node types that stand as pillars; LNG nodes are the terminals' own columns. */
const PILLAR_TYPES = new Set(["hub", "interconnection", "entry_point"]);

/**
 * Pillars for hubs and network points, and the ground shadows of pillars and site columns.
 * `part` is "solid" or "shadow"; `overview` is 1 for marks that stand at the overview zoom
 * (hubs), 0 for those that rise from regional zoom (points).
 */
export function siteSolids(nodes: NodeDTO[], assets: MapAssetDTO[] | undefined, project: Project): FC<Polygon> {
  const features: Feature[] = [];
  for (const node of nodes) {
    if (!PILLAR_TYPES.has(node.node_type) || !Number.isFinite(node.lon) || !Number.isFinite(node.lat)) continue;
    const hub = node.node_type === "hub";
    const size = hub ? HUB_PILLAR : POINT_PILLAR;
    const at: LonLat = [node.lon, node.lat];
    const footprint = polygonAround(at, size.radiusKm);
    const props: Props = { kind: "pillar", id: node.id, node_type: node.node_type, name: node.name, height: size.heightM, overview: hub ? 1 : 0 };
    features.push(polygon({ ...props, part: "shadow" }, shadowRing(footprint, size.heightM), project));
    features.push(polygon({ ...props, part: "solid" }, footprint, project));
  }
  const list = assets ?? [];
  const figures = list.map(assetFigures);
  const largest = Math.max(0, ...figures.map((item) => item.capacityGwhD ?? 0));
  list.forEach((asset, index) => {
    const height = columnHeightM(figures[index].capacityGwhD, largest);
    const footprint = squareAround([asset.location.lon, asset.location.lat], 10);
    features.push(polygon(
      { kind: "asset", id: asset.asset_id, asset_kind: asset.kind, part: "shadow", height, overview: 1 },
      shadowRing(footprint, height),
      project,
    ));
  });
  return fc(features);
}

export interface ShipMark {
  /** cargo id and basis: one hull per drawn position. */
  key: string;
  id: string;
  at: LonLat;
  headingDeg: number;
  own: boolean;
  basis: "reported" | "at_port" | "estimated";
  name: string;
}

/** Which way a vessel points: the reported track's last leg, else toward its destination. */
export function shipHeading(cargo: MapCargoDTO, at: LonLat, from?: LonLat): number {
  const track = cargo.track ?? [];
  if (track.length >= 2) {
    const a = track[track.length - 2];
    const b = track[track.length - 1];
    if (a[0] !== b[0] || a[1] !== b[1]) return bearingDeg(a, b);
  }
  const destination = cargo.destination ? [cargo.destination.lon, cargo.destination.lat] as LonLat : null;
  if (destination && (destination[0] !== at[0] || destination[1] !== at[1])) return bearingDeg(at, destination);
  if (from && (from[0] !== at[0] || from[1] !== at[1])) return bearingDeg(from, at);
  const origin = cargo.origin ? [cargo.origin.lon, cargo.origin.lat] as LonLat : null;
  if (origin && (origin[0] !== at[0] || origin[1] !== at[1])) return bearingDeg(origin, at);
  return 0;
}

/** The hulls to draw: each cargo's reported or at-port position, and its estimate if any. */
export function shipMarks(cargoes: MapCargoDTO[] | undefined, now: Date): ShipMark[] {
  const marks: ShipMark[] = [];
  for (const cargo of cargoes ?? []) {
    if (cargo.status === "delivered") continue;
    const { primary, estimate } = cargoPositions(cargo, now);
    if (primary) {
      marks.push({
        key: `${cargo.cargo_id}|${primary.basis}`,
        id: cargo.cargo_id,
        at: primary.at,
        headingDeg: shipHeading(cargo, primary.at),
        own: cargo.own,
        basis: primary.basis,
        name: cargo.vessel_name,
      });
    }
    if (estimate) {
      marks.push({
        key: `${cargo.cargo_id}|estimated`,
        id: cargo.cargo_id,
        at: estimate.at,
        // An estimate lies on the great circle to the destination: it points along it.
        headingDeg: cargo.destination ? bearingDeg(estimate.at, [cargo.destination.lon, cargo.destination.lat]) : shipHeading(cargo, estimate.at, estimate.fromAt),
        own: cargo.own,
        basis: "estimated",
        name: cargo.vessel_name,
      });
    }
  }
  return marks;
}

/** Hulls and their shadows; estimated hulls stand lower (half height). */
export function shipSolids(marks: ShipMark[], project: Project): FC<Polygon> {
  const features: Feature[] = [];
  for (const mark of marks) {
    const footprint = hullRing(mark.at, mark.headingDeg);
    const height = mark.basis === "estimated" ? HULL.heightM / 2 : HULL.heightM;
    const props: Props = { kind: "ship", id: mark.id, own: mark.own, basis: mark.basis, name: mark.name, height };
    features.push(polygon({ ...props, part: "shadow" }, shadowRing(footprint, height), project));
    features.push(polygon({ ...props, part: "solid" }, footprint, project));
  }
  return fc(features);
}

/** Shortest turn from one heading to another, eased by `k` (0..1). */
export function turnHeading(from: number, to: number, k: number): number {
  const delta = ((to - from + 540) % 360) - 180;
  return (from + delta * Math.min(1, Math.max(0, k)) + 360) % 360;
}

/** Marks eased from where they were drawn (`before`, by key) toward `to`, a share `k` of the way. */
export function tweenShips(before: ReadonlyMap<string, ShipMark>, to: ShipMark[], k: number): ShipMark[] {
  const t = Math.min(1, Math.max(0, k));
  if (t >= 1) return to;
  return to.map((mark) => {
    const was = before.get(mark.key);
    if (!was) return mark;
    return {
      ...mark,
      at: [was.at[0] + (mark.at[0] - was.at[0]) * t, was.at[1] + (mark.at[1] - was.at[1]) * t] as LonLat,
      headingDeg: turnHeading(was.headingDeg, mark.headingDeg, t),
    };
  });
}
