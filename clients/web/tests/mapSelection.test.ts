/**
 * The live map's selection model: one place with several roles is one site, roles are
 * words, hubs read the board's prices, and a cargo knows its voyage and waiting slot.
 */
import assert from "node:assert/strict";
import test from "node:test";
import type { EdgeDTO, FacilityDTO, MapSituationDTO, NodeDTO, NormalizedMarketObsDTO } from "../src/api/client.ts";
import {
  buildSites,
  cargoVoyage,
  hubPrices,
  hubZone,
  siteFacts,
  siteOf,
  siteRoles,
} from "../src/app/mapSelection.ts";

const node = (id: string, name: string, node_type: string, country: string, lat: number, lon: number): NodeDTO =>
  ({ id, name, node_type, country, lat, lon, capacity_boe_d: null, source_system: "ENTSOG", data_quality: "display_approximation", metadata_json: {} });
const facility = (id: string, name: string, facility_type: string, country: string, lat: number, lon: number, metadata = {}): FacilityDTO =>
  ({ id, name, facility_type, country, lat, lon, capacity_boe_d: null, source_dataset: "GEM", data_quality: "verified", metadata_json: metadata });

const nodes = [
  node("hub-nbp", "NBP", "hub", "GB", 53.2, -1.6),
  node("easington", "Easington", "entry_point", "GB", 53.655, 0.115),
  node("nyhamna", "Nyhamna", "production", "NO", 62.85, 6.95),
  node("grain", "Isle of Grain", "lng", "GB", 51.445, 0.705),
];
const facilities = [
  facility("fac-easington", "Easington gas terminal", "processing_plant", "GB", 53.66, 0.11, { operator: "Gassco" }),
  facility("fac-grain", "Isle of Grain", "lng_terminal", "GB", 51.445, 0.705, { operator: "National Grid Grain LNG", send_out_gwh_d: 645 }),
];
const edges: EdgeDTO[] = [
  { id: "langeled", from_node_id: "nyhamna", to_node_id: "easington", edge_type: "pipeline", length_km: null, metadata_json: { name: "Langeled" } },
];
const at = (ref_id: string, country = "GB") => ({ lon: 0, lat: 0, ref_id, ref_kind: "node" as const, country });
const situation: MapSituationDTO = {
  as_of_utc: "2026-11-01T06:00:00Z",
  outages: [
    {
      event_id: "UMM-1", facility_name: "Easington", asset_type: "Transmission", event_type: "Unplanned",
      status: "active", start_utc: "2026-11-01T00:00:00Z", end_utc: null, balancing_zone: "GB", unit: "GWh/d",
      technical_capacity: 900, unavailable_capacity: 100, unavailable_gwh_d: 100, unavailable_share: 0.11,
      description: "", market_participant: "x", source_system: "REMIT", location: at("easington"),
    } as never,
  ],
  flows: [
    { point_id: "easington", point_name: "Easington", direction: "entry", gas_day_start_utc: "2026-10-31T05:00:00Z", value: 7.2e8, unit: "kWh/d", gwh_d: 720, source_system: "ENTSOG", location: at("easington") },
    { point_id: "grain", point_name: "Isle of Grain", direction: "entry", gas_day_start_utc: "2026-10-31T05:00:00Z", value: 3.2e8, unit: "kWh/d", gwh_d: 322.5, source_system: "ENTSOG", location: at("grain") },
  ],
  contracts: [
    { contract_id: "langeled-24", contract_name: "Langeled supply", resource_type: "PIPELINE_IMPORT", delivery_point: "Easington", gas_year: "2026+", delivery_mwh_d: 24000, entry_capacity_mwh_d: 26000, book_id: "uk-nbp", location: at("easington") },
  ],
  cargoes: [
    {
      cargo_id: "C1", vessel_name: "Al Huwaila", vessel_imo: "9360879", status: "laden", load_port: "Ras Laffan",
      departed_at_utc: "2026-10-20T00:00:00Z", destination_terminal: "Isle of Grain", eta_utc: "2026-11-04T00:00:00Z",
      position_at_utc: "2026-11-01T00:00:00Z", volume_m3: 210000, energy_gwh: 1050, own: true, book_id: "uk-nbp",
      source_system: "ETRM", origin: null, position: null, destination: null, track: [],
    } as never,
  ],
  regas_slots: [
    { slot_id: "S1", terminal_name: "Isle of Grain", window_start_utc: "2026-11-04T00:00:00Z", window_end_utc: "2026-11-09T00:00:00Z", active: false, send_out_gwh_d: 190, energy_gwh: null, cargo_id: "C1", book_id: "uk-nbp", location: at("grain") },
  ],
  unlocated: { outages: 0, contracts: 0, cargoes: 0, regas_slots: 0 },
  positions_included: true,
};

test("points and facilities at one place form one site named after its network point", () => {
  const sites = buildSites(nodes, facilities);
  const easington = siteOf(sites, "fac-easington");
  assert.ok(easington);
  assert.equal(easington.name, "Easington");
  assert.deepEqual(easington.members.map((member) => member.id).sort(), ["easington", "fac-easington"]);
  // A hub is a market, not a place: it never joins a site.
  assert.equal(siteOf(sites, "hub-nbp"), null);
});

test("Easington reads as entry point, gas terminal, Langeled landing, NBP zone, our supply, outage", () => {
  const easington = siteOf(buildSites(nodes, facilities), "easington")!;
  const roles = siteRoles(easington, edges, situation);
  assert.deepEqual(
    roles.map((role) => `${role.key}${role.value ? `:${role.value}` : ""}:${role.tone}`),
    ["entry_point:neutral", "gas_terminal:neutral", "pipeline:Langeled:neutral", "zone:NBP:neutral", "own_supply:own", "outage_now:alert"],
  );
  const facts = siteFacts(easington, situation);
  assert.equal(facts.operator, "Gassco");
  assert.equal(facts.flowEntryGwhD, 720);
  // The REMIT technical capacity in GWh/d gives the utilisation.
  assert.equal(facts.capacityGwhD, 900);
  assert.equal(facts.utilisation, 0.8);
});

test("an LNG terminal shows its operator, send-out against capacity, cargoes heading in and our slot", () => {
  const grain = siteOf(buildSites(nodes, facilities), "fac-grain")!;
  const facts = siteFacts(grain, situation);
  assert.equal(facts.operator, "National Grid Grain LNG");
  assert.equal(facts.capacityGwhD, 645);
  assert.equal(Math.round((facts.utilisation ?? 0) * 100), 50);
  assert.deepEqual(facts.inbound.map((cargo) => cargo.cargo_id), ["C1"]);
  assert.deepEqual(facts.slots.map((slot) => slot.slot_id), ["S1"]);
  assert.ok(siteRoles(grain, edges, situation).some((role) => role.key === "own_slot" && role.tone === "own"));
});

test("a hub reads the board's latest day-ahead and month-ahead with the change, and its zone", () => {
  const row = (tenor: string, price: number, observed: string) =>
    ({ hub: "NBP", tenor, price, unit: "GBP/MWh", is_gas_price: true, observed_at_utc: observed, source_system: "ICE_ENDEX" }) as unknown as NormalizedMarketObsDTO;
  const prices = hubPrices("NBP", [
    row("day-ahead", 34.1, "2026-10-30T17:00:00Z"),
    row("day-ahead", 34.6, "2026-10-31T17:00:00Z"),
    row("month-ahead", 35.3, "2026-10-31T17:00:00Z"),
  ]);
  assert.deepEqual(prices.map((price) => [price.tenor, price.price]), [["day-ahead", 34.6], ["month-ahead", 35.3]]);
  assert.ok(Math.abs((prices[0].change ?? 0) - 0.5) < 1e-9);
  const zone = hubZone("NBP", situation, { nodes, edges });
  assert.equal(zone.outagesNow, 1);
  assert.equal(zone.entryGwhD, 1042.5);
  assert.equal(zone.supplyMwhD, 24000);
});

test("a cargo knows how far along it is and the slot waiting for it", () => {
  const voyage = cargoVoyage(situation.cargoes[0], situation, new Date("2026-11-01T00:00:00Z"));
  assert.equal(voyage.slot?.slot_id, "S1");
  assert.equal(voyage.etaDays, 3);
  assert.ok(voyage.progress != null && voyage.progress > 0.7 && voyage.progress < 0.9);
});


test("a hub lists outages one pipeline upstream of its zone", () => {
  const nyhamnaDown = {
    ...situation,
    outages: [{ ...situation.outages[0], event_id: "UMM-NYH", facility_name: "Nyhamna", location: at("nyhamna", "NO") }],
  } as MapSituationDTO;
  const zone = hubZone("NBP", nyhamnaDown, { nodes, edges });
  assert.equal(zone.outagesNow, 0);
  assert.deepEqual(zone.upstream.map((outage) => outage.event_id), ["UMM-NYH"]);
});

test("Bacton's two landings are one site called Bacton, and figures are not mixed between them", () => {
  const bacton = [
    node("bacton-iuk", "Bacton IUK", "interconnection", "GB", 52.858, 1.468),
    node("bacton-bbl", "Bacton BBL", "interconnection", "GB", 52.855, 1.462),
  ];
  const site = siteOf(buildSites(bacton, []), "bacton-bbl")!;
  assert.equal(site.name, "Bacton");
  const mixed = {
    ...situation,
    flows: [{ ...situation.flows[0], point_id: "bacton-iuk", direction: "exit", gwh_d: 183, location: at("bacton-iuk") }],
    outages: [{ ...situation.outages[0], technical_capacity: 470, location: at("bacton-bbl") }],
  } as MapSituationDTO;
  const facts = siteFacts(site, mixed);
  assert.equal(facts.capacityPoint, "Bacton BBL");
  // IUK's flow is not divided by BBL's capacity.
  assert.equal(facts.utilisation, null);
});

test("the topology check catches a pipeline that lands inland across a border, isolated points and duplicates", async () => {
  const { topologyIssues } = await import("../src/app/mapSelection.ts");
  const ireland = node("dublin", "Dublin city gate", "city_gate", "IE", 53.35, -6.26);
  const isolated = node("milford", "Milford Haven", "entry_point", "GB", 51.7, -5.05);
  const wrong: EdgeDTO = { id: "bad", from_node_id: "easington", to_node_id: "dublin", edge_type: "pipeline", length_km: null, metadata_json: { name: "Bad link" } };
  const twice: EdgeDTO = { ...edges[0], id: "langeled-copy" };
  const issues = topologyIssues([...nodes, ireland, isolated], [...edges, wrong, twice]);
  assert.deepEqual(issues.map((issue) => issue.kind).sort(), ["cross_border_landing", "duplicate_connection", "isolated_point"]);
  assert.match(issues.find((issue) => issue.kind === "cross_border_landing")!.detail, /lands at Dublin city gate/);
  // The North Sea network as built is clean.
  assert.deepEqual(topologyIssues(nodes, edges), []);
});
