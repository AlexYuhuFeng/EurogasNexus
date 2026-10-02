/**
 * Scenario panel input provenance (Decision workspace).
 *
 * The authenticated inspection found Decision > Scenario offering eight editable
 * contract-draft numbers (including "Target market EUR/MWh" / "Local market EUR/MWh" over
 * GBP-named draft fields) while the panel claimed "the economics you edit here are the ones
 * it sends". These tests prove against the actual request builders what the two actions
 * consume: only the annual financing rate reaches a run, and only as the pool optimiser's
 * fallback when no saved upstream contract carries a rate. Every other draft number reaches
 * neither request, so it must not be offered as editable.
 *
 * The runner cannot render React (no DOM), so the panel's wiring is checked from its source;
 * the behavioural proof is the request-composition diffing below.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import type { PortfolioResourceDTO, PortfolioSaleOptionDTO } from "../src/api/client.ts";
import {
  contractPayloadReadiness,
  type ContractPayloadReadiness,
} from "../src/app/contractPayload.ts";
import type { ContractDraft } from "../src/app/model/contractDraftModel.ts";
import {
  SCENARIO_EDITABLE_DRAFT_INPUTS,
  resolvePoolFinancingRate,
} from "../src/app/model/scenarioInputProvenance.ts";
import { buildResourcePoolOptimizationRequest } from "../src/app/resourcePoolRequest.ts";
import { buildRouteRecommendationRequest } from "../src/app/routeRecommendationRequest.ts";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

/** The transportable payload of a complete fixture draft, through the editor's own boundary. */
function payloadOf(
  draft: ContractDraft,
): NonNullable<ContractPayloadReadiness["payload"]> {
  const readiness = contractPayloadReadiness(draft);
  assert.equal(readiness.ready, true, "the fixture draft must be transportable");
  assert.ok(readiness.payload, "a ready readiness result carries its payload");
  return readiness.payload;
}

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
    ...overrides,
  };
}

// The persisted resource-pool read the Decision workspace composes both actions from.
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
    route_cost_gbp_mwh: 1.75,
    route_cost_currency: "GBP",
    route_cost_unit: "GBP/MWh",
    capacity_limit_mwh_per_day: 2000,
    required_tso_access: ["BBL Company"],
  },
];

const TOTAL_POOL_VOLUME = 10_000;
const SAVED_GAS_YEAR = [{ gas_year: "2027+" }];

test("Compare Options composes the saved pool read and carries no draft value", () => {
  const request = buildRouteRecommendationRequest(
    POOL_RESOURCES,
    SALE_OPTIONS,
    TOTAL_POOL_VOLUME,
    SAVED_GAS_YEAR,
  );

  // The exact transport, pinned as a whole: the comparison has no draft parameter, so any
  // draft field arriving here (or any persisted field silently dropped) fails this.
  assert.deepEqual(request, {
    request_id: "web-db-backed-route-allocation",
    source_point_id: "TTF",
    target_point_id: "NBP",
    required_quantity_mwh_per_day: 10_000,
    gas_year: "2027+",
    capacity_product: "ANNUAL",
    firmness: "FIRM",
    company_accessible_tsos: ["BBL Company"],
    candidates: [
      {
        route_id: "route-1",
        route_name: "TTF -> BBL -> NBP",
        destination_market: "NBP",
        sale_price: 52.5,
        price_currency: "GBP",
        price_unit: "GBP/MWh",
        required_tso_access: ["BBL Company"],
        available_capacity_mwh_per_day: 2000,
        manual_cost: 1.75,
        cost_currency: "GBP",
        cost_unit: "GBP/MWh",
      },
    ],
  });
  // The sale price and route cost are the persisted option's own values, unchanged: no
  // implicit conversion and no draft price substituted in.
  assert.equal(request.candidates[0].sale_price, SALE_OPTIONS[0].sale_price_gbp_mwh);
});

test("every draft number the panel no longer offers leaves both requests unchanged", () => {
  const baselineOptimize = buildResourcePoolOptimizationRequest(
    draft(),
    POOL_RESOURCES,
    SALE_OPTIONS,
    [],
  );

  // The seven fields the panel used to offer: mutating each one must change nothing this
  // panel's actions can send. The comparison's composition is pinned above and has no draft
  // parameter, so the optimiser request is where a leaked field could still appear.
  const intentionallyNotEditable: Array<keyof ContractDraft> = [
    "delivery_quantity_mwh_per_day",
    "contract_price_gbp_mwh",
    "nbp_sale_price_gbp_mwh",
    "physical_exit_sale_price_gbp_mwh",
    "delivery_tolerance_pct",
    "nomination_tolerance_pct",
    "screen_sale_cash_lag_days",
  ];
  for (const key of intentionallyNotEditable) {
    const mutated = draft({ [key]: 987_654.321 });
    assert.deepEqual(
      buildResourcePoolOptimizationRequest(mutated, POOL_RESOURCES, SALE_OPTIONS, []),
      baselineOptimize,
      `${key} leaked into the optimiser request`,
    );
  }

  // Two of the removed controls were not even persisted with the contract: the draft keeps
  // them for import back-compatibility, but the saved payload never carried them.
  const payload = payloadOf(draft()) as Record<string, unknown>;
  assert.equal("nbp_sale_price_gbp_mwh" in payload, false);
  assert.equal("physical_exit_sale_price_gbp_mwh" in payload, false);
  assert.equal("annual_financing_rate_pct" in payload, true);
});

test("the financing rate is the one consumed draft input, with saved-contract precedence", () => {
  const draftRate = draft({ annual_financing_rate_pct: 7.5 });

  // No saved rate: the draft fallback is sent, in percent per year, unconverted.
  const fallbackRequest = buildResourcePoolOptimizationRequest(
    draftRate,
    POOL_RESOURCES,
    SALE_OPTIONS,
    [],
  );
  assert.equal(fallbackRequest.annual_financing_rate_pct, 7.5);
  assert.deepEqual(resolvePoolFinancingRate(draftRate, []), {
    pct: 7.5,
    source: "draft_fallback",
  });
  assert.deepEqual(
    fallbackRequest.resources,
    POOL_RESOURCES,
    "resources are the persisted read, passed through uncopied",
  );
  assert.equal(
    fallbackRequest.resources,
    POOL_RESOURCES,
    "the persisted read is passed through by reference, not recomposed",
  );
  assert.equal(fallbackRequest.sale_options, SALE_OPTIONS);

  // A saved upstream contract rate overrides the draft, and the resolution the panel states
  // is exactly the value the request carries.
  const savedContracts = [{ annual_financing_rate_pct: 4.25 }];
  const savedRequest = buildResourcePoolOptimizationRequest(
    draftRate,
    POOL_RESOURCES,
    SALE_OPTIONS,
    savedContracts,
  );
  assert.equal(savedRequest.annual_financing_rate_pct, 4.25);
  assert.deepEqual(resolvePoolFinancingRate(draftRate, savedContracts), {
    pct: 4.25,
    source: "saved_upstream_contract",
  });

  // A null saved rate keeps the builder's nullish-fallback semantics: the draft applies.
  const nullSaved = [{ annual_financing_rate_pct: null }];
  assert.equal(
    buildResourcePoolOptimizationRequest(draftRate, POOL_RESOURCES, SALE_OPTIONS, nullSaved)
      .annual_financing_rate_pct,
    7.5,
  );
  assert.equal(resolvePoolFinancingRate(draftRate, nullSaved).source, "draft_fallback");

  // Editing the rate changes the optimiser request in exactly one field.
  const edited = buildResourcePoolOptimizationRequest(
    draft({ annual_financing_rate_pct: 9 }),
    POOL_RESOURCES,
    SALE_OPTIONS,
    [],
  );
  assert.deepEqual(
    { ...edited, annual_financing_rate_pct: 0 },
    { ...fallbackRequest, annual_financing_rate_pct: 0 },
  );
  assert.equal(edited.annual_financing_rate_pct, 9);
});

test("the Scenario panel offers the consumed input, names the provenance, and drops the rest", () => {
  const source = readWebSource("components/ScenarioWorkspace.tsx");

  // Exactly one editable draft control remains, rendered from the shared descriptor.
  assert.equal((source.match(/updateContractNumber\(/g) ?? []).length, 1);
  assert.match(source, /SCENARIO_EDITABLE_DRAFT_INPUTS/);
  assert.match(source, /resolvePoolFinancingRate\(contract, upstreamContracts\)/);
  assert.match(source, /value=\{financingRate\.pct \?\? ""\}/);
  assert.match(source, /readOnly=\{financingRate\.source === "saved_upstream_contract"\}/);
  for (const removedField of [
    "delivery_quantity_mwh_per_day",
    "contract_price_gbp_mwh",
    "nbp_sale_price_gbp_mwh",
    "physical_exit_sale_price_gbp_mwh",
    "delivery_tolerance_pct",
    "nomination_tolerance_pct",
    "screen_sale_cash_lag_days",
  ]) {
    assert.equal(source.includes(removedField), false, `${removedField} is still editable here`);
  }
  assert.match(source, /t\("scenario\.financing_rate_from_saved_contract"\)/);
  assert.match(source, /t\("scenario\.financing_rate_from_draft_fallback"\)/);
  assert.match(source, /t\("scenario\.compare_location"\)/);
  assert.match(source, /t\("scenario\.optimizer_location"\)/);
});

test("an unrecorded financing rate is refused, never run as a 0% fallback", () => {
  // A draft whose rate control was cleared (or a stored row that never recorded one) has no
  // rate to send: the resolution is explicit `unknown` and the optimiser request is refused.
  const unrecorded = draft({ annual_financing_rate_pct: null });
  assert.deepEqual(resolvePoolFinancingRate(unrecorded, []), {
    pct: null,
    source: "unknown",
  });
  assert.equal(
    buildResourcePoolOptimizationRequest(unrecorded, POOL_RESOURCES, SALE_OPTIONS, []),
    null,
    "an unknown rate never becomes a request with 0%",
  );

  // A saved rate that is not a finite number is not a recorded rate either: the request is
  // refused rather than relabelled with the draft's own rate.
  const notANumber = [{ annual_financing_rate_pct: Number.NaN }];
  assert.deepEqual(resolvePoolFinancingRate(draft({ annual_financing_rate_pct: 7.5 }), notANumber), {
    pct: null,
    source: "unknown",
  });
  assert.equal(
    buildResourcePoolOptimizationRequest(draft({ annual_financing_rate_pct: 7.5 }), POOL_RESOURCES, SALE_OPTIONS, notANumber),
    null,
  );

  // A saved null falls back to the draft only while the draft itself records a rate.
  const nullSaved = [{ annual_financing_rate_pct: null }];
  assert.deepEqual(resolvePoolFinancingRate(draft({ annual_financing_rate_pct: 7.5 }), nullSaved), {
    pct: 7.5,
    source: "draft_fallback",
  });
  assert.deepEqual(resolvePoolFinancingRate(draft({ annual_financing_rate_pct: null }), nullSaved), {
    pct: null,
    source: "unknown",
  });
});

test("the panel's vocabulary is translated and the false EUR/MWh labels are gone", () => {
  const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>;

  const keys = [
    "scenario.financing_rate_from_saved_contract",
    "scenario.financing_rate_from_draft_fallback",
    "scenario.compare_location",
    "scenario.optimizer_location",
    ...SCENARIO_EDITABLE_DRAFT_INPUTS.map((input) => input.labelKey),
  ];
  for (const key of keys) {
    assert.ok(en[key]?.trim(), `en ${key}`);
    assert.ok(zh[key]?.trim(), `zh ${key}`);
    assert.notEqual(en[key], zh[key], `untranslated ${key}`);
  }

  // The labels that named GBP-named draft fields as EUR/MWh are deleted, not reworded: the
  // fields have no consumer in either action, so nothing may name them as money.
  for (const removedKey of ["economics.nbp_price", "economics.physical_price"]) {
    assert.equal(removedKey in en, false, removedKey);
    assert.equal(removedKey in zh, false, removedKey);
  }
});
