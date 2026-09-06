import assert from "node:assert/strict";
import test from "node:test";
import {
  DEFAULT_TRADER_CONTEXT,
  isGasDayString,
  normalizeGasDay,
  normalizeHubId,
  traderContextKey,
} from "../src/app/context/traderContext.ts";
import {
  readPersistedTraderContext,
  writePersistedTraderContext,
} from "../src/app/context/contextPersistence.ts";
import {
  readSelectionContextUrl,
  readTraderContextUrl,
  resolveSelectionContext,
  resolveTraderContext,
} from "../src/app/context/contextUrl.ts";
import {
  normalizeSelectionId,
  selectionContextKey,
} from "../src/app/context/selectionContext.ts";
import { resultContextMatches } from "../src/app/context/contextInvalidation.ts";

const MEMORY = new Map<string, string>();
const storage = {
  getItem: (key: string) => MEMORY.get(key) ?? null,
  setItem: (key: string, value: string) => MEMORY.set(key, value),
};

function resetStorage() {
  MEMORY.clear();
}

test("default trader context is deterministic and gas day is a valid date", () => {
  assert.equal(DEFAULT_TRADER_CONTEXT.deliveryProduct, "all");
  assert.equal(DEFAULT_TRADER_CONTEXT.hubId, null);
  assert.equal(isGasDayString(DEFAULT_TRADER_CONTEXT.gasDay), true);
});

test("persisted valid context beats defaults when URL has no explicit keys", () => {
  resetStorage();
  writePersistedTraderContext(
    { gasDay: "2026-09-07", deliveryProduct: "day-ahead", hubId: "NBP" },
    storage,
  );
  const persisted = readPersistedTraderContext(storage);
  const resolved = resolveTraderContext({}, persisted);
  assert.deepEqual(resolved, {
    gasDay: "2026-09-07",
    deliveryProduct: "day-ahead",
    hubId: "NBP",
  });
});

test("explicit URL context beats persisted context", () => {
  const resolved = resolveTraderContext(
    { gasDay: "2026-09-08", product: "within-day", hub: "TTF" },
    { gasDay: "2026-09-07", deliveryProduct: "day-ahead", hubId: "NBP" },
  );
  assert.deepEqual(resolved, {
    gasDay: "2026-09-08",
    deliveryProduct: "within-day",
    hubId: "TTF",
  });
});

test("invalid URL context fails safely to defaults rather than persisted values", () => {
  const resolved = resolveTraderContext(
    { gasDay: "not-a-date", product: "unsupported-product", hub: "NOT_A_HUB" },
    { gasDay: "2026-09-07", deliveryProduct: "day-ahead", hubId: "NBP" },
  );
  assert.deepEqual(resolved, {
    gasDay: DEFAULT_TRADER_CONTEXT.gasDay,
    deliveryProduct: "all",
    hubId: null,
  });
});

test("optional hub context can be cleared and normalized", () => {
  assert.equal(normalizeHubId("nbp"), "NBP");
  assert.equal(normalizeHubId("not-a-hub"), null);
  assert.equal(normalizeHubId(null), null);
});

test("gas day normalization rejects impossible dates", () => {
  assert.equal(isGasDayString("2026-09-07"), true);
  assert.equal(isGasDayString("2026-02-30"), false);
  assert.equal(isGasDayString("07/09/2026"), false);
  assert.equal(normalizeGasDay("bad", "2026-09-09"), "2026-09-09");
});

test("selection ids use stable safe machine identifiers only", () => {
  assert.equal(normalizeSelectionId("bbl-forward-nl-gb"), "bbl-forward-nl-gb");
  assert.equal(normalizeSelectionId("run-abc123"), "run-abc123");
  assert.equal(normalizeSelectionId("../secrets"), null);
  assert.equal(normalizeSelectionId("display label"), null);
});

test("selection context restores from explicit deep-link query values", () => {
  const selection = resolveSelectionContext(
    readSelectionContextUrl("?workspace=scenario&route=route-1&resource=res-2&run=run-3"),
  );
  assert.deepEqual(selection, {
    routeId: "route-1",
    resourceId: "res-2",
    strategyRunId: "run-3",
  });
});

test("selection context is empty for legacy workspace-only links", () => {
  const selection = resolveSelectionContext(readSelectionContextUrl("?workspace=scenario"));
  assert.deepEqual(selection, {
    routeId: null,
    resourceId: null,
    strategyRunId: null,
  });
  assert.equal(selectionContextKey(selection), "-|-|-");
});

test("result context matching detects gas day, product, and hub changes", () => {
  const baseline = { gasDay: "2026-09-07", deliveryProduct: "day-ahead" as const, hubId: "NBP" as const };
  const key = traderContextKey(baseline);
  assert.equal(resultContextMatches(key, baseline), true);
  assert.equal(resultContextMatches(key, { ...baseline, gasDay: "2026-09-08" }), false);
  assert.equal(resultContextMatches(key, { ...baseline, deliveryProduct: "within-day" }), false);
  assert.equal(resultContextMatches(key, { ...baseline, hubId: "TTF" }), false);
  assert.equal(resultContextMatches(key, { ...baseline, hubId: null }), false);
});

test("URL reader preserves field presence for invalid-value fail-safe", () => {
  assert.deepEqual(readTraderContextUrl("?gasDay=bad&product=bad&hub=bad"), {
    gasDay: "bad",
    product: "bad",
    hub: "bad",
  });
});
