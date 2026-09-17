/**
 * Architecture V2 Wave 5 - market projection consumption tests.
 *
 * The market surface reads one coherent payload: a single as-of, one time basis and
 * per-slice freshness. These tests pin the honesty rules that make that safe - an
 * unavailable slice never reads as an empty market, a restricted slice never reads
 * as a zero, freshness is the backend's answer rather than the client's clock, and
 * the store's market lane no longer joins several endpoints.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  MARK_CONTEXT_SLICE_LABEL_KEYS,
  MARKET_CONTEXT_SLICE_ORDER,
  contextAlerts,
  contextAsOf,
  contextIsUsable,
  contextNormalizedRows,
  contextOpportunities,
  contextQuotes,
  contextTimeBasis,
  degradedSlices,
  sliceReadings,
  sliceRows,
} from "../src/app/model/marketContextModel.ts";
import type {
  MarketContextProjectionDTO,
  ProjectionSliceDTO,
} from "../src/api/client.ts";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

/**
 * A slice fixture. Only the fields a case asserts on are overridden; the cast keeps
 * the heterogeneous per-slice row generics out of the fixture's way.
 */
function slice(overrides: Record<string, unknown> = {}): ProjectionSliceDTO<never> {
  return {
    available: true,
    source_references: ["runtime-postgresql"],
    row_count: 0,
    rows: null,
    payload: null,
    freshness: {
      state: "FRESH",
      basis: "gas-day",
      evaluated_at_utc: "2026-09-16T06:00:00+00:00",
      last_observed_at_utc: "2026-09-16T05:58:00+00:00",
      expected_within_minutes: 15,
      expectation_source: "source-registry",
      measured: null,
      derived_from: null,
    },
    entitlement: null,
    context_filter: null,
    limits: null,
    warnings: [],
    notes: [],
    ...overrides,
  } as unknown as ProjectionSliceDTO<never>;
}

function projection(
  overrides: Partial<
    Record<keyof MarketContextProjectionDTO["slices"], ProjectionSliceDTO<never>>
  > = {},
): MarketContextProjectionDTO {
  return {
    projection: "market-context",
    projection_version: "market-context/v1",
    as_of_utc: "2026-09-16T06:00:00+00:00",
    time_basis: { basis_id: "EU-CAM-UTC-2025", gas_day: "2026-09-16" },
    active_context: { gas_day: "2026-09-16" },
    slices: {
      quotes: slice({ row_count: 2, rows: [{ quote_id: "q1" }, { quote_id: "q2" }] }),
      normalized_quotes: slice({ row_count: 1, rows: [{ observation_id: "n1" }] }),
      market_observations: slice({ row_count: 3, rows: [{ observation_id: "m1" }] }),
      intraday_opportunities: slice({ row_count: 1, rows: [{ opportunity_id: "o1" }] }),
      spreads: slice({ row_count: 1, rows: [{ spread_id: "s1" }] }),
      monitoring: slice({ row_count: 1, rows: [{ alert_id: "a1" }] }),
      data_sources: slice({ row_count: 4, rows: [] }),
      ...overrides,
    },
    warnings: [],
    research_only: true,
    human_review_required: true,
  } as unknown as MarketContextProjectionDTO;
}

test("the projection carries one as-of and one time basis for every slice", () => {
  const payload = projection();

  assert.equal(contextAsOf(payload), "2026-09-16T06:00:00+00:00");
  assert.equal(contextTimeBasis(payload)?.basis_id, "EU-CAM-UTC-2025");
  assert.equal(contextTimeBasis(payload)?.gas_day, "2026-09-16");

  assert.equal(contextQuotes(payload).length, 2);
  assert.equal(contextNormalizedRows(payload).length, 1);
  assert.equal(contextOpportunities(payload).length, 1);
  assert.equal(contextAlerts(payload).length, 1);
  assert.equal(sliceRows(payload, "spreads").length, 1);

  // Every slice is reported in reading order with its own freshness.
  const readings = sliceReadings(payload);
  assert.deepEqual(readings.map((reading) => reading.key), MARKET_CONTEXT_SLICE_ORDER);
  assert.equal(readings.every((reading) => reading.freshnessState === "FRESH"), true);
  assert.equal(readings.every((reading) => reading.available), true);
  assert.deepEqual(degradedSlices(payload), []);
});

test("an unavailable slice never reads as an empty market", () => {
  const payload = projection({
    quotes: slice({ available: false, row_count: 0, rows: null }),
    monitoring: slice({ available: false, row_count: 0, rows: null }),
  });

  // No rows are produced...
  assert.deepEqual(contextQuotes(payload), []);
  assert.deepEqual(contextAlerts(payload), []);

  // ...but the readings say unavailable, so a surface can qualify its values.
  const degraded = degradedSlices(payload);
  assert.deepEqual(
    degraded.map((reading) => reading.key),
    ["quotes", "monitoring"],
  );
  assert.equal(degraded.every((reading) => reading.available === false), true);

  // The payload is not usable as the market source when quotes are missing.
  assert.equal(contextIsUsable(payload), false);
});

test("stale and restricted slices are reported, not hidden", () => {
  const payload = projection({
    market_observations: slice({
      freshness: {
        ...slice().freshness,
        state: "STALE",
        last_observed_at_utc: "2026-09-16T04:00:00+00:00",
      },
    }),
    normalized_quotes: slice({
      entitlement: {
        row_filter_applied: true,
        filtered_out: 12,
        reason: "source family not entitled",
      },
      context_filter: { applied: ["hub", "product"], rule: "exact hub and product match" },
    }),
  });

  const readings = sliceReadings(payload);
  const stale = readings.find((reading) => reading.key === "market_observations");
  const restricted = readings.find((reading) => reading.key === "normalized_quotes");

  assert.equal(stale?.freshnessState, "STALE");
  assert.equal(stale?.lastObservedAtUtc, "2026-09-16T04:00:00+00:00");
  assert.equal(restricted?.restricted, true);
  assert.equal(restricted?.filteredOut, 12);
  assert.equal(restricted?.contextRule, "exact hub and product match");
  assert.equal(restricted?.available, true);

  // Degradation is freshness and availability only: a slice the backend served in
  // full, minus the rows an entitlement withheld, is restricted, not degraded - the
  // strip reports the withheld rows separately instead of calling the slice stale.
  assert.deepEqual(
    degradedSlices(payload).map((reading) => reading.key),
    ["market_observations"],
  );
});

test("an absent projection is not usable and yields no readings", () => {
  assert.equal(contextIsUsable(null), false);
  assert.equal(contextIsUsable(undefined), false);
  assert.deepEqual(sliceReadings(null), []);
  assert.deepEqual(degradedSlices(null), []);
  assert.equal(contextAsOf(null), null);
  assert.equal(contextTimeBasis(null), null);
});

test("the market lane reads the projection instead of joining five endpoints", () => {
  const store = readWebSource("stores/api.ts");
  const start = store.indexOf("refreshMarketData: async () =>");
  const end = store.indexOf("fetchMe: async () =>", start);
  assert.ok(start > 0 && end > start, "market refresh lane found");
  const lane = store.slice(start, end);

  // One coherent read replaces the previous five-endpoint join...
  assert.match(
    lane,
    /loadWorkspaceEndpoint\(\(loaderOptions\) => api\.marketContext\(undefined, loaderOptions\), options\)/,
  );
  for (const endpoint of [
    "api.marketQuotes",
    "api.normalizedMarketObservations",
    "api.marketSpreads",
    "api.intradayOpportunities",
    "api.monitoringAlerts",
  ]) {
    assert.equal(lane.includes(endpoint), false, endpoint);
  }

  // ...and its slices are mapped into the fields the surfaces already read, so no
  // downstream model changes and the projection itself is kept for the strip.
  assert.match(store, /marketContext: projection,/);
  assert.match(store, /const usable = contextIsUsable\(projection\);/);
  assert.match(store, /mergeMarketQuotes\(state\.marketQuotes, contextQuotes\(projection\)\)/);
  assert.match(
    store,
    /mergeIntradayOpportunities\(state\.intradayOpportunities, contextOpportunities\(projection\)\)/,
  );
  assert.match(lane, /\.\.\.applyMarketContext\(state, projection, fxRates\)/);
  assert.match(lane, /recordOutcome\("marketContext", contextResult\)/);
});

test("a failed market read stays retryable and re-derives every slice it feeds", () => {
  const store = readWebSource("stores/api.ts");

  // The projection is retry-only: an initial workspace load must not request it a
  // second time, but the bounded retry control must still be able to re-read it.
  assert.match(store, /const RETRY_ONLY_LOADERS: Array<\[string, WorkspaceApiLoader\]> = \[/);
  assert.match(store, /\["marketContext", \(options\) => api\.marketContext\(undefined, options\)\]/);
  assert.match(store, /new Map\(\[\.\.\.WORKSPACE_LOADERS, \.\.\.RETRY_ONLY_LOADERS\]\)/);

  // A retried projection re-derives the whole lane rather than only the payload,
  // so a recovered read cannot leave stale slice values behind.
  assert.match(
    store,
    /if \(key === "marketContext"\) \{\s*Object\.assign\(patch, applyMarketContext\(state, outcome\.value\.data\)\);\s*continue;\s*\}/s,
  );
});

test("the market surface renders the coherent context and its vocabulary is bilingual", () => {
  const cockpit = readWebSource("components/MarketCockpit.tsx");
  const strip = readWebSource("components/MarketContextStrip.tsx");

  assert.match(cockpit, /import \{ MarketContextStrip \} from "@\/components\/MarketContextStrip"/);
  assert.match(cockpit, /<MarketContextStrip projection=\{api\.marketContext\} t=\{t\} \/>/);

  // The strip renders the backend's reading; it does not fetch or recompute.
  assert.match(strip, /sliceReadings\(projection\)/);
  assert.match(strip, /degradedSlices\(projection\)/);
  assert.match(strip, /contextAsOf\(projection\)/);
  for (const banned of ["useEffect", "api.", "fetch(", "Date.now"]) {
    assert.equal(strip.includes(banned), false, banned);
  }

  const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>;
  const keys = [
    "market_context.title",
    "market_context.as_of",
    "market_context.as_of_unknown",
    "market_context.time_basis",
    "market_context.all_fresh",
    "market_context.degraded",
    "market_context.rows",
    "market_context.restricted",
    ...MARKET_CONTEXT_SLICE_ORDER.map((key) => MARK_CONTEXT_SLICE_LABEL_KEYS[key]),
    ...["FRESH", "STALE", "MISSING", "UNKNOWN", "UNAVAILABLE"].map(
      (state) => `market_context.freshness.${state}`,
    ),
  ];
  for (const key of keys) {
    assert.ok(en[key]?.trim(), key);
    assert.ok(zh[key]?.trim(), key);
    assert.notEqual(en[key], zh[key], key);
  }
  assert.equal(Object.keys(en).length, Object.keys(zh).length);
});
