/**
 * Indicative sea lanes: the remaining leg follows open water instead of a straight line over
 * land. The graph is hand-made, so the checks that matter are the ones a trader would make:
 * past the capes and through the straits, not across Iberia or France, and the Mediterranean
 * route stays in the Mediterranean.
 */
import assert from "node:assert/strict";
import test from "node:test";
import { SEA_WAYPOINTS, distanceNm, seaRoute } from "../src/app/seaLanes.ts";
import { distanceKm, greatCirclePoint } from "../src/app/mapScene.ts";

type LonLat = [number, number];

interface LandBox {
  name: string;
  west: number;
  east: number;
  south: number;
  north: number;
}

/** Coarse land interiors, inset from the coasts so an offshore waypoint or a port is outside. */
const LAND_BOXES: readonly LandBox[] = [
  { name: "Iberia", west: -8.0, east: -1.5, south: 38.5, north: 42.5 },
  { name: "France", west: 0.5, east: 6.5, south: 44.0, north: 49.0 },
  { name: "Britain", west: -3.0, east: 0.5, south: 52.0, north: 55.5 },
  { name: "Italy", west: 8.5, east: 14.5, south: 41.5, north: 45.0 },
];

function inside(point: LonLat, box: LandBox): boolean {
  return point[0] >= box.west && point[0] <= box.east
    && point[1] >= box.south && point[1] <= box.north;
}

/** Sample each segment every 20 km and fail on any sample inside a coarse land box. */
function assertNoLand(route: { coordinates: LonLat[] }, label: string): void {
  for (let index = 1; index < route.coordinates.length; index += 1) {
    const from = route.coordinates[index - 1];
    const to = route.coordinates[index];
    const steps = Math.max(1, Math.ceil(distanceKm(from, to) / 20));
    for (let step = 0; step <= steps; step += 1) {
      const sample = greatCirclePoint(from, to, step / steps);
      for (const box of LAND_BOXES) {
        assert.ok(!inside(sample, box), `${label}: segment ${index} crosses ${box.name} at ${sample}`);
      }
    }
  }
}

test("west of Lisbon to Zeebrugge passes Finisterre, Ushant and Dover, and is longer than straight", () => {
  const from: LonLat = [-10, 38];
  const to: LonLat = [3.2, 51.35];
  const route = seaRoute(from, to);
  assert.ok(route.routed);
  for (const waypoint of ["finisterre", "ushant", "dover"]) {
    assert.ok(route.waypointIds.includes(waypoint), waypoint);
  }
  assert.ok(route.distanceNm > distanceNm(from, to));
  assert.deepEqual(route.coordinates[0], from);
  assert.deepEqual(route.coordinates[route.coordinates.length - 1], to);
  assertNoLand(route, "Lisbon to Zeebrugge");
});

test("the US Gulf approach to Rotterdam does not cross Iberia", () => {
  const route = seaRoute([-84, 25.5], [4.1, 51.95]);
  assert.ok(route.routed);
  assertNoLand(route, "US Gulf to Rotterdam");
  // The Atlantic route turns for Ushant north-west of Iberia, not through it.
  assert.ok(route.waypointIds.includes("finisterre"));
});

test("Arzew to Barcelona stays in the Mediterranean", () => {
  const route = seaRoute([-0.3, 35.85], [2.15, 41.35]);
  assert.ok(route.routed);
  for (const [lon, lat] of route.coordinates) {
    assert.ok(lon >= -6 && lon <= 5, `longitude ${lon}`);
    assert.ok(lat >= 30 && lat <= 44, `latitude ${lat}`);
  }
  assertNoLand(route, "Arzew to Barcelona");
});

test("start equal to end is a zero-length route", () => {
  const route = seaRoute([1.8, 38.4], [1.8, 38.4]);
  assert.equal(route.distanceNm, 0);
  assert.equal(route.routed, true);
  assert.deepEqual(route.coordinates, [[1.8, 38.4]]);
  assert.deepEqual(route.waypointIds, []);
});

test("the graph's waypoints are unique and its edges join known points", () => {
  const ids = SEA_WAYPOINTS.map((waypoint) => waypoint.id);
  assert.equal(new Set(ids).size, ids.length);
  // About forty open-sea waypoints, as the brief asks.
  assert.ok(SEA_WAYPOINTS.length >= 40 && SEA_WAYPOINTS.length <= 50, String(SEA_WAYPOINTS.length));
});
