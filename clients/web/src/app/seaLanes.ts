/**
 * Indicative sea lanes for a cargo's remaining leg.
 *
 * A dashed line from a vessel to its terminal used to be one straight segment, which crossed
 * land (a ship west of Portugal bound for Zeebrugge was drawn over Spain and France). This
 * module holds a hand-made graph of open-sea waypoints around Europe and a shortest-path walk
 * (great-circle lengths) over it. It is presentation and ETA arithmetic only: no surveyed route,
 * no weather, no vessel draft, and nothing is priced from it.
 *
 * The graph is coarse on purpose:
 * - waypoints sit in open water (strait centres, capes approached offshore, sea-lane junctions);
 * - an edge exists only where its straight segment stays at sea by inspection;
 * - a start or end point is joined to its nearest waypoints whose connecting segment stays out
 *   of a small set of coarse land interiors; if no waypoint is reachable the line stays straight
 *   and `routed` is false, so the caller can say so rather than pretend.
 *
 * Distances are great-circle nautical miles (1 nm = 1.852 km).
 */

export type SeaPoint = [number, number];

export interface SeaWaypoint {
  /** Stable id, used by tests and to read a route's waypoint sequence. */
  id: string;
  lon: number;
  lat: number;
}

const EARTH_RADIUS_NM = 3440.065;
const rad = (degrees: number) => (degrees * Math.PI) / 180;

/** Great-circle distance in nautical miles. */
export function distanceNm(from: SeaPoint, to: SeaPoint): number {
  const [lon1, lat1] = [rad(from[0]), rad(from[1])];
  const [lon2, lat2] = [rad(to[0]), rad(to[1])];
  const a = Math.sin((lat2 - lat1) / 2) ** 2
    + Math.cos(lat1) * Math.cos(lat2) * Math.sin((lon2 - lon1) / 2) ** 2;
  return 2 * EARTH_RADIUS_NM * Math.asin(Math.min(1, Math.sqrt(a)));
}

/** The point a fraction of the way along the great circle from `a` to `b`. */
function pointAlong(a: SeaPoint, b: SeaPoint, fraction: number): SeaPoint {
  const f = Math.min(1, Math.max(0, fraction));
  const [lon1, lat1] = [rad(a[0]), rad(a[1])];
  const [lon2, lat2] = [rad(b[0]), rad(b[1])];
  const d = distanceNm(a, b) / EARTH_RADIUS_NM;
  if (d < 1e-9) return [a[0], a[1]];
  const A = Math.sin((1 - f) * d) / Math.sin(d);
  const B = Math.sin(f * d) / Math.sin(d);
  const x = A * Math.cos(lat1) * Math.cos(lon1) + B * Math.cos(lat2) * Math.cos(lon2);
  const y = A * Math.cos(lat1) * Math.sin(lon1) + B * Math.cos(lat2) * Math.sin(lon2);
  const z = A * Math.sin(lat1) + B * Math.sin(lat2);
  return [Math.atan2(y, x) / rad(1), Math.atan2(z, Math.sqrt(x * x + y * y)) / rad(1)];
}

/**
 * Open-sea waypoints around Europe, the North Atlantic approaches and the Mediterranean.
 * Positions are approximate sea-lane points for drawing, not navigational data.
 */
export const SEA_WAYPOINTS: readonly SeaWaypoint[] = [
  // North Atlantic approaches.
  { id: "us_gulf_approach", lon: -84.0, lat: 25.5 },
  { id: "mid_atlantic_us", lon: -45.0, lat: 40.0 },
  { id: "azores", lon: -28.0, lat: 38.0 },
  { id: "west_africa_approach", lon: -17.5, lat: 24.0 },
  { id: "canary", lon: -16.0, lat: 28.0 },

  // Western approaches: Portugal, Biscay, the Channel.
  { id: "lisbon_approach", lon: -9.7, lat: 38.7 },
  { id: "cape_st_vincent", lon: -9.3, lat: 36.9 },
  { id: "finisterre", lon: -9.9, lat: 43.6 },
  { id: "biscay", lon: -7.0, lat: 45.5 },
  { id: "ushant", lon: -5.2, lat: 48.6 },
  { id: "channel_west", lon: -3.4, lat: 49.8 },
  { id: "english_channel_mid", lon: -0.5, lat: 50.0 },
  { id: "dover", lon: 1.7, lat: 51.05 },

  // Southern North Sea and the Dutch/Belgian approaches.
  { id: "southern_north_sea", lon: 2.8, lat: 52.1 },
  { id: "rotterdam_approach", lon: 3.7, lat: 52.0 },
  { id: "zeebrugge_approach", lon: 2.9, lat: 51.55 },

  // North Sea northward, Skagerrak, Kattegat and the Baltic approaches.
  { id: "north_sea_north", lon: 2.5, lat: 56.5 },
  { id: "skagerrak", lon: 7.8, lat: 57.7 },
  { id: "kattegat", lon: 10.8, lat: 57.1 },
  { id: "baltic_approaches", lon: 12.6, lat: 55.3 },
  { id: "norwegian_coast_south", lon: 4.5, lat: 58.5 },
  { id: "norwegian_coast", lon: 3.5, lat: 60.5 },
  { id: "norwegian_sea", lon: 1.0, lat: 63.0 },

  // Northern Scotland and the Irish Sea.
  { id: "fair_isle", lon: -2.5, lat: 59.0 },
  { id: "pentland_firth", lon: -3.1, lat: 58.7 },
  { id: "north_minch", lon: -4.0, lat: 59.0 },
  { id: "hebrides", lon: -6.0, lat: 57.0 },
  { id: "north_channel", lon: -5.7, lat: 54.7 },
  { id: "irish_sea", lon: -4.6, lat: 53.6 },
  { id: "st_georges_channel", lon: -5.2, lat: 51.3 },

  // Gibraltar and the western Mediterranean.
  { id: "gibraltar_west", lon: -6.0, lat: 35.85 },
  { id: "gibraltar_east", lon: -5.0, lat: 36.05 },
  { id: "alboran", lon: -3.0, lat: 36.3 },
  { id: "balearic", lon: 1.8, lat: 38.4 },
  { id: "barcelona_approach", lon: 2.6, lat: 40.9 },
  { id: "gulf_of_lion", lon: 4.0, lat: 42.5 },

  // Tyrrhenian, Sicily, the Adriatic mouth and the eastern Mediterranean.
  { id: "tyrrhenian", lon: 10.0, lat: 39.0 },
  { id: "sicily_strait", lon: 12.0, lat: 37.2 },
  { id: "tunisia", lon: 11.5, lat: 37.0 },
  { id: "ionian", lon: 18.5, lat: 37.5 },
  { id: "adriatic_mouth", lon: 18.7, lat: 40.1 },
  { id: "aegean", lon: 24.5, lat: 37.5 },
  { id: "dardanelles_approach", lon: 25.6, lat: 40.1 },
  { id: "east_med", lon: 28.0, lat: 34.0 },
  { id: "suez_approach", lon: 32.2, lat: 31.6 },
];

/** Edges between waypoints whose straight segment stays at sea (by inspection). */
export const SEA_LANES: ReadonlyArray<readonly [string, string]> = [
  // Atlantic crossings and the approaches.
  ["us_gulf_approach", "mid_atlantic_us"],
  ["mid_atlantic_us", "azores"],
  ["mid_atlantic_us", "west_africa_approach"],
  ["west_africa_approach", "azores"],
  ["west_africa_approach", "canary"],
  ["azores", "finisterre"],
  ["canary", "lisbon_approach"],
  ["canary", "cape_st_vincent"],
  ["canary", "gibraltar_west"],
  ["lisbon_approach", "cape_st_vincent"],
  ["lisbon_approach", "finisterre"],
  ["cape_st_vincent", "gibraltar_west"],

  // Biscay, Ushant, the Channel and the Dover strait.
  ["finisterre", "biscay"],
  ["biscay", "ushant"],
  ["finisterre", "ushant"],
  ["ushant", "channel_west"],
  ["channel_west", "english_channel_mid"],
  ["english_channel_mid", "dover"],
  ["channel_west", "st_georges_channel"],

  // Southern North Sea and the Low Countries.
  ["dover", "southern_north_sea"],
  ["southern_north_sea", "rotterdam_approach"],
  ["southern_north_sea", "zeebrugge_approach"],

  // North Sea northward, Skagerrak, Kattegat and the Baltic approaches.
  ["southern_north_sea", "north_sea_north"],
  ["southern_north_sea", "skagerrak"],
  ["north_sea_north", "skagerrak"],
  ["north_sea_north", "fair_isle"],
  ["skagerrak", "kattegat"],
  ["kattegat", "baltic_approaches"],
  ["skagerrak", "norwegian_coast_south"],
  ["norwegian_coast_south", "norwegian_coast"],
  ["norwegian_coast", "norwegian_sea"],
  ["norwegian_sea", "fair_isle"],

  // Northern Scotland, the Minches and the Irish Sea.
  ["fair_isle", "pentland_firth"],
  ["pentland_firth", "north_minch"],
  ["north_minch", "hebrides"],
  ["hebrides", "north_channel"],
  ["north_channel", "irish_sea"],
  ["irish_sea", "st_georges_channel"],

  // Gibraltar and the Mediterranean.
  ["gibraltar_west", "gibraltar_east"],
  ["gibraltar_east", "alboran"],
  ["alboran", "balearic"],
  ["balearic", "barcelona_approach"],
  ["balearic", "gulf_of_lion"],
  ["gulf_of_lion", "tyrrhenian"],
  ["tyrrhenian", "sicily_strait"],
  ["sicily_strait", "tunisia"],
  ["sicily_strait", "ionian"],
  ["ionian", "adriatic_mouth"],
  ["ionian", "aegean"],
  ["aegean", "dardanelles_approach"],
  ["aegean", "east_med"],
  ["dardanelles_approach", "east_med"],
  ["east_med", "suez_approach"],
];

export interface SeaRoute {
  /** [start, ...waypoints, end] as [lon, lat]; one point when start equals end. */
  coordinates: SeaPoint[];
  /** Path length in nautical miles. */
  distanceNm: number;
  /** Ids of the waypoints the path passes, in order. */
  waypointIds: string[];
  /** False when no sea path was found: the coordinates are then the straight segment. */
  routed: boolean;
}

interface LandBox {
  west: number;
  east: number;
  south: number;
  north: number;
}

/**
 * Coarse land interiors, used only to reject an implausible start/end connection (a line from a
 * vessel to a waypoint on the other side of a peninsula). Deliberately inset from the coasts so
 * a terminal on the coast still connects offshore.
 */
const COARSE_LAND_BOXES: readonly LandBox[] = [
  { west: -8.0, east: -1.5, south: 38.5, north: 42.5 }, // Iberia
  { west: 0.5, east: 6.5, south: 44.0, north: 49.0 }, // France
  { west: -3.0, east: 0.5, south: 52.0, north: 55.5 }, // Britain
  { west: 8.5, east: 14.5, south: 41.5, north: 45.0 }, // Italy
  { west: 5.0, east: 12.0, south: 58.0, north: 64.0 }, // Norway
];

const INSIDE = (point: SeaPoint, box: LandBox): boolean =>
  point[0] >= box.west && point[0] <= box.east && point[1] >= box.south && point[1] <= box.north;

/** Whether a segment's great-circle samples pass through a coarse land box. */
function crossesLand(from: SeaPoint, to: SeaPoint): boolean {
  const steps = Math.max(1, Math.ceil((distanceNm(from, to) * 1.852) / 20));
  for (let index = 0; index <= steps; index += 1) {
    const sample = pointAlong(from, to, index / steps);
    if (COARSE_LAND_BOXES.some((box) => INSIDE(sample, box))) return true;
  }
  return false;
}

interface Neighbour {
  to: string;
  nm: number;
}

const WAYPOINT_BY_ID = new Map(SEA_WAYPOINTS.map((waypoint) => [waypoint.id, waypoint]));

function baseAdjacency(): Map<string, Neighbour[]> {
  const adjacency = new Map<string, Neighbour[]>();
  for (const waypoint of SEA_WAYPOINTS) adjacency.set(waypoint.id, []);
  for (const [a, b] of SEA_LANES) {
    const first = WAYPOINT_BY_ID.get(a);
    const second = WAYPOINT_BY_ID.get(b);
    if (!first || !second) continue;
    const nm = distanceNm([first.lon, first.lat], [second.lon, second.lat]);
    adjacency.get(a)!.push({ to: b, nm });
    adjacency.get(b)!.push({ to: a, nm });
  }
  return adjacency;
}

const ADJACENCY = baseAdjacency();

/** How many nearest clear waypoints a start or end is joined to. */
const APPROACH_WAYPOINTS = 4;

function nearestWaypoints(point: SeaPoint): Neighbour[] {
  const candidates = SEA_WAYPOINTS
    .map((waypoint) => ({
      id: waypoint.id,
      point: [waypoint.lon, waypoint.lat] as SeaPoint,
      nm: distanceNm(point, [waypoint.lon, waypoint.lat]),
    }))
    .sort((a, b) => a.nm - b.nm);
  const clear = candidates.filter((candidate) => !crossesLand(point, candidate.point));
  // A point far inland has no clear approach; the nearest ones still give a route to state.
  return (clear.length ? clear : candidates).slice(0, APPROACH_WAYPOINTS).map(({ id, nm }) => ({ to: id, nm }));
}

/** The shortest sea path from an arbitrary start to an arbitrary end. */
export function seaRoute(from: SeaPoint, to: SeaPoint): SeaRoute {
  if (from[0] === to[0] && from[1] === to[1]) {
    return { coordinates: [from], distanceNm: 0, waypointIds: [], routed: true };
  }
  const startId = "__start";
  const endId = "__end";
  const adjacency = new Map<string, Neighbour[]>();
  for (const [id, neighbours] of ADJACENCY) adjacency.set(id, [...neighbours]);
  adjacency.set(startId, nearestWaypoints(from));
  const approachesToEnd = nearestWaypoints(to);
  adjacency.set(endId, approachesToEnd);
  for (const approach of approachesToEnd) {
    const neighbours = adjacency.get(approach.to);
    if (neighbours) neighbours.push({ to: endId, nm: approach.nm });
    else adjacency.set(approach.to, [{ to: endId, nm: approach.nm }]);
  }

  const best = new Map<string, number>([[startId, 0]]);
  const previous = new Map<string, string>();
  const unvisited = new Set<string>([startId, endId, ...SEA_WAYPOINTS.map((waypoint) => waypoint.id)]);

  while (unvisited.size) {
    let current: string | null = null;
    let currentDistance = Infinity;
    for (const id of unvisited) {
      const value = best.get(id);
      if (value !== undefined && value < currentDistance) {
        current = id;
        currentDistance = value;
      }
    }
    if (current === null) break;
    unvisited.delete(current);
    if (current === endId) break;
    for (const neighbour of adjacency.get(current) ?? []) {
      if (!unvisited.has(neighbour.to)) continue;
      const candidate = currentDistance + neighbour.nm;
      if (candidate < (best.get(neighbour.to) ?? Infinity)) {
        best.set(neighbour.to, candidate);
        previous.set(neighbour.to, current);
      }
    }
  }

  const total = best.get(endId);
  if (total === undefined) {
    return {
      coordinates: [from, to],
      distanceNm: distanceNm(from, to),
      waypointIds: [],
      routed: false,
    };
  }
  const ids: string[] = [];
  let cursor: string | undefined = endId;
  while (cursor) {
    ids.push(cursor);
    cursor = previous.get(cursor);
  }
  ids.reverse();
  const coordinates: SeaPoint[] = [];
  for (const id of ids) {
    const point = id === startId
      ? from
      : id === endId
        ? to
        : (() => {
            const waypoint = WAYPOINT_BY_ID.get(id)!;
            return [waypoint.lon, waypoint.lat] as SeaPoint;
          })();
    const last = coordinates[coordinates.length - 1];
    if (!last || last[0] !== point[0] || last[1] !== point[1]) coordinates.push(point);
  }
  return {
    coordinates,
    distanceNm: total,
    waypointIds: ids.filter((id) => id !== startId && id !== endId),
    routed: true,
  };
}

/** The sea-route distance in nautical miles (straight-line when no route is found). */
export function seaDistanceNm(from: SeaPoint, to: SeaPoint): number {
  return seaRoute(from, to).distanceNm;
}
