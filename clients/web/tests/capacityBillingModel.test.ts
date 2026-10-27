import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import type {
  CapacityBillingMetaDTO,
  CapacityBillingResultDTO,
} from "../src/api/client.ts";
import {
  CAPACITY_BILLING_CURRENCIES,
  CAPACITY_BILLING_TARIFF_UNITS,
  capacityBillingReadiness,
  capacityBillingReducer,
  capacityBillingRefusal,
  capacityBillingRequest,
  capacityBillingSourceReferences,
  emptyCapacityBillingDraft,
  initialCapacityBillingState,
  type CapacityBillingDraft,
} from "../src/app/model/capacityBillingModel.ts";

function draftWith(patch: Partial<CapacityBillingDraft> = {}): CapacityBillingDraft {
  return { ...emptyCapacityBillingDraft(), ...patch };
}

function completeDraft(patch: Partial<CapacityBillingDraft> = {}): CapacityBillingDraft {
  return draftWith({
    scenarioId: "sandbox-scenario-1",
    tariffId: "tariff-1",
    tariffRate: "001.2300",
    currency: "GBP",
    tariffUnit: "p/(kWh/h)/h",
    bookedCapacityMwhPerHour: "100.000",
    deliveredEnergyMwh: "000123.4500",
    billedCapacityEnergyMwh: "2500.000000000000000000000000000000",
    billingStart: "2026-10-25T00:00:00+02:00",
    billingEnd: "2026-10-26T00:00:00+02:00",
    sourceReferences: "tariff-sheet:uat-1\noperator-input:capacity-1",
    ...patch,
  });
}

function successResult(): CapacityBillingResultDTO {
  return {
    research_only: true,
    human_review_required: true,
    model_version: "capacity-billing/v1",
    scenario_id: "sandbox-scenario-1",
    tariff_id: "tariff-1",
    currency: "GBP",
    tariff_unit: "p/(kWh/h)/h",
    tariff_rate: "1.2300",
    booked_capacity_mwh_per_h: "100.000",
    billed_capacity_energy_mwh: "2500.000000000000000000000000000000",
    delivered_energy_mwh: "123.4500",
    billing_start: "2026-10-24T22:00:00+00:00",
    billing_end: "2026-10-25T22:00:00+00:00",
    duration_microseconds: 86_400_000_000,
    duration_hours: "24",
    total_cost: "3075.0000",
    cost_per_delivered_mwh: "24.9091",
    basis: {
      tariff_rate: "1.2300",
      tariff_unit: "p/(kWh/h)/h",
      booked_capacity_mwh_per_h: "100.000",
      billed_capacity_energy_mwh: "2500.000000000000000000000000000000",
      delivered_energy_mwh: "123.4500",
      billing_start_utc: "2026-10-24T22:00:00+00:00",
      billing_end_utc: "2026-10-25T22:00:00+00:00",
      duration_microseconds: 86_400_000_000,
    },
    provenance: ["operator-input:capacity-1", "tariff-sheet:uat-1"],
    source_references: ["operator-input:capacity-1", "tariff-sheet:uat-1"],
    assumptions: ["Caller-supplied tariff."],
    warnings: ["RESEARCH_ONLY_DECISION_SUPPORT_NOT_INVOICE_OR_SETTLEMENT"],
    lineage: ["capacity-billing", "capacity-billing/v1"],
    physical_readiness: "NOT_ASSESSED",
  };
}

function successMeta(): CapacityBillingMetaDTO {
  return {
    research_only: true,
    human_review_required: true,
    decision_context: "SANDBOX_SCENARIO",
    caller_supplied: true,
    references_verified: false,
    booked_rights_established: false,
    physical_readiness: "NOT_ASSESSED",
    customer_approval: false,
    source_references: ["operator-input:capacity-1", "tariff-sheet:uat-1"],
    warnings: ["RESEARCH_ONLY_DECISION_SUPPORT_NOT_INVOICE_OR_SETTLEMENT"],
  };
}

test("a blank form carries no inferred tariff, unit, currency, window or billed energy", () => {
  const draft = emptyCapacityBillingDraft();
  assert.deepEqual(draft, {
    scenarioId: "",
    tariffId: "",
    tariffRate: "",
    currency: "",
    tariffUnit: "",
    bookedCapacityMwhPerHour: "",
    deliveredEnergyMwh: "",
    billedCapacityEnergyMwh: "",
    billingStart: "",
    billingEnd: "",
    sourceReferences: "",
  });
  const readiness = capacityBillingReadiness(draft);
  assert.equal(readiness.canSubmit, false);
  assert.deepEqual(readiness.blockerKeys, [
    "portfolio.capacity_billing.blocker.scenario_id",
    "portfolio.capacity_billing.blocker.tariff_id",
    "portfolio.capacity_billing.blocker.tariff_rate",
    "portfolio.capacity_billing.blocker.currency",
    "portfolio.capacity_billing.blocker.tariff_unit",
    "portfolio.capacity_billing.blocker.booked_capacity",
    "portfolio.capacity_billing.blocker.delivered_energy",
    "portfolio.capacity_billing.blocker.billed_capacity",
    "portfolio.capacity_billing.blocker.billing_start",
    "portfolio.capacity_billing.blocker.billing_end",
    "portfolio.capacity_billing.blocker.source_references",
  ]);
  assert.equal(readiness.firstBlockerKey, "portfolio.capacity_billing.blocker.scenario_id");
  assert.equal(capacityBillingRequest(draft), null);

  // The supported unit/currency lists are the engine's declared vocabulary, not a second default.
  assert.deepEqual([...CAPACITY_BILLING_TARIFF_UNITS], [
    "EUR/(MWh/h)/h",
    "GBP/(MWh/h)/h",
    "p/(kWh/h)/h",
  ]);
  assert.deepEqual([...CAPACITY_BILLING_CURRENCIES], ["EUR", "GBP"]);
});

test("billed energy is explicit: booking a window never fills it in", () => {
  const draft = completeDraft({ billedCapacityEnergyMwh: "" });
  const readiness = capacityBillingReadiness(draft);
  assert.equal(readiness.canSubmit, false);
  assert.ok(readiness.blockerKeys.includes("portfolio.capacity_billing.blocker.billed_capacity"));
  assert.equal(capacityBillingRequest(draft), null);
});

test("the request preserves exact decimal strings and sends no decision-context claim", () => {
  const body = capacityBillingRequest(completeDraft());
  assert.ok(body);
  assert.deepEqual(body, {
    scenario_id: "sandbox-scenario-1",
    tariff_id: "tariff-1",
    tariff_rate: "001.2300",
    currency: "GBP",
    tariff_unit: "p/(kWh/h)/h",
    booked_capacity_mwh_per_h: "100.000",
    delivered_energy_mwh: "000123.4500",
    billed_capacity_energy_mwh: "2500.000000000000000000000000000000",
    billing_start: "2026-10-25T00:00:00+02:00",
    billing_end: "2026-10-26T00:00:00+02:00",
    source_references: ["tariff-sheet:uat-1", "operator-input:capacity-1"],
  });
  assert.deepEqual(Object.keys(body), [
    "scenario_id",
    "tariff_id",
    "tariff_rate",
    "currency",
    "tariff_unit",
    "booked_capacity_mwh_per_h",
    "delivered_energy_mwh",
    "billed_capacity_energy_mwh",
    "billing_start",
    "billing_end",
    "source_references",
  ]);
  const serialized = JSON.stringify(body);
  assert.equal("decision_context" in body, false);
  assert.equal(serialized.includes("RUNTIME_DECISION"), false);
  assert.equal(serialized.includes("SANDBOX_SCENARIO"), false);
  // Leading zeros and trailing decimal places survive because they are the caller's text.
  assert.equal(body.tariff_rate, "001.2300");
  assert.equal(body.delivered_energy_mwh, "000123.4500");

  assert.deepEqual(capacityBillingSourceReferences(" a \n\n b \r\n c "), ["a", "b", "c"]);

  // Unit/currency agreement and timestamp awareness stay the backend's decisions: the form sends
  // what the operator stated and renders the engine's refusal rather than refusing it locally.
  const mismatched = capacityBillingRequest(
    completeDraft({ currency: "EUR", tariffUnit: "p/(kWh/h)/h" }),
  );
  assert.ok(mismatched);
  assert.equal(mismatched.currency, "EUR");
  const naive = capacityBillingRequest(
    completeDraft({ billingStart: "2026-10-25T00:00:00" }),
  );
  assert.ok(naive);
  assert.equal(naive.billing_start, "2026-10-25T00:00:00");
});

test("the reducer drops a result on edit, a new run, refusal and transport failure", () => {
  const base = initialCapacityBillingState(completeDraft());

  const succeeded = capacityBillingReducer(base, {
    type: "run_succeeded",
    result: successResult(),
    meta: successMeta(),
  });
  assert.equal(succeeded.result?.total_cost, "3075.0000");
  assert.equal(succeeded.busy, false);

  const edited = capacityBillingReducer(succeeded, {
    type: "draft_changed",
    draft: completeDraft({ tariffRate: "2" }),
  });
  assert.equal(edited.result, null, "an edited draft cannot keep the previous result");
  assert.equal(edited.meta, null);
  assert.equal(edited.busy, false);

  const restarted = capacityBillingReducer(succeeded, { type: "run_started" });
  assert.equal(restarted.result, null, "loading never shows the previous result");
  assert.equal(restarted.meta, null);
  assert.equal(restarted.busy, true);

  const refused = capacityBillingReducer(succeeded, {
    type: "run_failed",
    refusal: {
      status: 422,
      code: "capacity_billing_refused",
      message: "refused",
      violations: [{ code: "BILLED_CAPACITY_ENERGY_INCONSISTENT", detail: "detail" }],
    },
    error: new Error("typed refusal is not a transport error"),
  });
  assert.equal(refused.result, null, "a refusal produces no synthetic result");
  assert.equal(refused.meta, null);
  assert.equal(refused.busy, false);
  assert.equal(refused.refusal?.code, "capacity_billing_refused");
  assert.equal(refused.error, null);

  const failed = capacityBillingReducer(succeeded, {
    type: "run_failed",
    refusal: null,
    error: new Error("network down"),
  });
  assert.equal(failed.result, null);
  assert.equal(failed.refusal, null);
  assert.ok(failed.error instanceof Error);

  const recovered = capacityBillingReducer(refused, {
    type: "run_succeeded",
    result: successResult(),
    meta: successMeta(),
  });
  assert.equal(recovered.refusal, null);
  assert.equal(recovered.error, null);
  assert.equal(recovered.result?.cost_per_delivered_mwh, "24.9091");
});

test("a typed backend refusal is read without inventing one from a transport failure", () => {
  const refusal = capacityBillingRefusal({
    status: 422,
    detail: {
      code: "capacity_billing_refused",
      message: "The shared engine refused the supplied inputs.",
      codes: ["BILLED_CAPACITY_ENERGY_INCONSISTENT", "DELIVERED_ENERGY_EXCEEDS_BILLED_CAPACITY"],
      violations: [
        {
          code: "BILLED_CAPACITY_ENERGY_INCONSISTENT",
          detail: "billed_capacity_energy_mwh must equal booked capacity × actual duration",
        },
        {
          code: "DELIVERED_ENERGY_EXCEEDS_BILLED_CAPACITY",
          detail: "delivered_energy_mwh exceeds billed_capacity_energy_mwh",
        },
      ],
    },
  });
  assert.deepEqual(refusal, {
    status: 422,
    code: "capacity_billing_refused",
    message: "The shared engine refused the supplied inputs.",
    violations: [
      {
        code: "BILLED_CAPACITY_ENERGY_INCONSISTENT",
        detail: "billed_capacity_energy_mwh must equal booked capacity × actual duration",
      },
      {
        code: "DELIVERED_ENERGY_EXCEEDS_BILLED_CAPACITY",
        detail: "delivered_energy_mwh exceeds billed_capacity_energy_mwh",
      },
    ],
  });

  assert.equal(capacityBillingRefusal(new Error("network down")), null);
  assert.equal(capacityBillingRefusal({ status: 500, detail: "server error" }), null);

  // FastAPI request validation is also field evidence, not a generic transport failure.
  const validation = capacityBillingRefusal({
    status: 422,
    detail: [
      {
        loc: ["body", "billing_start"],
        msg: "String should match pattern '^\\d{4}-\\d{2}-\\d{2}T'",
        type: "string_pattern_mismatch",
      },
    ],
  });
  assert.deepEqual(validation, {
    status: 422,
    code: "",
    message: "",
    violations: [
      {
        code: "body.billing_start",
        detail: "String should match pattern '^\\d{4}-\\d{2}-\\d{2}T'",
      },
    ],
  });
});

test("every capacity-billing string is present in both English and Mandarin resources", () => {
  const readWebSource = (relativePath: string): string =>
    readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
  const panelSource = readWebSource("components/CapacityBillingPanel.tsx");
  const keys = new Set(
    [...panelSource.matchAll(/t\("([^"]+)"\)/g)].map((match) => match[1]),
  );
  for (const key of capacityBillingReadiness(emptyCapacityBillingDraft()).blockerKeys) {
    keys.add(key);
  }
  assert.ok(keys.size > 20);

  const resources = ["i18n/en.json", "i18n/zh.json"].map((path) =>
    JSON.parse(readWebSource(path)) as Record<string, unknown>,
  );
  for (const key of keys) {
    for (const catalog of resources) {
      assert.equal(typeof catalog[key], "string", `missing translation: ${key}`);
    }
  }
});
