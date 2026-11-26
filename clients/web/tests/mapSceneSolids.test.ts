/**
 * The 3D scene's solids: pillars for hubs and network points, hulls that point where a vessel
 * sails and ease to a new read, shadows away from the one light, nothing drawn for a vessel
 * with no position. Also the address that opens the map on one place.
 */
import assert from "node:assert/strict";
import test from "node:test";
import type { MapAssetDTO, MapCargoDTO, NodeDTO } from "../src/api/client.ts";
import { distanceKm } from "../src/app/mapScene.ts";
import {
  HULL,
  HUB_PILLAR,
  POINT_PILLAR,
  SCENE_LIGHT,
  SHADOW_BEARING_DEG,
  bearingDeg,
  convexHull,
  hullRing,
  polygonAround,
  shadowLengthKm,
  shadowRing,
  shipHeading,
  shipMarks,
  shipSolids,
  siteSolids,
  turnHeading,
  tweenShips,
} from "../src/app/mapSceneSolids.ts";
import { networkPlaceFromSearch, networkPlaceSearch } from "../src/app/model/networkPanelModel.ts";

const identity = (lon: number, lat: number): [number, number] => [lon, lat];
const NOW = new Date("2026-11-12T12:00:00Z");

const node = (id: string, node_type: string, lon = 4.5, lat = 52): NodeDTO => ({
  id, name: id.toUpperCase(), node_type, country: "NL", lat, lon, capacity_boe_d: null,
});

const laden = (overrides: Partial<MapCargoDTO> = {}): MapCargoDTO => ({
  cargo_id: "C1", vessel_name: "Arctic Voyager", vessel_imo: null, status: "laden", load_port: "Hammerfest",
  departed_at_utc: "2026-11-10T12:00:00Z", destination_terminal: "Gate", eta_utc: "2026-11-14T12:00:00Z",
  position_at_utc: null, volume_m3: null, energy_gwh: 950, own: true, book_id: "uk", source_system: "ETRM",
  origin: { lon: 23.6, lat: 70.68 }, position: null, destination: { lon: 4.03, lat: 51.95 }, track: [],
  position_basis: null, eta: null,
  ...overrides,
});

test("bearings run clockwise from north", () => {
  assert.ok(Math.abs(bearingDeg([0, 0], [0, 1]) - 0) < 1e-6);
  assert.ok(Math.abs(bearingDeg([0, 0], [1, 0]) - 90) < 1e-6);
  assert.ok(Math.abs(bearingDeg([0, 1], [0, 0]) - 180) < 1e-6);
  assert.ok(Math.abs(bearingDeg([1, 0], [0, 0]) - 270) < 1e-6);
});

test("a hull's bow points along its heading and its length is the symbol's", () => {
  const at: [number, number] = [4, 54];
  const ring = hullRing(at, 90);
  assert.equal(ring.length, 6);
  assert.deepEqual(ring[0], ring[ring.length - 1]);
  // Bow due east of the centre, half a length away.
  assert.ok(Math.abs(bearingDeg(at, ring[0]) - 90) < 0.5);
  assert.ok(Math.abs(distanceKm(at, ring[0]) - HULL.lengthKm / 2) < 0.2);
});

test("hubs and points stand as pillars; LNG nodes are left to the terminal columns", () => {
  const solids = siteSolids([node("ttf", "hub"), node("ip1", "interconnection"), node("lng1", "lng"), node("x", "city")], [], identity);
  const parts = solids.features.map((feature) => `${feature.properties.id}:${feature.properties.part}`);
  assert.deepEqual(parts, ["ttf:shadow", "ttf:solid", "ip1:shadow", "ip1:solid"]);
  const hub = solids.features.find((feature) => feature.properties.id === "ttf" && feature.properties.part === "solid");
  const point = solids.features.find((feature) => feature.properties.id === "ip1" && feature.properties.part === "solid");
  assert.equal(hub?.properties.height, HUB_PILLAR.heightM);
  assert.equal(hub?.properties.overview, 1);
  assert.equal(point?.properties.height, POINT_PILLAR.heightM);
  // Points rise from regional zoom; at the overview only hubs stand.
  assert.equal(point?.properties.overview, 0);
});

test("a site column casts a shadow too, filtered by its kind like the column", () => {
  const asset: MapAssetDTO = {
    asset_id: "entsog-lng-00027", kind: "lng_terminal", name: "Gate", country: "NL", eic: null,
    location: { lon: 4.03, lat: 51.95 }, capacity: [], flow: [], stock: null,
  };
  const solids = siteSolids([], [asset], identity);
  assert.equal(solids.features.length, 1);
  assert.equal(solids.features[0].properties.part, "shadow");
  assert.equal(solids.features[0].properties.asset_kind, "lng_terminal");
});

test("shadows fall away from the light, short and capped", () => {
  // MapLibre's light at azimuth 135 shines from the north-west; shadows go south-east.
  assert.equal(SCENE_LIGHT.anchor, "map");
  assert.equal(SCENE_LIGHT.position[1], 135);
  assert.equal(SHADOW_BEARING_DEG, 135);
  assert.equal(shadowLengthKm(1_000), 1.5);
  assert.equal(shadowLengthKm(40_000), 10);
  assert.equal(shadowLengthKm(1_000_000), 18);
  const at: [number, number] = [4, 52];
  const footprint = polygonAround(at, 4);
  const shadow = shadowRing(footprint, 40_000);
  const centroid = shadow.slice(0, -1).reduce((sum, p) => [sum[0] + p[0], sum[1] + p[1]], [0, 0]).map((v) => v / (shadow.length - 1));
  const towards = bearingDeg(at, [centroid[0], centroid[1]]);
  assert.ok(towards > 100 && towards < 170, `shadow lies to the south-east (${towards})`);
});

test("the convex hull is closed and drops inner points", () => {
  const hull = convexHull([[0, 0], [2, 0], [2, 2], [0, 2], [1, 1]]);
  assert.equal(hull.length, 5);
  assert.deepEqual(hull[0], hull[hull.length - 1]);
  assert.ok(!hull.some(([x, y]) => x === 1 && y === 1));
});

test("a vessel points along its reported track, else toward its destination", () => {
  const tracked = laden({ track: [[3, 60], [3, 59]], position: { lon: 3, lat: 59 }, position_basis: "reported" });
  assert.ok(Math.abs(shipHeading(tracked, [3, 59]) - 180) < 1e-6);
  const untracked = laden({ position: { lon: 4.03, lat: 60 }, position_basis: "reported" });
  assert.ok(Math.abs(shipHeading(untracked, [4.03, 60]) - 180) < 1e-6);
});

test("hulls only where a position is drawn: an estimate is marked, a delivered cargo and one with nothing known draw none", () => {
  const marks = shipMarks([
    laden(),
    laden({ cargo_id: "C2", status: "delivered" }),
    laden({ cargo_id: "C3", origin: null, departed_at_utc: null }),
  ], NOW);
  assert.deepEqual(marks.map((mark) => mark.key), ["C1|estimated"]);
  const solids = shipSolids(marks, identity);
  const solid = solids.features.find((feature) => feature.properties.part === "solid");
  assert.equal(solid?.properties.basis, "estimated");
  // An estimate stands lower than a reported hull.
  assert.equal(solid?.properties.height, HULL.heightM / 2);
});

test("a hull eases to its new place and turns the short way", () => {
  assert.equal(turnHeading(350, 10, 0.5), 0);
  assert.equal(turnHeading(10, 350, 0.5), 0);
  const was = { key: "C1|reported", id: "C1", at: [0, 50] as [number, number], headingDeg: 0, own: true, basis: "reported" as const, name: "V" };
  const next = { ...was, at: [2, 50] as [number, number], headingDeg: 90 };
  const [half] = tweenShips(new Map([[was.key, was]]), [next], 0.5);
  assert.deepEqual(half.at, [1, 50]);
  assert.equal(half.headingDeg, 45);
  assert.equal(tweenShips(new Map([[was.key, was]]), [next], 1)[0], next);
  // A new vessel appears in place.
  assert.equal(tweenShips(new Map(), [next], 0.2)[0], next);
});

test("an address can open the map on one place", () => {
  const search = networkPlaceSearch("entsog-lng-00027");
  assert.equal(search, "workspace=market&task=network&place=entsog-lng-00027");
  assert.equal(networkPlaceFromSearch(`?${search}`), "entsog-lng-00027");
  assert.equal(networkPlaceFromSearch("?workspace=market"), null);
});
