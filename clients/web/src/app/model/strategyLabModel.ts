import type { StrategyRunDTO } from "@/api/client";

export type StrategyTaskId = "design" | "backtest" | "compare" | "shadow";

export const STRATEGY_TASKS: StrategyTaskId[] = [
  "design",
  "backtest",
  "compare",
  "shadow",
];

export const MAX_COMPARE_RUNS = 5;

export function strategyTaskFromLocation(search: string): StrategyTaskId {
  const value = new URLSearchParams(search).get("task");
  return STRATEGY_TASKS.includes(value as StrategyTaskId)
    ? (value as StrategyTaskId)
    : "design";
}

export function strategyTaskToSearch(
  currentSearch: string,
  task: StrategyTaskId,
): string {
  const next = new URLSearchParams(currentSearch);
  next.set("workspace", "strategy");
  next.set("task", task);
  return next.toString();
}

export type RunCompatibility =
  | "COMPARABLE"
  | "COMPARABLE_WITH_CAVEATS"
  | "NOT_MEANINGFULLY_COMPARABLE";

export function classifyRunCompatibility(
  runs: StrategyRunDTO[],
): RunCompatibility {
  if (runs.length < 2) return "COMPARABLE";
  const strategyIds = new Set(runs.map((run) => run.strategy_id));
  if (strategyIds.size > 1) return "NOT_MEANINGFULLY_COMPARABLE";
  const engines = new Set(runs.map((run) => run.backtest_engine_version));
  const periods = new Set(
    runs.map(
      (run) => `${run.evaluation_start_utc ?? ""}→${run.evaluation_end_utc ?? ""}`,
    ),
  );
  const quality = new Set(
    runs.map((run) => run.backtest_metrics?.temporal_integrity),
  );
  if (engines.size > 1 || periods.size > 1 || quality.size > 1) {
    return "COMPARABLE_WITH_CAVEATS";
  }
  return "COMPARABLE";
}
