/**
 * The LNG economics-only sandbox in the existing Contracts workbench.
 *
 * `POST /api/research/lng-economics-only` is the shared domain composition's exact wire
 * adaptation: explicit caller-supplied cash amounts, an explicit ordered energy-stage chain and
 * explicit discount factors. The client is a form and a readback, never a second engine.
 *
 * The rules this module holds:
 *
 * - every financial or energy value is a `string` from the operator to the backend and back.
 *   Nothing here parses, converts or formats a value as a binary number, and no value is rounded,
 *   converted or annualised;
 * - no stage, cost, discount factor, price, basis, date, charge basis or source reference is
 *   invented. Adding a row adds blank text, never a synthetic `1` factor or a sample stage;
 * - readiness refuses only an empty required field (plus "at least one stage" and "at least one
 *   discount factor"). Decimal grammar, conservation, chain adjacency, discount coverage, date
 *   ordering and every other semantic rule stay the backend's decisions;
 * - the request carries no `decision_context` claim and no `model_version`: the sandbox dependency
 *   labels the response, and the backend's actual implementation version is authoritative;
 * - the response is rendered as returned. In particular `physical_readiness` is only ever the
 *   backend's own value (not-assessed for this path) and `readiness_assessed` is never inferred.
 */

import type {
  LngEconomicsOnlyDiscountFactorDTO,
  LngEconomicsOnlyDownstreamCostDTO,
  LngEconomicsOnlyEnergyStageDTO,
  LngEconomicsOnlyMetaDTO,
  LngEconomicsOnlyRequestDTO,
  LngEconomicsOnlyResultDTO,
} from "@/api/client";

/** The purchase bases the domain composition declares. The backend refuses any other value. */
export const LNG_ECONOMICS_PURCHASE_BASES = ["FOB", "DES"] as const;

export type LngEconomicsPurchaseBasis = (typeof LNG_ECONOMICS_PURCHASE_BASES)[number];

/** The only explicit reporting currency in the initial scope. */
export const LNG_ECONOMICS_REPORTING_CURRENCIES = ["EUR"] as const;

/** The only explicit energy unit the engine accepts; no volume/heat conversion is performed. */
export const LNG_ECONOMICS_ENERGY_UNITS = ["MWh"] as const;

/** The declared nature of one downstream charge. Only `invoiced_cash` becomes a cash expense. */
export const LNG_ECONOMICS_CHARGE_BASES = [
  "invoiced_cash",
  "in_kind",
  "unknown",
] as const;

/** The ordered stage kinds the energy-balance engine declares. */
export const LNG_ECONOMICS_STAGE_KINDS = [
  "cargo_transfer",
  "shipping",
  "storage",
  "regasification",
  "other",
] as const;

/**
 * The shared cash-flow leg vocabulary.
 *
 * This is the form's option list, not a second authority: the backend maps the same values and
 * refuses an unknown token with its own stable code.
 */
export const LNG_ECONOMICS_COST_CATEGORIES = [
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
] as const;

export interface LngEconomicsCostDraft {
  readonly costId: string;
  readonly category: string;
  readonly amountEur: string;
  readonly paymentDate: string;
  readonly sourceReference: string;
  readonly chargeBasis: string;
}

export interface LngEconomicsStageDraft {
  readonly stageId: string;
  readonly kind: string;
  readonly inputEnergyMwh: string;
  readonly outputEnergyMwh: string;
  readonly consumedEnergyMwh: string;
  readonly physicalLossEnergyMwh: string;
  /** One caller-supplied reference per line. */
  readonly sourceReferences: string;
}

export interface LngEconomicsDiscountDraft {
  readonly paymentDate: string;
  readonly factor: string;
  readonly curveReference: string;
  readonly sourceReference: string;
  readonly asOf: string;
}

/** One economics-only form as text, so a half-typed value is a state rather than a number. */
export interface LngEconomicsDraft {
  readonly contractId: string;
  readonly cargoId: string;
  readonly terminalId: string;
  readonly resourceId: string;
  readonly valuationDate: string;
  readonly reportingCurrency: string;
  readonly energyBasisReference: string;
  readonly energyUnit: string;
  readonly purchasedEnergyMwh: string;
  readonly deliveredEnergyMwh: string;
  readonly purchaseUnitPriceEurPerMwh: string;
  readonly saleUnitPriceEurPerMwh: string;
  readonly purchasePriceSourceReference: string;
  readonly salePriceSourceReference: string;
  readonly purchaseBasis: string;
  readonly purchaseIncludedCostItems: string;
  readonly costScopeStatement: string;
  readonly purchasePaymentDate: string;
  readonly salePaymentDate: string;
  readonly downstreamCosts: readonly LngEconomicsCostDraft[];
  readonly energyStages: readonly LngEconomicsStageDraft[];
  readonly discountFactors: readonly LngEconomicsDiscountDraft[];
}

export interface LngEconomicsReadiness {
  readonly canSubmit: boolean;
  readonly blockerKeys: readonly string[];
  readonly firstBlockerKey: string | null;
}

/**
 * A blank form with no inferred defaults.
 *
 * In particular the currency, energy unit, purchase basis, stage kinds, charge bases and discount
 * factors start empty, and all three dynamic collections start empty. Choosing any of those for
 * the caller would be inventing part of the calculation basis.
 */
export function emptyLngEconomicsDraft(): LngEconomicsDraft {
  return {
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
  };
}

export function emptyLngEconomicsCostDraft(): LngEconomicsCostDraft {
  return {
    costId: "",
    category: "",
    amountEur: "",
    paymentDate: "",
    sourceReference: "",
    chargeBasis: "",
  };
}

export function emptyLngEconomicsStageDraft(): LngEconomicsStageDraft {
  return {
    stageId: "",
    kind: "",
    inputEnergyMwh: "",
    outputEnergyMwh: "",
    consumedEnergyMwh: "",
    physicalLossEnergyMwh: "",
    sourceReferences: "",
  };
}

export function emptyLngEconomicsDiscountDraft(): LngEconomicsDiscountDraft {
  return {
    paymentDate: "",
    factor: "",
    curveReference: "",
    sourceReference: "",
    asOf: "",
  };
}

function hasText(value: string): boolean {
  return value.trim().length > 0;
}

/** One caller-supplied reference per line; order is preserved and blank lines are ignored. */
export function lngEconomicsReferences(value: string): string[] {
  return value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
}

function costBlockers(cost: LngEconomicsCostDraft): string[] {
  const blockers: string[] = [];
  if (!hasText(cost.costId)) blockers.push("contracts.lng_economics.blocker.cost_id");
  if (!hasText(cost.category)) blockers.push("contracts.lng_economics.blocker.cost_category");
  if (!hasText(cost.amountEur)) blockers.push("contracts.lng_economics.blocker.cost_amount");
  if (!hasText(cost.paymentDate)) blockers.push("contracts.lng_economics.blocker.cost_payment_date");
  if (!hasText(cost.sourceReference)) {
    blockers.push("contracts.lng_economics.blocker.cost_source_reference");
  }
  if (!hasText(cost.chargeBasis)) blockers.push("contracts.lng_economics.blocker.cost_charge_basis");
  return blockers;
}

function stageBlockers(stage: LngEconomicsStageDraft): string[] {
  const blockers: string[] = [];
  if (!hasText(stage.stageId)) blockers.push("contracts.lng_economics.blocker.stage_id");
  if (!hasText(stage.kind)) blockers.push("contracts.lng_economics.blocker.stage_kind");
  if (!hasText(stage.inputEnergyMwh)) blockers.push("contracts.lng_economics.blocker.stage_input");
  if (!hasText(stage.outputEnergyMwh)) blockers.push("contracts.lng_economics.blocker.stage_output");
  if (!hasText(stage.consumedEnergyMwh)) {
    blockers.push("contracts.lng_economics.blocker.stage_consumed");
  }
  if (!hasText(stage.physicalLossEnergyMwh)) {
    blockers.push("contracts.lng_economics.blocker.stage_physical_loss");
  }
  if (lngEconomicsReferences(stage.sourceReferences).length === 0) {
    blockers.push("contracts.lng_economics.blocker.stage_source_references");
  }
  return blockers;
}

function discountBlockers(discount: LngEconomicsDiscountDraft): string[] {
  const blockers: string[] = [];
  if (!hasText(discount.paymentDate)) {
    blockers.push("contracts.lng_economics.blocker.discount_payment_date");
  }
  if (!hasText(discount.factor)) blockers.push("contracts.lng_economics.blocker.discount_factor");
  if (!hasText(discount.curveReference)) {
    blockers.push("contracts.lng_economics.blocker.discount_curve_reference");
  }
  if (!hasText(discount.sourceReference)) {
    blockers.push("contracts.lng_economics.blocker.discount_source_reference");
  }
  if (!hasText(discount.asOf)) blockers.push("contracts.lng_economics.blocker.discount_as_of");
  return blockers;
}

/** The rule the submit control is enabled by. Only missing required text blocks a run. */
export function lngEconomicsReadiness(draft: LngEconomicsDraft): LngEconomicsReadiness {
  const blockerKeys: string[] = [];
  if (!hasText(draft.contractId)) blockerKeys.push("contracts.lng_economics.blocker.contract_id");
  if (!hasText(draft.cargoId)) blockerKeys.push("contracts.lng_economics.blocker.cargo_id");
  if (!hasText(draft.terminalId)) blockerKeys.push("contracts.lng_economics.blocker.terminal_id");
  if (!hasText(draft.resourceId)) blockerKeys.push("contracts.lng_economics.blocker.resource_id");
  if (!hasText(draft.valuationDate)) {
    blockerKeys.push("contracts.lng_economics.blocker.valuation_date");
  }
  if (!hasText(draft.reportingCurrency)) {
    blockerKeys.push("contracts.lng_economics.blocker.reporting_currency");
  }
  if (!hasText(draft.energyBasisReference)) {
    blockerKeys.push("contracts.lng_economics.blocker.energy_basis_reference");
  }
  if (!hasText(draft.energyUnit)) blockerKeys.push("contracts.lng_economics.blocker.energy_unit");
  if (!hasText(draft.purchasedEnergyMwh)) {
    blockerKeys.push("contracts.lng_economics.blocker.purchased_energy");
  }
  if (!hasText(draft.deliveredEnergyMwh)) {
    blockerKeys.push("contracts.lng_economics.blocker.delivered_energy");
  }
  if (!hasText(draft.purchaseUnitPriceEurPerMwh)) {
    blockerKeys.push("contracts.lng_economics.blocker.purchase_unit_price");
  }
  if (!hasText(draft.saleUnitPriceEurPerMwh)) {
    blockerKeys.push("contracts.lng_economics.blocker.sale_unit_price");
  }
  if (!hasText(draft.purchasePriceSourceReference)) {
    blockerKeys.push("contracts.lng_economics.blocker.purchase_price_source");
  }
  if (!hasText(draft.salePriceSourceReference)) {
    blockerKeys.push("contracts.lng_economics.blocker.sale_price_source");
  }
  if (!hasText(draft.purchaseBasis)) {
    blockerKeys.push("contracts.lng_economics.blocker.purchase_basis");
  }
  if (!hasText(draft.costScopeStatement)) {
    blockerKeys.push("contracts.lng_economics.blocker.cost_scope_statement");
  }
  if (!hasText(draft.purchasePaymentDate)) {
    blockerKeys.push("contracts.lng_economics.blocker.purchase_payment_date");
  }
  if (!hasText(draft.salePaymentDate)) {
    blockerKeys.push("contracts.lng_economics.blocker.sale_payment_date");
  }

  if (draft.energyStages.length === 0) {
    blockerKeys.push("contracts.lng_economics.blocker.energy_stages_required");
  } else {
    for (const stage of draft.energyStages) blockerKeys.push(...stageBlockers(stage));
  }

  if (draft.discountFactors.length === 0) {
    blockerKeys.push("contracts.lng_economics.blocker.discount_factors_required");
  } else {
    for (const discount of draft.discountFactors) blockerKeys.push(...discountBlockers(discount));
  }

  // Downstream costs are optional as a collection (a zero-cost cargo is a valid explicit claim).
  // Any cost row the caller added must be complete; the engine decides its category and basis.
  for (const cost of draft.downstreamCosts) blockerKeys.push(...costBlockers(cost));

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
 * whether the text is acceptable. No `model_version` and no `decision_context` are sent.
 */
export function lngEconomicsRequest(
  draft: LngEconomicsDraft,
): LngEconomicsOnlyRequestDTO | null {
  if (!lngEconomicsReadiness(draft).canSubmit) return null;
  return {
    contract_id: draft.contractId.trim(),
    cargo_id: draft.cargoId.trim(),
    terminal_id: draft.terminalId.trim(),
    resource_id: draft.resourceId.trim(),
    valuation_date: draft.valuationDate.trim(),
    reporting_currency: draft.reportingCurrency.trim(),
    energy_basis_reference: draft.energyBasisReference.trim(),
    energy_unit: draft.energyUnit.trim(),
    purchased_energy_mwh: draft.purchasedEnergyMwh.trim(),
    delivered_energy_mwh: draft.deliveredEnergyMwh.trim(),
    purchase_unit_price_eur_per_mwh: draft.purchaseUnitPriceEurPerMwh.trim(),
    sale_unit_price_eur_per_mwh: draft.saleUnitPriceEurPerMwh.trim(),
    purchase_price_source_reference: draft.purchasePriceSourceReference.trim(),
    sale_price_source_reference: draft.salePriceSourceReference.trim(),
    purchase_basis: draft.purchaseBasis.trim(),
    purchase_included_cost_items: lngEconomicsReferences(draft.purchaseIncludedCostItems),
    cost_scope_statement: draft.costScopeStatement.trim(),
    purchase_payment_date: draft.purchasePaymentDate.trim(),
    sale_payment_date: draft.salePaymentDate.trim(),
    downstream_costs: draft.downstreamCosts.map(
      (cost): LngEconomicsOnlyDownstreamCostDTO => ({
        cost_id: cost.costId.trim(),
        category: cost.category.trim(),
        amount_eur: cost.amountEur.trim(),
        payment_date: cost.paymentDate.trim(),
        source_reference: cost.sourceReference.trim(),
        charge_basis: cost.chargeBasis.trim(),
      }),
    ),
    energy_stages: draft.energyStages.map(
      (stage): LngEconomicsOnlyEnergyStageDTO => ({
        stage_id: stage.stageId.trim(),
        kind: stage.kind.trim(),
        input_energy_mwh: stage.inputEnergyMwh.trim(),
        output_energy_mwh: stage.outputEnergyMwh.trim(),
        consumed_energy_mwh: stage.consumedEnergyMwh.trim(),
        physical_loss_energy_mwh: stage.physicalLossEnergyMwh.trim(),
        source_references: lngEconomicsReferences(stage.sourceReferences),
      }),
    ),
    discount_factors: draft.discountFactors.map(
      (discount): LngEconomicsOnlyDiscountFactorDTO => ({
        payment_date: discount.paymentDate.trim(),
        factor: discount.factor.trim(),
        curve_reference: discount.curveReference.trim(),
        source_reference: discount.sourceReference.trim(),
        as_of: discount.asOf.trim(),
      }),
    ),
  };
}

/** One field-level violation the backend returned. */
export interface LngEconomicsViolation {
  readonly code: string;
  readonly detail: string;
}

/** A typed backend refusal, read from the route's structured error detail. */
export interface LngEconomicsRefusal {
  readonly status: number;
  readonly code: string;
  readonly message: string;
  readonly violations: readonly LngEconomicsViolation[];
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
export function lngEconomicsRefusal(error: unknown): LngEconomicsRefusal | null {
  if (!isRecord(error)) return null;
  const status = error.status;
  if (typeof status !== "number") return null;
  const rawDetail = error.detail;
  // FastAPI's own request-validation refusal is an array of {loc, msg, type}; the route's refusal
  // is a stable {code, message, codes, violations} object. Both are field evidence.
  if (Array.isArray(rawDetail)) {
    const violations: LngEconomicsViolation[] = [];
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
  const violations: LngEconomicsViolation[] = [];
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

export interface LngEconomicsState {
  readonly draft: LngEconomicsDraft;
  readonly busy: boolean;
  readonly result: LngEconomicsOnlyResultDTO | null;
  readonly meta: LngEconomicsOnlyMetaDTO | null;
  readonly refusal: LngEconomicsRefusal | null;
  readonly error: unknown;
}

export type LngEconomicsAction =
  | { type: "draft_changed"; draft: LngEconomicsDraft }
  | { type: "context_changed" }
  | { type: "run_started" }
  | {
      type: "run_succeeded";
      result: LngEconomicsOnlyResultDTO;
      meta: LngEconomicsOnlyMetaDTO;
    }
  | { type: "run_failed"; refusal: LngEconomicsRefusal | null; error: unknown };

export function initialLngEconomicsState(
  draft: LngEconomicsDraft = emptyLngEconomicsDraft(),
): LngEconomicsState {
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
 * A draft change, a context change, a new run, a backend refusal and a transport failure all clear
 * the previous result. That is what keeps a figure from surviving a change it no longer describes:
 * the panel never keeps a second copy of the answer, and it never discards the draft.
 */
export function lngEconomicsReducer(
  state: LngEconomicsState,
  action: LngEconomicsAction,
): LngEconomicsState {
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
    case "context_changed":
      return {
        ...state,
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

export interface LngEconomicsRunTicket {
  readonly sequence: number;
  readonly signal: AbortSignal;
}

/**
 * Transport guard for one form.
 *
 * `begin` is synchronous, so a second submit in the same tick is refused before React can render
 * the busy state. Edits and context changes call `invalidate`, which increments the sequence and
 * aborts the in-flight request; a late response then fails `isCurrent` and is discarded.
 */
export interface LngEconomicsRunGate {
  begin(): LngEconomicsRunTicket | null;
  isCurrent(sequence: number): boolean;
  isInFlight(): boolean;
  finish(sequence: number): void;
  invalidate(): void;
}

export function createLngEconomicsRunGate(): LngEconomicsRunGate {
  let sequence = 0;
  let controller: AbortController | null = null;
  let inFlight = false;
  return {
    begin() {
      if (inFlight) return null;
      inFlight = true;
      sequence += 1;
      controller = new AbortController();
      return { sequence, signal: controller.signal };
    },
    isCurrent(candidate: number) {
      return candidate === sequence;
    },
    isInFlight() {
      return inFlight;
    },
    finish(candidate: number) {
      if (candidate !== sequence) return;
      inFlight = false;
      controller = null;
    },
    invalidate() {
      sequence += 1;
      controller?.abort();
      controller = null;
      inFlight = false;
    },
  };
}

/** Ctrl+Enter is the documented submit chord, and only inside the panel's own key handler. */
export function lngEconomicsSubmitShortcut(
  event: Pick<KeyboardEvent, "key" | "ctrlKey" | "altKey" | "shiftKey" | "metaKey">,
  state: { readonly canSubmit: boolean; readonly busy: boolean },
): boolean {
  return (
    event.key === "Enter" &&
    event.ctrlKey &&
    !event.altKey &&
    !event.shiftKey &&
    !event.metaKey &&
    state.canSubmit &&
    !state.busy
  );
}
