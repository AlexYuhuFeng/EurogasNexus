/**
 * The "Our book" view's model (design basis 2, J.5; CP-21): emphasis from the server's classes,
 * the opportunities' paths with the core's headline on the far hub, and the "why" lines.
 */
import assert from "node:assert/strict";
import test from "node:test";
import type { BookRelevanceDTO } from "../src/api/client.ts";
import {
  bookEmphasis,
  bookReasonLines,
  opportunityLabel,
  opportunityPathLines,
} from "../src/app/mapBookRelevance.ts";

const t = (key: string, options?: Record<string, unknown>) =>
  options ? `${key} ${JSON.stringify(options)}` : key;
const node = (id: string, lon: number, lat: number, node_type = "interconnection") => ({ id, lon, lat, node_type });
const nodes = new Map([
  ["ttf", node("ttf", 4.9, 52.1, "hub")],
  ["vip", node("vip", 6.9, 52.3)],
  ["the", node("the", 9.5, 51.5, "hub")],
]);

const relevance: BookRelevanceDTO = {
  rule: "",
  ours: [{ kind: "hub", ref: "ttf", name: "TTF", location: { lon: 4.9, lat: 52.1 }, reasons: [{ key: "contract_hub", contract: "Kestrel" }] }],
  contract_paths: [],
  reachable: [],
  opportunities: [
    {
      opportunity_id: "o1", type: "locational", type_code: "L", state: "actionable", emphasis: "pop",
      claim: "Buy TTF, sell THE", headline: { value: "1.25", unit: "EUR/MWh" }, period: "2026-12",
      simulated: true, from_hub: "TTF", to_hub: "THE", path_node_ids: ["ttf", "vip", "the"], via: ["VIP TTF-THE-H"],
    },
    {
      opportunity_id: "o2", type: "locational", type_code: "L", state: "watch", emphasis: "outline",
      claim: "Buy THE, sell TTF", headline: { value: "-0.10", unit: "EUR/MWh" }, period: "2026-12",
      simulated: false, from_hub: "THE", to_hub: "TTF", path_node_ids: ["the", "vip", "ttf"], via: ["VIP TTF-THE-H"],
    },
  ],
  outages_touching: [],
};

test("an opportunity's path pops out with ours and is labelled with the core's headline", () => {
  const emphasis = bookEmphasis(relevance);
  assert.ok(["ttf", "vip", "the"].every((id) => emphasis.ours.has(id)));
  const lines = opportunityPathLines(relevance, nodes);
  assert.deepEqual(lines.map((line) => [line.opportunityId, line.emphasis]), [["o1", "pop"], ["o2", "outline"]]);
  assert.deepEqual(lines[0].labelAt, [9.5, 51.5]);
  assert.equal(lines[0].label, "L +1.25 EUR/MWh sim");
  assert.equal(opportunityLabel(relevance.opportunities[1]), "L -0.10 EUR/MWh");
  assert.deepEqual(lines[0].coordinates[0], [4.9, 52.1]);
});

test("a selection on the book view says why it is there", () => {
  const lines = bookReasonLines(relevance, { nodeIds: ["ttf"] }, t);
  assert.ok(lines.some((line) => line.startsWith("map.book.reason.contract_hub")));
});

test("a route splits into done and to go at the share delivered, meeting at the cut", async () => {
  const { periodFraction, splitAtFraction } = await import("../src/app/mapBookRelevance.ts");
  const fraction = periodFraction({ label: "2026/27", start: "2026-10-01", end: "2027-10-01", elapsed_days: 73, total_days: 365 });
  assert.equal(fraction, 0.2);
  const { done, toGo } = splitAtFraction([[0, 0], [10, 0]], 0.25);
  assert.deepEqual(done, [[0, 0], [2.5, 0]]);
  assert.deepEqual(toGo, [[2.5, 0], [10, 0]]);
  assert.deepEqual(splitAtFraction([[0, 0], [1, 0]], 1).toGo, []);
  assert.equal(periodFraction(null), null);
});

test("a disruption's callout says what, until when and how much of ours", async () => {
  const { disruptionCallout } = await import("../src/app/mapBookRelevance.ts");
  const callout = disruptionCallout(
    {
      event_id: "u1", facility_name: "VIP THE-ZTP", status: "active", start_utc: "2026-11-18T06:00:00Z",
      end_utc: "2026-11-28T06:00:00Z", unavailable_gwh_d: 120, simulated: false, placement: "point", hub: null,
      location: { lon: 6, lat: 51 }, touches: "ours", contracts: ["A", "B"], affected_mwh_d: 18000, pulse: true,
    },
    t,
  );
  assert.equal(callout.title, "VIP THE-ZTP");
  assert.match(callout.lines[0], /map\.book\.disruption_out_until .*28 Nov/);
  assert.match(callout.lines[1], /map\.book\.disruption_touches .*"count":2.*"mwh":"18,000"/);
});

test("a cargo's ETA is read against its slot, and the window to act counts down", async () => {
  const { cargoProgress, windowLeft, windowClosed } = await import("../src/app/mapBookRelevance.ts");
  const now = Date.parse("2026-11-19T00:00:00Z");
  const voyage = cargoProgress(
    { cargo_id: "C1", departed_at_utc: "2026-11-09T00:00:00Z", eta_utc: "2026-11-29T00:00:00Z" },
    [{ cargo_id: "C1", window_start_utc: "2026-11-28T00:00:00Z", window_end_utc: "2026-12-03T00:00:00Z" }],
    now,
    t,
  );
  assert.equal(voyage.fraction, 0.5);
  assert.match(voyage.line, /map\.book\.cargo_late .*"count":1/);
  assert.equal(windowLeft("2026-11-19T02:10:00Z", now), "2 h 10 min");
  assert.equal(windowLeft("2026-11-18T23:00:00Z", now), null);
  assert.equal(windowClosed({ window_closes_utc: "2026-11-18T23:00:00Z" }, now), true);
});
