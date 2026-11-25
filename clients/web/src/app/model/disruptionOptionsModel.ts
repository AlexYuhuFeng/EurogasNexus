/**
 * LNG-3: the pure logic of a cargo's disruption options (`GET /api/lng/cargoes/{id}/
 * disruption-options`). The server values every option, marks the Pareto frontier and names the
 * default; this module only orders the rows, says which badge each takes, words why a dominated
 * option lost, gives each option's range over the scenarios, and says when "Choose" may be
 * pressed. Choosing records the option; nothing is booked, traded, nominated or sent.
 */
import type { DisruptionOptionDTO, DisruptionOptionsDTO, DisruptionRunDTO } from "../../api/client.ts";

export type OptionStanding = "recommended" | "frontier" | "dominated" | "infeasible";

/** The option kinds the engine names, each with an i18n key under `lng.cargo.options.kind.`. */
export const OPTION_KINDS = ["wait", "borrow", "buy", "borrow_buy", "swap", "divert", "absorb", "cover", "combined"] as const;
export type OptionKind = (typeof OPTION_KINDS)[number];

export interface OptionRow {
  option: DisruptionOptionDTO;
  standing: OptionStanding;
  kind: OptionKind | "other";
  /** Lowest and highest P&L over the scenarios (base included). */
  range: { low: number; high: number } | null;
  /** The option that beats this one, by title, and where it does, when dominated. */
  beatenBy: { title: string; where: string[] } | null;
}

const ORDER: Record<OptionStanding, number> = { recommended: 0, frontier: 1, dominated: 2, infeasible: 3 };

export function standingOf(option: DisruptionOptionDTO, recommended: string | null): OptionStanding {
  if (!option.feasible) return "infeasible";
  if (option.option_id === recommended) return "recommended";
  return option.on_frontier ? "frontier" : "dominated";
}

export function kindOf(option: Pick<DisruptionOptionDTO, "kind">): OptionKind | "other" {
  return (OPTION_KINDS as readonly string[]).includes(option.kind) ? (option.kind as OptionKind) : "other";
}

export function scenarioRange(option: Pick<DisruptionOptionDTO, "scenarios">): { low: number; high: number } | null {
  if (!option.scenarios.length) return null;
  const values = option.scenarios.map((scenario) => scenario.pnl);
  return { low: Math.min(...values), high: Math.max(...values) };
}

/**
 * The rows in reading order: the default first, then the rest of the frontier, then the
 * dominated options, then those a hard constraint rules out; within a group by score, then key.
 */
export function optionRows(data: Pick<DisruptionOptionsDTO, "options" | "recommended">): OptionRow[] {
  const titles = new Map(data.options.map((option) => [option.option_id, option.title]));
  return data.options
    .map((option) => {
      const standing = standingOf(option, data.recommended);
      const beatenBy =
        standing === "dominated" && option.dominated_by
          ? { title: titles.get(option.dominated_by) ?? option.dominated_by, where: [...option.dominated_why] }
          : null;
      return { option, standing, kind: kindOf(option), range: scenarioRange(option), beatenBy };
    })
    .sort(
      (a, b) =>
        ORDER[a.standing] - ORDER[b.standing] ||
        b.option.score - a.option.score ||
        a.option.key.localeCompare(b.option.key),
    );
}

/** Whether "Choose" may be pressed: a feasible option, a person allowed to record, no choice in flight. */
export function canChoose(option: Pick<DisruptionOptionDTO, "feasible">, canWrite: boolean, busy: boolean): boolean {
  return option.feasible && canWrite && !busy;
}

/** The i18n key of a timeline row's change, and whether the roles were told. */
export function timelineLine(run: Pick<DisruptionRunDTO, "change" | "notified">): { changeKey: string; told: boolean } {
  return { changeKey: `lng.cargo.options.change.${run.change ?? "none"}`, told: run.notified };
}

/** The i18n key that says how this cargo stands in the book's re-optimisation. */
export function statusKey(status: DisruptionOptionsDTO["status"]): string {
  return `lng.cargo.options.status.${status}`;
}
