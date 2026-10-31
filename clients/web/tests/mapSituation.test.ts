/**
 * Live map situation layers: items are drawn only where a source located them, own and
 * market cargoes are told apart, and the leg to a destination is marked indicative.
 */
import assert from "node:assert/strict";
import test from "node:test";
import type { MapSituationDTO } from "../src/api/client.ts";
import {
  cargoFeatures,
  contractFeatures,
  outageFeatures,
  situationCardHtml,
  situationSummary,
  slotTerminalFeatures,
} from "../src/app/mapSituation.ts";

const identity = (lon: number, lat: number): [number, number] => [lon, lat];
const escape = (value: unknown) => String(value ?? "").replace(/</g, "&lt;");
const t = (key: string) => key;

const situation: MapSituationDTO = {
  as_of_utc: "2026-10-31T09:30:00+00:00",
  outages: [
    {
      event_id: "UMM-1", facility_name: "Easington <entry>", asset_type: "transmission", event_type: "Unplanned",
      status: "active", start_utc: "2026-10-31T06:00:00+00:00", end_utc: null, balancing_zone: "GB",
      unit: "GWh/d", technical_capacity: 400, unavailable_capacity: 100, unavailable_gwh_d: 100,
      unavailable_share: 0.25, description: "Compressor trip", market_participant: "TSO", source_system: "REMIT",
      location: { lon: -0.1, lat: 53.65, match: "eic" },
    },
  ],
  flows: [],
  contracts: [
    { contract_id: "a", contract_name: "Norway A", resource_type: "PIPELINE_IMPORT", delivery_point: "Easington", gas_year: "2026", delivery_mwh_d: 10_000, entry_capacity_mwh_d: 12_000, book_id: "uk", location: { lon: -0.1, lat: 53.65 } },
    { contract_id: "b", contract_name: "Norway B", resource_type: "PIPELINE_IMPORT", delivery_point: "Easington", gas_year: "2026", delivery_mwh_d: 5_000, entry_capacity_mwh_d: null, book_id: "uk", location: { lon: -0.1, lat: 53.65 } },
  ],
  cargoes: [
    {
      cargo_id: "C1", vessel_name: "Arctic Voyager", vessel_imo: null, status: "laden", load_port: "Hammerfest",
      departed_at_utc: null, destination_terminal: "Gate", eta_utc: "2026-11-03T08:00:00+00:00",
      position_at_utc: "2026-10-31T09:00:00+00:00", volume_m3: null, energy_gwh: 950, own: true, book_id: "uk",
      source_system: "KPLER", origin: { lon: 23.6, lat: 70.68 }, position: { lon: 4.5, lat: 62 },
      destination: { lon: 4, lat: 51.95 }, track: [[23.6, 70.68], [4.5, 62]],
    },
    {
      cargo_id: "M1", vessel_name: "Market ship", vessel_imo: null, status: "ballast", load_port: "Ras Laffan",
      departed_at_utc: null, destination_terminal: null, eta_utc: null, position_at_utc: null, volume_m3: 170_000,
      energy_gwh: null, own: false, book_id: null, source_system: "KPLER", origin: null, position: { lon: 10, lat: 40 },
      destination: null, track: [],
    },
  ],
  regas_slots: [
    { slot_id: "S1", terminal_name: "Gate", window_start_utc: "2026-11-03T00:00:00+00:00", window_end_utc: "2026-11-08T00:00:00+00:00", active: false, send_out_gwh_d: 190, energy_gwh: null, cargo_id: "C1", book_id: "uk", location: { lon: 4, lat: 51.95 } },
  ],
  unlocated: { outages: 1, contracts: 0, cargoes: 0, regas_slots: 0 },
  positions_included: true,
};

test("contracts landing at one point share a pin with their total", () => {
  const { features } = contractFeatures(situation.contracts, identity);
  assert.equal(features.length, 1);
  assert.equal(features[0].properties.count, 2);
  assert.equal(features[0].properties.mwh_d, 15_000);
});

test("cargoes: sailed track, indicative leg only for laden cargoes, own flag kept", () => {
  const { positions, sailed, ahead } = cargoFeatures(situation.cargoes, identity);
  assert.deepEqual(positions.features.map((f) => [f.properties.id, f.properties.own]), [["C1", true], ["M1", false]]);
  assert.equal(sailed.features.length, 1);
  assert.equal(ahead.features.length, 1);
  assert.equal(ahead.features[0].properties.indicative, true);
  assert.deepEqual(ahead.features[0].geometry.coordinates, [[4.5, 62], [4, 51.95]]);
});

test("outage radius follows the share of capacity out; slots highlight their terminal", () => {
  assert.equal(outageFeatures(situation.outages, identity).features[0].properties.share, 0.25);
  const terminals = slotTerminalFeatures(situation.regas_slots, identity).features;
  assert.deepEqual(terminals.map((f) => f.properties.name), ["Gate"]);
});

test("summary leads with what needs attention and counts unlocated items", () => {
  const summary = situationSummary(situation);
  assert.equal(summary?.outagesNow, 1);
  assert.equal(summary?.cargoesAtSea, 1);
  assert.equal(summary?.unlocated, 1);
});

test("hover cards are escaped and in desk units", () => {
  const outage = situationCardHtml("outage", "UMM-1", situation, t, escape);
  assert.match(outage, /Easington &lt;entry>/);
  assert.match(outage, /100 \/ 400 GWh\/d/);
  const contract = situationCardHtml("contract", "a,b", situation, t, escape);
  assert.match(contract, /10,000 MWh\/d/);
  const cargo = situationCardHtml("cargo", "C1", situation, t, escape);
  assert.match(cargo, /950 GWh/);
  assert.match(cargo, /map.situation.indicative_leg/);
});

test("the map container rule stays outside cascade layers", async () => {
  // maplibre-gl.css is unlayered; a layered rule loses to its `.maplibregl-map
  // { position: relative; overflow: hidden }` and the map collapses to 0 px.
  const { readFileSync } = await import("node:fs");
  const css = readFileSync(new URL("../src/styles/design-system.css", import.meta.url), "utf8");
  const at = css.indexOf(".gas-map > .maplibre-canvas");
  assert.ok(at > 0, "unlayered map container rule missing");
  const before = css.slice(0, at);
  const opened = (before.match(/@layer[^;{]*\{/g) ?? []).length;
  let depth = 0;
  for (const char of before) depth += char === "{" ? 1 : char === "}" ? -1 : 0;
  assert.ok(opened > 0 && depth === 0, "the rule must not sit inside an @layer block");
});
