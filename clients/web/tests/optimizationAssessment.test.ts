/**
 * The desk's two optimisation assessments (register C14/D8).
 *
 * `POST /api/optimization/nomination-window` and `POST /api/optimization/storage-dispatch` were
 * reachable only from the Python SDK: the web client had no method and no path literal for the
 * family. These tests hold the two surfaces to the engines they mirror, and to the two statements
 * that matter more than the fields:
 *
 * - it is an **assessment**, never a submission. Neither engine submits a nomination, a booking or
 *   a trade, and the panels may not look like they do;
 * - a run that was not persisted says so. `meta.run_id` is null when the deployment has no runtime
 *   database, and an assessment that says "no run record" is honest where one that implies evidence
 *   is not.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  MAX_NOMINATION_INSTRUCTIONS,
  MAX_NOMINATION_WINDOWS,
  MAX_STORAGE_PERIODS,
  dispatchDecisionRows,
  emptyNominationDraft,
  emptyStorageDispatchDraft,
  nominationDecisionRows,
  nominationReadiness,
  nominationRequest,
  runRecordState,
  storageDispatchReadiness,
  storageDispatchRequest,
  type NominationDraft,
  type StorageDispatchDraft,
} from "../src/app/model/optimizationAssessmentModel.ts";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

function nominationDraft(patch: Partial<NominationDraft> = {}): NominationDraft {
  return { ...emptyNominationDraft(), ...patch };
}

function facility(overrides: Partial<StorageDispatchDraft["facility"]> = {}) {
  return {
    ...emptyStorageDispatchDraft().facility,
    initialInventory: "1000",
    minimumInventory: "0",
    maximumInventory: "2000",
    maximumInjection: "100",
    maximumWithdrawal: "100",
    ...overrides,
  };
}

function dispatchDraft(patch: Partial<StorageDispatchDraft> = {}): StorageDispatchDraft {
  return {
    ...emptyStorageDispatchDraft(),
    facility: facility(),
    periods: [{ periodId: "p1", marketPrice: "30" }],
    ...patch,
  };
}

test("the nomination rule mirrors the engine and refuses only what it cannot read", () => {
  const empty = nominationReadiness(emptyNominationDraft());
  assert.equal(empty.canRun, false);
  // The surface reports every blocker it found; the first is the one the action explains.
  assert.equal(empty.firstBlockerKey, "decision.nomination.blocker.initial_required");

  // The engine rejects a negative initial quantity, an empty window id, a duplicate window id and a
  // negative cap; the surface refuses the same four, and a window with no readable time.
  const blockersOf = (draft: NominationDraft): readonly string[] =>
    nominationReadiness(draft).blockerKeys;

  assert.ok(blockersOf(nominationDraft({ initialQuantity: "-1" })).includes(
    "decision.nomination.blocker.initial_required",
  ));
  assert.deepEqual(
    blockersOf(
      nominationDraft({
        initialQuantity: "0",
        instructions: [{ submittedAt: "2026-09-19T05:10", requestedQuantity: "10" }],
        windows: [{ windowId: "", opensAt: "05:00", closesAt: "05:30", maximumChange: "" }],
      }),
    ),
    ["decision.nomination.blocker.window_id_required"],
  );
  assert.deepEqual(
    blockersOf(
      nominationDraft({
        initialQuantity: "0",
        instructions: [{ submittedAt: "2026-09-19T05:10", requestedQuantity: "10" }],
        windows: [
          { windowId: "W1", opensAt: "05:00", closesAt: "05:30", maximumChange: "" },
          { windowId: "W1", opensAt: "06:00", closesAt: "06:30", maximumChange: "" },
        ],
      }),
    ),
    ["decision.nomination.blocker.window_id_duplicate"],
  );
  assert.deepEqual(
    blockersOf(
      nominationDraft({
        initialQuantity: "0",
        instructions: [{ submittedAt: "2026-09-19T05:10", requestedQuantity: "10" }],
        windows: [{ windowId: "W1", opensAt: "05:00", closesAt: "", maximumChange: "" }],
      }),
    ),
    ["decision.nomination.blocker.window_time_invalid"],
  );
  assert.deepEqual(
    blockersOf(
      nominationDraft({
        initialQuantity: "0",
        instructions: [{ submittedAt: "2026-09-19T05:10", requestedQuantity: "10" }],
        windows: [{ windowId: "W1", opensAt: "05:00", closesAt: "05:30", maximumChange: "-1" }],
      }),
    ),
    ["decision.nomination.blocker.window_cap_invalid"],
  );

  // An instruction outside every window is the question the engine exists to answer, not a form
  // error: a run with a window and an instruction that lands outside it is allowed.
  const outsideAnyWindow = nominationDraft({
    initialQuantity: "0",
    windows: [{ windowId: "W1", opensAt: "05:00", closesAt: "05:30", maximumChange: "" }],
    instructions: [{ submittedAt: "2026-09-19T22:00", requestedQuantity: "500" }],
  });
  assert.equal(nominationReadiness(outsideAnyWindow).canRun, true);
  assert.ok(MAX_NOMINATION_WINDOWS >= 1 && MAX_NOMINATION_INSTRUCTIONS >= 1);
});

test("the nomination body is composed only when the rule allows it, as a sandbox assessment", () => {
  assert.equal(nominationRequest(emptyNominationDraft()), null);

  const draft = nominationDraft({
    initialQuantity: "1200",
    windows: [
      { windowId: "W1", opensAt: "05:00", closesAt: "05:30", maximumChange: "200" },
      { windowId: "W2", opensAt: "17:00", closesAt: "17:30", maximumChange: "" },
    ],
    instructions: [{ submittedAt: "2026-09-19T05:10", requestedQuantity: "300" }],
  });
  const body = nominationRequest(draft);
  assert.ok(body);
  // The window clock is a time of day, and the submission is an instant.
  assert.equal(body.windows[0].opens_at, "05:00:00");
  assert.equal(body.windows[0].closes_at, "05:30:00");
  assert.equal(body.windows[0].maximum_change_mwh, 200);
  assert.equal(body.windows[1].maximum_change_mwh, null);
  assert.equal(body.initial_quantity_mwh, 1200);
  assert.equal(body.instructions.length, 1);
  // A `datetime-local` field carries a local wall-clock time; the engine is sent the instant, which
  // is what the submitted time means.
  assert.equal(
    body.instructions[0].submitted_at,
    new Date("2026-09-19T05:10").toISOString(),
  );
  // The surface assesses; it never asks the deployment to decide from its own data.
  assert.equal(body.decision_context, "SANDBOX_SCENARIO");
});

test("the dispatch rule refuses exactly what the route refuses", () => {
  // The route answers 422 optimization_input_invalid for a sandbox run without a facility.
  assert.equal(
    storageDispatchReadiness(
      dispatchDraft({ facility: facility({ initialInventory: "" }) }),
    ).firstBlockerKey,
    "decision.dispatch.blocker.facility_required",
  );
  // ... or without periods.
  assert.equal(
    storageDispatchReadiness(dispatchDraft({ periods: [] })).firstBlockerKey,
    "decision.dispatch.blocker.period_required",
  );
  // An inventory band that cannot be respected is refused with the reason, not silently clamped.
  assert.equal(
    storageDispatchReadiness(
      dispatchDraft({ facility: facility({ minimumInventory: "3000", maximumInventory: "2000" }) }),
    ).firstBlockerKey,
    "decision.dispatch.blocker.inventory_band_invalid",
  );
  assert.equal(
    storageDispatchReadiness(
      dispatchDraft({ facility: facility({ initialInventory: "2500", maximumInventory: "2000" }) }),
    ).firstBlockerKey,
    "decision.dispatch.blocker.initial_outside_band",
  );
  // A band that is stated but unusable is refused rather than silently dropped.
  assert.equal(
    storageDispatchReadiness(
      dispatchDraft({ facility: facility({ terminalInventory: "later" }) }),
    ).firstBlockerKey,
    "decision.dispatch.blocker.terminal_invalid",
  );
  assert.equal(storageDispatchReadiness(dispatchDraft()).canRun, true);
  assert.ok(MAX_STORAGE_PERIODS >= 1);
});

test("the dispatch body carries the operator's own numbers and says so", () => {
  assert.equal(storageDispatchRequest(emptyStorageDispatchDraft()), null);

  const body = storageDispatchRequest(
    dispatchDraft({
      facilityId: "  storage-1 ",
      periods: [
        { periodId: "p1", marketPrice: "30" },
        { periodId: "p2", marketPrice: "45" },
      ],
    }),
  );
  assert.ok(body);
  assert.equal(body.facility?.initial_inventory_mwh, 1000);
  assert.equal(body.facility?.injection_efficiency, 1);
  assert.equal(body.facility?.terminal_inventory_mwh, null);
  assert.equal(body.facility_id, "storage-1");
  assert.deepEqual(
    body.periods.map((period) => period.market_price_gbp_mwh),
    [30, 45],
  );
  assert.equal(body.decision_context, "SANDBOX_SCENARIO");
});

test("a run that was not persisted is reported as not persisted", () => {
  // The engines persist a run when a runtime database is configured, and assess without one.
  assert.deepEqual(runRecordState({ run_id: "opt-abc" }), { recorded: true, runId: "opt-abc" });
  assert.deepEqual(runRecordState({ run_id: null }), { recorded: false, runId: null });
  assert.deepEqual(runRecordState(undefined), { recorded: false, runId: null });
});

test("decision rows keep the window and the engine's own reason", () => {
  const rows = nominationDecisionRows([
    {
      submitted_at: "2026-09-19T05:10:00Z",
      requested_quantity_mwh: 300,
      accepted_quantity_mwh: 200,
      window_id: "W1",
      accepted: false,
      reason: "WINDOW_CAP_APPLIED",
    },
    {
      submitted_at: "2026-09-19T22:00:00Z",
      requested_quantity_mwh: 500,
      accepted_quantity_mwh: 0,
      window_id: null,
      accepted: false,
      reason: "OUTSIDE_ANY_WINDOW",
    },
  ]);
  assert.equal(rows[0].windowId, "W1");
  assert.equal(rows[0].accepted, 200);
  assert.equal(rows[0].reason, "WINDOW_CAP_APPLIED");
  // An instruction outside every window keeps its null window rather than an invented one.
  assert.equal(rows[1].windowId, null);
  assert.deepEqual(nominationDecisionRows(null), []);

  assert.equal(dispatchDecisionRows([{ period_id: "p1" } as never]).length, 1);
  assert.deepEqual(dispatchDecisionRows(null), []);
});

test("the panels are assessments, and their runs come from the header", () => {
  const nominationPanel = readWebSource("components/decision/NominationWindowPanel.tsx");
  const dispatchPanel = readWebSource("components/decision/StorageDispatchPanel.tsx");
  const workspace = readWebSource("components/DecisionWorkspace.tsx");
  const hook = readWebSource("app/model/useOptimizationAssessment.ts");
  const client = readWebSource("api/client.ts");

  // The three calls that had no consumer, typed, through the loader seam.
  assert.match(client, /optimizeNominationWindow: \(body: NominationWindowRequestDTO\)/);
  assert.match(client, /optimizeStorageDispatch: \(body: StorageDispatchRequestDTO\)/);
  assert.match(client, /optimizationRun: \(runId: string/);
  assert.match(hook, /api\.optimizeNominationWindow as never/);
  assert.match(hook, /api\.optimizeStorageDispatch as never/);
  assert.match(hook, /api\.optimizationRun\(runId\.trim\(\)\)/);

  // The panels configure and report; the workspace header starts the run, one act per task.
  for (const panel of [nominationPanel, dispatchPanel]) {
    assert.equal(/api\.optimize|api\.optimizationRun/.test(panel), false, "the panel calls nothing");
    assert.match(panel, /presentError\(t, describeFailure\(error\)\)/);
    assert.match(panel, /t\("decision\.assessment\.run_record"\)/);
    assert.match(panel, /t\("decision\.assessment\.no_run_record"\)/);
  }
  assert.match(workspace, /task === "nomination" \? \(/);
  assert.match(workspace, /task === "dispatch" \? \(/);
  assert.match(workspace, /onClick=\{\(\) => void nomination\.run\(\)\}/);
  assert.match(workspace, /onClick=\{\(\) => void dispatch\.run\(\)\}/);
  assert.equal((workspace.match(/primaryAction=\{/g) ?? []).length, 1);
  assert.match(workspace, /<NominationWindowPanel t=\{t\} assessment=\{nomination\} record=\{optimizationRun\} \/>/);
  assert.match(workspace, /<StorageDispatchPanel t=\{t\} assessment=\{dispatch\} record=\{optimizationRun\} \/>/);

  // Neither engine submits anything, and the copy says so where the operator reads it.
  assert.match(nominationPanel, /t\("decision\.nomination\.assessment_only"\)/);
  assert.match(dispatchPanel, /t\("decision\.dispatch\.assessment_only"\)/);
  assert.match(dispatchPanel, /t\("strategy\.no_execution"\)/);
});

test("the assessment vocabulary is bilingual", () => {
  const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>;
  const keys = [
    "decision.task.nomination",
    "decision.task.dispatch",
    "decision.assessment.as_of",
    "decision.assessment.not_reported",
    "decision.assessment.engine_stateless",
    "decision.assessment.run_record",
    "decision.assessment.no_run_record",
    "decision.assessment.run_record_help",
    "decision.assessment.no_run_record_help",
    "decision.assessment.read_run_record",
    "decision.assessment.record_read",
    "decision.assessment.engine_status",
    "decision.assessment.objective",
    "decision.assessment.no_review_required",
    "decision.nomination.title",
    "decision.nomination.assessment_only",
    "decision.nomination.note",
    "decision.nomination.initial_quantity",
    "decision.nomination.windows",
    "decision.nomination.window_id",
    "decision.nomination.opens_at",
    "decision.nomination.closes_at",
    "decision.nomination.maximum_change",
    "decision.nomination.add_window",
    "decision.nomination.remove_window",
    "decision.nomination.instructions",
    "decision.nomination.submitted_at",
    "decision.nomination.requested",
    "decision.nomination.add_instruction",
    "decision.nomination.remove_instruction",
    "decision.nomination.assess",
    "decision.nomination.ready",
    "decision.nomination.result",
    "decision.nomination.final_quantity",
    "decision.nomination.accepted",
    "decision.nomination.window_applied",
    "decision.nomination.outside_any_window",
    "decision.nomination.reason",
    "decision.nomination.no_instructions",
    "decision.nomination.blocker.initial_required",
    "decision.nomination.blocker.window_required",
    "decision.nomination.blocker.window_id_required",
    "decision.nomination.blocker.window_id_duplicate",
    "decision.nomination.blocker.window_time_invalid",
    "decision.nomination.blocker.window_cap_invalid",
    "decision.nomination.blocker.instruction_time_required",
    "decision.nomination.blocker.instruction_quantity_required",
    "decision.dispatch.title",
    "decision.dispatch.assessment_only",
    "decision.dispatch.note",
    "decision.dispatch.facility_id",
    "decision.dispatch.initial_inventory",
    "decision.dispatch.minimum_inventory",
    "decision.dispatch.maximum_inventory",
    "decision.dispatch.maximum_injection",
    "decision.dispatch.maximum_withdrawal",
    "decision.dispatch.injection_efficiency",
    "decision.dispatch.withdrawal_efficiency",
    "decision.dispatch.injection_cost",
    "decision.dispatch.withdrawal_cost",
    "decision.dispatch.terminal_inventory",
    "decision.dispatch.periods",
    "decision.dispatch.period_id",
    "decision.dispatch.market_price",
    "decision.dispatch.add_period",
    "decision.dispatch.remove_period",
    "decision.dispatch.assess",
    "decision.dispatch.ready",
    "decision.dispatch.result",
    "decision.dispatch.objective_help",
    "decision.dispatch.terminal_help",
    "decision.dispatch.injection",
    "decision.dispatch.withdrawal",
    "decision.dispatch.ending_inventory",
    "decision.dispatch.cashflow",
    "decision.dispatch.no_periods",
    "decision.dispatch.blocker.facility_required",
    "decision.dispatch.blocker.inventory_band_invalid",
    "decision.dispatch.blocker.initial_outside_band",
    "decision.dispatch.blocker.terminal_invalid",
    "decision.dispatch.blocker.period_required",
    "decision.dispatch.blocker.period_id_required",
    "decision.dispatch.blocker.period_price_required",
    "strategy.warnings",
  ];
  for (const key of keys) {
    assert.ok(en[key]?.trim(), `en ${key}`);
    assert.ok(zh[key]?.trim(), `zh ${key}`);
    assert.notEqual(en[key], zh[key], key);
  }
});
