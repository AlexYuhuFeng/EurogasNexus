/**
 * Strategy backtest run model (Architecture V2 Wave 9, action geography).
 *
 * Running a backtest is a `compute` consequence, so the action geography puts it in the
 * workspace's single primary slot rather than inside the panel that configures it. That was
 * not possible while the rule deciding it lived in the panel: the blockers, the period and the
 * economic assumptions were all panel-local state, so a header could only have guessed at when
 * a run is allowed and what it would send.
 *
 * This module is that rule, kept pure and browser-free so it can be asserted directly. It
 * returns translation keys rather than copy - the panel renders them - and it composes the
 * request from the draft the workspace owns, so the action and the panel cannot disagree about
 * what will be run.
 */

/** The economic assumptions a backtest request carries, as the surface offers them. */
export const MISSING_DATA_POLICIES = ["FAIL", "SKIP_DECISION", "CARRY_FORWARD_WITH_MAX_AGE"] as const;
export const TRANSACTION_COST_TREATMENTS = ["UNAVAILABLE", "MODELED_COST", "EXCLUDED"] as const;

/**
 * Which declared price-name keys each component type requires evidence for.
 *
 * Mirrors the backend evidence contract; the surface uses it only to *disclose*
 * a missing declaration. The server remains the authority: a stale client that
 * says READY still receives the structured ``target_delivery_not_declared``
 * refusal.
 */
const COMPONENT_EVIDENCE_NAME_KEYS: Record<string, readonly string[]> = {
  OCM_VS_DAY_AHEAD: ["day_ahead_price_names", "intraday_price_names"],
};

/**
 * Whether a frozen definition declares a target for every required price name.
 *
 * A light, read-only projection of the backend rule so the preflight can show
 * "declare a target" instead of READY. It never authorizes a run by itself.
 */
export function strategyEvidenceDeclarationComplete(
  definition: Record<string, unknown> | undefined | null,
): boolean {
  if (!definition) return false;
  const components = Array.isArray(definition.components) ? definition.components : [];
  if (components.length === 0) return false;
  return components.every((entry) => {
    if (!entry || typeof entry !== "object") return false;
    const component = entry as Record<string, unknown>;
    const keys = COMPONENT_EVIDENCE_NAME_KEYS[String(component.component_type ?? "")];
    if (!keys) return false;
    const extension = (component.extension_json as Record<string, unknown>) ?? {};
    const required = keys.flatMap((key) =>
      Array.isArray(extension[key]) ? (extension[key] as unknown[]).map((item) => String(item)) : [],
    );
    if (required.length === 0) return false;
    const targets = Array.isArray(component.evidence_targets)
      ? (component.evidence_targets as Record<string, unknown>[])
      : [];
    const declared = new Set(
      targets.flatMap((target) =>
        Array.isArray(target.price_names)
          ? (target.price_names as unknown[]).map((name) => String(name).toUpperCase())
          : [],
      ),
    );
    return required.every((name) => declared.has(name.toUpperCase()));
  });
}

export type MissingDataPolicy = (typeof MISSING_DATA_POLICIES)[number];
export type TransactionCostTreatment = (typeof TRANSACTION_COST_TREATMENTS)[number];

/** The configuration the surface owns while the user assembles a run. */
export interface StrategyBacktestDraft {
  /** Evaluation period start, as the date input's `YYYY-MM-DD` value. */
  readonly start: string;
  /** Evaluation period end, as the date input's `YYYY-MM-DD` value. */
  readonly end: string;
  readonly missingDataPolicy: MissingDataPolicy;
  readonly transactionCostTreatment: TransactionCostTreatment;
  /** The modeled cost as typed; only read when the treatment is `MODELED_COST`. */
  readonly transactionCost: string;
}

export interface StrategyBacktestReadiness {
  /** Whether the run may be started as the draft stands. */
  readonly canRun: boolean;
  /** Every unsettled precondition, in a stable order, as translation keys. */
  readonly blockerKeys: readonly string[];
  /** The first blocker, for a control that can only show one explanation. */
  readonly firstBlockerKey: string | null;
}

/**
 * Whether a backtest may be run, and what has to be true first.
 *
 * A backtest evaluates a *frozen* strategy version: the platform refuses an unfrozen one, and a
 * surface that offered the run anyway would be offering a refusal. The period must be a real
 * interval - an end that is not after the start is not a period - and a modeled transaction
 * cost must be a number, because a modeled cost that is silently zero would change the result
 * rather than the request.
 */
export function strategyBacktestReadiness(input: {
  readonly draft: StrategyBacktestDraft;
  /** The selected version is frozen, i.e. its numbers can no longer move under the run. */
  readonly frozen: boolean;
  /**
   * The frozen definition declares a complete per-leg evidence target mapping.
   * An undeclared version is refused by the server, so the preflight must not
   * show READY while the obvious declaration is missing. Defaults to `true` so
   * callers that do not project the definition keep their previous behaviour and
   * still rely on the server's refusal.
   */
  readonly evidenceDeclared?: boolean;
  /** A run (or the reads that feed the surface) is already in flight. */
  readonly running: boolean;
}): StrategyBacktestReadiness {
  const blockerKeys: string[] = [];
  if (!input.frozen) blockerKeys.push("strategy_lab.blocker.frozen_required");
  if (input.evidenceDeclared === false) {
    blockerKeys.push("strategy_lab.blocker.evidence_target_missing");
  }
  const { start, end, transactionCostTreatment, transactionCost } = input.draft;
  if (!start || !end || start >= end) blockerKeys.push("strategy_lab.blocker.period");
  if (transactionCostTreatment === "MODELED_COST" && Number.isNaN(Number(transactionCost))) {
    blockerKeys.push("strategy_lab.blocker.transaction_cost");
  }
  if (input.running) blockerKeys.push("strategy_lab.blocker.in_flight");
  return {
    canRun: blockerKeys.length === 0,
    blockerKeys,
    firstBlockerKey: blockerKeys.length > 0 ? blockerKeys[0] : null,
  };
}

/**
 * The backtest request for a draft, or null when there is no version to run.
 *
 * The period is sent as an instant range rather than as the raw date strings, so the run's
 * window is unambiguous; the assumptions are sent exactly as configured, including a modeled
 * cost that is only read when its treatment says so.
 */
export function strategyBacktestRequest(
  draft: StrategyBacktestDraft,
  strategyVersionId: string | null | undefined,
): Record<string, unknown> | null {
  if (!strategyVersionId) return null;
  return {
    strategy_version_id: strategyVersionId,
    evaluation_period_start_utc: `${draft.start}T00:00:00Z`,
    evaluation_period_end_utc: `${draft.end}T00:00:00Z`,
    economic_assumptions: {
      missing_data_policy: draft.missingDataPolicy,
      fill_price_policy: "NEXT_ELIGIBLE",
      cost_components: [
        {
          code: "TRANSACTION_COST",
          treatment: draft.transactionCostTreatment,
          amount_gbp_mwh:
            draft.transactionCostTreatment === "MODELED_COST" ? Number(draft.transactionCost) : null,
        },
      ],
    },
  };
}
