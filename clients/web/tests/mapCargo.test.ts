/**
 * Our cargo on the map (owner review 2026-11-26): where it is, where it is going, how long, and
 * what that rests on. Rule 19: a reported ETA is named by its basis; an ETA is computed only
 * when none was reported, and says how; nothing is drawn or stated that the data does not hold.
 */
import assert from "node:assert/strict";
import test from "node:test";
import type { MapCargoDTO } from "../src/api/client.ts";
import {
  arrivalPhrase,
  bearing,
  cargoDrawable,
  cargoEta,
  cargoHeading,
  cargoMapLabel,
  cargoSpeedKn,
  distanceNm,
  etaBasisPhrase,
  etaUtcText,
  formatRemaining,
} from "../src/app/mapCargo.ts";

const t = (key: string, options?: Record<string, unknown>) =>
  options ? `${key}(${Object.entries(options).map(([k, v]) => `${k}=${String(v)}`).join(",")})` : key;
const NOW = Date.parse("2026-11-26T12:00:00Z");

function cargo(overrides: Partial<MapCargoDTO> = {}): MapCargoDTO {
  return {
    cargo_id: "C1", vessel_name: "Meridian", vessel_imo: null, status: "laden", load_port: "Ras Laffan",
    departed_at_utc: null, destination_terminal: "Zeebrugge LNG", eta_utc: null, position_at_utc: "2026-11-26T10:00:00Z",
    volume_m3: null, energy_gwh: 1000, own: true, book_id: "lng", source_system: "AIS_FEED",
    origin: null, position: { lon: -10, lat: 40 }, destination: { lon: 3.2, lat: 51.33 },
    track: [[-12, 36], [-11, 38]], track_times: ["2026-11-25T10:00:00Z", "2026-11-25T22:00:00Z"],
    ...overrides,
  };
}

test("distance and bearing are great-circle figures", () => {
  // One degree of latitude is 60 nautical miles.
  assert.ok(Math.abs(distanceNm([0, 50], [0, 51]) - 60) < 0.2);
  assert.equal(Math.round(bearing([0, 50], [0, 51])), 0);
  assert.equal(Math.round(bearing([0, 0], [1, 0])), 90);
});

test("heading comes from the last two reported positions, never from the destination", () => {
  // From (-11, 38) to the reported position (-10, 40): north-north-east.
  const heading = cargoHeading(cargo())!;
  assert.ok(heading > 15 && heading < 30, String(heading));
  // One position and no track: no direction is claimed.
  assert.equal(cargoHeading(cargo({ track: [], track_times: [] })), null);
});

test("a reported ETA is named by its basis and source", () => {
  const eta = cargoEta(
    cargo({ eta_utc: "2026-11-28T16:00:00Z", eta: { basis: "ais_declared", confidence: null, source: "AIS_FEED", recorded_at_utc: null, text: "" } }),
    NOW,
  );
  assert.equal(eta.state, "eta");
  assert.equal(eta.basis, "ais");
  assert.equal(eta.remainingMs, 2 * 86_400_000 + 4 * 3_600_000);
  assert.equal(arrivalPhrase(eta, t), "map.cargo.arrives_in(span=map.cargo.duration_dh(days=2,hours=4))");
  assert.equal(etaBasisPhrase(eta, t), "map.cargo.basis.ais(source=AIS_FEED)");
  assert.equal(etaUtcText(eta.etaUtc), "28 Nov 2026 16:00 UTC");
  // A source that did not state its basis is said so, not promoted to AIS.
  const stated = cargoEta(cargo({ eta_utc: "2026-11-28T16:00:00Z" }), NOW);
  assert.equal(stated.basis, "stated");
  // The master's notice keeps its confidence.
  const master = cargoEta(
    cargo({ eta_utc: "2026-11-28T16:00:00Z", eta: { basis: "master_notice", confidence: "medium", source: "ETRM", recorded_at_utc: null, text: "" } }),
    NOW,
  );
  assert.equal(etaBasisPhrase(master, t), "map.cargo.basis.master(source=ETRM) · map.cargo.confidence.medium(defaultValue=medium)");
});

test("without a reported ETA one is computed from distance and speed, and says so", () => {
  // The track's two timed fixes and the reported position give the speed over the last leg.
  const speed = cargoSpeedKn(cargo())!;
  assert.ok(speed > 9 && speed < 11, String(speed));
  const eta = cargoEta(cargo(), NOW);
  assert.equal(eta.basis, "computed");
  assert.ok(eta.distanceNm! > 750 && eta.distanceNm! < 900, String(eta.distanceNm));
  assert.ok(eta.remainingMs! > 0);
  assert.match(etaBasisPhrase(eta, t), /^map\.cargo\.basis\.computed\(speed=\d+\.\d,distance=\d+\)$/);
  // A vessel not under way, or with no timed fixes, gets no invented ETA.
  assert.equal(cargoEta(cargo({ track_times: [null, null], position_at_utc: null }), NOW).state, "no_eta");
});

test("no destination and no ETA are stated, not drawn", () => {
  const unknown = cargoEta(cargo({ destination_terminal: null, destination: null }), NOW);
  assert.equal(unknown.state, "no_destination");
  assert.equal(arrivalPhrase(unknown, t), "map.cargo.no_destination");
  assert.deepEqual(cargoDrawable(cargo({ position: null })), { position: false, destination: true });
  assert.deepEqual(cargoDrawable(cargo({ destination: null })), { position: true, destination: false });
});

test("the map label is name, terminal and time to go", () => {
  const eta = cargoEta(cargo({ eta_utc: "2026-11-28T16:00:00Z" }), NOW);
  assert.equal(cargoMapLabel(cargo(), eta, t), "Meridian → Zeebrugge LNG · map.cargo.duration_dh(days=2,hours=4)");
  const passed = cargoEta(cargo({ eta_utc: "2026-11-26T06:00:00Z" }), NOW);
  assert.equal(arrivalPhrase(passed, t), "map.cargo.eta_passed(span=map.cargo.duration_hm(hours=6,minutes=0))");
  assert.equal(cargoMapLabel(cargo(), passed, t), "Meridian → Zeebrugge LNG · map.cargo.overdue_short");
  assert.equal(formatRemaining(40 * 60_000, t), "map.cargo.duration_m(minutes=40)");
});
