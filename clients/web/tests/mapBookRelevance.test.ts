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
