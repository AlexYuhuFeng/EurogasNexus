import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import type { LngEconomicsOnlyMetaDTO } from "../src/api/client.ts";
import {
  LNG_ECONOMICS_CHARGE_BASES,
  LNG_ECONOMICS_COST_CATEGORIES,
  LNG_ECONOMICS_ENERGY_UNITS,
  LNG_ECONOMICS_PURCHASE_BASES,
  LNG_ECONOMICS_REPORTING_CURRENCIES,
  LNG_ECONOMICS_STAGE_KINDS,
  createLngEconomicsRunGate,
  emptyLngEconomicsCostDraft,
  emptyLngEconomicsDiscountDraft,
  emptyLngEconomicsDraft,
  emptyLngEconomicsStageDraft,
  initialLngEconomicsState,
  lngEconomicsReducer,
  lngEconomicsRefusal,
  lngEconomicsRequest,
  lngEconomicsReadiness,
  lngEconomicsSubmitShortcut,
  type LngEconomicsDraft,
} from "../src/app/model/lngEconomicsModel.ts";
import {
  goldenDraft,
  goldenMeta,
  goldenResult,
} from "./support/lngEconomicsFixtures.ts";

function draftWith(patch: Partial<LngEconomicsDraft> = {}): LngEconomicsDraft {
  return { ...emptyLngEconomicsDraft(), ...patch };
}

function successfulState() {
  return lngEconomicsReducer(initialLngEconomicsState(goldenDraft()), {
    type: "run_succeeded",
    result: goldenResult(),
    meta: goldenMeta(),
  });
}

test("a blank form has no inferred currency, unit, basis, stage, cost or discount factor", () => {
  const draft = emptyLngEconomicsDraft();
  assert.deepEqual(draft, {
    contractId: "",
    cargoId: "",
    terminalId: "",
    resourceId: "",
    valuationDate: "",
    reportingCurrency: "",
    energyBasisReference: "",
    energyUnit: "",
    purchasedEnergyMwh: "",
    deliveredEnergyMwh: "",
    purchaseUnitPriceEurPerMwh: "",
    saleUnitPriceEurPerMwh: "",
    purchasePriceSourceReference: "",
    salePriceSourceReference: "",
    purchaseBasis: "",
    purchaseIncludedCostItems: "",
    costScopeStatement: "",
    purchasePaymentDate: "",
    salePaymentDate: "",
    downstreamCosts: [],
    energyStages: [],
    discountFactors: [],
  });
  const readiness = lngEconomicsReadiness(draft);
  assert.equal(readiness.canSubmit, false);
  assert.equal(lngEconomicsRequest(draft), null);
  assert.ok(readiness.blockerKeys.includes("contracts.lng_economics.blocker.energy_stages_required"));
  assert.ok(
    readiness.blockerKeys.includes("contracts.lng_economics.blocker.discount_factors_required"),
  );
  assert.equal(
    readiness.firstBlockerKey,
    "contracts.lng_economics.blocker.contract_id",
  );

  // Adding a row starts blank: no sample stage, no `1` discount factor and no charge basis.
  assert.equal(emptyLngEconomicsStageDraft().kind, "");
  assert.equal(emptyLngEconomicsStageDraft().inputEnergyMwh, "");
  assert.equal(emptyLngEconomicsDiscountDraft().factor, "");
  assert.equal(emptyLngEconomicsCostDraft().chargeBasis, "");
  assert.equal(emptyLngEconomicsCostDraft().amountEur, "");

  // The supported vocabularies are the engine's declared sets, not a second default.
  assert.deepEqual([...LNG_ECONOMICS_PURCHASE_BASES], ["FOB", "DES"]);
  assert.deepEqual([...LNG_ECONOMICS_REPORTING_CURRENCIES], ["EUR"]);
  assert.deepEqual([...LNG_ECONOMICS_ENERGY_UNITS], ["MWh"]);
  assert.deepEqual([...LNG_ECONOMICS_CHARGE_BASES], ["invoiced_cash", "in_kind", "unknown"]);
  assert.deepEqual([...LNG_ECONOMICS_STAGE_KINDS], [
    "cargo_transfer",
    "shipping",
    "storage",
    "regasification",
    "other",
  ]);
  assert.deepEqual([...LNG_ECONOMICS_COST_CATEGORIES], [
    "cargo_purchase",
    "cargo_sale",
    "shipping",
    "transport",
    "regas",
    "storage",
    "fuel",
    "demurrage",
    "boil_off",
    "other",
  ]);
});

test("readiness blocks incomplete explicit rows without inventing defaults", () => {
  const noStage = draftWith({
    ...goldenDraft(),
    energyStages: [],
    discountFactors: [],
    downstreamCosts: [],
  });
  const readiness = lngEconomicsReadiness(noStage);
  assert.equal(readiness.canSubmit, false);
  assert.ok(readiness.blockerKeys.includes("contracts.lng_economics.blocker.energy_stages_required"));
  // Purchase and sale payment dates are mandatory, and the composition requires every declared
  // cash date to be covered, so an empty factor collection blocks without inventing a factor.
  assert.ok(
    readiness.blockerKeys.includes("contracts.lng_economics.blocker.discount_factors_required"),
  );

  const incomplete = draftWith({
    ...goldenDraft(),
    downstreamCosts: [emptyLngEconomicsCostDraft()],
    energyStages: [emptyLngEconomicsStageDraft()],
    discountFactors: [emptyLngEconomicsDiscountDraft()],
  });
  const rowReadiness = lngEconomicsReadiness(incomplete);
  for (const key of [
    "contracts.lng_economics.blocker.cost_id",
    "contracts.lng_economics.blocker.cost_charge_basis",
    "contracts.lng_economics.blocker.stage_id",
    "contracts.lng_economics.blocker.stage_physical_loss",
    "contracts.lng_economics.blocker.stage_source_references",
    "contracts.lng_economics.blocker.discount_factor",
    "contracts.lng_economics.blocker.discount_curve_reference",
  ]) {
    assert.ok(rowReadiness.blockerKeys.includes(key), key);
  }
  // No factor is defaulted: an empty row stays empty and therefore blocks.
  assert.equal(incomplete.discountFactors[0].factor, "");
  assert.equal(lngEconomicsRequest(incomplete), null);
});

test("the documented golden request is exact and sends no model version or decision context", () => {
  const body = lngEconomicsRequest(goldenDraft());
  assert.ok(body);
  assert.deepEqual(body, {
    contract_id: "contract-synthetic-lng-1",
    cargo_id: "cargo-synthetic-1",
    terminal_id: "terminal-synthetic-regas-1",
    resource_id: "resource-synthetic-supply-1",
    valuation_date: "2026-09-29",
    reporting_currency: "EUR",
    energy_basis_reference: "synthetic-basis:gcV-energy-mwh",
    energy_unit: "MWh",
    purchased_energy_mwh: "100",
    delivered_energy_mwh: "90",
    purchase_unit_price_eur_per_mwh: "20",
    sale_unit_price_eur_per_mwh: "30",
    purchase_price_source_reference: "synthetic-test-input:purchase-price-1",
    sale_price_source_reference: "synthetic-test-input:sale-price-1",
    purchase_basis: "DES",
    purchase_included_cost_items: [],
    cost_scope_statement:
      "Synthetic scope: the DES purchase price covers the cargo only; regas is invoiced separately below.",
    purchase_payment_date: "2026-09-29",
    sale_payment_date: "2026-11-30",
    downstream_costs: [
      {
        cost_id: "regas-1",
        category: "regas",
        amount_eur: "150",
        payment_date: "2026-09-29",
        source_reference: "synthetic-test-input:invoiced-cost-1",
        charge_basis: "invoiced_cash",
      },
    ],
    energy_stages: [
      {
        stage_id: "shipping-1",
        kind: "shipping",
        input_energy_mwh: "100",
        output_energy_mwh: "96",
        consumed_energy_mwh: "3",
        physical_loss_energy_mwh: "1",
        source_references: ["synthetic-test-input:stage-shipping-1"],
      },
      {
        stage_id: "regas-1",
        kind: "regasification",
        input_energy_mwh: "96",
        output_energy_mwh: "90",
        consumed_energy_mwh: "4",
        physical_loss_energy_mwh: "2",
        source_references: ["synthetic-test-input:stage-regas-1"],
      },
    ],
    discount_factors: [
      {
        payment_date: "2026-09-29",
        factor: "1",
        curve_reference: "synthetic-test-curve:eur-flat",
        source_reference: "synthetic-test-input:df-1",
        as_of: "2026-09-29",
      },
      {
        payment_date: "2026-11-30",
        factor: "0.975",
        curve_reference: "synthetic-test-curve:eur-flat",
        source_reference: "synthetic-test-input:df-1",
        as_of: "2026-09-29",
      },
    ],
  });
  assert.deepEqual(Object.keys(body), [
    "contract_id",
    "cargo_id",
    "terminal_id",
    "resource_id",
    "valuation_date",
    "reporting_currency",
    "energy_basis_reference",
    "energy_unit",
    "purchased_energy_mwh",
    "delivered_energy_mwh",
    "purchase_unit_price_eur_per_mwh",
    "sale_unit_price_eur_per_mwh",
    "purchase_price_source_reference",
    "sale_price_source_reference",
    "purchase_basis",
    "purchase_included_cost_items",
    "cost_scope_statement",
    "purchase_payment_date",
    "sale_payment_date",
    "downstream_costs",
    "energy_stages",
    "discount_factors",
  ]);
  const serialized = JSON.stringify(body);
  assert.equal("model_version" in body, false);
  assert.equal("decision_context" in body, false);
  assert.equal(serialized.includes("SANDBOX_SCENARIO"), false);
  assert.equal(serialized.includes("RUNTIME_DECISION"), false);
});

test("decimal text is transported as typed, including leading zeros and trailing places", () => {
  const body = lngEconomicsRequest(
    draftWith({
      ...goldenDraft(),
      purchasedEnergyMwh: "000100.0000",
      deliveredEnergyMwh: "090.0000",
      purchaseUnitPriceEurPerMwh: "0020.000",
      saleUnitPriceEurPerMwh: "00030.0",
      purchaseIncludedCostItems: " shipping \n\n regas ",
      downstreamCosts: [
        {
          ...goldenDraft().downstreamCosts[0],
          amountEur: "000150.000",
        },
      ],
      energyStages: [
        {
          ...goldenDraft().energyStages[0],
          inputEnergyMwh: "000100.0000",
          outputEnergyMwh: "096.0000",
        },
        {
          ...goldenDraft().energyStages[1],
          inputEnergyMwh: "096.0000",
          outputEnergyMwh: "090.0000",
        },
      ],
      discountFactors: [
        { ...goldenDraft().discountFactors[0], factor: "1.000000" },
        { ...goldenDraft().discountFactors[1], factor: "0.975000" },
      ],
    }),
  );
  assert.ok(body);
  assert.equal(body.purchased_energy_mwh, "000100.0000");
  assert.equal(body.delivered_energy_mwh, "090.0000");
  assert.equal(body.purchase_unit_price_eur_per_mwh, "0020.000");
  assert.equal(body.sale_unit_price_eur_per_mwh, "00030.0");
  assert.deepEqual(body.purchase_included_cost_items, ["shipping", "regas"]);
  assert.equal(body.downstream_costs[0].amount_eur, "000150.000");
  assert.equal(body.energy_stages[0].input_energy_mwh, "000100.0000");
  assert.equal(body.energy_stages[1].output_energy_mwh, "090.0000");
  assert.equal(body.discount_factors[0].factor, "1.000000");
  assert.equal(body.discount_factors[1].factor, "0.975000");
  // Adjacency, conservation and even the golden's endpoint equality are the backend's checks.
  assert.equal(body.purchased_energy_mwh, "000100.0000");
});

test("the reducer clears the result on edit, context change, run, refusal and failure, keeping the draft", () => {
  const succeeded = successfulState();
  assert.equal(succeeded.result?.cargo_margin_eur, "550.0000");
  assert.equal(succeeded.meta?.customer_approval, false);

  const nextDraft = { ...goldenDraft(), saleUnitPriceEurPerMwh: "31" };
  const edited = lngEconomicsReducer(succeeded, { type: "draft_changed", draft: nextDraft });
  assert.equal(edited.result, null);
  assert.equal(edited.meta, null);
  assert.equal(edited.draft.saleUnitPriceEurPerMwh, "31");

  const contextChanged = lngEconomicsReducer(succeeded, { type: "context_changed" });
  assert.equal(contextChanged.result, null);
  assert.equal(contextChanged.meta, null);
  assert.equal(contextChanged.refusal, null);
  assert.equal(contextChanged.error, null);
  assert.equal(contextChanged.draft.contractId, "contract-synthetic-lng-1");

  const restarted = lngEconomicsReducer(succeeded, { type: "run_started" });
  assert.equal(restarted.result, null);
  assert.equal(restarted.busy, true);

  const refused = lngEconomicsReducer(succeeded, {
    type: "run_failed",
    refusal: {
      status: 422,
      code: "lng_economics_only_refused",
      message: "refused",
      violations: [{ code: "STAGE_NOT_CONSERVED", detail: "detail" }],
    },
    error: new Error("typed refusal is not a transport error"),
  });
  assert.equal(refused.result, null);
  assert.equal(refused.refusal?.code, "lng_economics_only_refused");
  assert.equal(refused.error, null);
  assert.equal(refused.draft.salePaymentDate, "2026-11-30");

  const failed = lngEconomicsReducer(succeeded, {
    type: "run_failed",
    refusal: null,
    error: new Error("network down"),
  });
  assert.equal(failed.result, null);
  assert.equal(failed.refusal, null);
  assert.ok(failed.error instanceof Error);
  assert.equal(failed.draft.contractId, "contract-synthetic-lng-1");
});

test("a typed backend refusal is read without inventing one from a transport failure", () => {
  const refusal = lngEconomicsRefusal({
    status: 422,
    detail: {
      code: "lng_economics_only_refused",
      message: "The shared LNG economics-only composition refused the supplied inputs.",
      codes: ["STAGE_NOT_CONSERVED", "DISCOUNT_FACTOR_MISSING"],
      violations: [
        { code: "STAGE_NOT_CONSERVED", detail: "stage 1 input != output + consumed + loss" },
        { code: "DISCOUNT_FACTOR_MISSING", detail: "2026-11-30 has no explicit factor" },
      ],
    },
  });
  assert.deepEqual(refusal, {
    status: 422,
    code: "lng_economics_only_refused",
    message: "The shared LNG economics-only composition refused the supplied inputs.",
    violations: [
      { code: "STAGE_NOT_CONSERVED", detail: "stage 1 input != output + consumed + loss" },
      { code: "DISCOUNT_FACTOR_MISSING", detail: "2026-11-30 has no explicit factor" },
    ],
  });
  assert.equal(lngEconomicsRefusal(new Error("network down")), null);
  assert.equal(lngEconomicsRefusal({ status: 500, detail: "server error" }), null);

  const validation = lngEconomicsRefusal({
    status: 422,
    detail: [
      {
        loc: ["body", "valuation_date"],
        msg: "String should match pattern",
        type: "string_pattern_mismatch",
      },
    ],
  });
  assert.deepEqual(validation, {
    status: 422,
    code: "",
    message: "",
    violations: [{ code: "body.valuation_date", detail: "String should match pattern" }],
  });
});

test("the run gate suppresses duplicate submits and ignores a late response after invalidation", () => {
  const gate = createLngEconomicsRunGate();
  const first = gate.begin();
  assert.ok(first);
  assert.equal(gate.isInFlight(), true);
  assert.equal(gate.begin(), null, "a second submit in the same tick is refused");

  gate.invalidate();
  assert.equal(first.signal.aborted, true, "an edit aborts the request it described");
  assert.equal(gate.isCurrent(first.sequence), false);
  assert.equal(gate.isInFlight(), false);

  const second = gate.begin();
  assert.ok(second);
  assert.notEqual(second.sequence, first.sequence);
  assert.equal(gate.isCurrent(first.sequence), false);
  assert.equal(gate.isCurrent(second.sequence), true);
  assert.equal(second.signal.aborted, false);

  // A stale completion must not release the newer request's guard.
  gate.finish(first.sequence);
  assert.equal(gate.isInFlight(), true);
  assert.equal(gate.isCurrent(second.sequence), true);
  gate.finish(second.sequence);
  assert.equal(gate.isInFlight(), false);
});

test("Ctrl+Enter is recognised only for a ready, idle panel", () => {
  const chord = {
    key: "Enter",
    ctrlKey: true,
    altKey: false,
    shiftKey: false,
    metaKey: false,
  };
  assert.equal(lngEconomicsSubmitShortcut(chord, { canSubmit: true, busy: false }), true);
  assert.equal(lngEconomicsSubmitShortcut(chord, { canSubmit: false, busy: false }), false);
  assert.equal(lngEconomicsSubmitShortcut(chord, { canSubmit: true, busy: true }), false);
  assert.equal(
    lngEconomicsSubmitShortcut({ ...chord, ctrlKey: false }, { canSubmit: true, busy: false }),
    false,
  );
  assert.equal(
    lngEconomicsSubmitShortcut(
      { ...chord, altKey: true },
      { canSubmit: true, busy: false },
    ),
    false,
  );
});

test("every panel and blocker string exists in both English and Mandarin resources", () => {
  const readWebSource = (relativePath: string): string =>
    readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
  const panelSource = readWebSource("components/LngEconomicsPanel.tsx");
  const workbenchSource = readWebSource("components/ContractWorkbench.tsx");
  const hookSource = readWebSource("app/model/useLngEconomicsOnly.ts");
  const modelSource = readWebSource("app/model/lngEconomicsModel.ts");

  const keys = new Set(
    [...panelSource.matchAll(/t\("([^"]+)"\)/g)].map((match) => match[1]),
  );
  keys.add("contracts.lng_economics.ready");
  keys.add("contracts.lng_economics.blocker.energy_stages_required");
  keys.add("contracts.lng_economics.blocker.discount_factors_required");
  keys.add("contracts.view.lng_economics");
  assert.ok(workbenchSource.includes('t("contracts.view.lng_economics")'));

  const allRowsDraft = draftWith({
    ...goldenDraft(),
    downstreamCosts: [emptyLngEconomicsCostDraft()],
    energyStages: [emptyLngEconomicsStageDraft()],
    discountFactors: [emptyLngEconomicsDiscountDraft()],
  });
  for (const key of lngEconomicsReadiness(allRowsDraft).blockerKeys) keys.add(key);
  assert.ok(keys.size > 100);

  const resources = ["i18n/en.json", "i18n/zh.json"].map((path) =>
    JSON.parse(readWebSource(path)) as Record<string, unknown>,
  );
  for (const key of keys) {
    for (const catalog of resources) {
      assert.equal(typeof catalog[key], "string", `missing translation: ${key}`);
    }
  }

  for (const source of [modelSource, panelSource, hookSource]) {
    for (const forbidden of ["Number(", "parseFloat(", "parseInt(", "toFixed(", "Math."]) {
      assert.equal(source.includes(forbidden), false, forbidden);
    }
  }
  assert.match(hookSource, /gate\.begin\(\)/, "the synchronous duplicate guard is used");
  assert.match(hookSource, /if \(!gate\.isCurrent\(ticket\.sequence\)\) return;/);
  assert.match(hookSource, /gate\.invalidate\(\)/, "edits, context changes and unmount abort");
  assert.match(hookSource, /lngEconomicsRefusal\(error\)/);
  assert.match(hookSource, /type: "context_changed"/);
});

test("the meta type is the only decision context this request declares", () => {
  const meta: LngEconomicsOnlyMetaDTO = goldenMeta();
  assert.equal(meta.decision_context, "SANDBOX_SCENARIO");
  assert.equal(meta.caller_supplied, true);
  assert.equal(meta.references_verified, false);
  assert.equal(meta.physical_readiness, "NOT_ASSESSED");
  assert.equal(meta.readiness_assessed, false);
  assert.equal(meta.customer_approval, false);
});
