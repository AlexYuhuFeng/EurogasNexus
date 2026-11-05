/**
 * "Our book" on the map: what is in play comes first, what is done is history, and a
 * delivered cargo replays along its timed track.
 */
import assert from "node:assert/strict";
import test from "node:test";
import type { MapCargoDTO, MapSituationDTO } from "../src/api/client.ts";
import { bookItems, bookSituation, gasYearWindow, liveSituation, replayAt, replayTrack } from "../src/app/mapBook.ts";

const NOW = Date.parse("2026-11-05T12:00:00Z");
const at = (ref_id: string) => ({ lon: 1, lat: 52, ref_id, ref_kind: "node" as const });
const cargo = (cargo_id: string, status: MapCargoDTO["status"], extra: Partial<MapCargoDTO> = {}): MapCargoDTO => ({
  cargo_id, vessel_name: cargo_id, vessel_imo: null, status, load_port: "Ras Laffan", departed_at_utc: null,
  destination_terminal: "Isle of Grain", eta_utc: null, position_at_utc: null, volume_m3: null, energy_gwh: 1000,
  own: true, book_id: "uk", source_system: "ETRM", origin: null, position: null,
  destination: { lon: 0.7, lat: 51.4, ref_id: "grain" }, track: [], ...extra,
});
const situation: MapSituationDTO = {
  as_of_utc: "2026-11-05T12:00:00Z",
  outages: [
    { status: "active", event_id: "A" } as never,
    { status: "scheduled", event_id: "B" } as never,
  ],
  flows: [{ point_id: "x" } as never],
  contracts: [
    { contract_id: "now", contract_name: "Langeled", resource_type: "PIPELINE_IMPORT", delivery_point: "Easington", gas_year: "2026", delivery_mwh_d: 24000, entry_capacity_mwh_d: null, book_id: "uk", location: at("easington") },
    { contract_id: "old", contract_name: "Old supply", resource_type: "PIPELINE_IMPORT", delivery_point: "Bacton", gas_year: "2024", delivery_mwh_d: 5000, entry_capacity_mwh_d: null, book_id: "uk", location: at("bacton") },
    { contract_id: "next", contract_name: "Next year", resource_type: "PIPELINE_IMPORT", delivery_point: "St Fergus", gas_year: "2027+", delivery_mwh_d: 9000, entry_capacity_mwh_d: null, book_id: "uk", location: at("fergus") },
  ],
  cargoes: [
    cargo("SEA", "laden", { eta_utc: "2026-11-09T00:00:00Z" }),
    cargo("SOON", "laden", { departed_at_utc: "2026-11-08T00:00:00Z", eta_utc: "2026-11-25T00:00:00Z" }),
    cargo("DONE", "delivered", { eta_utc: "2026-10-01T00:00:00Z", track: [[51.5, 25.9], [-5, 45]], track_times: ["2026-09-15T00:00:00Z", "2026-09-25T00:00:00Z"] }),
    { ...cargo("THEIRS", "laden"), own: false },
  ],
  regas_slots: [
    { slot_id: "OPEN", terminal_name: "Isle of Grain", window_start_utc: "2026-11-04T00:00:00Z", window_end_utc: "2026-11-07T00:00:00Z", active: true, send_out_gwh_d: 190, energy_gwh: null, cargo_id: null, book_id: "uk", location: at("grain") },
    { slot_id: "ENDED", terminal_name: "Gate", window_start_utc: "2026-10-01T00:00:00Z", window_end_utc: "2026-10-05T00:00:00Z", active: false, send_out_gwh_d: 190, energy_gwh: null, cargo_id: null, book_id: "uk", location: at("gate") },
  ],
  unlocated: { outages: 0, contracts: 0, cargoes: 0, regas_slots: 0 },
  positions_included: true,
};

test("gas years read as delivery periods", () => {
  assert.deepEqual(gasYearWindow("2026"), { start: Date.UTC(2026, 9, 1, 5), end: Date.UTC(2027, 9, 1, 5) });
  assert.equal(gasYearWindow("2026+")?.end, null);
  assert.equal(gasYearWindow("winter"), null);
});

test("the book lists what is in play first, the soonest first, and keeps the rest as history", () => {
  const items = bookItems(situation, NOW);
  assert.deepEqual(
    items.map((item) => `${item.phase}:${item.id}`),
    [
      "in_progress:OPEN", "in_progress:SEA", "in_progress:now",
      "next_7_days:SOON",
      "later:next",
      "completed:ENDED", "completed:DONE", "completed:old",
    ],
  );
  // Other companies' cargoes are not our book.
  assert.ok(!items.some((item) => item.id === "THEIRS"));
});

test("the book picture drops what is done and what is not ours; the network picture keeps the market", () => {
  const book = bookSituation(situation, NOW)!;
  assert.deepEqual(book.cargoes.map((c) => c.cargo_id), ["SEA", "SOON"]);
  assert.deepEqual(book.regas_slots.map((s) => s.slot_id), ["OPEN"]);
  assert.deepEqual(book.contracts.map((c) => c.contract_id), ["now", "next"]);
  assert.deepEqual(book.outages.map((o) => o.event_id), ["A"]);
  assert.equal(book.flows.length, 0);
  const live = liveSituation(situation, NOW)!;
  assert.deepEqual(live.cargoes.map((c) => c.cargo_id), ["SEA", "SOON", "THEIRS"]);
  assert.equal(live.flows.length, 1);
});

test("a delivered cargo replays along its timed track to the terminal", () => {
  const done = situation.cargoes.find((c) => c.cargo_id === "DONE")!;
  const track = replayTrack(done)!;
  assert.equal(track.coords.length, 3); // two reported points and the terminal at arrival
  assert.equal(track.end, Date.parse("2026-10-01T00:00:00Z"));
  const halfway = replayAt(track, Date.parse("2026-09-20T00:00:00Z"));
  assert.deepEqual(halfway.at, [23.25, 35.45]);
  assert.equal(halfway.sailed.length, 2);
  assert.deepEqual(replayAt(track, track.end).at, [0.7, 51.4]);
  // Untimed points are not invented into a voyage.
  assert.equal(replayTrack(cargo("X", "laden", { track: [[1, 2], [3, 4]] })), null);
});
