/**
 * Strategy draft model (Architecture V2 Wave 9, action geography).
 *
 * Saving a strategy draft is a `persist` consequence, so it belongs in the Design task's primary
 * slot rather than in the panel that edits the form. That was impossible while the *draft itself*
 * lived in the panel - about twenty-five form fields, their validation and the request builder -
 * so the draft moved here (state and rule) and the workspace that hosts the action owns it.
 *
 * The rule returns **translation keys**, not copy, so the panel renders the verdict it was handed
 * and cannot disagree with the header about whether the draft may be written.
 *
 * The other two acts on this surface are deliberately *not* here: freezing a version and creating
 * a new one are `lifecycle` consequences, which the geography keeps as bounded actions next to the
 * version they change (`requiresDeliberateStep("lifecycle")` is true), never in the primary slot.
 */

import type { StrategyVersionCreateInputDTO, StrategyVersionDTO } from "../../api/client.ts";

export interface StrategyDesignFormState {
  name: string;
  description: string;
  hypothesis: string;
  hubs: string;
  dayAheadNames: string;
  intradayNames: string;
  weight: string;
  positiveThreshold: string;
  negativeThreshold: string;
  windowStart: string;
  windowEnd: string;
  barMinutes: string;
  maxOcm: string;
  minDayAhead: string;
  requireTsoAccess: boolean;
  fillPricePolicy: string;
  missingDataPolicy: string;
  transactionCostTreatment: string;
  transactionCost: string;
  slippageTreatment: string;
  slippage: string;
  resourceId: string;
  resourceName: string;
  resourceQuantity: string;
  resourceCost: string;
}

export const DEFAULT_STRATEGY_FORM: StrategyDesignFormState = {
  name: "",
  description: "",
  hypothesis: "",
  hubs: "NBP",
  dayAheadNames: "SAP",
  intradayNames: "ICE_OCM",
  weight: "1.0",
  positiveThreshold: "0.0",
  negativeThreshold: "0.0",
  windowStart: "05:00",
  windowEnd: "05:30",
  barMinutes: "5",
  maxOcm: "80.0",
  minDayAhead: "10.0",
  requireTsoAccess: false,
  fillPricePolicy: "NEXT_ELIGIBLE",
  missingDataPolicy: "FAIL",
  transactionCostTreatment: "UNAVAILABLE",
  transactionCost: "",
  slippageTreatment: "UNAVAILABLE",
  slippage: "",
  resourceId: "res-1",
  resourceName: "Resource 1",
  resourceQuantity: "100",
  resourceCost: "20",
};

/** Read a stored version's definition back into the form, defaulting anything it omits. */
export function strategyFormFromVersion(
  definition: Record<string, unknown> | undefined,
): StrategyDesignFormState {
  if (!definition) return DEFAULT_STRATEGY_FORM;
  const component = Array.isArray(definition.components)
    ? (definition.components[0] as Record<string, unknown>)
    : null;
  const extension = (component?.extension_json as Record<string, unknown>) ?? {};
  const risk = (definition.risk_controls as Record<string, unknown>) ?? {};
  const resources = Array.isArray(definition.resource_contexts)
    ? (definition.resource_contexts[0] as Record<string, unknown>)
    : null;
  return {
    ...DEFAULT_STRATEGY_FORM,
    name: String(definition.strategy_name ?? ""),
    hypothesis: String(definition.hypothesis ?? ""),
    hubs: Array.isArray(component?.hubs) ? (component?.hubs as string[]).join(", ") : "NBP",
    dayAheadNames: Array.isArray(extension.day_ahead_price_names)
      ? (extension.day_ahead_price_names as string[]).join(", ")
      : "SAP",
    intradayNames: Array.isArray(extension.intraday_price_names)
      ? (extension.intraday_price_names as string[]).join(", ")
      : "ICE_OCM",
    weight: String(extension.weight ?? 1.0),
    positiveThreshold: String(extension.positive_spread_threshold_gbp_mwh ?? 0.0),
    negativeThreshold: String(extension.negative_spread_threshold_gbp_mwh ?? 0.0),
    windowStart: String(extension.time_window_start ?? "05:00"),
    windowEnd: String(extension.time_window_end ?? "05:30"),
    barMinutes: String(extension.target_bar_minutes ?? 5),
    maxOcm: String(risk.max_ocm_allocation_pct ?? 80.0),
    minDayAhead: String(risk.min_day_ahead_allocation_pct ?? 10.0),
    requireTsoAccess: Boolean(risk.require_tso_access),
    resourceId: String(resources?.resource_id ?? "res-1"),
    resourceName: String(resources?.resource_name ?? "Resource 1"),
    resourceQuantity: String(resources?.available_quantity_mwh_per_day ?? "100"),
    resourceCost: String(resources?.all_in_cost_gbp_mwh ?? "20"),
  };
}

export function strategyCsv(value: string): string[] {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function numberValue(value: string): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export interface StrategyDraftValidation {
  readonly blockerKeys: readonly string[];
  readonly warningKeys: readonly string[];
}

/**
 * What stops this draft being written, as translation keys.
 *
 * The thresholds are the surface's own contract: a strategy without a name, without either price
 * series, or without a usable resource cannot be evaluated, and a modeled cost that does not parse
 * would change the backtest rather than the request.
 */
export function strategyDraftValidation(form: StrategyDesignFormState): StrategyDraftValidation {
  const blockerKeys: string[] = [];
  const warningKeys: string[] = [];
  if (!form.name.trim()) blockerKeys.push("strategy_lab.blocker.name");
  if (strategyCsv(form.dayAheadNames).length === 0) {
    blockerKeys.push("strategy_lab.blocker.day_ahead");
  }
  if (strategyCsv(form.intradayNames).length === 0) {
    blockerKeys.push("strategy_lab.blocker.intraday");
  }
  const quantity = numberValue(form.resourceQuantity);
  const cost = numberValue(form.resourceCost);
  if (quantity === null || quantity <= 0 || cost === null || cost <= 0) {
    blockerKeys.push("strategy_lab.blocker.resource");
  }
  if (form.transactionCostTreatment === "MODELED_COST" && numberValue(form.transactionCost) === null) {
    blockerKeys.push("strategy_lab.blocker.transaction_cost");
  }
  if (form.transactionCostTreatment === "UNAVAILABLE") {
    warningKeys.push("strategy_lab.warning.transaction_cost_unavailable");
  }
  if (form.missingDataPolicy === "CARRY_FORWARD_WITH_MAX_AGE") {
    warningKeys.push("strategy_lab.warning.carry_forward");
  }
  return { blockerKeys, warningKeys };
}

export interface StrategyDraftReadiness {
  readonly canSave: boolean;
  readonly blockerKeys: readonly string[];
  readonly firstBlockerKey: string | null;
}

/**
 * Whether the draft may be written, and what stops it.
 *
 * A frozen version is not editable through this act at all - its numbers can no longer move - so a
 * frozen draft is not "blocked", it is *not this act*: the surface offers forking a new version
 * instead, which the geography keeps out of the primary slot.
 */
export function strategyDraftReadiness(input: {
  readonly validation: StrategyDraftValidation;
  readonly busy: boolean;
  readonly frozen: boolean;
}): StrategyDraftReadiness {
  const blockerKeys = [...input.validation.blockerKeys];
  if (input.frozen) blockerKeys.push("strategy_lab.blocker.frozen_edit");
  if (input.busy) blockerKeys.push("strategy_lab.blocker.in_flight");
  return {
    canSave: blockerKeys.length === 0,
    blockerKeys,
    firstBlockerKey: blockerKeys.length > 0 ? blockerKeys[0] : null,
  };
}

/**
 * The request body a draft describes.
 *
 * The body is built here because the action that sends it lives in the workspace: a panel that
 * built its own request could send something the header never approved.
 */
export function strategyDraftBody(form: StrategyDesignFormState): StrategyVersionCreateInputDTO {
  return {
    hypothesis: form.hypothesis,
    definition: {
      components: [
        {
          component_id: "ocm-da-1",
          component_type: "OCM_VS_DAY_AHEAD",
          hubs: strategyCsv(form.hubs),
          tenors: ["within-day", "day-ahead"],
          extension_json: {
            weight: numberValue(form.weight) ?? 1.0,
            day_ahead_price_names: strategyCsv(form.dayAheadNames),
            intraday_price_names: strategyCsv(form.intradayNames),
            positive_spread_threshold_gbp_mwh: numberValue(form.positiveThreshold) ?? 0,
            negative_spread_threshold_gbp_mwh: numberValue(form.negativeThreshold) ?? 0,
            time_window_start: form.windowStart || null,
            time_window_end: form.windowEnd || null,
            target_bar_minutes: numberValue(form.barMinutes) ?? 5,
          },
        },
      ],
      parameter_definitions: [],
      parameter_values: {},
      risk_controls: {
        max_ocm_allocation_pct: numberValue(form.maxOcm) ?? 80,
        min_day_ahead_allocation_pct: numberValue(form.minDayAhead) ?? 10,
        require_tso_access: form.requireTsoAccess,
      },
      economic_assumptions: {
        fill_price_policy: form.fillPricePolicy,
        missing_data_policy: form.missingDataPolicy,
        cost_components: [
          {
            code: "TRANSACTION_COST",
            treatment: form.transactionCostTreatment,
            amount_gbp_mwh:
              form.transactionCostTreatment === "MODELED_COST"
                ? numberValue(form.transactionCost)
                : null,
          },
          {
            code: "SLIPPAGE",
            treatment: form.slippageTreatment,
            amount_gbp_mwh:
              form.slippageTreatment === "MODELED_COST" ? numberValue(form.slippage) : null,
          },
        ],
      },
      data_requirements: { hubs: strategyCsv(form.hubs) },
      evaluation_windows: [],
    },
    strategy_name: form.name,
    run_mode: "BACKTEST",
    resource_contexts: [
      {
        resource_id: form.resourceId,
        resource_name: form.resourceName,
        available_quantity_mwh_per_day: numberValue(form.resourceQuantity) ?? 100,
        all_in_cost_gbp_mwh: numberValue(form.resourceCost) ?? 20,
        required_tso_access: [],
      },
    ],
    price_observations: [],
    existing_shadow_pnl_gbp: 0,
  };
}

/** The name a first save uses when the operator has not typed one. */
export function strategyDraftName(form: StrategyDesignFormState): string {
  return form.name.trim() || "Untitled strategy";
}

/** Whether the selected version may be edited in place. */
export function strategyVersionEditable(version: StrategyVersionDTO | null): boolean {
  return version?.status === "DRAFT";
}

/** Whether the selected version is frozen, i.e. its numbers can no longer move. */
export function strategyVersionFrozen(version: StrategyVersionDTO | null): boolean {
  return version?.status === "FROZEN";
}
