import assert from "node:assert/strict";
import test from "node:test";
import { lineMatters, NO_ROUTES_MATTER, routesInUse } from "../src/app/routeEmphasis.ts";

const line = (id: string, from: string, to: string, routeId = "") => ({ routeId, edge: { id }, from: { id: from }, to: { id: to } });

test("routes are context unless the book uses them", () => {
  const iuk = line("edge-iuk", "bacton", "zeebrugge");
  const bbl = line("edge-bbl", "balgzand", "bacton");
  assert.equal(lineMatters(iuk, NO_ROUTES_MATTER), false);
  assert.equal(lineMatters(bbl, NO_ROUTES_MATTER), false);

  // An NBP to TTF allocation the decision routed through IUK lights IUK, not BBL.
  const inUse = routesInUse(
    [
      { routeId: "nbp-ttf-iuk", routeState: "allocated", allocatedQuantityMwhPerDay: 24_000 },
      { routeId: "nbp-ttf-bbl", routeState: "candidate", allocatedQuantityMwhPerDay: null },
      { routeId: "nbp-peg", routeState: "allocated", allocatedQuantityMwhPerDay: 0 },
    ],
    new Map([["nbp-ttf-iuk", [{ id: "edge-iuk" }]], ["nbp-ttf-bbl", [{ id: "edge-bbl" }]]]),
  );
  assert.deepEqual(inUse, { routeIds: ["nbp-ttf-iuk"], edgeIds: ["edge-iuk"] });
  const matter = { routeIds: new Set(inUse.routeIds), edgeIds: new Set(inUse.edgeIds), pointIds: new Set<string>() };
  assert.equal(lineMatters(iuk, matter), true);
  assert.equal(lineMatters(bbl, matter), false);

  // A pipeline landing gas where the book has a live contract matters too.
  const langeled = line("edge-langeled", "nyhamna", "easington");
  assert.equal(lineMatters(langeled, { ...NO_ROUTES_MATTER, pointIds: new Set(["easington"]) }), true);
  // So does an indicative route the decision chose, by its route id.
  assert.equal(lineMatters(line("x", "a", "b", "nbp-ttf-iuk"), matter), true);
});
