/**
 * Which kind of shadow run "Track this strategy" starts for a StrategySpec.
 *
 * A history with a rule is tracked daily with that rule, whatever its tenors: the user has
 * just backtested that rule on daily closes, and the forward run must be the same strategy.
 * Before, any spec whose legs were all prompt products (WD, DA, WE, BOM) was tracked intraday
 * with a fixed 30-minute rule instead, so a backtested TTF DA - NBP DA z-score could not be
 * tracked at all (the intraday engine refuses legs in two currencies) and a TTF WD - DA one
 * silently became a different strategy.
 */
import type { StrategySpecDTO } from "../../api/spreads.ts";

const PROMPT = new Set(["WD", "DA", "WE", "BOM"]);

export type TrackMode = "intraday" | "daily";

export function trackModeOf(spec: StrategySpecDTO | null): TrackMode | null {
  if (!spec || spec.legs.length < 2) return null;
  if (spec.kind === "history" && spec.rule) return "daily";
  if (spec.legs.every((leg) => PROMPT.has((leg.tenor ?? "").toUpperCase()))) return "intraday";
  return null;
}
