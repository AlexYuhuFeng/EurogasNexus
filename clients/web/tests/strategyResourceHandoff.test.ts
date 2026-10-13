import assert from "node:assert/strict";
import test from "node:test";
import type { UpstreamContractDTO } from "../src/api/client.ts";
import { strategyFormForContract } from "../src/app/model/strategyResourceHandoff.ts";
import { DEFAULT_STRATEGY_FORM, strategyDraftBody, strategyDraftValidation, strategyFormFromVersion } from "../src/app/model/strategyDraftModel.ts";

function contract(overrides: Record<string, unknown> = {}): UpstreamContractDTO {
  return { contract_id: "own-id", contract_name: "Explicit resource", delivery_quantity_mwh_per_day: 987,
    contract_price_gbp_mwh: 29.75, delivery_point_name: "Bacton Beach", ...overrides } as UpstreamContractDTO;
}

test("new and missing stored resources have no fabricated identity, energy or price", () => {
  for (const form of [DEFAULT_STRATEGY_FORM, strategyFormFromVersion({ strategy_name: "Missing" })]) {
    assert.equal(form.resourceId, ""); assert.equal(form.resourceQuantity, ""); assert.equal(form.resourceCost, "");
    assert.ok(strategyDraftValidation(form).blockerKeys.includes("strategy_lab.blocker.resource"));
    assert.throws(() => strategyDraftBody(form), /explicit compatible resource/);
  }
});

test("three supported resource types carry exact native identity/energy but no inferred market or all-in price", () => {
  for (const resource_type of ["CONTRACT_POOL", "PIPELINE_IMPORT", "LNG_REGAS"]) {
    const form = strategyFormForContract(contract({ resource_type }));
    assert.equal(form.resourceId, "own-id"); assert.equal(form.resourceName, "Explicit resource");
    assert.equal(form.resourceQuantity, "987"); assert.equal(form.resourceCost, "");
    assert.equal(form.hubs, ""); assert.equal(form.dayAheadNames, ""); assert.equal(form.intradayNames, "");
    assert.throws(() => strategyDraftBody(form));
    const complete = { ...form, name: "Explicit UAT", hubs: "NBP", dayAheadNames: "SAP", intradayNames: "ICE_OCM", resourceCost: "31.125" };
    const body = strategyDraftBody(complete);
    assert.deepEqual(body.resource_contexts?.[0], {
      resource_id: "own-id", resource_name: "Explicit resource", available_quantity_mwh_per_day: 987,
      all_in_cost_gbp_mwh: 31.125, required_tso_access: [],
    });
    assert.equal(contract().contract_price_gbp_mwh, 29.75);
  }
});

test("EUR, therm or incompatible daily units cannot be relabelled as GBP/MWh", () => {
  for (const metadata of [{ currency: "EUR" }, { unit: "therm" }, { quantity_unit: "MWh/hour" }]) {
    const form = strategyFormForContract(contract(metadata));
    assert.equal(form.resourceBasisBlocked, true); assert.equal(form.resourceQuantity, "");
    assert.equal(form.resourceCost, "");
    assert.throws(() => strategyDraftBody({ ...form, resourceQuantity: "987", resourceCost: "31.125" }));
  }
});
