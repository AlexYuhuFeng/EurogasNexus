/**
 * Architecture V2 Wave 5 - portfolio projection consumption tests.
 *
 * The portfolio surface used to join `/portfolio/live-summary`,
 * `/portfolio/screen-orders` and `/portfolio/pnl-snapshots` with three timestamps.
 * These tests pin what the single coherent read must preserve: one as-of, a summary
 * aggregate that is `null` rather than zero when it was not measured, per-slice
 * freshness and restriction, and a client that keeps one definition of "usable
 * slice" for every projection it reads.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  PORTFOLIO_SNAPSHOT_SLICE_LABEL_KEYS,
  PORTFOLIO_SNAPSHOT_SLICE_ORDER,
  degradedPortfolioSlices,
  portfolioReadings,
  snapshotAsOf,
  snapshotContracts,
  snapshotIsUsable,
  snapshotPnlSnapshots,
  snapshotResourceNote,
  snapshotResourcePoolOptions,
  snapshotScreenOrders,
  snapshotSummary,
  snapshotTimeBasis,
} from "../src/app/model/portfolioSnapshotModel.ts";
import { projectionSliceReadings } from "../src/app/model/projectionModel.ts";
import type {
  PortfolioSnapshotProjectionDTO,
  ProjectionSliceDTO,
} from "../src/api/client.ts";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

/** A slice fixture; only the fields a case asserts on are overridden. */
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
    Record<keyof PortfolioSnapshotProjectionDTO["slices"], ProjectionSliceDTO<never>>
  > = {},
): PortfolioSnapshotProjectionDTO {
  return {
    projection: "portfolio-snapshot",
    projection_version: "portfolio-snapshot/v1",
    as_of_utc: "2026-09-16T06:00:00+00:00",
    time_basis: {
      basis: "as_of_instant",
      gas_day: "2026-09-16",
      gas_day_calendar: "EU-CAM-UTC-2025",
    },
    active_context: { gas_day: "2026-09-16" },
    slices: {
      summary: slice({
        payload: { open_order_count: 3, net_volume_gbp: null, warnings: [] },
      }),
      screen_orders: slice({ row_count: 2, rows: [{ order_id: "o1" }, { order_id: "o2" }] }),
      pnl_snapshots: slice({ row_count: 1, rows: [{ snapshot_id: "s1" }] }),
      contracts: slice({ row_count: 1, rows: [{ contract_id: "c1" }] }),
      resources: slice({
        available: false,
        rows: null,
        payload: null,
        notes: ["Portfolio resources require the runtime PostgreSQL database."],
      }),
      data_sources: slice({ row_count: 4, rows: [] }),
      ...overrides,
    },
    warnings: [],
    research_only: true,
    human_review_required: true,
  } as unknown as PortfolioSnapshotProjectionDTO;
}

test("the snapshot carries one as-of and one time basis for every slice", () => {
  const payload = projection();

  assert.equal(snapshotAsOf(payload), "2026-09-16T06:00:00+00:00");
  assert.equal(snapshotTimeBasis(payload)?.gas_day, "2026-09-16");

  // The summary is an aggregate, not a row set: it is read as a payload.
  assert.equal(snapshotSummary(payload)?.open_order_count, 3);
  assert.equal(snapshotScreenOrders(payload).length, 2);
  assert.equal(snapshotPnlSnapshots(payload).length, 1);
  assert.equal(snapshotContracts(payload).length, 1);

  assert.deepEqual(
    portfolioReadings(payload).map((reading) => reading.key),
    PORTFOLIO_SNAPSHOT_SLICE_ORDER,
  );
  assert.equal(snapshotIsUsable(payload), true);
});

test("a summary the backend could not measure is null, never a zero", () => {
  const payload = projection({
    summary: slice({ available: false, payload: null }),
    screen_orders: slice({ available: false, rows: null }),
    pnl_snapshots: slice({ available: false, rows: null }),
  });

  // No aggregate is invented and no empty row set is substituted...
  assert.equal(snapshotSummary(payload), null);
  assert.deepEqual(snapshotScreenOrders(payload), []);
  assert.deepEqual(snapshotPnlSnapshots(payload), []);

  // ...and the payload is not usable as the portfolio surface's source, so the
  // surface keeps what it read before instead of rendering a flat portfolio.
  assert.equal(snapshotIsUsable(payload), false);
  // With no runtime database the backend marks every slice unavailable - including
  // the resource-pool slice it declares rather than approximates - so the whole
  // reading is degraded and the surface keeps what it read before.
  assert.deepEqual(
    degradedPortfolioSlices(payload).map((reading) => reading.key),
    ["summary", "screen_orders", "pnl_snapshots", "resources"],
  );
});

test("an unavailable resource-pool slice is declared, not approximated", () => {
  // The backend composes the pool from the same application code the route calls; when
  // the runtime store cannot serve it, the slice reports the route's identical degraded
  // block and explains itself instead of the client inventing an empty pool.
  const payload = projection({
    resources: slice({
      available: false,
      rows: null,
      payload: { scope: "RESOURCE_POOL_ROUTE_OPTIONS", data_source: "runtime-db-not-configured" },
      notes: ["Resource-pool options require the runtime PostgreSQL database."],
    }),
  });

  const reading = portfolioReadings(payload).find((item) => item.key === "resources");
  assert.equal(reading?.available, false);
  assert.equal(snapshotResourceNote(payload), "Resource-pool options require the runtime PostgreSQL database.");
  // The pool block is not rebuilt from a degraded slice, so the surface keeps the
  // options it already had rather than showing an empty pool.
  assert.equal(snapshotResourcePoolOptions(payload), null);
  // The rest of the snapshot is still usable: only the pool block is withheld.
  assert.equal(snapshotIsUsable(payload), true);
});

test("the pool block is read from the snapshot instead of a second route call", () => {
  const payload = projection({
    resources: slice({
      available: true,
      row_count: 2,
      rows: [
        { option_id: "option-1", label: "Gate to NCG", sale_price_gbp_mwh: 27.5 },
        { option_id: "option-2", label: "Gate to TTF", sale_price_gbp_mwh: 29.1 },
      ],
      payload: {
        scope: "portfolio-live",
        data_source: "runtime-postgresql",
        portfolio_resources: [{ resource_id: "resource-1", resource_name: "Gate slot" }],
        blockers: ["missing_fx_rate"],
        warnings: ["stale_sale_price"],
        counts: { portfolio_resources: 1, sale_options: 2 },
      },
    }),
  });

  const options = snapshotResourcePoolOptions(payload);
  assert.ok(options);
  assert.equal(options.scope, "portfolio-live");
  assert.equal(options.data_source, "runtime-postgresql");
  assert.equal(options.portfolio_resources.length, 1);
  assert.deepEqual(
    options.sale_options.map((option) => option.option_id),
    ["option-1", "option-2"],
  );
  assert.deepEqual(options.blockers, ["missing_fx_rate"]);
  assert.deepEqual(options.warnings, ["stale_sale_price"]);

  // A slice the backend withheld, or a payload without the pool's identifying
  // fields, yields no pool block at all rather than an empty one.
  assert.equal(snapshotResourcePoolOptions(projection()), null);
  assert.equal(
    snapshotResourcePoolOptions(projection({ resources: slice({ available: true, payload: {} }) })),
    null,
  );
  assert.equal(snapshotResourcePoolOptions(null), null);
});

test("stale and restricted slices are qualified, and an absent payload is not usable", () => {
  const payload = projection({
    pnl_snapshots: slice({
      freshness: { ...slice().freshness, state: "STALE" },
      entitlement: {
        row_filter_applied: true,
        filtered_out: 5,
        reason: "derived result access denied for source family",
      },
    }),
  });

  const readings = portfolioReadings(payload);
  const stale = readings.find((reading) => reading.key === "pnl_snapshots");
  assert.equal(stale?.freshnessState, "STALE");
  assert.equal(stale?.restricted, true);
  assert.equal(stale?.filteredOut, 5);

  assert.equal(snapshotIsUsable(null), false);
  assert.deepEqual(portfolioReadings(null), []);
  assert.deepEqual(degradedPortfolioSlices(null), []);
  assert.equal(snapshotAsOf(null), null);
  assert.equal(snapshotSummary(undefined), null);
});

test("both projection surfaces read through one shared implementation", () => {
  const marketModel = readWebSource("app/model/marketContextModel.ts");
  const portfolioModel = readWebSource("app/model/portfolioSnapshotModel.ts");
  const shared = readWebSource("app/model/projectionModel.ts");

  // One definition of "unavailable, stale, restricted": the two surfaces cannot
  // drift into disagreeing about what a usable slice is.
  for (const model of [marketModel, portfolioModel]) {
    assert.match(model, /from "\.\/projectionModel\.ts"/);
    assert.equal(model.includes("slice?.entitlement?.filtered_out"), false);
    assert.equal(model.includes("freshnessState: (slice"), false);
  }
  assert.match(shared, /export function projectionSliceReadings/);
  assert.match(shared, /export function degradedReadings/);

  // The shared reader is order-driven, so a surface's strip follows its own order.
  const readings = projectionSliceReadings(projection().slices, ["summary", "contracts"]);
  assert.deepEqual(readings.map((reading) => reading.key), ["summary", "contracts"]);
  assert.equal(readings[0].restricted, false);
});

test("the portfolio lane reads one projection instead of three endpoints", () => {
  const store = readWebSource("stores/api.ts");
  const loaders = /function workspaceLoaders\([\s\S]*?\n\}/.exec(store)?.[0] ?? "";
  assert.ok(loaders.length > 0, "workspace loaders found");

  // The read carries the query the pass was bound to - the published trading context - so the
  // payload declares the gas day the caller selected rather than the one the backend would derive
  // from its own clock, and every retry attempt of the pass asks the same question.
  assert.match(
    loaders,
    /\["portfolioSnapshot", \(options\) => api\.portfolioSnapshot\(query, options\)\]/,
  );
  for (const endpoint of [
    "api.screenOrders",
    "api.pnlSnapshots",
    "api.portfolioLiveSummary",
    // The pool block now comes from the snapshot's `resources` slice: loading the
    // route as well would compose the same pool twice on every workspace load.
    "api.resourcePoolOptions",
  ]) {
    assert.equal(loaders.includes(endpoint), false, endpoint);
  }

  // The three state fields come from the snapshot's slices, and a payload the
  // backend could not serve leaves the previous values in place.
  // The batch maps the payload through the same applier - unless a newer request owns the lane
  // (the context change's own re-read), in which case the lane is left as it was
  // (retainedPortfolioLane) and that re-read answers the context the caller is standing in.
  assert.match(store, /const portfolioIsCurrent = projectionClaimHolds\(claims\.portfolioSnapshot\);/);
  assert.match(store, /const portfolioLane = portfolioIsCurrent/);
  assert.match(store, /\? applyPortfolioSnapshot\(/);
  assert.match(store, /: retainedPortfolioLane\(get\(\)\);/);
  assert.match(store, /screenOrders: portfolioLane\.screenOrders,/);
  assert.match(store, /pnlSnapshots: portfolioLane\.pnlSnapshots,/);
  assert.match(store, /portfolioSummary: portfolioLane\.portfolioSummary,/);
  assert.match(store, /portfolioSnapshot: portfolioLane\.portfolioSnapshot,/);
  assert.match(store, /resourcePoolOptions: portfolioLane\.resourcePoolOptions,/);
  assert.match(
    store,
    /resourcePoolOptions: snapshotResourcePoolOptions\(projection\) \?\? state\.resourcePoolOptions,/,
  );
  assert.match(store, /if \(!snapshotIsUsable\(projection\)\) \{/);
  assert.match(
    store,
    /portfolioSnapshot: \(state, payload\) =>\s*applyPortfolioSnapshot\(state, payload as PortfolioSnapshotProjectionDTO \| null\),/,
  );

  // A retried projection re-derives every field it feeds.
  assert.match(store, /const applyProjection = PROJECTION_LANE_APPLIERS\[key\];/);
});

test("the portfolio surface renders the coherent context and its vocabulary is bilingual", () => {
  const workspace = readWebSource("components/PortfolioWorkspace.tsx");
  const strip = readWebSource("components/PortfolioContextStrip.tsx");
  const sharedStrip = readWebSource("components/ProjectionContextStrip.tsx");

  assert.match(workspace, /import \{ PortfolioContextStrip \} from "@\/components\/PortfolioContextStrip"/);
  assert.match(workspace, /<PortfolioContextStrip projection=\{api\.portfolioSnapshot\} t=\{t\} \/>/);

  // The strip renders the backend's reading; it does not fetch or recompute.
  assert.match(strip, /portfolioReadings\(projection\)/);
  assert.match(strip, /degradedPortfolioSlices\(projection\)/);
  assert.match(strip, /snapshotAsOf\(projection\)/);
  for (const banned of ["useEffect", "api.", "fetch(", "Date.now"]) {
    assert.equal(strip.includes(banned), false, banned);
  }
  // One presentational component serves every projection surface.
  assert.match(sharedStrip, /className=\{className \? `projection-context \$\{className\}` : "projection-context"\}/);
  for (const banned of ["useEffect", "api.", "fetch(", "Date.now"]) {
    assert.equal(sharedStrip.includes(banned), false, banned);
  }

  const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>;
  const keys = [
    "portfolio_context.title",
    "portfolio_context.as_of",
    "portfolio_context.as_of_unknown",
    "portfolio_context.time_basis",
    "portfolio_context.all_fresh",
    "portfolio_context.degraded",
    "portfolio_context.rows",
    "portfolio_context.restricted",
    ...PORTFOLIO_SNAPSHOT_SLICE_ORDER.map((key) => PORTFOLIO_SNAPSHOT_SLICE_LABEL_KEYS[key]),
    ...["FRESH", "STALE", "MISSING", "UNKNOWN", "UNAVAILABLE"].map(
      (state) => `portfolio_context.freshness.${state}`,
    ),
  ];
  for (const key of keys) {
    assert.ok(en[key]?.trim(), `en ${key}`);
    assert.ok(zh[key]?.trim(), `zh ${key}`);
    assert.notEqual(en[key], zh[key], key);
  }
  assert.equal(Object.keys(en).length, Object.keys(zh).length);
});
