/**
 * Backtest experiments (Architecture V2, Wave 9 surface completion).
 *
 * `POST /api/strategy-runs` has accepted an `experiment_id` since the strategy registry shipped,
 * and `BacktestRunDefinition` has recorded it for as long as that, but no surface ever created an
 * experiment: the three experiment reads and the create call were declared in the client and never
 * called, so a run could only be grouped by a caller using the API directly. This module is the
 * rule the Backtest task gates its create action on and composes its request with.
 *
 * It mirrors the route rather than inventing a policy, because a surface that offered an
 * experiment the route refuses would be offering an action that can only fail. The route requires:
 *
 * - the strategy to exist (`404` otherwise), which is the one selected in the navigator;
 * - the base version to be **FROZEN** (`409` otherwise) - an experiment is grouped around an
 *   immutable version, so a draft cannot be its base;
 * - a period the deterministic engine accepts, i.e. an end after its start (`422` otherwise).
 *
 * Nothing here is authority: the route re-authorises the caller and re-checks every one of these
 * facts. This is the preflight a user reads before pressing the button.
 */

import type { BacktestExperimentCreateInputDTO, BacktestExperimentDTO } from "@/api/client";
import type { StrategyVersionDTO } from "@/api/client";

/** Route bounds for the experiment name (`BacktestExperimentCreateRequest`). */
export const EXPERIMENT_NAME_MAX_LENGTH = 256;
/** Route bound for the experiment hypothesis. */
export const EXPERIMENT_HYPOTHESIS_MAX_LENGTH = 4000;
/**
 * The longest period the engine accepts (`BacktestPeriod` refuses more than 3660 days), mirrored
 * so the surface refuses it too instead of translating the refusal afterwards.
 */
export const EXPERIMENT_MAX_PERIOD_DAYS = 3660;

/** The period an experiment is evaluated over, as UTC instants. */
export interface ExperimentPeriod {
  readonly start: string;
  readonly end: string;
}

export interface ExperimentDraft {
  readonly name: string;
  readonly hypothesis: string;
  readonly period: ExperimentPeriod;
}

/** Which object the create action applies to: the selected strategy and version. */
export interface ExperimentSubject {
  readonly strategyId: string | null;
  readonly version: Pick<StrategyVersionDTO, "strategy_version_id" | "status"> | null;
}

export interface ExperimentReadiness {
  readonly canCreate: boolean;
  /** Every unsettled precondition, in a stable order, as translation keys. */
  readonly blockerKeys: readonly string[];
  readonly firstBlockerKey: string | null;
}

/**
 * Whether an experiment may be created as things stand.
 *
 * The order is the order a user fixes them in: choose a strategy, then a frozen version (an
 * experiment's base is immutable, so a draft is refused), then name it, then give it a period the
 * engine accepts. An empty period is reported once, not twice, because "no period" is one thing
 * to fix.
 */
export function experimentReadiness(input: {
  readonly subject: ExperimentSubject;
  readonly draft: ExperimentDraft;
}): ExperimentReadiness {
  const blockerKeys: string[] = [];
  const { strategyId, version } = input.subject;
  if (!strategyId) {
    blockerKeys.push("strategy_lab.experiment.blocker.no_strategy");
  } else if (!version) {
    blockerKeys.push("strategy_lab.experiment.blocker.no_version");
  } else if (version.status !== "FROZEN") {
    // The route answers 409 with a stable code rather than grouping a draft, so the surface says
    // so before the click instead of translating a refusal afterwards.
    blockerKeys.push("strategy_lab.experiment.blocker.version_not_frozen");
  }
  const name = input.draft.name.trim();
  if (!name) {
    blockerKeys.push("strategy_lab.experiment.blocker.name_required");
  } else if (name.length > EXPERIMENT_NAME_MAX_LENGTH) {
    blockerKeys.push("strategy_lab.experiment.blocker.name_too_long");
  }
  if (input.draft.hypothesis.length > EXPERIMENT_HYPOTHESIS_MAX_LENGTH) {
    blockerKeys.push("strategy_lab.experiment.blocker.hypothesis_too_long");
  }
  const { start, end } = input.draft.period;
  if (!start || !end) {
    blockerKeys.push("strategy_lab.experiment.blocker.period_required");
  } else {
    const startMs = new Date(startOfDayUtc(start)).getTime();
    const endMs = new Date(endOfDayUtc(end)).getTime();
    if (!(endMs > startMs)) {
      blockerKeys.push("strategy_lab.experiment.blocker.period_order");
    } else if (endMs - startMs > EXPERIMENT_MAX_PERIOD_DAYS * 86_400_000) {
      blockerKeys.push("strategy_lab.experiment.blocker.period_too_long");
    }
  }
  return {
    canCreate: blockerKeys.length === 0,
    blockerKeys,
    firstBlockerKey: blockerKeys.length > 0 ? blockerKeys[0] : null,
  };
}

/**
 * The request body for the experiment as it stands, or `null` when it is not ready.
 *
 * Returning `null` rather than a partial body is deliberate: a caller that composed a body from
 * an unready draft would be inventing the missing facts (an empty strategy id, a period the
 * engine rejects), and the route would answer with a refusal the surface could have prevented.
 */
export function experimentRequest(
  input: { readonly subject: ExperimentSubject; readonly draft: ExperimentDraft },
  readiness: ExperimentReadiness = experimentReadiness(input),
): BacktestExperimentCreateInputDTO | null {
  if (!readiness.canCreate || !input.subject.strategyId || !input.subject.version) return null;
  return {
    strategy_id: input.subject.strategyId,
    base_strategy_version_id: input.subject.version.strategy_version_id,
    name: input.draft.name.trim(),
    hypothesis: input.draft.hypothesis.trim(),
    // The engine's period is half-open over UTC instants; the surface collects dates, so the
    // instants are composed here instead of at the call site.
    evaluation_period_start_utc: startOfDayUtc(input.draft.period.start),
    evaluation_period_end_utc: endOfDayUtc(input.draft.period.end),
  };
}

/** Midnight UTC of a `YYYY-MM-DD` date, echoed unchanged when it already carries a time. */
export function startOfDayUtc(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return "";
  return trimmed.includes("T") ? trimmed : `${trimmed}T00:00:00Z`;
}

/** The last second of a `YYYY-MM-DD` date, so a single-day period is not empty. */
export function endOfDayUtc(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return "";
  return trimmed.includes("T") ? trimmed : `${trimmed}T23:59:59Z`;
}

/** Experiments belonging to one strategy, newest first (the route lists newest first already). */
export function experimentsForStrategy(
  experiments: readonly BacktestExperimentDTO[],
  strategyId: string | null,
): BacktestExperimentDTO[] {
  if (!strategyId) return [];
  return experiments.filter((experiment) => experiment.strategy_id === strategyId);
}

/**
 * The runs an experiment groups.
 *
 * An experiment names its runs by id, so the match is on the id and not on a time window: a run
 * that was grouped into the experiment is in it, and one that merely happened during the period is
 * not. A run the workspace has not read still counts towards the group, which is why the count
 * comes from the experiment's own `run_ids`.
 */
export function runsInExperiment<T extends { readonly run_id: string }>(
  runs: readonly T[],
  experiment: BacktestExperimentDTO | null,
): T[] {
  if (!experiment) return [];
  const ids = new Set(experiment.run_ids);
  return runs.filter((run) => ids.has(run.run_id));
}

/**
 * Experiment ids a run history knows nothing about.
 *
 * The run list is bounded (50 per read), so an experiment whose runs are older than that window
 * names runs the surface has not loaded. They are reported as a count rather than silently
 * dropped, because "3 runs, 2 shown" is a different statement than "the group holds 2".
 */
export function unloadedRunIds(
  experiment: BacktestExperimentDTO | null,
  runs: readonly { readonly run_id: string }[],
): string[] {
  if (!experiment) return [];
  const known = new Set(runs.map((run) => run.run_id));
  return experiment.run_ids.filter((runId) => !known.has(runId));
}

/** The period an experiment was created over, formatted from its own payload. */
export function experimentPeriod(experiment: BacktestExperimentDTO): ExperimentPeriod {
  const period = experiment.evaluation_period ?? {};
  const start = typeof period.start_utc === "string" ? period.start_utc : "";
  const end = typeof period.end_utc === "string" ? period.end_utc : "";
  return { start, end };
}
