import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { cloneDefaultContractDraft } from "../src/app/defaultContractDraft.ts";
import {
  contractDraftFromRecord,
  sourceReferenceFromRecord,
} from "../src/app/contractImport.ts";

/**
 * The stored shape of the live preview row (`seed_preview_runtime_data.py`): the columns and
 * the raw notes string, and none of the notes-carried text terms the editor template holds.
 */
const PREVIEW_RECORD: Record<string, unknown> = {
  contract_id: "preview-portfolio-contract-ttf-pool-2025",
  contract_name: "Preview TTF portfolio supply 2025",
  resource_type: "PIPELINE_IMPORT",
  delivery_point_name: "TTF",
  gas_year: "2025+",
  delivery_quantity_mwh_per_day: 10_000,
  contract_price_gbp_mwh: 25,
  settlement_frequency: "monthly",
  upstream_payment_lag_days: 20,
  screen_sale_cash_lag_days: 1,
  annual_financing_rate_pct: 6,
  delivery_tolerance_pct: 2,
  nomination_tolerance_pct: 1,
  tolerance_risk_allowance_gbp_mwh: 0.1,
  owned_entry_capacity_mwh_per_day: null,
  owned_exit_capacity_mwh_per_day: null,
  allowed_exit_points: ["NBP", "TTF", "ZTP", "PEG", "THE"],
  eligible_sale_modes: ["TARGET_MARKET_SALE", "LOCAL_MARKET_SALE", "REROUTE_SALE"],
  notes: "preview_portfolio_contract:not_customer_data",
};

/** Terms the template carries but the stored row does not record anywhere. */
const ABSENT_TEXT_KEYS = [
  "counterparty",
  "contract_type",
  "physical_exit_point_name",
  "title_transfer_point",
  "beach_delivery_point",
  "index_basis",
  "terminal_access",
  "capacity_expiry",
  "document_name",
  "document_status",
  "source_reference",
  "governing_law",
] as const;

test("import overlay preserves unspecified draft fields", () => {
  const current = cloneDefaultContractDraft();
  current.counterparty = "Unsaved draft counterparty";
  const mapped = contractDraftFromRecord(
    {
      contract_id: "preview-portfolio-contract-ttf-pool-2025",
      contract_name: "Preview TTF portfolio supply 2025",
      resource_type: "PIPELINE_IMPORT",
      delivery_point_name: "TTF",
      gas_year: "2025+",
      delivery_quantity_mwh_per_day: 10_000,
      contract_price_gbp_mwh: 25,
      settlement_frequency: "monthly",
      upstream_payment_lag_days: 20,
      screen_sale_cash_lag_days: 1,
      delivery_tolerance_pct: 2,
      nomination_tolerance_pct: 1,
      annual_financing_rate_pct: 6,
      allowed_exit_points: ["NBP"],
      eligible_sale_modes: ["TARGET_MARKET_SALE"],
      notes: JSON.stringify({ source_reference: "preview:contract" }),
    },
    current,
  );

  assert.equal(mapped.contract_id, "preview-portfolio-contract-ttf-pool-2025");
  assert.equal(mapped.delivery_quantity_mwh_per_day, 10_000);
  assert.equal(mapped.source_reference, "preview:contract");
  assert.equal(mapped.counterparty, "Unsaved draft counterparty");
});

test("stored hydration clears absent text instead of presenting template facts", () => {
  const template = cloneDefaultContractDraft();
  const mapped = contractDraftFromRecord(PREVIEW_RECORD, template, "stored");

  for (const key of ABSENT_TEXT_KEYS) {
    assert.equal(mapped[key], "", `${key} must be blank when the stored row does not record it`);
    assert.notEqual(mapped[key], template[key], `${key} must not fall back to template text`);
  }

  // Recorded values survive verbatim: the stored columns, the list columns and the structured
  // numeric semantics are not replaced by the template.
  assert.equal(mapped.contract_id, "preview-portfolio-contract-ttf-pool-2025");
  assert.equal(mapped.contract_name, "Preview TTF portfolio supply 2025");
  assert.equal(mapped.resource_type, "PIPELINE_IMPORT");
  assert.equal(mapped.delivery_point_name, "TTF");
  assert.equal(mapped.gas_year, "2025+");
  assert.equal(mapped.settlement_frequency, "monthly");
  assert.equal(mapped.delivery_quantity_mwh_per_day, 10_000);
  assert.equal(mapped.contract_price_gbp_mwh, 25);
  assert.equal(mapped.upstream_payment_lag_days, 20);
  assert.equal(mapped.screen_sale_cash_lag_days, 1);
  assert.equal(mapped.annual_financing_rate_pct, 6);
  assert.equal(mapped.delivery_tolerance_pct, 2);
  assert.equal(mapped.nomination_tolerance_pct, 1);
  assert.equal(mapped.tolerance_risk_allowance_gbp_mwh, 0.1);
  assert.deepEqual(mapped.allowed_exit_points, ["NBP", "TTF", "ZTP", "PEG", "THE"]);
  assert.deepEqual(mapped.eligible_sale_modes, [
    "TARGET_MARKET_SALE",
    "LOCAL_MARKET_SALE",
    "REROUTE_SALE",
  ]);

  // An explicit null numeric capacity stays null; it does not become an assumed zero.
  assert.equal(mapped.owned_entry_capacity_mwh_per_day, null);
  assert.equal(mapped.owned_exit_capacity_mwh_per_day, null);
});

test("stored hydration keeps explicit values, including structured notes terms", () => {
  const mapped = contractDraftFromRecord(
    {
      contract_id: "persisted-contract-2",
      contract_name: "Persisted contract 2",
      resource_type: "BEACH_DELIVERY",
      delivery_point_name: "ZTP",
      gas_year: "2026",
      delivery_quantity_mwh_per_day: "1500",
      contract_price_gbp_mwh: 12.5,
      settlement_frequency: "weekly",
      upstream_payment_lag_days: 14,
      screen_sale_cash_lag_days: 2,
      annual_financing_rate_pct: 4.5,
      delivery_tolerance_pct: 3,
      nomination_tolerance_pct: 1.5,
      tolerance_risk_allowance_gbp_mwh: 0.25,
      owned_entry_capacity_mwh_per_day: 500,
      owned_exit_capacity_mwh_per_day: null,
      allowed_exit_points: ["ZTP"],
      eligible_sale_modes: ["LOCAL_MARKET_SALE"],
      notes: JSON.stringify({
        counterparty: "Recorded counterparty",
        contract_type: "EFET physical supply",
        physical_exit_point_name: "NBP",
        title_transfer_point: "ZTP virtual point",
        beach_delivery_point: "Bacton",
        index_basis: "TTF day-ahead index",
        terminal_access: "firm",
        capacity_expiry: "2027-10-01",
        document_name: "contract-2.pdf",
        document_status: "STAGED_REVIEW_REQUIRED",
        source_reference: "db:contract-2",
        governing_law: "English law",
        variable_cost_gbp_mwh: 1.25,
        regas_fee_gbp_mwh: 0.5,
        fuel_loss_allowance_pct: 1.1,
      }),
    },
    cloneDefaultContractDraft(),
    "stored",
  );

  assert.equal(mapped.counterparty, "Recorded counterparty");
  assert.equal(mapped.contract_type, "EFET physical supply");
  assert.equal(mapped.physical_exit_point_name, "NBP");
  assert.equal(mapped.title_transfer_point, "ZTP virtual point");
  assert.equal(mapped.beach_delivery_point, "Bacton");
  assert.equal(mapped.index_basis, "TTF day-ahead index");
  assert.equal(mapped.terminal_access, "firm");
  assert.equal(mapped.capacity_expiry, "2027-10-01");
  assert.equal(mapped.document_name, "contract-2.pdf");
  assert.equal(mapped.document_status, "STAGED_REVIEW_REQUIRED");
  assert.equal(mapped.source_reference, "db:contract-2");
  assert.equal(mapped.governing_law, "English law");
  assert.equal(mapped.variable_cost_gbp_mwh, 1.25);
  assert.equal(mapped.regas_fee_gbp_mwh, 0.5);
  assert.equal(mapped.fuel_loss_allowance_pct, 1.1);
  assert.equal(mapped.delivery_quantity_mwh_per_day, 1500);
  assert.equal(mapped.owned_entry_capacity_mwh_per_day, 500);
  assert.equal(mapped.owned_exit_capacity_mwh_per_day, null);
});

test("invalid or non-object notes read as absent, never as template text", () => {
  const template = cloneDefaultContractDraft();
  for (const notes of [
    "{not json",
    "[1,2,3]",
    "42",
    "{}",
    [],
    null,
    42,
    JSON.stringify({ counterparty: 42, source_reference: ["not", "text"] }),
  ]) {
    const mapped = contractDraftFromRecord(
      { contract_id: "persisted-contract-3", delivery_point_name: "TTF", notes },
      template,
      "stored",
    );
    assert.equal(mapped.counterparty, "", `notes=${JSON.stringify(notes)}`);
    assert.equal(mapped.document_name, "", `notes=${JSON.stringify(notes)}`);
    assert.equal(mapped.source_reference, "", `notes=${JSON.stringify(notes)}`);
  }
});

test("list isolation: mapped lists never alias the base draft or the record", () => {
  const base = cloneDefaultContractDraft();
  const fromBase = contractDraftFromRecord({ contract_id: "persisted-contract-4" }, base, "stored");
  assert.notEqual(fromBase.allowed_exit_points, base.allowed_exit_points);
  assert.notEqual(fromBase.eligible_sale_modes, base.eligible_sale_modes);
  assert.deepEqual(fromBase.allowed_exit_points, base.allowed_exit_points);

  const recorded = ["ZTP", "PEG"];
  const fromRecord = contractDraftFromRecord(
    {
      contract_id: "persisted-contract-5",
      allowed_exit_points: recorded,
      eligible_sale_modes: "TARGET_MARKET_SALE, REROUTE_SALE",
    },
    cloneDefaultContractDraft(),
    "stored",
  );
  assert.notEqual(fromRecord.allowed_exit_points, recorded);
  assert.deepEqual(fromRecord.eligible_sale_modes, ["TARGET_MARKET_SALE", "REROUTE_SALE"]);

  fromBase.allowed_exit_points.push("MUTATED");
  fromRecord.allowed_exit_points.push("MUTATED");
  assert.deepEqual(base.allowed_exit_points, ["NBP", "TTF"]);
  assert.deepEqual(recorded, ["ZTP", "PEG"]);
});

test("stored hydration is distinct from the new-draft template and the import overlay", () => {
  const record = {
    contract_id: "persisted-contract-6",
    notes: JSON.stringify({ source_reference: "db:contract-6" }),
  };

  // The new-draft template still carries its explicit operator-entry defaults.
  const fresh = cloneDefaultContractDraft();
  assert.equal(fresh.counterparty, "Operator draft counterparty");
  assert.equal(fresh.contract_type, "EFET physical supply");
  assert.equal(fresh.governing_law, "English law / EFET master confirmation to review");

  // The file-import overlay keeps the working draft's unstated terms...
  const overlaid = contractDraftFromRecord(record, fresh);
  assert.equal(overlaid.counterparty, "Operator draft counterparty");
  assert.equal(overlaid.source_reference, "db:contract-6");

  // ...while stored hydration of the same record clears them.
  const stored = contractDraftFromRecord(record, cloneDefaultContractDraft(), "stored");
  assert.equal(stored.counterparty, "");
  assert.equal(stored.contract_type, "");
  assert.equal(stored.governing_law, "");
  assert.equal(stored.source_reference, "db:contract-6");
});

test("saved-record load asks for stored hydration while file import keeps the draft overlay", () => {
  const hook = readFileSync(
    new URL("../src/app/hooks/useContractEditor.ts", import.meta.url),
    "utf8",
  );
  assert.match(
    hook,
    /contractDraftFromRecord\(saved as unknown as Record<string, unknown>, cloneDefaultContractDraft\(\), "stored"\)/,
  );
  assert.match(hook, /contractDraftFromRecord\(record, current\)/);
});

test("persisted load mapping uses a clean base for absent draft fields", () => {
  const priorDraft = cloneDefaultContractDraft();
  priorDraft.owned_entry_capacity_mwh_per_day = 777;
  priorDraft.source_reference = "prior-draft-source";
  const mapped = contractDraftFromRecord(
    {
      contract_id: "persisted-contract-1",
      contract_name: "Persisted contract",
      delivery_point_name: "TTF",
      delivery_quantity_mwh_per_day: 10_000,
      notes: JSON.stringify({ source_reference: "db:contract-1" }),
    },
    cloneDefaultContractDraft(),
    "stored",
  );

  assert.notEqual(mapped.owned_entry_capacity_mwh_per_day, priorDraft.owned_entry_capacity_mwh_per_day);
  assert.equal(mapped.owned_entry_capacity_mwh_per_day, null);
  assert.equal(mapped.source_reference, "db:contract-1");
  assert.notEqual(mapped.source_reference, priorDraft.source_reference);
});

test("source mapping keeps structured lineage and ignores raw JSON as a reference", () => {
  assert.equal(sourceReferenceFromRecord({ notes: JSON.stringify({ source_reference: "db:contract-1" }) }), "db:contract-1");
  assert.equal(sourceReferenceFromRecord({ notes: "legacy-source-note" }), "legacy-source-note");
  assert.equal(sourceReferenceFromRecord({ notes: JSON.stringify({ lineage: ["db:contract-1"] }) }), "");
});
