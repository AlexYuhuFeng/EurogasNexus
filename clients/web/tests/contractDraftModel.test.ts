/**
 * Architecture V2 Wave 9 - contract draft rule tests (action-geography precondition).
 *
 * Writing a reviewed contract draft is a `persist` consequence, so the action geography
 * wants it in the workspace's single primary slot. A header can only own that decision if
 * the rule behind it lives outside the panel that renders the form, so these tests pin the
 * rule itself: which issues a draft has, which facts describe the sub-view, when a save is
 * genuinely allowed, and what the reported status says when it is not. The panel must not be
 * able to disagree with the header about any of that, so the rule is asserted here rather
 * than through the component.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  contractSaveState,
  contractValidationIssueKeys,
  contractViewFacts,
  type ContractDraft,
  type ContractViewFacts,
} from "../src/app/model/contractDraftModel.ts";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
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
    physical_exit_point_name: "TTF",
    title_transfer_point: "TTF",
    beach_delivery_point: "TTF",
    index_basis: "TTF day-ahead",
    terminal_access: "firm",
    capacity_expiry: "2026-10-01",
    document_name: "supply.pdf",
    document_status: "MANUAL_DRAFT",
    source_reference: "manual",
    governing_law: "English law",
    delivery_tolerance_pct: 2,
    nomination_tolerance_pct: 2,
    tolerance_risk_allowance_gbp_mwh: 0.1,
    variable_cost_gbp_mwh: 1,
    regas_fee_gbp_mwh: 0.5,
    fuel_loss_allowance_pct: 1,
    settlement_frequency: "monthly",
    upstream_payment_lag_days: 30,
    screen_sale_cash_lag_days: 30,
    annual_financing_rate_pct: 5,
    owned_entry_capacity_mwh_per_day: null,
    owned_exit_capacity_mwh_per_day: null,
    allowed_exit_points: ["TTF"],
    eligible_sale_modes: ["SCREEN"],
    ...overrides,
  };
}

function viewFacts(overrides: Partial<ContractViewFacts> = {}): ContractViewFacts {
  return {
    readOnlyLibrary: false,
    readOnlySelectedResource: false,
    knownSelectedResource: false,
    ...overrides,
  };
}

function saveState(overrides: Partial<Parameters<typeof contractSaveState>[0]> = {}) {
  return contractSaveState({
    contract: draft(),
    runtimeDbReady: true,
    loading: false,
    viewFacts: viewFacts(),
    ...overrides,
  });
}

test("a complete draft reports no validation issues and may be saved", () => {
  assert.deepEqual(contractValidationIssueKeys(draft()), []);
  assert.deepEqual(saveState(), { canSave: true, statusKey: "contracts.validation.ready" });
});

test("each missing term reports its own issue, in the workbench's reporting order", () => {
  assert.deepEqual(contractValidationIssueKeys(draft({ contract_id: "  " })), [
    "contracts.validation.contract_id",
  ]);
  assert.deepEqual(contractValidationIssueKeys(draft({ contract_name: "" })), [
    "contracts.validation.contract_name",
  ]);
  assert.deepEqual(contractValidationIssueKeys(draft({ counterparty: "" })), [
    "contracts.validation.counterparty",
  ]);
  assert.deepEqual(contractValidationIssueKeys(draft({ delivery_point_name: "" })), [
    "contracts.validation.delivery_point",
  ]);
  assert.deepEqual(contractValidationIssueKeys(draft({ gas_year: "" })), [
    "contracts.validation.gas_year",
  ]);

  // A draft missing several terms reports all of them, in one stable order, so the same
  // draft always produces the same issue list.
  assert.deepEqual(
    contractValidationIssueKeys(
      draft({
        contract_id: "",
        contract_name: "",
        counterparty: "",
        delivery_point_name: "",
        gas_year: "",
      }),
    ),
    [
      "contracts.validation.contract_id",
      "contracts.validation.contract_name",
      "contracts.validation.counterparty",
      "contracts.validation.delivery_point",
      "contracts.validation.gas_year",
    ],
  );
});

test("volume, price, cost and fuel-loss bounds are enforced at the rule's own thresholds", () => {
  // A contract that delivers nothing is not a contract.
  assert.deepEqual(contractValidationIssueKeys(draft({ delivery_quantity_mwh_per_day: 0 })), [
    "contracts.validation.volume",
  ]);
  assert.deepEqual(contractValidationIssueKeys(draft({ delivery_quantity_mwh_per_day: -1 })), [
    "contracts.validation.volume",
  ]);

  // Negative prices and costs are refused; a zero price is a legitimate terms draft.
  assert.deepEqual(contractValidationIssueKeys(draft({ contract_price_gbp_mwh: -0.01 })), [
    "contracts.validation.price",
  ]);
  assert.deepEqual(contractValidationIssueKeys(draft({ contract_price_gbp_mwh: 0 })), []);
  assert.deepEqual(contractValidationIssueKeys(draft({ variable_cost_gbp_mwh: -1 })), [
    "contracts.validation.costs",
  ]);
  assert.deepEqual(contractValidationIssueKeys(draft({ regas_fee_gbp_mwh: -1 })), [
    "contracts.validation.costs",
  ]);

  // Fuel loss is a percentage that cannot consume the whole volume: 100% and above is
  // unrepresentable, and so is a negative share.
  assert.deepEqual(contractValidationIssueKeys(draft({ fuel_loss_allowance_pct: -0.1 })), [
    "contracts.validation.fuel_loss",
  ]);
  assert.deepEqual(contractValidationIssueKeys(draft({ fuel_loss_allowance_pct: 100 })), [
    "contracts.validation.fuel_loss",
  ]);
  assert.deepEqual(contractValidationIssueKeys(draft({ fuel_loss_allowance_pct: 99.9 })), []);
});

test("an incomplete draft is refused with the blocked status, never saved half-way", () => {
  const state = saveState({ contract: draft({ contract_id: "" }) });
  assert.equal(state.canSave, false);
  assert.equal(state.statusKey, "contracts.validation.blocked");
});

test("the view facts say whether a selected resource is known, and only the library reads", () => {
  // A selection in the terms editor is not a read-only library view.
  assert.deepEqual(
    contractViewFacts({
      selectedResourceId: "res-1",
      readOnlyLibrary: false,
      resourceIds: ["res-1"],
      contractIds: [],
    }),
    {
      readOnlyLibrary: false,
      readOnlySelectedResource: false,
      knownSelectedResource: true,
    },
  );

  // In the library, a selection that resolves to a portfolio resource is known...
  assert.deepEqual(
    contractViewFacts({
      selectedResourceId: "res-1",
      readOnlyLibrary: true,
      resourceIds: ["res-1"],
      contractIds: [],
    }),
    {
      readOnlyLibrary: true,
      readOnlySelectedResource: true,
      knownSelectedResource: true,
    },
  );

  // ...a selection that resolves to a persisted contract term is equally known...
  assert.equal(
    contractViewFacts({
      selectedResourceId: "term-9",
      readOnlyLibrary: true,
      resourceIds: ["res-1"],
      contractIds: ["term-9"],
    }).knownSelectedResource,
    true,
  );

  // ...and a selection this client cannot resolve reads as unknown rather than as an empty
  // contract, so the strip never invents a contract that was not loaded.
  assert.equal(
    contractViewFacts({
      selectedResourceId: "missing",
      readOnlyLibrary: true,
      resourceIds: ["res-1"],
      contractIds: ["term-9"],
    }).knownSelectedResource,
    false,
  );

  // The library is open on nothing.
  assert.deepEqual(
    contractViewFacts({
      selectedResourceId: null,
      readOnlyLibrary: true,
      resourceIds: [],
      contractIds: [],
    }),
    { readOnlyLibrary: true, readOnlySelectedResource: false, knownSelectedResource: false },
  );
});

test("a read-only library view never saves and reports the library, not save readiness", () => {
  assert.deepEqual(saveState({ viewFacts: viewFacts({ readOnlyLibrary: true }) }), {
    canSave: false,
    statusKey: "contracts.library",
  });

  // With a stored contract selected the library reports what it is showing: the persisted
  // record when the client knows it, and an explicit unknown when it does not.
  assert.deepEqual(
    saveState({
      viewFacts: viewFacts({
        readOnlyLibrary: true,
        readOnlySelectedResource: true,
        knownSelectedResource: true,
      }),
    }),
    { canSave: false, statusKey: "contracts.persisted" },
  );
  assert.deepEqual(
    saveState({
      viewFacts: viewFacts({
        readOnlyLibrary: true,
        readOnlySelectedResource: true,
        knownSelectedResource: false,
      }),
    }),
    { canSave: false, statusKey: "status.unknown" },
  );

  // A complete draft is still refused while the library view is showing.
  assert.equal(
    saveState({ viewFacts: viewFacts({ readOnlyLibrary: true, readOnlySelectedResource: true }) })
      .canSave,
    false,
  );
});

test("a database that is not ready blocks the write and says why", () => {
  const state = saveState({ runtimeDbReady: false });
  assert.equal(state.canSave, false);
  assert.equal(state.statusKey, "home.blocker_runtime_db");

  // The runtime blocker is reported even for an incomplete draft, because the write is
  // refused either way and the runtime is the first thing that has to be true.
  assert.equal(
    saveState({ runtimeDbReady: false, contract: draft({ contract_id: "" }) }).statusKey,
    "home.blocker_runtime_db",
  );
});

test("a read in flight blocks the write without misreporting the draft as incomplete", () => {
  const state = saveState({ loading: true });
  assert.equal(state.canSave, false);
  assert.equal(state.statusKey, "contracts.validation.ready");
});

test("the panel consumes the rule instead of restating it, and no longer holds the action", () => {
  const workbench = readWebSource("components/ContractWorkbench.tsx");

  // The panel builds its translated issue list from the rule's keys and reports the save
  // state it was handed.
  assert.match(
    workbench,
    /import \{\s*contractValidationIssueKeys,\s*type ContractDraft,\s*type ContractSaveState,\s*type ContractViewFacts,\s*\} from "@\/app\/model\/contractDraftModel";/s,
  );
  assert.match(
    workbench,
    /const validationIssues = useMemo\(\s*\(\) => contractValidationIssueKeys\(contract\)\.map\(\(key\) => t\(key\)\),\s*\[contract, t\],\s*\);/s,
  );
  assert.match(workbench, /const saveStatus = t\(saveState\.statusKey\);/);

  // The gesture that writes the draft is gone from the panel: the panel has no save
  // control, no save-rule evaluation, and not even the payload the action needs.
  assert.equal(workbench.includes("contracts.action.save"), false);
  assert.equal(workbench.includes("contractSaveState"), false);
  assert.equal(workbench.includes("contractPayload"), false);
  assert.equal(workbench.includes("saveDraftContract"), false);

  // The sub-view is a prop, so the header and the panel share one fact rather than keeping
  // two copies of it that can drift.
  assert.equal(workbench.includes("useState<ContractTaskView>"), false);
  assert.match(workbench, /taskView: ContractTaskView;/);
  assert.match(workbench, /onTaskViewChange: \(view: ContractTaskView\) => void;/);
  assert.equal(workbench.includes("setTaskView"), false);

  // The draft shape and the rule are declared once, in the model, not in the panel.
  assert.equal(workbench.includes("export interface ContractDraft"), false);
  assert.equal(workbench.includes("contracts.validation.volume"), false);
  assert.match(workbench, /export type \{ ContractDraft \};/);
  const defaultDraft = readWebSource("app/defaultContractDraft.ts");
  assert.match(
    defaultDraft,
    /import type \{ ContractDraft as ContractDraftModel \} from "\.\/model\/contractDraftModel";/,
  );
});

test("the workspace header owns the save action, and the panel is the only surface it acts on", () => {
  const workspace = readWebSource("components/PortfolioWorkspace.tsx");

  // The action is derived from the shared rule and the workspace-owned sub-view.
  assert.match(workspace, /const \[contractView, setContractView\] = useState<ContractTaskView>/);
  assert.match(
    workspace,
    /const contractViewFactsForSelection = contractViewFacts\(\{[\s\S]*?readOnlyLibrary: contractView === "library",/,
  );
  assert.match(
    workspace,
    /const contractSaveStateForDraft = contractSaveState\(\{[\s\S]*?viewFacts: contractViewFactsForSelection,/,
  );
  assert.match(workspace, /disabled=\{!contractSaveStateForDraft\.canSave\}/);
  assert.match(workspace, /title=\{t\(contractSaveStateForDraft\.statusKey\)\}/);
  assert.match(
    workspace,
    /onClick=\{\(\) =>\s*contractSaveStateForDraft\.canSave && api\.saveDraftContract\(contractEditor\.contractPayload\),?\s*\}/,
  );
  assert.match(workspace, /primaryAction=\{primaryAction\}/);
  // The panel receives the facts and the state rather than computing them again.
  assert.match(workspace, /viewFacts=\{contractViewFactsForSelection\}/);
  assert.match(workspace, /saveState=\{contractSaveStateForDraft\}/);

  // An unknown sub-view cannot become saveable: the header's button only exists for the
  // task that owns the draft.
  assert.match(workspace, /const primaryAction =\s*task === "resources" \? \(/);
});
