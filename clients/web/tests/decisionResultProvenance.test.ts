/**
 * Result provenance for the Decision workspace's governed computes.
 *
 * The observed defect: the two actions' results were provenanced to the trading context
 * (`gasDay|product|hub`) only, so editing a saved contract, refreshing the pool/market read or
 * changing a consumed financing input left the previous result displayed as current on every
 * consumer, not just Scenario. `app/model/decisionResultProvenance.ts` now owns one posture:
 * the caller-known effective inputs are canonicalised into an input identity, a run is stamped
 * with `scope::context::identity`, and a held result whose key differs from the key of the
 * inputs the caller now knows is stale.
 *
 * These tests hold the model to its contract with the real request builders: the exact request
 * is the identity (so request-ignored draft fields cannot invalidate anything), saved-contract
 * edit tokens and market-read marks are bound (so a revision or read update does), and the two
 * actions carry distinct keys because their dependencies differ. The runner cannot render
 * React, so the surface wiring is asserted from source in `decisionActionLifecycle.test.ts`.
 */

import assert from "node:assert/strict";
import test from "node:test";

import type { PortfolioResourceDTO, PortfolioSaleOptionDTO } from "../src/api/client.ts";
import type { ContractDraft } from "../src/app/model/contractDraftModel.ts";
import {
  UNORDERED_DECISION_INPUT_KEYS,
  canonicalDecisionIdentity,
  decisionInputIdentity,
  decisionProvenanceKey,
  decisionProvenanceMismatch,
  marketReadIdentityTokens,
  savedContractIdentityTokens,
} from "../src/app/model/decisionResultProvenance.ts";
import { buildResourcePoolOptimizationRequest } from "../src/app/resourcePoolRequest.ts";
import { buildRouteRecommendationRequest } from "../src/app/routeRecommendationRequest.ts";
import { selectScenarioRouteEconomics } from "../src/app/model/scenarioRouteEconomics.ts";

function draft(overrides: Partial<ContractDraft> = {}): ContractDraft {
  return {
    contract_id: "operator-ttf-supply-2025",
    contract_name: "Operator TTF supply 2025",
    resource_type: "PIPELINE_IMPORT",
    counterparty: "Operator draft counterparty",
    contract_type: "EFET physical supply",
    delivery_point_name: "TTF",
    gas_year: "2025+",
    delivery_quantity_mwh_per_day: 100,
    contract_price_gbp_mwh: 30,
    nbp_sale_price_gbp_mwh: 31,
    physical_exit_sale_price_gbp_mwh: 30.5,
    physical_exit_point_name: "NBP",
    title_transfer_point: "TTF virtual trading point",
    beach_delivery_point: "Bacton Beach",
    index_basis: "TTF day-ahead index",
    terminal_access: "BBL / Bacton terminal access to confirm",
    capacity_expiry: "operator to enter",
    document_name: "manual draft",
    document_status: "MANUAL_DRAFT",
    source_reference: "operator manual entry",
    governing_law: "English law",
    delivery_tolerance_pct: 2,
    nomination_tolerance_pct: 1,
    tolerance_risk_allowance_gbp_mwh: 0.1,
    variable_cost_gbp_mwh: 0,
    regas_fee_gbp_mwh: 0,
    fuel_loss_allowance_pct: 0,
    settlement_frequency: "monthly",
    upstream_payment_lag_days: 20,
    screen_sale_cash_lag_days: 1,
    annual_financing_rate_pct: 6,
    owned_entry_capacity_mwh_per_day: null,
    owned_exit_capacity_mwh_per_day: null,
    allowed_exit_points: ["NBP", "TTF"],
    eligible_sale_modes: ["TARGET_MARKET_SALE", "LOCAL_MARKET_SALE", "REROUTE_SALE"],
    preserved_notes: null,
    stored_edit: null,
    ...overrides,
  };
}

const POOL_RESOURCES: PortfolioResourceDTO[] = [
  {
    resource_id: "preview-portfolio-contract-ttf-pool-2025",
    resource_name: "Preview TTF portfolio supply 2025",
    resource_type: "PIPELINE_IMPORT",
    delivery_mode: "PHYSICAL_ENTRY_DELIVERY",
    location_point_name: "TTF",
    available_quantity_mwh_per_day: 10_000,
    contract_cost_gbp_mwh: 25,
    required_tso_access: [],
    accessible_tsos: ["BBL Company"],
  },
];

const SALE_OPTIONS: PortfolioSaleOptionDTO[] = [
  {
    option_id: "route-1",
    label: "TTF -> BBL -> NBP",
    delivery_mode: "VIRTUAL_HUB_SALE",
    target_point_name: "NBP",
    sale_price_gbp_mwh: 52.5,
    sale_price_currency: "GBP",
    sale_price_unit: "GBP/MWh",
    sale_price_source_system: "ICE_OCM",
    sale_price_source_reference: "market_observation:obs-1",
    sale_price_observed_at_utc: "2026-10-01T05:00:00+00:00",
    sale_price_freshness: "fresh",
    sale_price_quality_score: 1,
    sale_price_simulated: false,
    route_cost_gbp_mwh: 1.75,
    route_cost_currency: "GBP",
    route_cost_unit: "GBP/MWh",
    capacity_limit_mwh_per_day: 2000,
    required_tso_access: ["BBL Company"],
  },
];

const TOTAL_POOL_VOLUME = 10_000;

const SAVED_CONTRACTS = [
  { contract_id: "contract-a", edit_token: "token-1", updated_at_utc: "2026-10-01T08:00:00Z" },
  { contract_id: "contract-b", edit_token: "token-2", updated_at_utc: "2026-10-01T08:00:00Z" },
];

function optimizeIdentity(
  overrides: Parameters<typeof draft>[0] = {},
  contracts: ReadonlyArray<{
    contract_id: string;
    edit_token?: string | null;
    annual_financing_rate_pct?: number | null;
  }> = SAVED_CONTRACTS,
) {
  const request = buildResourcePoolOptimizationRequest(
    draft(overrides),
    POOL_RESOURCES,
    SALE_OPTIONS,
    contracts,
  );
  assert.ok(request, "the fixture draft must compose an optimiser request");
  return decisionInputIdentity({
    request,
    savedContracts: contracts,
    marketReads: SALE_OPTIONS,
  });
}

function compareIdentity(
  saleOptions: ReadonlyArray<PortfolioSaleOptionDTO> = SALE_OPTIONS,
  contracts: ReadonlyArray<{ contract_id: string; edit_token?: string | null; gas_year?: string }> = SAVED_CONTRACTS,
) {
  const request = buildRouteRecommendationRequest(
    POOL_RESOURCES,
    saleOptions,
    TOTAL_POOL_VOLUME,
    contracts,
  );
  return decisionInputIdentity({ request, savedContracts: contracts, marketReads: saleOptions });
}

test("the canonical identity sorts object keys but keeps order where it is meaningful", () => {
  assert.equal(
    canonicalDecisionIdentity({ b: 1, a: null }),
    canonicalDecisionIdentity({ a: null, b: 1 }),
  );
  // A recorded null is not the same identity as an absent field.
  assert.notEqual(canonicalDecisionIdentity({ a: null }), canonicalDecisionIdentity({}));
  // Numbers, zero and false are preserved exactly rather than coerced.
  assert.notEqual(canonicalDecisionIdentity({ n: 0 }), canonicalDecisionIdentity({ n: null }));
  assert.notEqual(canonicalDecisionIdentity({ n: 0 }), canonicalDecisionIdentity({ n: false }));
  assert.notEqual(canonicalDecisionIdentity({ n: 1 }), canonicalDecisionIdentity({ n: "1" }));
  assert.notEqual(canonicalDecisionIdentity({ n: Number.NaN }), canonicalDecisionIdentity({ n: 0 }));

  // Semantically unordered string sets carry the same identity in any order...
  for (const key of UNORDERED_DECISION_INPUT_KEYS) {
    assert.equal(
      canonicalDecisionIdentity({ [key]: ["B", "A"] }),
      canonicalDecisionIdentity({ [key]: ["A", "B"] }),
      `${key} is an unordered set`,
    );
  }
  // ...while order-meaningful arrays (candidates, resources, observations) keep their order.
  assert.notEqual(
    canonicalDecisionIdentity({ candidates: [{ id: "a" }, { id: "b" }] }),
    canonicalDecisionIdentity({ candidates: [{ id: "b" }, { id: "a" }] }),
  );
});

test("saved-contract tokens are ordered sets and fall back to updated_at, then a stated marker", () => {
  const tokens = savedContractIdentityTokens([
    { contract_id: "b", edit_token: "t2" },
    { contract_id: "a", edit_token: "t1" },
    { contract_id: "a", edit_token: "t1" },
  ]);
  assert.deepEqual(tokens, ["a@t1", "b@t2"]);
  assert.deepEqual(
    savedContractIdentityTokens([{ contract_id: "a", updated_at_utc: "2026-10-01T00:00:00Z" }]),
    ["a@updated_at:2026-10-01T00:00:00Z"],
  );
  assert.deepEqual(savedContractIdentityTokens([{ contract_id: "a" }]), ["a@unavailable"]);
});

test("market-read tokens carry the observation identity, not a server snapshot claim", () => {
  const [token] = marketReadIdentityTokens(SALE_OPTIONS);
  assert.ok(token.includes("route-1"), "the option id names the read");
  assert.ok(token.includes("2026-10-01T05:00:00+00:00"), "the observation instant is bound");
  assert.ok(token.includes("market_observation:obs-1"), "the source reference is bound");
  assert.equal(marketReadIdentityTokens([...SALE_OPTIONS, SALE_OPTIONS[0]]).length, 1, "deduplicated");
});

test("a draft field the optimiser request ignores cannot change the input identity", () => {
  const baseline = optimizeIdentity();
  const intentionallyNotConsumed: Array<keyof ContractDraft> = [
    "delivery_quantity_mwh_per_day",
    "contract_price_gbp_mwh",
    "nbp_sale_price_gbp_mwh",
    "physical_exit_sale_price_gbp_mwh",
    "delivery_tolerance_pct",
    "nomination_tolerance_pct",
    "screen_sale_cash_lag_days",
    "owned_entry_capacity_mwh_per_day",
  ];
  for (const key of intentionallyNotConsumed) {
    assert.equal(
      optimizeIdentity({ [key]: 987_654.321 }),
      baseline,
      `${key} is not consumed by the optimiser request and must not invalidate its result`,
    );
  }
  // The one draft field the request consumes does change the identity: the financing fallback
  // is applied only while no saved contract records a rate.
  assert.notEqual(optimizeIdentity({ annual_financing_rate_pct: 9 }), baseline);
  // A saved contract rate governs the request, so a draft edit is inert for the identity too.
  const savedRate = [{ contract_id: "contract-a", edit_token: "token-1", annual_financing_rate_pct: 4.25 }];
  assert.equal(optimizeIdentity({ annual_financing_rate_pct: 9 }, savedRate), optimizeIdentity({}, savedRate));
  // Changing the saved rate itself does change the request and therefore the identity.
  const savedRateChanged = [{ contract_id: "contract-a", edit_token: "token-1", annual_financing_rate_pct: 5 }];
  assert.notEqual(optimizeIdentity({}, savedRateChanged), optimizeIdentity({}, savedRate));
});

test("a saved-contract revision and a moved market read invalidate, a same-value re-read does not", () => {
  const baseline = optimizeIdentity();
  // A contract save refreshes the edit token even when the numbers happen to be unchanged:
  // the client can no longer vouch that the pool read came from this revision.
  assert.notEqual(
    optimizeIdentity({}, [
      { contract_id: "contract-a", edit_token: "token-1-edited" },
      { contract_id: "contract-b", edit_token: "token-2" },
    ]),
    baseline,
  );
  // The pool read's own economics are part of the request identity.
  const movedPriceOptions = [{ ...SALE_OPTIONS[0], sale_price_gbp_mwh: 53.5 }];
  const movedPriceRequest = buildResourcePoolOptimizationRequest(
    draft(),
    POOL_RESOURCES,
    movedPriceOptions,
    SAVED_CONTRACTS,
  );
  assert.ok(movedPriceRequest);
  assert.notEqual(
    decisionInputIdentity({
      request: movedPriceRequest,
      savedContracts: SAVED_CONTRACTS,
      marketReads: movedPriceOptions,
    }),
    baseline,
  );
  // A byte-identical re-read yields the identical identity by design (not a fake invalidation).
  assert.equal(optimizeIdentity(), baseline);
});

test("the comparison binds the market read even though its request projection drops the marks", () => {
  const baseline = compareIdentity();
  const newerMark = [{ ...SALE_OPTIONS[0], sale_price_observed_at_utc: "2026-10-01T06:00:00+00:00" }];

  const baselineRequest = buildRouteRecommendationRequest(
    POOL_RESOURCES,
    SALE_OPTIONS,
    TOTAL_POOL_VOLUME,
    SAVED_CONTRACTS,
  );
  const newerRequest = buildRouteRecommendationRequest(
    POOL_RESOURCES,
    newerMark,
    TOTAL_POOL_VOLUME,
    SAVED_CONTRACTS,
  );
  assert.deepEqual(newerRequest, baselineRequest, "the sent candidates carry no observation mark");
  assert.notEqual(
    compareIdentity(newerMark),
    baseline,
    "the read the candidates came from is what moved, and the identity states that",
  );
  // The same applies to a saved-contract revision behind the compared pool.
  assert.notEqual(
    compareIdentity(SALE_OPTIONS, [{ contract_id: "contract-a", edit_token: "token-1-edited" }, SAVED_CONTRACTS[1]]),
    baseline,
  );
});

test("each action and context carries its own provenance key", () => {
  const optimizeRequest = buildResourcePoolOptimizationRequest(
    draft(),
    POOL_RESOURCES,
    SALE_OPTIONS,
    SAVED_CONTRACTS,
  );
  assert.ok(optimizeRequest);
  const optimizeKey = decisionProvenanceKey(
    "optimize_pool",
    "2026-10-01|day-ahead|NBP",
    decisionInputIdentity({ request: optimizeRequest, savedContracts: SAVED_CONTRACTS }),
  );
  const compareKey = decisionProvenanceKey(
    "compare_routes",
    "2026-10-01|day-ahead|NBP",
    decisionInputIdentity({ request: buildRouteRecommendationRequest(POOL_RESOURCES, SALE_OPTIONS, TOTAL_POOL_VOLUME, SAVED_CONTRACTS), savedContracts: SAVED_CONTRACTS }),
  );
  assert.notEqual(optimizeKey, compareKey, "the two actions' dependencies are distinct");
  assert.notEqual(
    optimizeKey,
    decisionProvenanceKey(
      "optimize_pool",
      "2026-10-02|day-ahead|NBP",
      decisionInputIdentity({ request: optimizeRequest, savedContracts: SAVED_CONTRACTS }),
    ),
    "a trading-context switch changes the key",
  );
  assert.ok(optimizeKey.startsWith("optimize_pool::2026-10-01|day-ahead|NBP::"));
});

test("the mismatch rule treats an unknown key on either side as stale, and no payload as no mismatch", () => {
  assert.equal(decisionProvenanceMismatch(false, null, null), false);
  assert.equal(decisionProvenanceMismatch(false, "a", "b"), false);
  assert.equal(decisionProvenanceMismatch(true, null, "current"), true);
  assert.equal(decisionProvenanceMismatch(true, "held", null), true);
  assert.equal(decisionProvenanceMismatch(true, "current", "current"), false);
  assert.equal(decisionProvenanceMismatch(true, "held", "current"), true);
});

test("a consumer selector fed the gated payload reads unavailable, not another context's economics", () => {
  const contextKey = "2026-10-01|day-ahead|NBP";
  const compareRequest = (saleOptions: ReadonlyArray<PortfolioSaleOptionDTO>) =>
    buildRouteRecommendationRequest(POOL_RESOURCES, saleOptions, TOTAL_POOL_VOLUME, SAVED_CONTRACTS);

  const keyOf = (saleOptions: ReadonlyArray<PortfolioSaleOptionDTO>) =>
    decisionProvenanceKey(
      "compare_routes",
      contextKey,
      decisionInputIdentity({
        request: compareRequest(saleOptions),
        savedContracts: SAVED_CONTRACTS,
        marketReads: saleOptions,
      }),
    );
  const keyHeld = keyOf(SALE_OPTIONS);
  const keyNow = keyOf([{ ...SALE_OPTIONS[0], sale_price_observed_at_utc: "2026-10-01T06:00:00+00:00" }]);
  const mismatched = decisionProvenanceMismatch(true, keyHeld, keyNow);
  assert.equal(mismatched, true);

  const heldRecommendation = {
    request_id: "web-db-backed-route-allocation",
    status: "SUCCESS",
    total_requested_mwh_per_day: TOTAL_POOL_VOLUME,
    total_allocated_mwh_per_day: 2000,
    unallocated_mwh_per_day: 8000,
    allocations: [
      {
        route_id: "route-1",
        route_name: "TTF -> BBL -> NBP",
        allocated_mwh_per_day: 2000,
        route_cost: 1.75,
        sale_price: 52.5,
        netback: 25,
        rationale: [],
      },
    ],
    excluded_routes: [],
    warnings: [],
    assumptions: [],
    research_only: true,
    human_review_required: false,
  };
  // What the model hands the selector: the payload only while it is current, else null.
  const economics = selectScenarioRouteEconomics({
    carriedRouteId: "route-1",
    selectedResourceId: "preview-portfolio-contract-ttf-pool-2025",
    routeRecommendation: mismatched ? null : heldRecommendation,
    resourcePoolResult: null,
    portfolioResources: POOL_RESOURCES,
    saleOptionById: new Map([["route-1", { option_id: "route-1", route_cost_gbp_mwh: 1.75 }]]),
  });
  assert.equal(economics.source, "unavailable");
  assert.equal(economics.salePrice, null, "no figure is substituted for the withheld payload");
  assert.equal(economics.allocatedVolumeMwhPerDay, null);
  assert.equal(
    selectScenarioRouteEconomics({
      carriedRouteId: "route-1",
      selectedResourceId: "preview-portfolio-contract-ttf-pool-2025",
      routeRecommendation: heldRecommendation,
      resourcePoolResult: null,
      portfolioResources: POOL_RESOURCES,
      saleOptionById: new Map([["route-1", { option_id: "route-1", route_cost_gbp_mwh: 1.75 }]]),
    }).source,
    "route_recommendation",
    "the same payload is this context's economics while its key matches",
  );
});
