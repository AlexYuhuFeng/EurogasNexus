/**
 * The connected route-comparison request identity.
 *
 * The Web request is built from the backend-owned resource-pool read. These cases
 * hold three fail-closed rules that the old builder broke:
 *
 * - an unknown route cost stays `null`, not `0`; only an explicit zero is zero;
 * - the already-normalized GBP/MWh prices keep their GBP identity and are never
 *   relabelled EUR or converted twice;
 * - the backend's capacity state is forwarded (`NOT_REQUIRED` is not lost, a
 *   missing state is `UNKNOWN`), and the caller's gas day is the explicit
 *   tariff-applicability date so a context move invalidates a held result.
 *
 * Source-option references travel as candidate provenance only; the backend
 * prefixes them `unverified_input:`.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import type { PortfolioResourceDTO, PortfolioSaleOptionDTO } from "../src/api/client.ts";
import type { ContractDraft } from "../src/app/model/contractDraftModel.ts";
import { buildResourcePoolOptimizationRequest } from "../src/app/resourcePoolRequest.ts";
import { buildRouteRecommendationRequest } from "../src/app/routeRecommendationRequest.ts";
import { decisionInputIdentity } from "../src/app/model/decisionResultProvenance.ts";

const RESOURCES: PortfolioResourceDTO[] = [
  {
    resource_id: "pool-ttf",
    resource_name: "TTF supply",
    resource_type: "PIPELINE_IMPORT",
    delivery_mode: "PHYSICAL_ENTRY_DELIVERY",
    location_point_name: "TTF",
    available_quantity_mwh_per_day: 10_000,
    contract_cost_gbp_mwh: 25,
    accessible_tsos: ["BBL Company"],
  },
];

const CONTRACTS = [{ contract_id: "contract-a", gas_year: "2025+", edit_token: "token-1" }];

function saleOption(overrides: Partial<PortfolioSaleOptionDTO> = {}): PortfolioSaleOptionDTO {
  return {
    option_id: "route-1",
    label: "TTF -> BBL -> NBP",
    delivery_mode: "VIRTUAL_HUB_SALE",
    target_point_name: "NBP",
    sale_price_gbp_mwh: 52.5,
    sale_price_currency: "GBP",
    sale_price_unit: "GBP/MWh",
    route_cost_gbp_mwh: 1.75,
    route_cost_currency: "GBP",
    route_cost_unit: "GBP/MWh",
    capacity_limit_mwh_per_day: 2000,
    capacity_status: "KNOWN",
    tariff_applicability_date: "2026-01-31",
    route_cost_source_refs: ["tariff:jan", "test:bridge-tariff"],
    source_refs: ["route_candidate:route-1"],
    required_tso_access: ["BBL Company"],
    ...overrides,
  };
}

function candidateOf(request: ReturnType<typeof buildRouteRecommendationRequest>): Record<string, unknown> {
  return request.candidates[0];
}

test("the current gas day is the request's explicit tariff applicability date", () => {
  const request = buildRouteRecommendationRequest(
    RESOURCES,
    [saleOption()],
    10_000,
    CONTRACTS,
    "2026-01-31",
  );

  assert.equal(request.tariff_applicability_date, "2026-01-31");
  assert.equal(candidateOf(request).tariff_applicability_date, "2026-01-31");
  assert.equal(candidateOf(request).price_currency, "GBP");
  assert.equal(candidateOf(request).price_unit, "GBP/MWh");
  // The backend-normalized GBP cost keeps that identity; it is not relabelled
  // EUR and does not need another conversion.
  assert.equal(candidateOf(request).manual_cost, 1.75);
  assert.equal(candidateOf(request).cost_currency, "GBP");
  assert.equal(candidateOf(request).cost_unit, "GBP/MWh");
});

test("an unknown route cost stays null while an explicit zero stays zero", () => {
  const unknown = buildRouteRecommendationRequest(
    RESOURCES,
    [saleOption({ route_cost_gbp_mwh: null })],
    10_000,
    CONTRACTS,
    "2026-01-31",
  );
  const unknownCandidate = candidateOf(unknown);
  assert.equal(unknownCandidate.manual_cost, null);
  assert.notEqual(unknownCandidate.manual_cost, 0);
  assert.equal(unknownCandidate.cost_currency, null);
  assert.equal(unknownCandidate.cost_unit, null);

  const explicitZero = buildRouteRecommendationRequest(
    RESOURCES,
    [saleOption({ route_cost_gbp_mwh: 0 })],
    10_000,
    CONTRACTS,
    "2026-01-31",
  );
  const zeroCandidate = candidateOf(explicitZero);
  assert.equal(zeroCandidate.manual_cost, 0);
  assert.equal(zeroCandidate.cost_currency, "GBP");
  assert.equal(zeroCandidate.cost_unit, "GBP/MWh");
});

test("capacity state is forwarded and a missing state is UNKNOWN, never NOT_REQUIRED", () => {
  const notRequired = buildRouteRecommendationRequest(
    RESOURCES,
    [saleOption({ capacity_limit_mwh_per_day: null, capacity_status: "NOT_REQUIRED" })],
    10_000,
    CONTRACTS,
    "2026-01-31",
  );
  assert.equal(candidateOf(notRequired).capacity_status, "NOT_REQUIRED");
  assert.equal(candidateOf(notRequired).available_capacity_mwh_per_day, null);

  const missing = buildRouteRecommendationRequest(
    RESOURCES,
    [saleOption({ capacity_limit_mwh_per_day: null, capacity_status: null })],
    10_000,
    CONTRACTS,
    "2026-01-31",
  );
  assert.equal(candidateOf(missing).capacity_status, "UNKNOWN");
  assert.notEqual(candidateOf(missing).capacity_status, "NOT_REQUIRED");
});

test("source-option references are carried once as candidate provenance", () => {
  const request = buildRouteRecommendationRequest(
    RESOURCES,
    [
      saleOption({
        route_cost_source_refs: ["tariff:jan", "test:bridge-tariff"],
        source_refs: ["route_candidate:route-1", "test:bridge-tariff"],
      }),
    ],
    10_000,
    CONTRACTS,
    "2026-01-31",
  );

  assert.deepEqual(candidateOf(request).source_refs, [
    "tariff:jan",
    "test:bridge-tariff",
    "route_candidate:route-1",
  ]);
});

test("the four-argument builder stays compatible and declares no assessed date", () => {
  const request = buildRouteRecommendationRequest(RESOURCES, [saleOption()], 10_000, CONTRACTS);

  assert.equal(request.tariff_applicability_date, null);
});

test("a changed gas day changes the request identity and cannot reuse the prior allocation", () => {
  const first = buildRouteRecommendationRequest(
    RESOURCES,
    [saleOption()],
    10_000,
    CONTRACTS,
    "2026-01-31",
  );
  const moved = buildRouteRecommendationRequest(
    RESOURCES,
    [saleOption()],
    10_000,
    CONTRACTS,
    "2026-02-01",
  );

  assert.notEqual(first.tariff_applicability_date, moved.tariff_applicability_date);
  assert.notEqual(
    decisionInputIdentity({ request: first, savedContracts: CONTRACTS }),
    decisionInputIdentity({ request: moved, savedContracts: CONTRACTS }),
  );
});

test("the sandbox resource-pool request adds no runtime gas day and preserves explicit data", () => {
  const option = saleOption();
  const request = buildResourcePoolOptimizationRequest(
    { annual_financing_rate_pct: 6 } as ContractDraft,
    RESOURCES,
    [option],
    CONTRACTS,
  );

  assert.ok(request);
  assert.equal(Object.prototype.hasOwnProperty.call(request, "gas_day"), false);
  assert.equal(request.sale_options[0], option);
  assert.equal(request.sale_options[0].tariff_applicability_date, "2026-01-31");
  assert.equal(request.sale_options[0].route_cost_currency, "GBP");
});

test("the decision model passes the caller's gas day into the request builder", () => {
  const model = readFileSync(
    new URL("../src/app/model/usePortfolioDecisionModel.ts", import.meta.url),
    "utf8",
  );

  assert.match(model, /buildRouteRecommendationRequest\([\s\S]*?\bgasDay\b[\s\S]*?\)/);
});
