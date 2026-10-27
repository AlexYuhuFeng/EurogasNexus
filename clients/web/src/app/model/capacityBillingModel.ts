/**
 * The capacity-billing sandbox in the Routes task.
 *
 * `POST /api/research/capacity-billing` is the shared engine's exact wire adaptation: one
 * explicitly supplied capacity tariff over one explicit UTC billing window. The client is a form
 * and a display, never a second engine.
 *
 * The rules this module holds:
 *
 * - every financial or physical value is a `string` from the operator to the backend and back.
 *   Nothing here calls `Number`, `parseFloat` or `toFixed`, and no value is rounded, converted or
 *   annualised;
 * - `billed_capacity_energy_mwh` is a required input. The engine verifies it against booked
 *   capacity and the exact UTC duration by integer cross-multiplication; this form never infers it
 *   from the window and never supplies a default tariff, FX, price or source verification;
 * - readiness refuses only an empty required field. Vocabulary, decimal grammar, unit/currency
 *   agreement, bounds, duration and the billed-energy identity stay the backend's decisions, so a
 *   malformed or inconsistent input reaches the engine and comes back as its typed refusal;
 * - the request has no `decision_context` field. The route is a sandbox and the response labels it
 *   `SANDBOX_SCENARIO`; a `RUNTIME_DECISION` claim is never composed here.
 */

import type {
  CapacityBillingMetaDTO,
  CapacityBillingRequestDTO,
  CapacityBillingResultDTO,
} from "@/api/client";

/**
 * The explicit capacity units `domain/research/capacity_billing.py` supports.
 *
 * This is the form's option list, not a second authority: the backend refuses any other value.
 */
export const CAPACITY_BILLING_TARIFF_UNITS = [
  "EUR/(MWh/h)/h",
  "GBP/(MWh/h)/h",
  "p/(kWh/h)/h",
] as const;

export type CapacityBillingTariffUnit = (typeof CAPACITY_BILLING_TARIFF_UNITS)[number];

/** The currencies the engine supports. The unit still decides which one it requires. */
export const CAPACITY_BILLING_CURRENCIES = ["EUR", "GBP"] as const;

export type CapacityBillingCurrency = (typeof CAPACITY_BILLING_CURRENCIES)[number];

/** One capacity-billing form as text, so a half-typed value is a state rather than a number. */
export interface CapacityBillingDraft {
  readonly scenarioId: string;
  readonly tariffId: string;
  readonly tariffRate: string;
  readonly currency: string;
  readonly tariffUnit: string;
  readonly bookedCapacityMwhPerHour: string;
  readonly deliveredEnergyMwh: string;
  readonly billedCapacityEnergyMwh: string;
  readonly billingStart: string;
  readonly billingEnd: string;
  /** One caller-supplied reference per line. */
  readonly sourceReferences: string;
}

export interface CapacityBillingReadiness {
  readonly canSubmit: boolean;
  readonly blockerKeys: readonly string[];
  readonly firstBlockerKey: string | null;
}

/**
 * A blank form with no inferred defaults.
 *
 * In particular the currency, tariff unit and billed energy start empty: choosing a unit or
 * computing billed energy for the caller would be inventing part of the calculation basis.
 */
export function emptyCapacityBillingDraft(): CapacityBillingDraft {
  return {
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
  };
}

function hasText(value: string): boolean {
  return value.trim().length > 0;
}

/** One caller-supplied reference per line; order is preserved and blank lines are ignored. */
export function capacityBillingSourceReferences(value: string): string[] {
  return value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
}

/** The rule the submit control is enabled by. Only missing required text blocks a run. */
export function capacityBillingReadiness(
  draft: CapacityBillingDraft,
): CapacityBillingReadiness {
  const blockerKeys: string[] = [];
  if (!hasText(draft.scenarioId)) blockerKeys.push("portfolio.capacity_billing.blocker.scenario_id");
  if (!hasText(draft.tariffId)) blockerKeys.push("portfolio.capacity_billing.blocker.tariff_id");
  if (!hasText(draft.tariffRate)) blockerKeys.push("portfolio.capacity_billing.blocker.tariff_rate");
  if (!hasText(draft.currency)) blockerKeys.push("portfolio.capacity_billing.blocker.currency");
  if (!hasText(draft.tariffUnit)) blockerKeys.push("portfolio.capacity_billing.blocker.tariff_unit");
  if (!hasText(draft.bookedCapacityMwhPerHour)) {
    blockerKeys.push("portfolio.capacity_billing.blocker.booked_capacity");
  }
  if (!hasText(draft.deliveredEnergyMwh)) {
    blockerKeys.push("portfolio.capacity_billing.blocker.delivered_energy");
  }
  if (!hasText(draft.billedCapacityEnergyMwh)) {
    blockerKeys.push("portfolio.capacity_billing.blocker.billed_capacity");
  }
  if (!hasText(draft.billingStart)) {
    blockerKeys.push("portfolio.capacity_billing.blocker.billing_start");
  }
  if (!hasText(draft.billingEnd)) blockerKeys.push("portfolio.capacity_billing.blocker.billing_end");
  if (capacityBillingSourceReferences(draft.sourceReferences).length === 0) {
    blockerKeys.push("portfolio.capacity_billing.blocker.source_references");
  }

  return {
    canSubmit: blockerKeys.length === 0,
    blockerKeys,
    firstBlockerKey: blockerKeys[0] ?? null,
  };
}

/**
 * The request body, or `null` while the required text is incomplete.
 *
 * Decimal strings are transported as typed (apart from surrounding whitespace), including leading
 * zeros and trailing decimal places; the backend's plain-decimal grammar is the authority on
 * whether the text is acceptable. No `model_version` is sent, so the backend's own default and
 * refusal code decide an unsupported version. No `decision_context` is sent.
 */
export function capacityBillingRequest(
  draft: CapacityBillingDraft,
): CapacityBillingRequestDTO | null {
  if (!capacityBillingReadiness(draft).canSubmit) return null;
  const sourceReferences = capacityBillingSourceReferences(draft.sourceReferences);
  if (sourceReferences.length === 0) return null;
  return {
    scenario_id: draft.scenarioId.trim(),
    tariff_id: draft.tariffId.trim(),
    tariff_rate: draft.tariffRate.trim(),
    currency: draft.currency.trim(),
    tariff_unit: draft.tariffUnit.trim(),
    booked_capacity_mwh_per_h: draft.bookedCapacityMwhPerHour.trim(),
    delivered_energy_mwh: draft.deliveredEnergyMwh.trim(),
    billed_capacity_energy_mwh: draft.billedCapacityEnergyMwh.trim(),
    billing_start: draft.billingStart.trim(),
    billing_end: draft.billingEnd.trim(),
    source_references: sourceReferences,
  };
}

/** One field-level violation the backend returned. */
export interface CapacityBillingViolation {
  readonly code: string;
  readonly detail: string;
}

/** A typed backend refusal, read from the route's structured error detail. */
export interface CapacityBillingRefusal {
  readonly status: number;
  readonly code: string;
  readonly message: string;
  readonly violations: readonly CapacityBillingViolation[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

/**
 * Read the backend's refusal without inventing one.
 *
 * Returns `null` for a transport failure or an untyped response, so the caller can present that
 * separately as "the request did not complete" rather than as an engine decision.
 */
export function capacityBillingRefusal(error: unknown): CapacityBillingRefusal | null {
  if (!isRecord(error)) return null;
  const status = error.status;
  if (typeof status !== "number") return null;
  const rawDetail = error.detail;
  // FastAPI's own request-validation refusal is an array of {loc, msg, type}; the engine's refusal
  // is the route's stable {code, message, codes, violations} object. Both are field evidence, so
  // both are rendered instead of being reduced to a generic transport failure.
  if (Array.isArray(rawDetail)) {
    const violations: CapacityBillingViolation[] = [];
    for (const item of rawDetail) {
      if (!isRecord(item)) continue;
      const location = Array.isArray(item.loc)
        ? item.loc.filter((part) => typeof part === "string").join(".")
        : "";
      const detail = typeof item.msg === "string" ? item.msg : "";
      if (location || detail) violations.push({ code: location, detail });
    }
    if (violations.length === 0) return null;
    return { status, code: "", message: "", violations };
  }
  if (!isRecord(rawDetail)) return null;
  const detail = rawDetail;
  const code =
    typeof detail.code === "string"
      ? detail.code
      : typeof detail.error === "string"
        ? detail.error
        : "";
  const message = typeof detail.message === "string" ? detail.message : "";
  const violations: CapacityBillingViolation[] = [];
  if (Array.isArray(detail.violations)) {
    for (const item of detail.violations) {
      if (!isRecord(item)) continue;
      violations.push({
        code: typeof item.code === "string" ? item.code : "",
        detail: typeof item.detail === "string" ? item.detail : "",
      });
    }
  }
  if (violations.length === 0 && Array.isArray(detail.codes)) {
    for (const item of detail.codes) {
      if (typeof item === "string" && item) violations.push({ code: item, detail: "" });
    }
  }
  if (!code && !message && violations.length === 0) return null;
  return { status, code, message, violations };
}

export interface CapacityBillingState {
  readonly draft: CapacityBillingDraft;
  readonly busy: boolean;
  readonly result: CapacityBillingResultDTO | null;
  readonly meta: CapacityBillingMetaDTO | null;
  readonly refusal: CapacityBillingRefusal | null;
  readonly error: unknown;
}

export type CapacityBillingAction =
  | { type: "draft_changed"; draft: CapacityBillingDraft }
  | { type: "run_started" }
  | { type: "run_succeeded"; result: CapacityBillingResultDTO; meta: CapacityBillingMetaDTO }
  | { type: "run_failed"; refusal: CapacityBillingRefusal | null; error: unknown };

export function initialCapacityBillingState(
  draft: CapacityBillingDraft = emptyCapacityBillingDraft(),
): CapacityBillingState {
  return {
    draft,
    busy: false,
    result: null,
    meta: null,
    refusal: null,
    error: null,
  };
}

/**
 * The one owner of the result lifecycle.
 *
 * A draft change, a new run, a backend refusal and a transport failure all clear the previous
 * result. That is what keeps a figure from surviving a change it no longer describes: the panel
 * never keeps a second copy of the answer.
 */
export function capacityBillingReducer(
  state: CapacityBillingState,
  action: CapacityBillingAction,
): CapacityBillingState {
  switch (action.type) {
    case "draft_changed":
      return {
        ...state,
        draft: action.draft,
        busy: false,
        result: null,
        meta: null,
        refusal: null,
        error: null,
      };
    case "run_started":
      return {
        ...state,
        busy: true,
        result: null,
        meta: null,
        refusal: null,
        error: null,
      };
    case "run_succeeded":
      return {
        ...state,
        busy: false,
        result: action.result,
        meta: action.meta,
        refusal: null,
        error: null,
      };
    case "run_failed":
      return {
        ...state,
        busy: false,
        result: null,
        meta: null,
        refusal: action.refusal,
        error: action.refusal ? null : action.error,
      };
    default:
      return state;
  }
}
