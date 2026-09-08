import assert from "node:assert/strict";
import test from "node:test";
import { cloneDefaultContractDraft } from "../src/app/defaultContractDraft.ts";
import {
  contractDraftFromRecord,
  sourceReferenceFromRecord,
} from "../src/app/contractImport.ts";

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
