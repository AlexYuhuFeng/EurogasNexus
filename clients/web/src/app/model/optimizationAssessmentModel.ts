/**
 * The desk's two optimisation assessments (register C14/D8).
 *
 * `POST /api/optimization/nomination-window` answers the day's clock question - which nomination
 * instruction lands in which window, and what the window's cap did to it - and
 * `POST /api/optimization/storage-dispatch` answers the swing question - how much to inject or
 * withdraw in each period, and what that is worth. Both are *assessments*: the engines return
 * accepted or adjusted quantities and never submit anything, so nothing here may be described as a
 * nomination, a booking or a trade.
 *
 * The rules mirror the engines rather than inventing stricter ones. The nomination engine rejects a
 * negative initial quantity, an empty window id, a duplicate window id and a negative cap; the
 * dispatch route answers `422 optimization_input_invalid` for a sandbox run without a facility or
 * without periods. Everything else the engines accept - no instructions at all, an instruction
 * outside every window - is a legitimate assessment the surface must be able to ask for and then
 * report, not a form error.
 */

import type {
  NominationDecisionDTO,
  NominationWindowInputDTO,
  NominationWindowRequestDTO,
  StorageDecisionDTO,
  StorageDispatchRequestDTO,
  StorageFacilityInputDTO,
  StoragePeriodInputDTO,
} from "@/api/client";

/** A nomination instruction as the form holds it: text in, so a half-typed time is a state. */
export interface NominationInstructionDraft {
  readonly submittedAt: string;
  readonly requestedQuantity: string;
}

export interface NominationWindowDraft {
  readonly windowId: string;
  readonly opensAt: string;
  readonly closesAt: string;
  readonly maximumChange: string;
}

export interface NominationDraft {
  readonly initialQuantity: string;
  readonly instructions: readonly NominationInstructionDraft[];
  readonly windows: readonly NominationWindowDraft[];
}

export interface StorageFacilityDraft {
  readonly initialInventory: string;
  readonly minimumInventory: string;
  readonly maximumInventory: string;
  readonly maximumInjection: string;
  readonly maximumWithdrawal: string;
  readonly injectionEfficiency: string;
  readonly withdrawalEfficiency: string;
  readonly injectionCost: string;
  readonly withdrawalCost: string;
  readonly terminalInventory: string;
}

export interface StoragePeriodDraft {
  readonly periodId: string;
  readonly marketPrice: string;
}

export interface StorageDispatchDraft {
  readonly facilityId: string;
  readonly facility: StorageFacilityDraft;
  readonly periods: readonly StoragePeriodDraft[];
}

export interface AssessmentReadiness {
  readonly canRun: boolean;
  readonly blockerKeys: readonly string[];
  readonly firstBlockerKey: string | null;
}

/** Bounded forms: a larger assessment belongs in the engine, not in a panel. */
export const MAX_NOMINATION_INSTRUCTIONS = 12;
export const MAX_NOMINATION_WINDOWS = 8;
export const MAX_STORAGE_PERIODS = 24;

function parsedNumber(value: string): number | null {
  const text = value.trim();
  if (!text) return null;
  const parsed = Number(text);
  return Number.isFinite(parsed) ? parsed : null;
}

/** `YYYY-MM-DDTHH:MM` from a `datetime-local` field, as an instant the engine can read. */
function parsedInstant(value: string): string | null {
  const text = value.trim();
  if (!text) return null;
  const parsed = new Date(text);
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
}

/** `HH:MM` from a time field, as the engine's local window clock reads it. */
function parsedTime(value: string): string | null {
  const text = value.trim();
  return /^([01]\d|2[0-3]):[0-5]\d$/.test(text) ? text : null;
}

export function emptyNominationDraft(): NominationDraft {
  return {
    initialQuantity: "",
    instructions: [{ submittedAt: "", requestedQuantity: "" }],
    windows: [{ windowId: "", opensAt: "", closesAt: "", maximumChange: "" }],
  };
}

export function emptyStorageDispatchDraft(): StorageDispatchDraft {
  return {
    facilityId: "",
    facility: {
      initialInventory: "",
      minimumInventory: "",
      maximumInventory: "",
      maximumInjection: "",
      maximumWithdrawal: "",
      injectionEfficiency: "1",
      withdrawalEfficiency: "1",
      injectionCost: "",
      withdrawalCost: "",
      terminalInventory: "",
    },
    periods: [{ periodId: "", marketPrice: "" }],
  };
}

/**
 * What the nomination assessment needs before the run, and nothing more.
 *
 * Windows are the deadline the whole assessment turns on, so a window without a readable open and
 * close time is refused here rather than sent for the engine to reject with a schema error; an
 * instruction with no submitted time cannot be placed in a window at all, so it is refused too. A
 * submitted time *outside* every window is not refused - it is the case the engine exists to
 * answer.
 */
export function nominationReadiness(draft: NominationDraft): AssessmentReadiness {
  const blockerKeys: string[] = [];
  const initial = parsedNumber(draft.initialQuantity);
  if (initial === null || initial < 0) {
    blockerKeys.push("decision.nomination.blocker.initial_required");
  }
  if (draft.windows.length === 0) {
    blockerKeys.push("decision.nomination.blocker.window_required");
  }
  const seen = new Set<string>();
  for (const window of draft.windows) {
    const id = window.windowId.trim();
    if (!id) {
      blockerKeys.push("decision.nomination.blocker.window_id_required");
      break;
    }
    if (seen.has(id)) {
      blockerKeys.push("decision.nomination.blocker.window_id_duplicate");
      break;
    }
    seen.add(id);
    if (parsedTime(window.opensAt) === null || parsedTime(window.closesAt) === null) {
      blockerKeys.push("decision.nomination.blocker.window_time_invalid");
      break;
    }
    if (window.maximumChange.trim() && (parsedNumber(window.maximumChange) ?? -1) < 0) {
      blockerKeys.push("decision.nomination.blocker.window_cap_invalid");
      break;
    }
  }
  for (const instruction of draft.instructions) {
    if (parsedInstant(instruction.submittedAt) === null) {
      blockerKeys.push("decision.nomination.blocker.instruction_time_required");
      break;
    }
    if (parsedNumber(instruction.requestedQuantity) === null) {
      blockerKeys.push("decision.nomination.blocker.instruction_quantity_required");
      break;
    }
  }
  return {
    canRun: blockerKeys.length === 0,
    blockerKeys,
    firstBlockerKey: blockerKeys[0] ?? null,
  };
}

/** The nomination body, or null when the rule blocks it: a partial body would invent a time. */
export function nominationRequest(draft: NominationDraft): NominationWindowRequestDTO | null {
  if (!nominationReadiness(draft).canRun) return null;
  const windows: NominationWindowInputDTO[] = draft.windows.map((window) => ({
    window_id: window.windowId.trim(),
    opens_at: `${parsedTime(window.opensAt) ?? "00:00"}:00`,
    closes_at: `${parsedTime(window.closesAt) ?? "00:00"}:00`,
    maximum_change_mwh: window.maximumChange.trim() ? parsedNumber(window.maximumChange) : null,
  }));
  return {
    initial_quantity_mwh: parsedNumber(draft.initialQuantity) ?? 0,
    instructions: draft.instructions.map((instruction) => ({
      submitted_at: parsedInstant(instruction.submittedAt) ?? "",
      requested_quantity_mwh: parsedNumber(instruction.requestedQuantity) ?? 0,
    })),
    windows,
    decision_context: "SANDBOX_SCENARIO",
  };
}

/**
 * What the dispatch assessment needs: the route itself refuses a sandbox run without a facility or
 * without periods (`422 optimization_input_invalid`), so the surface refuses the same two things
 * and names them.
 */
export function storageDispatchReadiness(draft: StorageDispatchDraft): AssessmentReadiness {
  const blockerKeys: string[] = [];
  const facility = draft.facility;
  const numbers = [
    facility.initialInventory,
    facility.minimumInventory,
    facility.maximumInventory,
    facility.maximumInjection,
    facility.maximumWithdrawal,
  ];
  if (numbers.some((value) => parsedNumber(value) === null)) {
    blockerKeys.push("decision.dispatch.blocker.facility_required");
  } else {
    const minimum = parsedNumber(facility.minimumInventory) ?? 0;
    const maximum = parsedNumber(facility.maximumInventory) ?? 0;
    const initial = parsedNumber(facility.initialInventory) ?? 0;
    if (minimum > maximum) {
      blockerKeys.push("decision.dispatch.blocker.inventory_band_invalid");
    } else if (initial < minimum || initial > maximum) {
      blockerKeys.push("decision.dispatch.blocker.initial_outside_band");
    }
  }
  const terminal = facility.terminalInventory.trim();
  if (terminal && parsedNumber(terminal) === null) {
    blockerKeys.push("decision.dispatch.blocker.terminal_invalid");
  }
  if (draft.periods.length === 0) {
    blockerKeys.push("decision.dispatch.blocker.period_required");
  }
  for (const period of draft.periods) {
    if (!period.periodId.trim()) {
      blockerKeys.push("decision.dispatch.blocker.period_id_required");
      break;
    }
    if (parsedNumber(period.marketPrice) === null) {
      blockerKeys.push("decision.dispatch.blocker.period_price_required");
      break;
    }
  }
  return {
    canRun: blockerKeys.length === 0,
    blockerKeys,
    firstBlockerKey: blockerKeys[0] ?? null,
  };
}

export function storageDispatchRequest(
  draft: StorageDispatchDraft,
): StorageDispatchRequestDTO | null {
  if (!storageDispatchReadiness(draft).canRun) return null;
  const facility = draft.facility;
  const facilityInput: StorageFacilityInputDTO = {
    initial_inventory_mwh: parsedNumber(facility.initialInventory) ?? 0,
    minimum_inventory_mwh: parsedNumber(facility.minimumInventory) ?? 0,
    maximum_inventory_mwh: parsedNumber(facility.maximumInventory) ?? 0,
    maximum_injection_mwh: parsedNumber(facility.maximumInjection) ?? 0,
    maximum_withdrawal_mwh: parsedNumber(facility.maximumWithdrawal) ?? 0,
    injection_efficiency: parsedNumber(facility.injectionEfficiency) ?? 1,
    withdrawal_efficiency: parsedNumber(facility.withdrawalEfficiency) ?? 1,
    injection_cost_gbp_mwh: parsedNumber(facility.injectionCost) ?? 0,
    withdrawal_cost_gbp_mwh: parsedNumber(facility.withdrawalCost) ?? 0,
    terminal_inventory_mwh: facility.terminalInventory.trim()
      ? parsedNumber(facility.terminalInventory)
      : null,
  };
  const periods: StoragePeriodInputDTO[] = draft.periods.map((period) => ({
    period_id: period.periodId.trim(),
    market_price_gbp_mwh: parsedNumber(period.marketPrice) ?? 0,
  }));
  return {
    facility: facilityInput,
    periods,
    facility_id: draft.facilityId.trim() || null,
    decision_context: "SANDBOX_SCENARIO",
  };
}

/** One decision row per instruction, with the window that applied and the engine's own reason. */
export interface NominationDecisionRow {
  readonly submittedAt: string;
  readonly requested: number;
  readonly accepted: number;
  readonly windowId: string | null;
  readonly accepted_instruction: boolean;
  readonly reason: string;
}

export function nominationDecisionRows(
  decisions: readonly NominationDecisionDTO[] | null,
): NominationDecisionRow[] {
  if (!decisions) return [];
  return decisions.map((decision) => ({
    submittedAt: decision.submitted_at,
    requested: decision.requested_quantity_mwh,
    accepted: decision.accepted_quantity_mwh,
    windowId: decision.window_id,
    accepted_instruction: decision.accepted,
    reason: decision.reason,
  }));
}

export function dispatchDecisionRows(
  decisions: readonly StorageDecisionDTO[] | null,
): StorageDecisionDTO[] {
  return decisions ? [...decisions] : [];
}

/**
 * The run record behind an assessment, as the envelope states it.
 *
 * `run_id: null` is not a failure: the engines persist a run when a runtime database is
 * configured, and a deployment without one still assesses. The surface says which of the two
 * happened rather than presenting an unrepeatable figure as if it were evidence.
 */
export function runRecordState(meta: { run_id?: string | null } | null | undefined): {
  readonly recorded: boolean;
  readonly runId: string | null;
} {
  const runId = meta?.run_id ?? null;
  return { recorded: Boolean(runId), runId };
}
