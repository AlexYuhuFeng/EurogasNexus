/**
 * Scenario panel input provenance (Decision workspace).
 *
 * The Scenario panel used to offer eight editable contract-draft numbers and claim "the
 * economics you edit here are the ones it sends". Tracing the two request builders shows
 * that claim was false for seven of the eight:
 *
 * - `buildRouteRecommendationRequest` (the Scenario task's primary action, "Compare
 *   Options") composes its candidates from the persisted resource-pool read
 *   (`api.resourcePoolOptions`) and the first saved upstream contract's gas year. It takes
 *   no draft parameter at all.
 * - `buildResourcePoolOptimizationRequest` (the Optimize task's primary action) sends the
 *   same persisted resources and sale options, plus one financing rate: the first saved
 *   upstream contract's annual rate when it carries one, otherwise the draft's
 *   `annual_financing_rate_pct`.
 *
 * So exactly one draft field is genuinely consumable from this panel - the annual financing
 * rate fallback - and this module owns that fact so the panel's copy and the request cannot
 * disagree about it. `nbp_sale_price_gbp_mwh` and `physical_exit_sale_price_gbp_mwh` have
 * no consumer anywhere and are not even part of the persisted contract payload; they stay
 * declared on `ContractDraft` for import back-compatibility but are not editable controls.
 */

import type { ContractDraft } from "./contractDraftModel";

/** The saved-contract fields the pool optimiser's financing rate may come from. */
export interface FinancingRateSource {
  annual_financing_rate_pct?: number | null;
}

/** Where the rate the pool optimiser will send comes from. */
export type FinancingRateProvenance = "saved_upstream_contract" | "draft_fallback";

export interface ResolvedFinancingRate {
  /** The rate in percent per year, exactly as the optimiser request carries it. */
  readonly pct: number;
  readonly source: FinancingRateProvenance;
}

/**
 * The draft fields the Scenario panel may offer as editable.
 *
 * One entry, and the request-composition test proves it is the only draft field whose value
 * reaches either action: mutating any other draft number leaves both requests unchanged.
 * The panel renders from this list, so a field that stops being consumed fails the test
 * before it can stay editable.
 */
export const SCENARIO_EDITABLE_DRAFT_INPUTS: ReadonlyArray<{
  readonly key: "annual_financing_rate_pct";
  readonly labelKey: string;
}> = [{ key: "annual_financing_rate_pct", labelKey: "economics.finance_rate" }];

/**
 * Resolve the annual financing rate the pool-optimisation request will carry.
 *
 * The precedence is the request builder's own (`upstreamContracts[0]?.rate ?? draft`, a
 * nullish fallback): a saved upstream contract that carries a rate governs the run, and the
 * draft value applies only when no saved rate exists. No unit conversion happens here; the
 * backend reads the value as percent per year for its early-cash term
 * (`base_cost * rate / 100 * lag_days / 365`).
 */
export function resolvePoolFinancingRate(
  draft: Pick<ContractDraft, "annual_financing_rate_pct">,
  upstreamContracts: ReadonlyArray<FinancingRateSource>,
): ResolvedFinancingRate {
  const saved = upstreamContracts[0]?.annual_financing_rate_pct;
  if (saved === null || saved === undefined) {
    return { pct: draft.annual_financing_rate_pct, source: "draft_fallback" };
  }
  return { pct: saved, source: "saved_upstream_contract" };
}
