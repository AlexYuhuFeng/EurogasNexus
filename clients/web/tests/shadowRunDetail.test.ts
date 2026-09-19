/**
 * What a shadow run's economics rest on (owner decision on the unmounted terminal, completing
 * slice B of the D3 decision).
 *
 * `StrategyShadowRunTerminal.tsx` (838 lines) was mounted nowhere while the shadow task was served
 * by monitor management alone, so the price basis behind every figure, the pool's own cost, the
 * PnL each basis puts at risk and the provenance of the persisted run were unreachable. The owner
 * chose to keep the content and retire the parallel shell: the derivations live in
 * `app/model/shadowRunPresentation.ts`, the panels render inside the shadow task, and the
 * terminal's own tab set and dead props are gone.
 *
 * The theme these tests hold is that no figure is invented: a basis with nothing observed stays
 * unavailable rather than dropping out of the board, and a margin against a price or cost the
 * platform does not hold stays null rather than becoming a zero.
 */

import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";

import {
  PRICE_BASIS_ORDER,
  STALE_HOURS_BY_BASIS,
  basisCounts,
  basisExposureRows,
  classifyPriceBasis,
  contractPnlRows,
  isSimulatedSource,
  isStaleObservation,
  latestRun,
  maxAbsPnl,
  pnlCurveRows,
  poolQuantity,
  poolRows,
  priceBasisRows,
  priceMatchesBasis,
  priceTape,
  shadowRunProvenance,
  strategyWarningLabel,
  tapePriceFromMarketObservation,
  weightedPoolCost,
} from "../src/app/model/shadowRunPresentation.ts";

const WEB_SRC = new URL("../src/", import.meta.url);

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(relativePath, WEB_SRC), "utf8");
}

function webSourceExists(relativePath: string): boolean {
  return existsSync(new URL(relativePath, WEB_SRC));
}

const NOW = Date.parse("2026-09-19T12:00:00Z");

function marketObservation(overrides: Record<string, unknown>) {
  return {
    observation_id: "obs-1",
    market_venue: "ICE",
    product: "Within-day",
    price: 30,
    unit: "GBP/MWh",
    currency: "GBP",
    period_start_utc: "2026-09-19T10:00:00Z",
    period_end_utc: "2026-09-19T11:00:00Z",
    observed_at_utc: "2026-09-19T10:05:00Z",
    source_system: "ICE_OCM",
    hub: "NBP",
    tenor: "WITHIN_DAY",
    is_gas_price: true,
    price_gbp_mwh: 30,
    ...overrides,
  } as never;
}

test("the board always carries all seven bases, and an unobserved one is unavailable", () => {
  const tape = priceTape([], [marketObservation({})]);
  const rows = priceBasisRows({ tape, fxRates: [], nowMs: NOW });

  assert.deepEqual(
    rows.map((row) => row.basis),
    [...PRICE_BASIS_ORDER],
  );
  const iceOcm = rows.find((row) => row.basis === "ICE_OCM_MARK");
  assert.equal(iceOcm?.latestPrice, 30);
  assert.equal(iceOcm?.observationCount, 1);
  // A basis this deployment has not observed keeps null rather than a zero, and is counted.
  const eex = rows.find((row) => row.basis === "EEX_CURVE");
  assert.equal(eex?.latestPrice, null);
  assert.equal(eex?.observationCount, 0);
  assert.equal(eex?.latestObservedAtUtc, null);
  assert.equal(basisCounts(rows).unavailable, 5);
  // FX comes from the FX read, not from the price tape.
  assert.equal(rows.at(-1)?.basis, "FX");
  assert.equal(rows.at(-1)?.observationCount, 0);
});

test("a basis is classified from the source it names, and a simulated or stale one is marked", () => {
  assert.equal(
    classifyPriceBasis(tapePriceFromMarketObservation(marketObservation({}))!),
    "ICE_OCM_MARK",
  );
  const withinDay = tapePriceFromMarketObservation(
    marketObservation({ source_system: "ICIS_HEREN", market_venue: "ICIS" }),
  )!;
  assert.equal(classifyPriceBasis(withinDay), "ICIS_ASSESSMENT");
  // The extra matching rules see a basis the classifier would not have chosen on its own.
  assert.equal(priceMatchesBasis(withinDay, "ICIS_ASSESSMENT"), true);
  assert.equal(priceMatchesBasis(withinDay, "FX"), false);

  assert.equal(isSimulatedSource("GIE_ALSI_Sim"), true);
  assert.equal(isSimulatedSource("GIE_ALSI"), false);
  assert.equal(isSimulatedSource(null), false);

  // A simulated source raises the simulated count even when its observation is fresh.
  const tape = priceTape([], [
    marketObservation({ observation_id: "sim-1", source_system: "ICE_OCM_Sim" }),
  ]);
  const rows = priceBasisRows({ tape, fxRates: [], nowMs: NOW });
  const iceOcm = rows.find((row) => row.basis === "ICE_OCM_MARK");
  assert.equal(iceOcm?.simulatedCount, 1);
  assert.equal(iceOcm?.staleCount, 0);

  // Staleness is a statement about the figure the board shows: a basis is stale when its *latest*
  // observation is old, even if every earlier observation was old too - and it stays fresh when
  // only the archive behind it is old.
  const mixed = priceTape([], [
    marketObservation({ observation_id: "old", observed_at_utc: "2026-09-17T10:00:00Z" }),
    marketObservation({ observation_id: "new", observed_at_utc: "2026-09-19T11:55:00Z" }),
  ]);
  const mixedRows = priceBasisRows({ tape: mixed, fxRates: [], nowMs: NOW });
  const mixedIce = mixedRows.find((row) => row.basis === "ICE_OCM_MARK");
  assert.equal(mixedIce?.observationCount, 2);
  assert.equal(mixedIce?.staleCount, 0, "a live latest observation is not stale");
  assert.equal(mixedIce?.latestObservedAtUtc, "2026-09-19T11:55:00Z");

  const archiveOnly = priceTape([], [
    marketObservation({ observation_id: "old", observed_at_utc: "2026-09-17T10:00:00Z" }),
    marketObservation({ observation_id: "older", observed_at_utc: "2026-09-16T10:00:00Z" }),
  ]);
  const archiveRows = priceBasisRows({ tape: archiveOnly, fxRates: [], nowMs: NOW });
  assert.equal(archiveRows.find((row) => row.basis === "ICE_OCM_MARK")?.staleCount, 1);

  assert.equal(isStaleObservation("2026-09-19T10:05:00Z", 2, NOW), false);
  assert.equal(isStaleObservation("2026-09-19T05:00:00Z", 2, NOW), true);
  // An instant nobody can read is not evidence of currency.
  assert.equal(isStaleObservation("not-a-time", 2, NOW), true);
  assert.equal(isStaleObservation(null, 2, NOW), true);
  assert.ok(STALE_HOURS_BY_BASIS.WITHIN_DAY < STALE_HOURS_BY_BASIS.MONTHLY);
});

test("the pool's cost is weighted by volume, and an unknown side stays null", () => {
  const resources = [
    {
      resource_id: "r-1",
      resource_name: "NBP purchase",
      resource_type: "SUPPLY",
      delivery_mode: "PIPELINE",
      location_point_name: "NBP",
      available_quantity_mwh_per_day: 1000,
      contract_cost_gbp_mwh: 20,
      variable_cost_gbp_mwh: 1,
      tolerance_risk_allowance_gbp_mwh: 0.5,
    },
    {
      resource_id: "r-2",
      resource_name: "TTF purchase",
      resource_type: "SUPPLY",
      delivery_mode: "PIPELINE",
      location_point_name: "TTF",
      available_quantity_mwh_per_day: 3000,
      contract_cost_gbp_mwh: 24,
    },
  ] as never;

  const pool = poolRows(resources);
  // The all-in cost is the contract cost plus the variable and tolerance allowances stated.
  assert.equal(pool[0].costGbpMwh, 21.5);
  assert.equal(pool[1].costGbpMwh, 24);
  assert.equal(poolQuantity(pool), 4000);
  assert.equal(weightedPoolCost(pool), (1000 * 21.5 + 3000 * 24) / 4000);

  // No volume means no weighting, which is not a cost of zero.
  assert.equal(weightedPoolCost([]), null);
  assert.equal(weightedPoolCost([{ ...pool[0], quantityMwhPerDay: 0 }]), null);
});

test("a margin against an unknown price or cost is null, never a fabricated break-even", () => {
  const tape = priceTape([], [marketObservation({})]);
  const basis = priceBasisRows({ tape, fxRates: [], nowMs: NOW });

  const withoutCost = pnlCurveRows(basis, { quantityMwhPerDay: 4000, weightedCostGbpMwh: null });
  assert.ok(withoutCost.every((row) => row.marginGbpMwh === null));
  assert.ok(withoutCost.every((row) => row.pnlGbpPerDay === null));

  const withCost = pnlCurveRows(basis, { quantityMwhPerDay: 4000, weightedCostGbpMwh: 22 });
  const iceOcm = withCost.find((row) => row.basis === "ICE_OCM_MARK");
  assert.equal(iceOcm?.marginGbpMwh, 8);
  assert.equal(iceOcm?.pnlGbpPerDay, 32000);
  // A basis with no price has no margin even when the cost is known.
  assert.equal(withCost.find((row) => row.basis === "EEX_CURVE")?.marginGbpMwh, null);
  // FX is not a sale basis, so it is not on the curve.
  assert.equal(withCost.some((row) => row.basis === "FX"), false);

  const exposure = basisExposureRows(withCost, basis);
  assert.equal(
    exposure.find((row) => row.basis === "EEX_CURVE")?.observationCount,
    0,
  );
  assert.equal(maxAbsPnl(withCost), 32000);
  assert.equal(maxAbsPnl([]), 1);
});

test("a contract's contribution is its own margin, once a sale price exists", () => {
  const pool = poolRows([
    {
      resource_id: "r-1",
      resource_name: "NBP purchase",
      resource_type: "SUPPLY",
      delivery_mode: "PIPELINE",
      location_point_name: "NBP",
      available_quantity_mwh_per_day: 1000,
      contract_cost_gbp_mwh: 20,
    },
  ] as never);

  const unknown = contractPnlRows(pool, null);
  assert.equal(unknown[0].marginGbpMwh, null);
  assert.equal(unknown[0].dailyPnlGbp, null);

  const priced = contractPnlRows(pool, 30);
  assert.equal(priced[0].marginGbpMwh, 10);
  assert.equal(priced[0].dailyPnlGbp, 10000);
});

test("the provenance prefers the evaluated result and keeps the run's registry fields", () => {
  const runs = [
    {
      run_id: "run-old",
      strategy_id: "s-1",
      run_mode: "SHADOW",
      status: "COMPLETED",
      started_at_utc: "2026-09-18T05:00:00Z",
      manifest_hash: "hash-old",
      source_refs: ["operator-input"],
      missing_inputs: [],
      warnings: [],
      research_only: true,
      human_review_required: false,
      allocation_targets: [],
    },
    {
      run_id: "run-new",
      strategy_id: "s-1",
      run_mode: "SHADOW",
      status: "READY_FOR_HUMAN_REVIEW",
      run_type: "SHADOW",
      started_at_utc: "2026-09-19T05:00:00Z",
      data_cutoff_utc: "2026-09-18T23:00:00Z",
      dataset_snapshot_id: "ds-1",
      manifest_hash: "hash-new",
      engine_version: "shadow/v2",
      git_commit_sha: "abc1234",
      application_version: "0.2.0",
      paper_pnl_gbp: 1200,
      cumulative_pnl_gbp: 4200,
      day_ahead_average_gbp_mwh: 28.5,
      intraday_average_gbp_mwh: 30.25,
      source_refs: ["runtime-postgresql"],
      missing_inputs: ["baseline_run is required."],
      warnings: ["PROFILE_STAGES_NOT_REACHED:BACKTESTED"],
      research_only: true,
      human_review_required: true,
      allocation_targets: [],
    },
  ] as never;

  assert.equal(latestRun(runs)?.run_id, "run-new");

  const fromRun = shadowRunProvenance({ result: null, runs });
  assert.equal(fromRun.run?.run_id, "run-new");
  assert.equal(fromRun.humanReviewRequired, true);
  assert.deepEqual(fromRun.sourceRefs, ["runtime-postgresql"]);
  // The review boundary joins the engine's own statements rather than replacing them.
  assert.ok(fromRun.warnings.includes("HUMAN_REVIEW_REQUIRED"));
  assert.ok(fromRun.warnings.includes("baseline_run is required."));
  assert.equal(fromRun.candidateAction, null);

  const evaluated = shadowRunProvenance({
    result: {
      run_id: "run-live",
      strategy_id: "s-1",
      strategy_name: "NBP-TTF",
      run_mode: "SHADOW",
      status: "READY_FOR_HUMAN_REVIEW",
      weighted_score: 1,
      day_ahead_average_gbp_mwh: null,
      intraday_average_gbp_mwh: null,
      intraday_vs_day_ahead_spread_gbp_mwh: null,
      allocation_targets: [],
      missing_inputs: [],
      warnings: [],
      source_refs: ["operator-input"],
      candidate_action_for_review: "SELL_DAY_AHEAD",
      paper_pnl_gbp: 100,
      cumulative_pnl_gbp: 200,
      hit: true,
      research_only: true,
      human_review_required: false,
    },
    runs,
  });
  // The evaluation the operator just asked for is preferred over the persisted run, while the run
  // still supplies the engine, dataset and commit.
  assert.equal(evaluated.run?.run_id, "run-new");
  assert.equal(evaluated.candidateAction, "SELL_DAY_AHEAD");
  assert.deepEqual(evaluated.sourceRefs, ["operator-input"]);
  assert.equal(evaluated.humanReviewRequired, false);
  assert.deepEqual(evaluated.warnings, []);

  assert.equal(shadowRunProvenance({ result: null, runs: [] }).run, null);
  assert.equal(shadowRunProvenance({ result: null, runs: [] }).humanReviewRequired, false);
});

test("a warning code reads as prose, in the user's language", () => {
  const t = (key: string): string => {
    const table: Record<string, string> = {
      "strategy.warning.human_review_required": "Human review required",
      "strategy.warning.profile_stages_not_reached": "The run did not reach every declared stage",
    };
    return table[key] ?? key;
  };
  // A code the vocabulary covers is said in words, and the engine's own detail is kept.
  assert.equal(
    strategyWarningLabel("PROFILE_STAGES_NOT_REACHED:BACKTESTED", t),
    "The run did not reach every declared stage: BACKTESTED",
  );
  assert.equal(strategyWarningLabel("HUMAN_REVIEW_REQUIRED", t), "Human review required");
  // A code the vocabulary does not cover yet still reads as prose rather than as a raw token.
  assert.equal(strategyWarningLabel("SOMETHING_FAILED", t), "SOMETHING FAILED");
});

test("the detail is mounted in the shadow task and the parallel terminal is retired", () => {
  const workspace = readWebSource("components/strategy/StrategyLabWorkspace.tsx");
  const detail = readWebSource("components/strategy/StrategyShadowRunDetail.tsx");
  const model = readWebSource("app/model/shadowRunPresentation.ts");

  // Mounted inside the task that manages the monitors, so a shadow run's two halves are read
  // together, and no new page was created for it.
  assert.match(workspace, /<StrategyShadowRunDetail language=\{language\} t=\{t\} \/>/);
  assert.match(workspace, /controller\.task === "shadow"/);
  assert.equal(webSourceExists("components/StrategyShadowRunTerminal.tsx"), false);
  assert.equal(webSourceExists("components/strategy/StrategyShadowRunSections.tsx"), true);

  // It reads only what the identity already received, and it starts nothing: running a shadow
  // evaluation stays the workspace's primary action.
  assert.match(detail, /useApiStore\(\(state\) => state\.normalizedMarkets\)/);
  assert.match(detail, /useApiStore\(\(state\) => state\.resourcePoolOptions\)/);
  assert.match(detail, /useApiStore\(\(state\) => state\.strategyRuns\)/);
  assert.equal(/apiClient\.|api\.[a-zA-Z]+\(/.test(detail), false, "the panel calls no route");
  assert.equal(/onClick=\{[^}]*run[A-Z]/.test(detail), false, "the panel starts no run");

  // The shared evidence block and the one UTC formatter, not a hand-rolled instant.
  assert.match(detail, /<EvidenceBlock/);
  assert.match(detail, /formatUtcTimestamp\(value\)/);
  assert.equal(/toLocaleTimeString/.test(detail), false);

  // The arithmetic lives in the model, which is where it can be tested without a render.
  assert.equal(/useState|useMemo|useEffect/.test(model), false, "the model is pure");
});

test("the shadow detail vocabulary is bilingual", () => {
  const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>;
  const keys = [
    "strategy.shadow_detail_note",
    "strategy.observation_time_basis",
    "strategy.contract_pnl_note",
    "strategy.run_provenance_note",
    "strategy.reproducible_yes",
    "strategy.price_basis_board",
    "strategy.selected_price_basis",
    "strategy.basis_exposure_ladder",
    "strategy.pnl_curve",
    "strategy.contract_pnl_attribution",
    "strategy.cumulative_paper_pnl",
    "strategy.run_provenance",
    "strategy.warning_stack",
    "strategy.unavailable_basis_count",
    "strategy.stale_basis_count",
    "strategy.simulated_basis_count",
  ];
  for (const key of keys) {
    assert.ok(en[key]?.trim(), `en ${key}`);
    assert.ok(zh[key]?.trim(), `zh ${key}`);
    assert.notEqual(en[key], zh[key], key);
  }
  // Every basis the board can present has a label in both locales.
  for (const basis of PRICE_BASIS_ORDER) {
    const key = `strategy.basis.${basis.toLowerCase()}`;
    assert.ok(en[key]?.trim(), `en ${key}`);
    assert.ok(zh[key]?.trim(), `zh ${key}`);
  }
});
