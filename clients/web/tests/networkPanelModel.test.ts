/**
 * Desk → Network: one task for the map and what was "Outages & capacity". The panel beside the
 * map, its URL, the selection that links panel and map, "Follow map", outage placement and order.
 */
import assert from "node:assert/strict";
import test from "node:test";
import type { MapSituationDTO, NodeDTO, OutageEventDTO } from "../src/api/client.ts";
import { buildSites } from "../src/app/mapSelection.ts";
import {
  compareOutages,
  hubCode,
  inScope,
  networkPanelFromSearch,
  networkPanelToSearch,
  outageListRows,
  unlocatedReasonKey,
  panelFilter,
  selectionScope,
  type OutageListRow,
} from "../src/app/model/networkPanelModel.ts";
import { marketTaskFromLocation, marketTaskFromSearch } from "../src/app/model/marketCockpitModel.ts";
import { timeWindow } from "../src/app/model/todayModel.ts";
import { modeLocationFromSearch } from "../src/app/navigation/modeNavigation.ts";
import { workspaceTaskSearch } from "../src/workspaceNavigation.ts";

test("the panel tab round-trips through the URL and keeps the trading context", () => {
  for (const tab of ["outages", "capacity", "flows", "book"] as const) {
    const search = networkPanelToSearch("workspace=market&task=network&gasDay=2026-11-16&hub=TTF", tab);
    assert.equal(networkPanelFromSearch(search), tab, tab);
    assert.equal(networkPanelToSearch(search, tab), search, `${tab} is stable`);
    const params = new URLSearchParams(search);
    assert.equal(params.get("gasDay"), "2026-11-16");
    assert.equal(params.get("hub"), "TTF");
    assert.equal(marketTaskFromSearch(search), "network");
  }
  // The default tab writes no parameter.
  assert.equal(new URLSearchParams(networkPanelToSearch("workspace=market&task=network&panel=flows", "outages")).has("panel"), false);
  assert.equal(networkPanelFromSearch("workspace=market&task=network&panel=nonsense"), "outages");
});

test("the retired Outages & capacity addresses open Network with the Capacity tab", () => {
  const cases: Array<[string, string]> = [
    ["?workspace=capacity", "capacity"],
    ["?workspace=capacity&task=capacity", "capacity"],
    ["?workspace=market&task=capacity", "capacity"],
    ["?workspace=market&task=capacity&panel=outages", "outages"],
    ["?workspace=market&task=network", "outages"],
    ["?workspace=network", "outages"],
  ];
  for (const [search, tab] of cases) {
    const page = new URLSearchParams(search).get("workspace") ?? "market";
    assert.equal(networkPanelFromSearch(search, page), tab, search);
    assert.equal(marketTaskFromLocation(search, page), "network", search);
    assert.equal(modeLocationFromSearch(page as never, search)?.task.id, "network", search);
    // The canonical address the page rewrites a retired one to.
    const canonical = networkPanelToSearch(search, tab as never);
    assert.equal(new URLSearchParams(canonical).get("task"), "network", search);
    assert.equal(networkPanelFromSearch(canonical, "market"), tab, `${search} after rewrite`);
  }
  // Leaving the market page drops the panel with the other market object parameters.
  assert.equal(new URLSearchParams(workspaceTaskSearch("workspace=market&task=network&panel=flows", "contracts", "overview")).has("panel"), false);
  assert.equal(new URLSearchParams(workspaceTaskSearch("workspace=market&task=network&panel=flows", "market", "curves")).get("panel"), "flows");
});

const node = (id: string, name: string, node_type: string, country: string, lat: number, lon: number): NodeDTO =>
  ({ id, name, node_type, country, lat, lon, capacity_boe_d: null, source_system: "ENTSOG", data_quality: "display_approximation", metadata_json: {} }) as NodeDTO;

const nodes = [
  node("hub-ttf", "TTF", "hub", "NL", 52.1, 5.1),
  node("hub-the", "THE VTP (DE)", "hub", "DE", 51, 10),
  node("vip-fr-de", "VIP France - Germany", "interconnection", "DE", 49.0851, 6.7816),
  node("gate", "Gate Terminal (I)", "lng", "NL", 51.95, 4.04),
];

test("a map selection is the panel's scope: a hub is its zone, a site its members", () => {
  const sites = buildSites(nodes, []);
  assert.equal(hubCode("THE VTP (DE)"), "THE");
  assert.equal(hubCode("TTF"), "TTF");
  const zone = selectionScope({ kind: "hub", id: "TTF" }, { sites, nodes });
  assert.equal(zone?.kind, "zone");
  assert.equal(zone?.label, "TTF");
  assert.equal(inScope(zone, { name: "Gate Terminal (I)", country: "NL" }), true);
  assert.equal(inScope(zone, { name: "VIP France - Germany", country: "DE" }), false);
  // An outage the map cannot place still belongs to its balancing zone.
  assert.equal(inScope(zone, { name: "Demo Kestrel export line", zone: "TTF" }), true);
  const the = selectionScope({ kind: "hub", id: "THE VTP (DE)" }, { sites, nodes });
  assert.equal(inScope(the, { name: "VIP France - Germany", country: "DE" }), true);
  const site = sites.find((item) => item.name === "VIP France - Germany")!;
  const scope = selectionScope({ kind: "site", id: site.id }, { sites, nodes });
  assert.equal(scope?.label, "VIP France - Germany");
  assert.equal(inScope(scope, { refId: "vip-fr-de" }), true);
  // The other operator's message spells the point differently: matched on the name's letters.
  assert.equal(inScope(scope, { name: "VIP France-Germany" }), true);
  assert.equal(inScope(scope, { name: "Gate Terminal (I)", country: "NL" }), false);
  // A cargo filters nothing; no selection filters nothing.
  assert.equal(selectionScope({ kind: "cargo", id: "c1" }, { sites, nodes }), null);
  assert.equal(inScope(null, { name: "anything" }), true);
});

test("Follow map keeps what is in view; a row with no position is never hidden", () => {
  type Row = { id: string; at: [number, number] | null };
  const rows: Row[] = [
    { id: "in", at: [5, 52] },
    { id: "out", at: [20, 60] },
    { id: "unplaced", at: null },
  ];
  const bounds = { west: 0, south: 45, east: 10, north: 55 };
  const describe = (row: Row) => ({ at: row.at });
  assert.deepEqual(panelFilter(rows, { scope: null, followMap: true, bounds, describe }).map((row) => row.id), ["in", "unplaced"]);
  assert.deepEqual(panelFilter(rows, { scope: null, followMap: false, bounds, describe }).map((row) => row.id), ["in", "out", "unplaced"]);
  // Before the map reports a view, nothing is filtered.
  assert.equal(panelFilter(rows, { scope: null, followMap: true, bounds: null, describe }).length, 3);
  // A selection is the filter while it lasts, whatever the view.
  const sites = buildSites(nodes, []);
  const scope = selectionScope({ kind: "hub", id: "TTF" }, { sites, nodes });
  const named = [
    { id: "gate", at: [4.04, 51.95] as [number, number], country: "NL" },
    { id: "vip", at: [6.78, 49.08] as [number, number], country: "DE" },
  ];
  assert.deepEqual(
    panelFilter(named, { scope, followMap: true, bounds: { west: 6, south: 48, east: 8, north: 50 }, describe: (row) => ({ at: row.at, country: row.country }) }).map((row) => row.id),
    ["gate"],
  );
});

const event = (id: string, fields: Partial<OutageEventDTO> = {}): OutageEventDTO =>
  ({
    event_id: id,
    version: 1,
    facility_id: "",
    facility_name: "Asset",
    asset_type: "transmission",
    event_type: "planned",
    status: "active",
    start_utc: "2026-11-15T05:00:00+00:00",
    end_utc: "2026-11-18T05:00:00+00:00",
    published_at_utc: null,
    balancing_zone: "THE",
    unit: "GWh/d",
    unavailable_capacity: 10,
    capacity_impact_mcm_d: 0,
    description: "",
    market_participant: "Operator",
    unavailable_gwh_d: 10,
    ...fields,
  }) as OutageEventDTO;

test("every outage is listed with where the map stands on it", () => {
  const situation = {
    outages: [
      { event_id: "P016", facility_name: "VIP France - Germany", location: { lon: 6.78, lat: 49.08, ref_id: "vip-fr-de", country: "DE" } },
    ],
    known_facility_outages: [{ facility_eic: "X", facility_name: "Store", country: "DE", operator: null, reason: "no_published_position", outages: 1, event_ids: ["K1"] }],
    unlocated_outages: [{ event_id: "U1", facility_name: "Field", facility_id: "", reason: "no_reference_match" }],
  } as unknown as MapSituationDTO;
  const rows = outageListRows(
    [
      // The server's event row: led by P016, with every message of the event.
      event("P016", { facility_name: "VIP France - Germany", messages: ["P012", "P014", "P015", "P016"], operators: ["GRTgaz Deutschland"], message_count: 4, unavailable_gwh_d: 81 }),
      event("K1", { facility_name: "Store" }),
      event("U1", { facility_name: "Field" }),
      // Starts after the map's 14 days, at an asset the map places for another event.
      event("LATER", { facility_name: "VIP France - Germany", status: "scheduled" }),
      event("FAR", { facility_name: "Elsewhere", status: "scheduled" }),
    ],
    situation,
  );
  assert.deepEqual(rows.map((row) => [row.eventId, row.placement]), [
    ["P016", "placed"],
    ["K1", "known_no_position"],
    ["U1", "not_located"],
    ["LATER", "placed"],
    ["FAR", "later"],
  ]);
  assert.deepEqual(rows[0].at, [6.78, 49.08]);
  assert.equal(rows[0].refId, "vip-fr-de");
  assert.deepEqual(rows[0].operators, ["GRTgaz Deutschland"]);
  assert.equal(rows[0].messages.length, 4);
  // An unplaced row says what it was identified as, or why it could not be.
  assert.deepEqual(rows[1].placementNote, { key: "outages.known.no_position", values: { facility: "Store", country: "DE" } });
  assert.deepEqual(rows[2].placementNote, { key: "outages.unresolved.no_match", values: {} });
  assert.equal(rows[0].placementNote, null);
  // No situation read yet: nothing is claimed placed.
  assert.equal(outageListRows([event("A")], null)[0].placement, "not_located");
});

test("a site of a storage group outside the loaded network names the group, its sites and why", () => {
  const situation = {
    outages: [],
    known_facility_outages: [{
      facility_eic: "21Z000000000383D", facility_name: "VGS GIM Kawerna (Kosakowo, Mogilno)", country: "PL",
      operator: "Gas Storage Poland sp. z o.o.", reason: "outside_reference_network", outages: 1, event_ids: ["M1"], sites: ["Mogilno"],
    }],
    unlocated_outages: [{ event_id: "A1", facility_name: "Epe", facility_id: "", reason: "ambiguous_facility_name:2_places:Epe (DE)" }],
  } as unknown as MapSituationDTO;
  const rows = outageListRows([event("M1", { facility_name: "CUGS Mogilno" }), event("A1", { facility_name: "Epe" })], situation);
  assert.deepEqual(rows[0].placementNote, {
    key: "outages.known.outside_network",
    values: { facility: "VGS GIM Kawerna (Kosakowo, Mogilno)", country: "PL" },
  });
  // A site the group's name does not list is named after it (accents ignored when comparing).
  const sanok = outageListRows([event("S1", { facility_name: "UGS Brzeźnica" })], {
    outages: [],
    known_facility_outages: [{ facility_eic: "21Z000000000382F", facility_name: "VGS GIM Sanok (Brzeznica, Husow)", country: "PL", operator: null, reason: "outside_reference_network", outages: 1, event_ids: ["S1"], sites: ["Brzeźnica", "Strachocina"] }],
  } as unknown as MapSituationDTO);
  assert.equal(sanok[0].placementNote?.values.facility, "VGS GIM Sanok (Brzeznica, Husow) (Strachocina)");
  assert.equal(unlocatedReasonKey(situation.unlocated_outages![0].reason), "outages.unresolved.ambiguous");
  assert.deepEqual(rows[1].placementNote, { key: "outages.unresolved.ambiguous", values: {} });
});

test("outages order: out now, planned, ended; within each, the largest offline first", () => {
  const row = (eventId: string, state: OutageListRow["state"], gwhD: number | null): OutageListRow =>
    ({ eventId, key: eventId, state, gwhD, startUtc: "2026-11-15" }) as OutageListRow;
  const sorted = [row("a", "scheduled", 500), row("b", "active", 10), row("c", "ended", 900), row("d", "active", 81), row("e", "active", null)].sort(compareOutages);
  assert.deepEqual(sorted.map((item) => item.eventId), ["d", "b", "e", "a", "c"]);
});

test("an outage window states the year when it leaves the current year or spans years", () => {
  const now = Date.parse("2026-11-16T12:00:00Z");
  assert.equal(timeWindow("2026-10-01T04:00:00Z", "2029-10-01T04:00:00Z", now), "1 Oct 2026 – 1 Oct 2029");
  assert.equal(timeWindow("2026-11-16T09:56:00Z", "2026-11-19T09:56:00Z", now), "16 Nov 09:56 – 19 Nov 09:56");
  // A week or more drops the clock; inside the current year no year.
  assert.equal(timeWindow("2026-11-01T05:00:00Z", "2026-11-30T05:00:00Z", now), "1 Nov – 30 Nov");
  // Into next year: both ends carry their year.
  assert.equal(timeWindow("2026-12-30T05:00:00Z", "2027-01-02T05:00:00Z", now), "30 Dec 2026 05:00 – 2 Jan 2027 05:00");
  // Open-ended.
  assert.equal(timeWindow("2026-11-16T05:00:00Z", null, now), "16 Nov –");
});
