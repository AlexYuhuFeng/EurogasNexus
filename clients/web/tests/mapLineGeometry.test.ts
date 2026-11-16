import assert from "node:assert/strict";
import test from "node:test";
import {
  BOOK_FLOW_MAX_WIDTH,
  bookFlowWidth,
  buildBookFlows,
  collapseSchematicPairs,
  compactMwhPerDay,
  hubAdjacencyEdges,
  isAdjacencyEdge,
  isDrawnAdjacency,
  isZoneMembershipEdge,
  pairKey,
  straightSegment,
  zoneMemberIds,
  type LineEndpoint,
} from "../src/app/mapLineGeometry.ts";

const node = (id: string, lon: number, lat: number, node_type = "interconnection"): LineEndpoint => ({ id, lon, lat, node_type });
const ttf = node("vtp-ttf", 4.87, 52.13, "hub");
const bacton = node("bacton-iuk", 1.46, 52.85);
const zeebrugge = node("zeebrugge-izt", 3.2, 51.33);
const julianadorp = node("julianadorp", 4.75, 52.9);
const emden = node("emden", 7.2, 53.35);

// The reference bundle's edge shape: each point to its zone's trading point.
const zoneEdge = (point: string, hub: string) => ({
  id: `zone-${point}-${hub}`,
  from_node_id: point,
  to_node_id: hub,
  edge_type: "virtual",
  metadata_json: { schematic: true, connection_basis: "entry_exit_zone" },
});

test("a zone link is membership of a market area, never a line", () => {
  assert.equal(isZoneMembershipEdge(zoneEdge("julianadorp", "vtp-ttf"), julianadorp, ttf), true);
  // Even without the flags, an unsurveyed link with a hub at one end is not a connection.
  assert.equal(
    isZoneMembershipEdge({ id: "x", from_node_id: "emden", to_node_id: "vtp-ttf", edge_type: "pipeline" }, emden, ttf),
    true,
  );
  // A link between two physical points is a connection.
  assert.equal(
    isZoneMembershipEdge({ id: "iuk", from_node_id: "bacton-iuk", to_node_id: "zeebrugge-izt", edge_type: "pipeline" }, bacton, zeebrugge),
    false,
  );
});

test("a hub's members come from its zone links, without drawing them", () => {
  const edges = [zoneEdge("julianadorp", "vtp-ttf"), zoneEdge("emden", "vtp-the"), zoneEdge("gate", "vtp-ttf")];
  assert.deepEqual([...zoneMemberIds("vtp-ttf", edges)].sort(), ["gate", "julianadorp"]);
  // A pipeline that happens to touch a point is not membership.
  const pipeline = { id: "p", from_node_id: "vtp-ttf", to_node_id: "x", edge_type: "pipeline" };
  assert.equal(zoneMemberIds("vtp-ttf", [pipeline]).size, 0);
});

test("a schematic connection is one straight segment, the same for every record of a pair", () => {
  const segment = straightSegment(bacton, zeebrugge);
  assert.deepEqual(segment[0], [bacton.lon, bacton.lat]);
  assert.deepEqual(segment.at(-1), [zeebrugge.lon, zeebrugge.lat]);
  // Every vertex lies on the chord: no bend, so nothing fans out.
  for (const [lon, lat] of segment) {
    const cross = (zeebrugge.lon - bacton.lon) * (lat - bacton.lat) - (zeebrugge.lat - bacton.lat) * (lon - bacton.lon);
    assert.ok(Math.abs(cross) < 1e-9);
  }
  assert.equal(pairKey("a", "b"), pairKey("b", "a"));

  const line = (id: string, from: LineEndpoint, to: LineEndpoint, schematic = true) => ({ id, from, to, schematic, kind: "network_link" });
  const collapsed = collapseSchematicPairs([
    line("iuk-1", bacton, zeebrugge),
    line("iuk-2", zeebrugge, bacton),
    line("iuk-3", bacton, zeebrugge),
    line("bbl", bacton, julianadorp),
    // Two surveyed pipes between the same places are two lines on the ground.
    line("surveyed-1", bacton, zeebrugge, false),
    line("surveyed-2", bacton, zeebrugge, false),
  ]);
  assert.deepEqual(collapsed.map((item) => item.id), ["iuk-1", "bbl", "surveyed-1", "surveyed-2"]);
});

const nodes = new Map([ttf, bacton, zeebrugge, julianadorp, emden].map((item) => [item.id, item]));
const resolvePoint = (name: string) => ({ ttf: "vtp-ttf", bacton: "bacton-iuk", zeebrugge: "zeebrugge-izt", julianadorp: "julianadorp", emden: "emden" } as Record<string, string>)[name.toLowerCase()];
const path = (routeId: string, from: string, to: string, volume: number | null, routeState = "allocated") => ({
  routeId,
  sourcePointName: from,
  targetPointName: to,
  routeState,
  allocatedQuantityMwhPerDay: volume,
});

test("the book draws one line per origin and destination, volumes summed", () => {
  const flows = buildBookFlows({
    paths: [
      // Three contracts and two days of the same flow: one line, not five.
      path("iuk-a", "Bacton", "Zeebrugge", 12_000),
      path("iuk-b", "Bacton", "Zeebrugge", 9_000),
      path("iuk-a", "Bacton", "Zeebrugge", 3_000),
      path("bbl", "Bacton", "Julianadorp", 4_000),
      // Not flows: a candidate, a blocked option, nothing allocated, a sale where the gas is.
      path("cand", "Bacton", "Emden", 5_000, "candidate"),
      path("blocked", "Bacton", "Emden", 5_000, "blocked"),
      path("zero", "Bacton", "Emden", 0),
      { ...path("local", "TTF", "TTF", 18_000), routeTopologyKind: "LOCAL_MARKET_DISPOSITION" },
      // An unknown place draws nothing rather than a guessed line.
      path("unknown", "Nowhere", "Zeebrugge", 1_000),
    ],
    resolvePoint,
    nodes,
  });
  assert.equal(flows.length, 2);
  const iuk = flows.find((flow) => flow.toId === "zeebrugge-izt")!;
  assert.equal(iuk.mwhPerDay, 24_000);
  assert.equal(iuk.pathCount, 3);
  assert.deepEqual(iuk.routeIds, ["iuk-a", "iuk-b"]);
  assert.equal(iuk.label, "24k MWh/d");
  assert.equal(iuk.geometryBasis, "segment");
  // No two flows leave one origin as offset arcs: each is the straight segment of its pair.
  assert.deepEqual(iuk.coordinates, straightSegment(bacton, zeebrugge));
});

test("a book flow follows the surveyed route where there is one", () => {
  const surveyed: Array<[number, number]> = [[1.46, 52.85], [2.4, 52.0], [3.2, 51.33]];
  const [flow] = buildBookFlows({
    paths: [path("iuk", "Bacton", "Zeebrugge", 10_000)],
    resolvePoint,
    nodes,
    surveyedRoute: (routeId) => (routeId === "iuk" ? surveyed : null),
  });
  assert.equal(flow.geometryBasis, "surveyed");
  assert.deepEqual(flow.coordinates, surveyed);
});

test("line width is a few capped steps of volume", () => {
  assert.equal(bookFlowWidth(1_000), 2);
  assert.equal(bookFlowWidth(10_000), 3);
  assert.equal(bookFlowWidth(30_000), 4.5);
  assert.equal(bookFlowWidth(60_000), BOOK_FLOW_MAX_WIDTH);
  assert.equal(bookFlowWidth(10_000_000), BOOK_FLOW_MAX_WIDTH);
  assert.equal(compactMwhPerDay(18_000), "18k MWh/d");
  assert.equal(compactMwhPerDay(1_250), "1.3k MWh/d");
  assert.equal(compactMwhPerDay(950), "950 MWh/d");
});

// The adjacency the route pricing walks (reference bundle market_area_link / interconnector).
const link = (point: string, hubId: string, representative: boolean) => ({
  id: `adj-${point}-${hubId}`,
  from_node_id: point,
  to_node_id: hubId,
  edge_type: "market_area_link",
  metadata_json: { representative, connection_basis: "entsog_interconnection" },
});
const iuk = { id: "pipe-iuk", from_node_id: "bacton-iuk", to_node_id: "zeebrugge-izt", edge_type: "interconnector", metadata_json: {} };

test("adjacency is drawn hub - interconnection point - hub, one point per pair by default", () => {
  const vipH = link("vip-ttf-the-h", "vtp-ttf", true);
  const bocholtz = link("bocholtz", "vtp-ttf", false);
  // A link with a hub end is adjacency, not zone membership: it is not hidden.
  assert.equal(isZoneMembershipEdge(vipH, julianadorp, ttf), false);
  assert.equal(isAdjacencyEdge(vipH), true);
  assert.equal(isDrawnAdjacency(vipH), true);
  assert.equal(isDrawnAdjacency(bocholtz), false);
  assert.equal(isDrawnAdjacency(iuk), true);
  assert.equal(isDrawnAdjacency(zoneEdge("julianadorp", "vtp-ttf")), false);
  // Selecting the hub shows every point joining it to a neighbour, and the pipelines from them.
  const all = [vipH, bocholtz, link("bacton-iuk", "vtp-nbp", true), iuk, zoneEdge("gate", "vtp-ttf")];
  assert.deepEqual(hubAdjacencyEdges("vtp-ttf", all).map((edge) => edge.id), [vipH.id, bocholtz.id]);
  assert.deepEqual(hubAdjacencyEdges("vtp-nbp", all).map((edge) => edge.id), ["adj-bacton-iuk-vtp-nbp", "pipe-iuk"]);
});

test("a book flow follows exactly the path it was priced along", () => {
  const nbp = node("vtp-nbp", -0.96, 53.03, "hub");
  const ztp = node("vtp-ztp", 4.02, 50.94, "hub");
  const priced = new Map([nbp, bacton, zeebrugge, ztp].map((item) => [item.id, item]));
  const [flow] = buildBookFlows({
    paths: [{ ...path("nbp-ztp", "NBP", "ZTP", 12_000), pathNodeIds: ["vtp-nbp", "bacton-iuk", "zeebrugge-izt", "vtp-ztp"] }],
    resolvePoint: (name) => ({ nbp: "vtp-nbp", ztp: "vtp-ztp" } as Record<string, string>)[name.toLowerCase()],
    nodes: priced,
  });
  assert.equal(flow.geometryBasis, "priced_path");
  assert.deepEqual(flow.coordinates[0], [nbp.lon, nbp.lat]);
  assert.deepEqual(flow.coordinates.at(-1), [ztp.lon, ztp.lat]);
  // It passes through both ends of IUK.
  assert.ok(flow.coordinates.some(([lon, lat]) => lon === bacton.lon && lat === bacton.lat));
  assert.ok(flow.coordinates.some(([lon, lat]) => lon === zeebrugge.lon && lat === zeebrugge.lat));
});
