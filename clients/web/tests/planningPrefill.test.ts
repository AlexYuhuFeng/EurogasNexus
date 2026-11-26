import assert from "node:assert/strict";
import test from "node:test";

import { emptyNominationDraft, emptyStorageDispatchDraft } from "../src/app/model/optimizationAssessmentModel.ts";
import { manualInputs, nominationDraftFrom, planningContractOptions, storageDraftFrom, type PlanningInputsDTO } from "../src/app/model/planningPrefill.ts";

// Planning starts from what the product holds (AGENTS rule 19); typed inputs are said as such.
const inputs: PlanningInputsDTO = {
  gas_day: "2026-11-27",
  contracts: [{ contract_id: "c1", name: "Brae North supply", hub: "NBP", dcq_mwh: 10000, acq_mwh: 3650000, delivery_start: "2025-10-01", delivery_end: "2026-09-30", nomination_tolerance_pct: 5, nominated_mwh: null }],
  windows: { basis: "assumption", windows: [{ window_id: "default-renomination", name: "last_renomination", opens_at: "05:00", closes_at: "02:00", maximum_change_mwh: null, source: "network code" }] },
  storage: [{ facility_id: "f1", name: "Rough", hub: "NBP", inventory_mwh: 1200, inventory_as_of: "2026-11-26T06:00:00Z", minimum_inventory_mwh: 0, maximum_inventory_mwh: 5000, maximum_injection_mwh: 300, maximum_withdrawal_mwh: 400, injection_efficiency: 0.99, withdrawal_efficiency: 1, injection_cost_gbp_mwh: 0.5, withdrawal_cost_gbp_mwh: 0.4, terminal_inventory_mwh: null, source: "masters" }],
};

test("a contract prefills the initial quantity, the calendar's windows and an instruction", () => {
  const draft = nominationDraftFrom(inputs, "c1");
  assert.ok(draft);
  assert.equal(draft.initialQuantity, "10000");
  assert.deepEqual(draft.windows, [{ windowId: "default-renomination", opensAt: "05:00", closesAt: "02:00", maximumChange: "" }]);
  assert.equal(draft.instructions[0].requestedQuantity, "10000");
  assert.match(draft.instructions[0].submittedAt, /^2026-11-27T\d{2}:\d{2}$/);
  assert.equal(nominationDraftFrom(inputs, "nope"), null);
  assert.equal(planningContractOptions(inputs)?.[0].label, "Brae North supply");
});

test("a facility prefills its terms and its latest inventory", () => {
  const draft = storageDraftFrom(inputs, "f1", emptyStorageDispatchDraft());
  assert.equal(draft?.facility.initialInventory, "1200");
  assert.equal(draft?.facility.maximumInventory, "5000");
  assert.equal(draft?.facility.terminalInventory, "");
});

test("the inputs entered by hand are the ones that differ from the prefill", () => {
  const prefilled = nominationDraftFrom(inputs, "c1")!;
  const edited = { ...prefilled, initialQuantity: "9000", windows: [{ ...prefilled.windows[0], maximumChange: "500" }] };
  assert.deepEqual(manualInputs(edited, prefilled), ["initialQuantity", "windows.0.maximumChange"]);
  assert.deepEqual(manualInputs(prefilled, prefilled), []);
  const typed = { ...emptyNominationDraft(), initialQuantity: "5" };
  assert.deepEqual(manualInputs(typed, emptyNominationDraft()), ["initialQuantity"]);
});
