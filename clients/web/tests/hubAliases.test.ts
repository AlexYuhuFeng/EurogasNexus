/**
 * One hub, one code: a hub's other name (the Danish hub's OTC name GTF, CEGH's VTP) is the hub
 * itself wherever the client reads a code, so no screen lists it twice.
 */
import assert from "node:assert/strict";
import test from "node:test";
import { canonicalHub } from "../src/app/hubAliases.ts";
import { GAS_HUBS, hubOfPoint } from "../src/app/contractChoices.ts";
import { readBoardHubs } from "../src/app/model/priceBoard.ts";
import { zoneHubs } from "../src/app/model/tickerItems.ts";

test("a hub's other name is its registry code", () => {
  assert.equal(canonicalHub("GTF"), "ETF");
  assert.equal(canonicalHub(" vtp "), "CEGH");
  assert.equal(canonicalHub("TTF"), "TTF");
  assert.ok(!(GAS_HUBS as readonly string[]).includes("GTF"));
});

test("a point, a board and a zone written GTF are the Danish hub, once", () => {
  assert.equal(hubOfPoint("GTF"), "ETF");
  assert.equal(hubOfPoint("VTP Austria"), "CEGH");
  const store = { getItem: () => JSON.stringify(["TTF", "ETF", "GTF"]), setItem: () => undefined };
  assert.deepEqual(readBoardHubs(store), ["TTF", "ETF"]);
  assert.deepEqual(zoneHubs("GTF"), ["ETF"]);
});
