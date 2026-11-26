/**
 * Book -> Planning starts from what the product holds (AGENTS rule 19, live by default).
 *
 * `GET /api/optimization/planning-inputs` returns the contracts in execution on the gas day, the
 * TSO calendar's windows and the storage facilities with their latest inventory. These helpers
 * turn a chosen contract or facility into the assessment's draft, and compare the draft with what
 * was prefilled so the result can say which inputs were entered by hand. Planning only: nothing
 * is nominated or booked (AGENTS rule 8).
 */
import type { RecordOption } from "../../components/ui/recordPickerModel.ts";
import type { NominationDraft, StorageDispatchDraft } from "./optimizationAssessmentModel.ts";

export interface PlanningContractDTO {
  contract_id: string;
  name: string;
  hub: string | null;
  dcq_mwh: number;
  acq_mwh: number;
  delivery_start: string;
  delivery_end: string;
  nomination_tolerance_pct: number;
  nominated_mwh: number | null;
}

export interface PlanningWindowDTO {
  window_id: string;
  name: string;
  opens_at: string;
  closes_at: string;
  maximum_change_mwh: number | null;
  source: string;
}

export interface PlanningStorageDTO {
  facility_id: string;
  name: string;
  hub: string;
  inventory_mwh: number | null;
  inventory_as_of: string | null;
  minimum_inventory_mwh: number;
  maximum_inventory_mwh: number;
  maximum_injection_mwh: number;
  maximum_withdrawal_mwh: number;
  injection_efficiency: number;
  withdrawal_efficiency: number;
  injection_cost_gbp_mwh: number;
  withdrawal_cost_gbp_mwh: number;
  terminal_inventory_mwh: number | null;
  source: string;
}

export interface PlanningInputsDTO {
  gas_day: string;
  contracts: PlanningContractDTO[];
  windows: { basis: "held" | "assumption"; windows: PlanningWindowDTO[] };
  storage: PlanningStorageDTO[];
}

const text = (value: number | null | undefined) => (value === null || value === undefined ? "" : String(value));

/** The contracts as a picker's records: name, then hub, DCQ and delivery window. */
export function planningContractOptions(inputs: PlanningInputsDTO | null): RecordOption[] | null {
  if (!inputs) return null;
  return inputs.contracts.map((contract) => ({
    id: contract.contract_id,
    label: contract.name,
    detail: [contract.hub, `DCQ ${contract.dcq_mwh.toLocaleString("en-GB")} MWh/d`, `${contract.delivery_start} – ${contract.delivery_end}`].filter(Boolean).join(" · "),
    keywords: [contract.hub ?? "", contract.contract_id],
  }));
}

export function planningStorageOptions(inputs: PlanningInputsDTO | null): RecordOption[] {
  return (inputs?.storage ?? []).map((facility) => ({
    id: facility.facility_id,
    label: facility.name,
    detail: [facility.hub, facility.inventory_mwh === null ? null : `${facility.inventory_mwh.toLocaleString("en-GB")} MWh`].filter(Boolean).join(" · "),
    keywords: [facility.hub, facility.facility_id],
  }));
}

/**
 * A `YYYY-MM-DDTHH:MM` local value for a UTC clock time on the gas day (window clocks are UTC,
 * as the engine reads them); the PeriodPicker holds local date-times.
 */
export function localDateTime(gasDay: string, utcClock: string): string {
  const instant = new Date(`${gasDay}T${utcClock}:00Z`);
  if (Number.isNaN(instant.getTime())) return "";
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${instant.getFullYear()}-${pad(instant.getMonth() + 1)}-${pad(instant.getDate())}T${pad(instant.getHours())}:${pad(instant.getMinutes())}`;
}

/**
 * The nomination draft a contract starts from: the day's nominated quantity (else its DCQ) as the
 * initial quantity, the calendar's windows, and one instruction at the first window's opening for
 * the DCQ, which the trader then changes to what they plan to renominate.
 */
export function nominationDraftFrom(inputs: PlanningInputsDTO, contractId: string): NominationDraft | null {
  const contract = inputs.contracts.find((item) => item.contract_id === contractId);
  if (!contract) return null;
  const windows = inputs.windows.windows.map((window) => ({
    windowId: window.window_id,
    opensAt: window.opens_at,
    closesAt: window.closes_at,
    maximumChange: text(window.maximum_change_mwh),
  }));
  const first = inputs.windows.windows[0];
  return {
    initialQuantity: text(contract.nominated_mwh ?? contract.dcq_mwh),
    windows,
    instructions: [
      { submittedAt: first ? localDateTime(inputs.gas_day, first.opens_at) : "", requestedQuantity: text(contract.dcq_mwh) },
    ],
  };
}

/** The storage draft a facility starts from: its master terms and its latest inventory. */
export function storageDraftFrom(inputs: PlanningInputsDTO, facilityId: string, current: StorageDispatchDraft): StorageDispatchDraft | null {
  const facility = inputs.storage.find((item) => item.facility_id === facilityId);
  if (!facility) return null;
  return {
    ...current,
    facilityId: facility.facility_id,
    facility: {
      initialInventory: text(facility.inventory_mwh),
      minimumInventory: text(facility.minimum_inventory_mwh),
      maximumInventory: text(facility.maximum_inventory_mwh),
      maximumInjection: text(facility.maximum_injection_mwh),
      maximumWithdrawal: text(facility.maximum_withdrawal_mwh),
      injectionEfficiency: text(facility.injection_efficiency),
      withdrawalEfficiency: text(facility.withdrawal_efficiency),
      injectionCost: text(facility.injection_cost_gbp_mwh),
      withdrawalCost: text(facility.withdrawal_cost_gbp_mwh),
      terminalInventory: text(facility.terminal_inventory_mwh),
    },
  };
}

/**
 * The inputs entered by hand: every leaf of the draft that differs from what was prefilled (or
 * every filled leaf when nothing was). Paths name the field ("initialQuantity",
 * "windows.0.maximumChange", "facility.initialInventory") for the screen to say in words.
 */
export function manualInputs(draft: unknown, prefilled: unknown, path = ""): string[] {
  if (Array.isArray(draft)) {
    const base = Array.isArray(prefilled) ? prefilled : [];
    return draft.flatMap((item, index) => manualInputs(item, base[index], path ? `${path}.${index}` : String(index)));
  }
  if (draft && typeof draft === "object") {
    const base = (prefilled && typeof prefilled === "object" ? prefilled : {}) as Record<string, unknown>;
    return Object.entries(draft as Record<string, unknown>).flatMap(([key, value]) => manualInputs(value, base[key], path ? `${path}.${key}` : key));
  }
  const value = String(draft ?? "").trim();
  const before = String(prefilled ?? "").trim();
  return value !== before && value !== "" ? [path] : [];
}

/** The words for a manual-input path ("windows.0.maximumChange" -> "Window 1 · Change cap"). */
export function manualInputLabel(path: string, t: (key: string, options?: Record<string, unknown>) => string): string {
  const FIELD: Record<string, string> = {
    initialQuantity: "decision.nomination.initial_quantity",
    opensAt: "decision.nomination.opens_at",
    closesAt: "decision.nomination.closes_at",
    maximumChange: "decision.nomination.maximum_change",
    submittedAt: "decision.nomination.submitted_at",
    requestedQuantity: "decision.nomination.requested",
    facilityId: "decision.dispatch.facility",
    initialInventory: "decision.dispatch.initial_inventory",
    minimumInventory: "decision.dispatch.minimum_inventory",
    maximumInventory: "decision.dispatch.maximum_inventory",
    maximumInjection: "decision.dispatch.maximum_injection",
    maximumWithdrawal: "decision.dispatch.maximum_withdrawal",
    injectionEfficiency: "decision.dispatch.injection_efficiency",
    withdrawalEfficiency: "decision.dispatch.withdrawal_efficiency",
    injectionCost: "decision.dispatch.injection_cost",
    withdrawalCost: "decision.dispatch.withdrawal_cost",
    terminalInventory: "decision.dispatch.terminal_inventory",
    marketPrice: "decision.dispatch.market_price",
  };
  const parts = path.split(".");
  const field = parts[parts.length - 1] ?? path;
  const words = FIELD[field] ? t(FIELD[field]) : field;
  if (parts[0] === "windows" && parts.length === 3) return `${t("decision.nomination.window_n", { n: Number(parts[1]) + 1 })} · ${words}`;
  if (parts[0] === "instructions" && parts.length === 3) return `${t("decision.nomination.instructions")} ${Number(parts[1]) + 1} · ${words}`;
  if (parts[0] === "periods" && parts.length === 3) return `${Number(parts[1]) + 1} · ${words}`;
  return words;
}
