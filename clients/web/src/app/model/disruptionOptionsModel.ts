/**
 * LNG-3 and LNG-4: the pure logic of a cargo's disruption options (`GET /api/lng/cargoes/{id}/
 * disruption-options`). The server values every option, ranks the list, flags what each option
 * breaks or moves, and names a recommended set; this module only orders the rows, says which
 * badge and flags each takes, words why a dominated option lost, splits the P&L into direct and
 * opportunity cost, lists the consequences, gives each cost line its sources, reads the FX
 * picker, and says when "Choose" may be pressed. Choosing records the option; nothing is
 * booked, traded, nominated or sent.
 */
import type {
  DisruptionDemurrageDTO,
  DisruptionFxQuery,
  DisruptionLineDTO,
  DisruptionOptionDTO,
  DisruptionOptionsDTO,
  DisruptionRecommendedDTO,
  DisruptionRunDTO,
} from "../../api/client.ts";

export type OptionStanding = "recommended" | "frontier" | "dominated" | "infeasible";

/** The option kinds the engine names, each with an i18n key under `lng.cargo.options.kind.`. */
export const OPTION_KINDS = ["wait", "borrow", "buy", "borrow_buy", "swap", "divert", "absorb", "cover", "combined", "substitute", "spot"] as const;
export type OptionKind = (typeof OPTION_KINDS)[number];

/** LNG-4 flags, each with an i18n key under `lng.cargo.options.flag.`. */
export type OptionFlag = "contract_breach" | "disrupts_normal_cargo" | "not_possible";

export interface OptionRow {
  option: DisruptionOptionDTO;
  standing: OptionStanding;
  kind: OptionKind | "other";
  /** Lowest and highest P&L over the scenarios (base included). */
  range: { low: number; high: number } | null;
  /** The option that beats this one, by title, and where it does, when dominated. */
  beatenBy: { title: string; where: string[] } | null;
  /** LNG-4: what the option breaks or moves, or that it cannot physically happen. */
  flags: OptionFlag[];
  /** LNG-4: why it is in the recommended set (empty when it is not). */
  recommended: { basis: string; reason: string }[];
}

/** Whether the option can physically happen (LNG-3 rows carry `feasible` only). */
export function isPossible(option: Pick<DisruptionOptionDTO, "feasible" | "possible">): boolean {
  return option.possible ?? option.feasible;
}

export function standingOf(
  option: DisruptionOptionDTO,
  recommended: string | null,
  set: readonly DisruptionRecommendedDTO[] = [],
): OptionStanding {
  if (!isPossible(option)) return "infeasible";
  if (option.option_id === recommended || set.some((item) => item.option_id === option.option_id)) return "recommended";
  return option.on_frontier ? "frontier" : "dominated";
}

export function kindOf(option: Pick<DisruptionOptionDTO, "kind">): OptionKind | "other" {
  return (OPTION_KINDS as readonly string[]).includes(option.kind) ? (option.kind as OptionKind) : "other";
}

export function flagsOf(option: Pick<DisruptionOptionDTO, "feasible" | "possible" | "flags" | "breaches" | "disrupts">): OptionFlag[] {
  const out: OptionFlag[] = [];
  if (!isPossible(option)) out.push("not_possible");
  if (option.flags?.contract_breach || (option.breaches?.length ?? 0) > 0) out.push("contract_breach");
  if (option.flags?.disrupts_normal_cargo || (option.disrupts?.length ?? 0) > 0) out.push("disrupts_normal_cargo");
  return out;
}

export function scenarioRange(option: Pick<DisruptionOptionDTO, "scenarios">): { low: number; high: number } | null {
  if (!option.scenarios.length) return null;
  const values = option.scenarios.map((scenario) => scenario.pnl);
  return { low: Math.min(...values), high: Math.max(...values) };
}

function recommendedFor(option: DisruptionOptionDTO, set: readonly DisruptionRecommendedDTO[]): { basis: string; reason: string }[] {
  const fromSet = set.filter((item) => item.option_id === option.option_id).map((item) => ({ basis: item.basis, reason: item.reason }));
  if (fromSet.length) return fromSet;
  const bases = option.recommended_as ?? [];
  return bases.map((basis, index) => ({ basis, reason: option.recommended_why?.[index] ?? "" }));
}

/**
 * The rows in reading order. LNG-4: every option that can physically happen by the server's
 * rank (the ordering weights), then those that cannot; an LNG-3 read without ranks keeps the
 * old grouping (default, frontier, dominated, infeasible; then score, then key).
 */
export function optionRows(data: Pick<DisruptionOptionsDTO, "options" | "recommended"> & { recommended_set?: DisruptionRecommendedDTO[] }): OptionRow[] {
  const set = data.recommended_set ?? [];
  const titles = new Map(data.options.map((option) => [option.option_id, option.title]));
  const order: Record<OptionStanding, number> = { recommended: 0, frontier: 1, dominated: 2, infeasible: 3 };
  const ranked = data.options.some((option) => typeof option.rank === "number");
  return data.options
    .map((option) => {
      const standing = standingOf(option, data.recommended, set);
      const beatenBy =
        standing === "dominated" && option.dominated_by
          ? { title: titles.get(option.dominated_by) ?? option.dominated_by, where: [...option.dominated_why] }
          : null;
      return {
        option,
        standing,
        kind: kindOf(option),
        range: scenarioRange(option),
        beatenBy,
        flags: flagsOf(option),
        recommended: recommendedFor(option, set),
      };
    })
    .sort((a, b) => {
      if (ranked) {
        const possible = Number(isPossible(b.option)) - Number(isPossible(a.option));
        if (possible) return possible;
        const rank = (a.option.rank ?? Number.MAX_SAFE_INTEGER) - (b.option.rank ?? Number.MAX_SAFE_INTEGER);
        if (rank) return rank;
      } else if (order[a.standing] !== order[b.standing]) {
        return order[a.standing] - order[b.standing];
      }
      return b.option.score - a.option.score || a.option.key.localeCompare(b.option.key);
    });
}

/** LNG-4: the expected P&L as direct P&L less opportunity cost (both in EUR). */
export function costSplit(option: Pick<DisruptionOptionDTO, "objectives" | "direct_pnl_expected" | "opportunity_cost_expected">): { direct: number; opportunity: number; pnl: number } {
  const pnl = option.objectives.pnl_expected;
  const opportunity = option.opportunity_cost_expected ?? option.objectives.opportunity_cost ?? 0;
  const direct = option.direct_pnl_expected ?? option.objectives.direct_pnl_expected ?? pnl + opportunity;
  return { direct, opportunity, pnl };
}

export interface Consequence {
  kind: "breach" | "moves" | "opportunity" | "cover";
  text: string;
  /** EUR when the consequence is valued, null when the data does not hold its value. */
  value: number | null;
  sources: string[];
}

/** LNG-4: what choosing the option does to others, each line with its value and sources. */
export function consequences(option: DisruptionOptionDTO): Consequence[] {
  const out: Consequence[] = [];
  for (const breach of option.breaches ?? []) {
    out.push({ kind: "breach", text: breach.text, value: breach.exposure_eur, sources: breach.contract_id ? [`contract ${breach.contract_id}`] : [] });
  }
  for (const moved of option.disrupts ?? []) {
    const where = [moved.from, moved.to].filter(Boolean).join(" → ");
    const text = [moved.label, `${Math.round(moved.mwh).toLocaleString("en-GB")} MWh`, where, moved.cause].filter(Boolean).join(" · ");
    out.push({ kind: "moves", text, value: null, sources: [] });
  }
  for (const item of option.opportunity ?? []) {
    out.push({ kind: "opportunity", text: item.text, value: item.value_eur, sources: [...(item.sources ?? [])] });
  }
  for (const cover of option.covers ?? []) {
    out.push({ kind: "cover", text: `${cover.source_id}: ${Math.round(cover.mwh).toLocaleString("en-GB")} MWh for ${cover.obligation_id}`, value: null, sources: [] });
  }
  return out;
}

/** LNG-4: a cost line's sources as one reading (null when the line names none). */
export function lineSources(line: Pick<DisruptionLineDTO, "sources">): string | null {
  const sources = (line.sources ?? []).map((text) => text.trim()).filter(Boolean);
  return sources.length ? sources.join("; ") : null;
}

/** LNG-4: the arithmetic lines grouped by basis, direct first. */
export function linesByBasis(lines: readonly DisruptionLineDTO[]): { direct: DisruptionLineDTO[]; opportunity: DisruptionLineDTO[] } {
  return {
    direct: lines.filter((line) => line.basis !== "opportunity"),
    opportunity: lines.filter((line) => line.basis === "opportunity"),
  };
}

/** The FX picker's state as the reader set it. */
export interface FxPicker {
  source: "ECB" | "WMR" | "BFIX" | "manual";
  rateDate: string;
  rate: string;
  rateCurrency: "USD" | "GBP";
  reporting: "EUR" | "GBP" | "USD";
}

export const DEFAULT_FX: FxPicker = { source: "ECB", rateDate: "", rate: "", rateCurrency: "USD", reporting: "EUR" };

/**
 * LNG-4: the query for the FX picker, or an error key when a rate entered by hand is not a
 * positive number. The default (ECB, latest fix, EUR) sends nothing.
 */
export function fxQuery(picker: FxPicker): { query: DisruptionFxQuery | undefined; error: string | null } {
  const query: DisruptionFxQuery = {};
  if (picker.reporting !== "EUR") query.reporting_currency = picker.reporting;
  if (picker.source === "manual") {
    const rate = Number(picker.rate.replace(",", "."));
    if (!picker.rate.trim() || !Number.isFinite(rate) || rate <= 0) return { query: undefined, error: "lng.cargo.options.fx.rate_invalid" };
    query.fx_source = "manual";
    query.fx_rate = rate;
    query.fx_currency = picker.rateCurrency;
  } else if (picker.source !== "ECB") {
    query.fx_source = picker.source;
  }
  if (picker.rateDate) query.fx_rate_date = picker.rateDate;
  return { query: Object.keys(query).length ? query : undefined, error: null };
}

/** LNG-4: the demurrage a reader sees: as the contract states it, and the rate used with its source and date. */
export function demurrageLine(block: DisruptionDemurrageDTO | null | undefined): {
  original: string | null;
  eurPerDay: number | null;
  rate: string | null;
  source: string | null;
  warning: string | null;
} {
  if (!block) return { original: null, eurPerDay: null, rate: null, source: null, warning: null };
  const original = block.rate_per_day !== null && block.currency ? `${Math.round(block.rate_per_day).toLocaleString("en-GB")} ${block.currency}/day` : null;
  const fx = block.fx;
  const flags = [fx?.entered_by_hand ? "entered by hand" : null, fx?.simulated ? "simulated" : null].filter(Boolean);
  const rate =
    fx && fx.rate !== null && block.currency && block.currency !== "EUR"
      ? [`1 ${fx.from} = ${fx.rate.toFixed(6)} ${fx.to}`, fx.label ?? fx.source, fx.rate_date, ...flags].filter(Boolean).join(" · ")
      : null;
  return { original, eurPerDay: block.eur_per_day, rate, source: block.source, warning: block.warning };
}

/** Whether "Choose" may be pressed: an option that can physically happen, a person allowed to record, no choice in flight. */
export function canChoose(option: Pick<DisruptionOptionDTO, "feasible" | "possible">, canWrite: boolean, busy: boolean): boolean {
  return isPossible(option) && canWrite && !busy;
}

/** The i18n key of a timeline row's change, and whether the roles were told. */
export function timelineLine(run: Pick<DisruptionRunDTO, "change" | "notified">): { changeKey: string; told: boolean } {
  return { changeKey: `lng.cargo.options.change.${run.change ?? "none"}`, told: run.notified };
}

/** The i18n key that says how this cargo stands in the book's re-optimisation. */
export function statusKey(status: DisruptionOptionsDTO["status"]): string {
  return `lng.cargo.options.status.${status}`;
}
