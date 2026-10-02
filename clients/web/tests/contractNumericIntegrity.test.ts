/**
 * Contract numeric-term integrity (commercial-numeric editor boundary).
 *
 * The stored-contract editor used to blur three different facts into one number: a term the
 * row records, a term it does not record (which inherited the template's rate/cost/lag/
 * tolerance/quantity/price), and a control the operator cleared (which silently became `0`).
 * These tests pin the replacement contract on the mapper, the rule and the payload boundary:
 *
 * * `number | null` draft terms mean *recorded* number / *unknown*; an explicit `0` is
 *   recorded and stays `0`, while `null`, `false`, `""`, `NaN` and `±Infinity` never become a
 *   recorded `0` and never fall back to a template or draft value;
 * * stored hydration has no template numeric fallback; the file-import overlay keeps genuinely
 *   omitted fields but not supplied invalid ones;
 * * validation enforces the existing governed write route's own numeric bounds
 *   (`UpstreamContractUpsertRequest`) and a non-recorded required term blocks the save;
 * * the payload boundary refuses any draft validation refuses, before transport.
 *
 * Backend-bound parity is asserted against the bounds written into the route at
 * `src/eurogas_nexus/api/routes/public/route_cost.py::UpstreamContractUpsertRequest`; this
 * suite cannot import the Python route, so each bound below is transcribed from it and the
 * route remains the authority.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { contractDraftFromRecord, numberFromRecord } from "../src/app/contractImport.ts";
import { contractPayloadReadiness } from "../src/app/contractPayload.ts";
import { cloneDefaultContractDraft } from "../src/app/defaultContractDraft.ts";
import {
  contractSaveState,
  contractValidationIssueKeys,
  draftNumberFromInput,
  isRecordedNumber,
  type ContractDraft,
} from "../src/app/model/contractDraftModel.ts";
import { resolvePoolFinancingRate } from "../src/app/model/scenarioInputProvenance.ts";
import { buildResourcePoolOptimizationRequest } from "../src/app/resourcePoolRequest.ts";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

/** A stored row that records every numeric term the write route can carry. */
function storedRow(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    contract_id: "stored-numeric-1",
    contract_name: "Stored numeric contract",
    resource_type: "PIPELINE_IMPORT",
    delivery_point_name: "TTF",
    gas_year: "2025+",
    delivery_quantity_mwh_per_day: 9_000,
    contract_price_gbp_mwh: 27.5,
    settlement_frequency: "monthly",
    upstream_payment_lag_days: 20,
    screen_sale_cash_lag_days: 1,
    annual_financing_rate_pct: 6,
    delivery_tolerance_pct: 2,
    nomination_tolerance_pct: 1,
    tolerance_risk_allowance_gbp_mwh: 0.1,
    owned_entry_capacity_mwh_per_day: null,
    owned_exit_capacity_mwh_per_day: null,
    // The cost terms travel in the row's structured notes; the read surfaces them top-level.
    variable_cost_gbp_mwh: 1.25,
    regas_fee_gbp_mwh: 0.5,
    fuel_loss_allowance_pct: 1.1,
    allowed_exit_points: ["NBP", "TTF"],
    eligible_sale_modes: ["TARGET_MARKET_SALE"],
    notes: JSON.stringify({
      counterparty: "Recorded counterparty",
      variable_cost_gbp_mwh: 1.25,
      regas_fee_gbp_mwh: 0.5,
      fuel_loss_allowance_pct: 1.1,
    }),
    ...overrides,
  };
}

/** A complete draft the boundary can transport, for overrides to be applied onto. */
function completeDraft(overrides: Partial<ContractDraft> = {}): ContractDraft {
  return {
    contract_id: "numeric-draft-1",
    contract_name: "Numeric draft",
    resource_type: "PIPELINE_IMPORT",
    counterparty: "Draft counterparty",
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
    terminal_access: "firm",
    capacity_expiry: "2026-10-01",
    document_name: "manual draft",
    document_status: "MANUAL_DRAFT",
    source_reference: "operator manual entry",
    governing_law: "English law",
    delivery_tolerance_pct: 2,
    nomination_tolerance_pct: 1,
    tolerance_risk_allowance_gbp_mwh: null,
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
    eligible_sale_modes: ["TARGET_MARKET_SALE"],
    preserved_notes: null,
    stored_edit: null,
    ...overrides,
  };
}

/** Draft numeric terms that must not inherit the template when the stored row omits them. */
const TEMPLATE_SENSITIVE_TERMS = [
  "delivery_quantity_mwh_per_day",
  "contract_price_gbp_mwh",
  "delivery_tolerance_pct",
  "nomination_tolerance_pct",
  "tolerance_risk_allowance_gbp_mwh",
  "variable_cost_gbp_mwh",
  "regas_fee_gbp_mwh",
  "fuel_loss_allowance_pct",
  "upstream_payment_lag_days",
  "screen_sale_cash_lag_days",
  "annual_financing_rate_pct",
] as const;

test("stored hydration of an incomplete row leaves absent numeric terms unknown, not template numbers", () => {
  const template = cloneDefaultContractDraft();
  const mapped = contractDraftFromRecord(
    { contract_id: "stored-incomplete-1", contract_name: "Incomplete row", delivery_point_name: "TTF", gas_year: "2025+" },
    template,
    "stored",
  );

  for (const key of TEMPLATE_SENSITIVE_TERMS) {
    assert.equal(mapped[key], null, `${key} must be unknown when the row does not record it`);
    assert.notEqual(mapped[key], template[key], `${key} must not inherit the template value`);
    assert.equal(isRecordedNumber(mapped[key]), false);
  }

  // The unknown required terms block the save instead of being written as template defaults.
  const issues = contractValidationIssueKeys(mapped);
  for (const key of [
    "contracts.validation.volume",
    "contracts.validation.costs",
    "contracts.validation.tolerance",
    "contracts.validation.cash_lag",
    "contracts.validation.financing_rate",
  ]) {
    assert.ok(issues.includes(key), `missing ${key}`);
  }
  const readiness = contractPayloadReadiness(mapped);
  assert.equal(readiness.ready, false);
  assert.equal(readiness.payload, null);
  assert.ok(readiness.issueKeys.length > 0, "a refusal must carry its reasons");
});

test("stored hydration keeps recorded numbers, including explicit zero and nullable capacities", () => {
  const mapped = contractDraftFromRecord(storedRow(), cloneDefaultContractDraft(), "stored");
  assert.equal(mapped.delivery_quantity_mwh_per_day, 9_000);
  assert.equal(mapped.contract_price_gbp_mwh, 27.5);
  assert.equal(mapped.variable_cost_gbp_mwh, 1.25);
  assert.equal(mapped.regas_fee_gbp_mwh, 0.5);
  assert.equal(mapped.fuel_loss_allowance_pct, 1.1);
  assert.equal(mapped.owned_entry_capacity_mwh_per_day, null);
  assert.equal(mapped.owned_exit_capacity_mwh_per_day, null);
  assert.deepEqual(contractValidationIssueKeys(mapped), []);
  assert.equal(contractPayloadReadiness(mapped).ready, true);

  // Explicit zero is a recorded value: it stays 0, is reported as itself, and is transported.
  const zeroed = contractDraftFromRecord(
    storedRow({
      delivery_quantity_mwh_per_day: 0,
      contract_price_gbp_mwh: 0,
      variable_cost_gbp_mwh: 0,
      regas_fee_gbp_mwh: 0,
      fuel_loss_allowance_pct: 0,
      annual_financing_rate_pct: 0,
      upstream_payment_lag_days: 0,
      screen_sale_cash_lag_days: 0,
    }),
    cloneDefaultContractDraft(),
    "stored",
  );
  assert.equal(zeroed.contract_price_gbp_mwh, 0);
  assert.equal(zeroed.variable_cost_gbp_mwh, 0);
  assert.equal(zeroed.fuel_loss_allowance_pct, 0);
  assert.equal(zeroed.annual_financing_rate_pct, 0);
  assert.deepEqual(contractValidationIssueKeys(zeroed), ["contracts.validation.volume"]);

  // A legacy recorded 0 volume is still a refusal, never silently accepted.
  assert.equal(contractPayloadReadiness(zeroed).ready, false);
});

test("supplied invalid values are unknown, never a fallback to the template or the draft", () => {
  const template = cloneDefaultContractDraft();
  for (const invalid of [null, false, "", "not-a-number", Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY]) {
    const direct = numberFromRecord({ term: invalid }, "term", 12.5);
    assert.equal(direct, null, `supplied ${String(invalid)} must map to unknown`);
  }
  assert.equal(numberFromRecord({}, "term", 12.5), 12.5, "an omitted key keeps the fallback");
  assert.equal(numberFromRecord({ term: undefined }, "term", 12.5), 12.5);
  assert.equal(numberFromRecord({ term: 0 }, "term", 12.5), 0, "an explicit zero is recorded");
  assert.equal(numberFromRecord({ term: "1500" }, "term", 12.5), 1500);
  assert.equal(numberFromRecord({ term: " 2.5 " }, "term", 12.5), 2.5);

  // Stored hydration of a row that states an invalid value must not show the template's number.
  const storedInvalid = contractDraftFromRecord(
    storedRow({
      delivery_quantity_mwh_per_day: "abc",
      contract_price_gbp_mwh: false,
      annual_financing_rate_pct: Number.POSITIVE_INFINITY,
    }),
    template,
    "stored",
  );
  assert.equal(storedInvalid.delivery_quantity_mwh_per_day, null);
  assert.notEqual(storedInvalid.delivery_quantity_mwh_per_day, template.delivery_quantity_mwh_per_day);
  assert.equal(storedInvalid.contract_price_gbp_mwh, null);
  assert.equal(storedInvalid.annual_financing_rate_pct, null);

  // The file-import overlay keeps a genuinely omitted field, but a supplied invalid value is
  // unknown - it does not silently keep the working draft's number as if it were imported.
  const current = completeDraft({ delivery_quantity_mwh_per_day: 777 });
  const omitted = contractDraftFromRecord({ contract_id: "import-1" }, current);
  assert.equal(omitted.delivery_quantity_mwh_per_day, 777);
  for (const invalid of [null, "", false, Number.NaN, Number.POSITIVE_INFINITY]) {
    const overlaid = contractDraftFromRecord(
      { contract_id: "import-1", delivery_quantity_mwh_per_day: invalid },
      current,
    );
    assert.equal(overlaid.delivery_quantity_mwh_per_day, null, `overlay must not keep 777 for ${String(invalid)}`);
    assert.notEqual(overlaid.delivery_quantity_mwh_per_day, current.delivery_quantity_mwh_per_day);
  }
  const explicitZero = contractDraftFromRecord(
    { contract_id: "import-1", delivery_quantity_mwh_per_day: 0 },
    current,
  );
  assert.equal(explicitZero.delivery_quantity_mwh_per_day, 0);
});

test("clearing a number control is unknown; an explicit zero stays zero", () => {
  assert.equal(draftNumberFromInput(""), null);
  assert.equal(draftNumberFromInput("   "), null);
  assert.equal(draftNumberFromInput("0"), 0);
  assert.equal(draftNumberFromInput("12.5"), 12.5);
  assert.equal(draftNumberFromInput("-3"), -3);
  assert.equal(draftNumberFromInput("abc"), null);
  assert.equal(draftNumberFromInput("NaN"), null);
  assert.equal(draftNumberFromInput("Infinity"), null);
  assert.equal(draftNumberFromInput("1e999"), null);

  // The hook routes every numeric edit through that mapper, and the workbench renders an
  // unknown term blank instead of 0.
  const hook = readWebSource("app/hooks/useContractEditor.ts");
  assert.match(hook, /\[key\]: draftNumberFromInput\(value\)/);
  assert.equal(hook.includes(": value === \"\" ? 0"), false, "a cleared control must not become 0");
  const workbench = readWebSource("components/ContractWorkbench.tsx");
  assert.equal(
    /<input type="number"[^>]*value=\{contract\.[a-z_0-9]+\}/.test(workbench),
    false,
    "every number input must render an unknown term blank, not null/0",
  );
});

test("validation matches the governed write route's numeric bounds", () => {
  // Transcribed from UpstreamContractUpsertRequest: gt=0 volume; ge=0 price, costs, tolerances,
  // rate, allowance, capacities; int ge=0 lags; fuel loss in [0, 100).
  const refused: Array<[keyof ContractDraft, number | null, string]> = [
    ["delivery_quantity_mwh_per_day", null, "contracts.validation.volume"],
    ["delivery_quantity_mwh_per_day", 0, "contracts.validation.volume"],
    ["delivery_quantity_mwh_per_day", -1, "contracts.validation.volume"],
    ["delivery_quantity_mwh_per_day", Number.NaN, "contracts.validation.volume"],
    ["delivery_quantity_mwh_per_day", Number.POSITIVE_INFINITY, "contracts.validation.volume"],
    ["contract_price_gbp_mwh", null, "contracts.validation.price"],
    ["contract_price_gbp_mwh", -0.01, "contracts.validation.price"],
    ["contract_price_gbp_mwh", Number.NaN, "contracts.validation.price"],
    ["variable_cost_gbp_mwh", null, "contracts.validation.costs"],
    ["variable_cost_gbp_mwh", -1, "contracts.validation.costs"],
    ["regas_fee_gbp_mwh", null, "contracts.validation.costs"],
    ["tolerance_risk_allowance_gbp_mwh", -0.1, "contracts.validation.costs"],
    ["fuel_loss_allowance_pct", null, "contracts.validation.fuel_loss"],
    ["fuel_loss_allowance_pct", -0.1, "contracts.validation.fuel_loss"],
    ["fuel_loss_allowance_pct", 100, "contracts.validation.fuel_loss"],
    ["delivery_tolerance_pct", null, "contracts.validation.tolerance"],
    ["delivery_tolerance_pct", -1, "contracts.validation.tolerance"],
    ["nomination_tolerance_pct", null, "contracts.validation.tolerance"],
    ["upstream_payment_lag_days", null, "contracts.validation.cash_lag"],
    ["upstream_payment_lag_days", -1, "contracts.validation.cash_lag"],
    ["upstream_payment_lag_days", 1.5, "contracts.validation.cash_lag"],
    ["screen_sale_cash_lag_days", null, "contracts.validation.cash_lag"],
    ["annual_financing_rate_pct", null, "contracts.validation.financing_rate"],
    ["annual_financing_rate_pct", -1, "contracts.validation.financing_rate"],
    ["owned_entry_capacity_mwh_per_day", -1, "contracts.validation.capacity"],
    ["owned_exit_capacity_mwh_per_day", -1, "contracts.validation.capacity"],
    ["owned_exit_capacity_mwh_per_day", Number.NaN, "contracts.validation.capacity"],
  ];
  for (const [key, value, expected] of refused) {
    const issues = contractValidationIssueKeys(completeDraft({ [key]: value }));
    assert.ok(issues.includes(expected), `${String(key)}=${String(value)} must report ${expected}`);
  }

  // Values at the route's own bounds stay acceptable, and the optional route fields stay
  // blank-able (their `float | None` shape is the "not declared" state).
  const accepted: Array<[keyof ContractDraft, number | null]> = [
    ["delivery_quantity_mwh_per_day", 0.001],
    ["contract_price_gbp_mwh", 0],
    ["variable_cost_gbp_mwh", 0],
    ["regas_fee_gbp_mwh", 0],
    ["tolerance_risk_allowance_gbp_mwh", 0],
    ["tolerance_risk_allowance_gbp_mwh", null],
    ["fuel_loss_allowance_pct", 0],
    ["fuel_loss_allowance_pct", 99.999],
    ["delivery_tolerance_pct", 0],
    ["nomination_tolerance_pct", 0],
    ["upstream_payment_lag_days", 0],
    ["screen_sale_cash_lag_days", 0],
    ["annual_financing_rate_pct", 0],
    ["owned_entry_capacity_mwh_per_day", 0],
    ["owned_entry_capacity_mwh_per_day", null],
    ["owned_exit_capacity_mwh_per_day", null],
  ];
  for (const [key, value] of accepted) {
    assert.deepEqual(contractValidationIssueKeys(completeDraft({ [key]: value })), [], `${String(key)}=${String(value)}`);
  }

  // The save rule reads the same issues, so an unknown required term cannot be saved even when
  // a caller evaluates the rule directly.
  const state = contractSaveState({
    contract: completeDraft({ annual_financing_rate_pct: null }),
    runtimeDbReady: true,
    loading: false,
    viewFacts: { readOnlyLibrary: false, readOnlySelectedResource: false, knownSelectedResource: false },
  });
  assert.equal(state.canSave, false);
  assert.equal(state.statusKey, "contracts.validation.blocked");
});

test("the payload boundary refuses every term validation refuses, and never diverges", () => {
  const complete = contractPayloadReadiness(completeDraft());
  assert.equal(complete.ready, true);
  assert.ok(complete.payload);
  // The valid payload keeps the draft's own numerics and shape, including the nullable fields.
  assert.equal(complete.payload.delivery_quantity_mwh_per_day, 100);
  assert.equal(complete.payload.annual_financing_rate_pct, 6);
  assert.equal(complete.payload.tolerance_risk_allowance_gbp_mwh, null);
  assert.equal(complete.payload.owned_entry_capacity_mwh_per_day, null);
  assert.equal(complete.payload.expected_edit_token, null);
  assert.deepEqual(complete.issueKeys, []);

  const refused: Array<Partial<ContractDraft>> = [
    { delivery_quantity_mwh_per_day: null },
    { contract_price_gbp_mwh: null },
    { variable_cost_gbp_mwh: null },
    { regas_fee_gbp_mwh: Number.NaN },
    { fuel_loss_allowance_pct: null },
    { delivery_tolerance_pct: null },
    { nomination_tolerance_pct: Number.POSITIVE_INFINITY },
    { upstream_payment_lag_days: null },
    { screen_sale_cash_lag_days: 1.25 },
    { annual_financing_rate_pct: null },
    { contract_price_gbp_mwh: -1 },
    { owned_exit_capacity_mwh_per_day: -1 },
    { counterparty: "" },
  ];
  for (const override of refused) {
    const readiness = contractPayloadReadiness(completeDraft(override));
    assert.equal(readiness.ready, false, String(Object.keys(override)[0]));
    assert.equal(readiness.payload, null);
    // The refusal is explainable by the same issue list the workbench shows: the two cannot
    // disagree in the direction that would strand a blocked draft with a "ready" status.
    assert.ok(readiness.issueKeys.length > 0, String(Object.keys(override)[0]));
  }

  // Optional fields staying blank keeps the draft transportable and the payload explicit.
  const optionalBlank = contractPayloadReadiness(
    completeDraft({ tolerance_risk_allowance_gbp_mwh: null, owned_entry_capacity_mwh_per_day: null, owned_exit_capacity_mwh_per_day: null }),
  );
  assert.equal(optionalBlank.ready, true);
  assert.equal(optionalBlank.payload?.tolerance_risk_allowance_gbp_mwh, null);
});

test("optional owned capacity keeps its documented null meaning, and a recorded zero is kept", () => {
  const blankStored = contractDraftFromRecord(
    storedRow({ owned_entry_capacity_mwh_per_day: null, owned_exit_capacity_mwh_per_day: null }),
    cloneDefaultContractDraft(),
    "stored",
  );
  assert.equal(blankStored.owned_entry_capacity_mwh_per_day, null);
  assert.equal(blankStored.owned_exit_capacity_mwh_per_day, null);
  assert.equal(contractPayloadReadiness(blankStored).ready, true);
  assert.equal(contractPayloadReadiness(blankStored).payload?.owned_entry_capacity_mwh_per_day, null);

  const recorded = contractDraftFromRecord(
    storedRow({ owned_entry_capacity_mwh_per_day: 500, owned_exit_capacity_mwh_per_day: 0 }),
    cloneDefaultContractDraft(),
    "stored",
  );
  assert.equal(recorded.owned_entry_capacity_mwh_per_day, 500);
  assert.equal(recorded.owned_exit_capacity_mwh_per_day, 0);
  assert.deepEqual(contractValidationIssueKeys(recorded), []);
});

test("unknown required numbers cannot be transported, and the editor's save refuses first", () => {
  const unknown = completeDraft({
    delivery_quantity_mwh_per_day: null,
    annual_financing_rate_pct: null,
  });
  const readiness = contractPayloadReadiness(unknown);
  assert.equal(readiness.ready, false);
  assert.equal(readiness.payload, null, "no payload exists for a refused draft");

  // The hook holds the same guard before its single transport call, so an invocation that
  // bypasses the disabled button still cannot send a refused draft.
  const hook = readWebSource("app/hooks/useContractEditor.ts");
  assert.match(
    hook,
    /const readiness = contractPayloadReadiness\(contractRef\.current\);\s*if \(!readiness\.ready \|\| readiness\.payload === null\) return;/,
  );
  const guardAt = hook.indexOf("if (!readiness.ready || readiness.payload === null) return;");
  const transportAt = hook.indexOf("await saveContractDraft(payload)");
  assert.ok(guardAt > 0 && guardAt < transportAt, "the readiness guard must precede transport");

  // The financing-rate consumer refuses an unknown rate rather than calculating with 0.
  assert.deepEqual(resolvePoolFinancingRate(unknown, []), { pct: null, source: "unknown" });
  assert.equal(buildResourcePoolOptimizationRequest(unknown, [], [], []), null);
  const model = readWebSource("app/model/usePortfolioDecisionModel.ts");
  assert.match(model, /resourcePoolOptimizationRequest === null/);
  assert.match(model, /buildResourcePoolOptimizationRequest/);
});

test("numeric summaries render unknown as n/a rather than 0 or NaN", () => {
  const workbench = readWebSource("components/ContractWorkbench.tsx");
  // Both formatters refuse every non-finite value, so a poisoned or unknown term cannot render
  // as a number.
  assert.match(workbench, /function formatQuantity\(value: number \| null \| undefined\): string \{\s*if \(value === null \|\| value === undefined \|\| !Number\.isFinite\(value\)\) return "n\/a";/);
  assert.match(workbench, /function formatMoney\(value: number \| null \| undefined\): string \{\s*if \(value === null \|\| value === undefined \|\| !Number\.isFinite\(value\)\) return "n\/a";/);
});
