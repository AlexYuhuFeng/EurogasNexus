import type { SpreadLegInputDTO, SpreadRuleInputDTO, SpreadSeriesDTO } from "@/api/client";

/**
 * Spread lab: the trader's question "what is the THE-TTF month-ahead spread doing, and would a
 * simple rule on it have paid?" answered with a declarative rule - legs, weights and two or
 * three thresholds - not code. Anything the rule cannot express belongs in the Python SDK.
 */

export interface SpreadLegDraft {
  /** `${hub}|${tenor}|${source}` from the series catalogue, or "" when not chosen yet. */
  seriesKey: string;
  weight: number;
}

export interface SpreadLabDraft {
  legs: SpreadLegDraft[];
  dateFrom: string;
  dateTo: string;
  rule: SpreadRuleInputDTO;
}

export const MAX_SPREAD_LEGS = 4;

export const DEFAULT_SPREAD_RULE: SpreadRuleInputDTO = {
  kind: "zscore",
  lookback: 20,
  entry_z: 2,
  exit_z: 0.5,
  low: null,
  high: null,
  volume_mwh_per_day: 1000,
  cost_per_mwh: 0.02,
};

export function seriesKey(series: Pick<SpreadSeriesDTO, "hub" | "tenor" | "source_system">): string {
  return `${series.hub}|${series.tenor}|${series.source_system}`;
}

/** The name a trader reads: "THE month-ahead · EEX_Settlement". */
export function seriesLabel(series: SpreadSeriesDTO): string {
  return `${series.hub} ${series.tenor} · ${series.source_system}${series.simulated ? " (sim)" : ""}`;
}

/**
 * A two-leg spread of two hubs that share a tenor and unit, against TTF where it can be, so the
 * lab opens on something a trader recognises (e.g. THE vs TTF month-ahead) instead of an empty form.
 */
export function defaultSpreadDraft(catalogue: readonly SpreadSeriesDTO[]): SpreadLabDraft {
  const real = catalogue.filter((series) => !series.simulated);
  const pool = real.length >= 2 ? real : catalogue;
  let legs: SpreadLegDraft[] = [
    { seriesKey: "", weight: 1 },
    { seriesKey: "", weight: -1 },
  ];
  // Continental spreads are quoted against TTF, so a TTF series is preferred as the short leg.
  const ordered = [...pool].sort((left, right) => Number(left.hub === "TTF") - Number(right.hub === "TTF"));
  for (const first of ordered) {
    const sameShape = (other: SpreadSeriesDTO) =>
      other.hub !== first.hub && other.tenor === first.tenor && other.unit === first.unit;
    const second = pool.find((other) => other.hub === "TTF" && sameShape(other)) ?? pool.find(sameShape);
    if (second) {
      legs = [
        { seriesKey: seriesKey(first), weight: 1 },
        { seriesKey: seriesKey(second), weight: -1 },
      ];
      break;
    }
  }
  return { legs, dateFrom: "", dateTo: "", rule: { ...DEFAULT_SPREAD_RULE } };
}

export type SpreadDraftBlocker =
  | "spread_lab.blocker.leg_missing"
  | "spread_lab.blocker.weight_zero"
  | "spread_lab.blocker.unit_mismatch"
  | "spread_lab.blocker.exit_above_entry"
  | "spread_lab.blocker.band_order"
  | "spread_lab.blocker.lookback";

/** The first reason the draft cannot run, checked client-side; the server stays the authority. */
export function spreadDraftBlocker(
  draft: SpreadLabDraft,
  catalogue: readonly SpreadSeriesDTO[],
): SpreadDraftBlocker | null {
  const byKey = new Map(catalogue.map((series) => [seriesKey(series), series]));
  const chosen = draft.legs.map((leg) => byKey.get(leg.seriesKey));
  if (chosen.some((series) => !series)) return "spread_lab.blocker.leg_missing";
  if (draft.legs.some((leg) => !Number.isFinite(leg.weight) || leg.weight === 0)) {
    return "spread_lab.blocker.weight_zero";
  }
  if (new Set(chosen.map((series) => series?.unit)).size > 1) return "spread_lab.blocker.unit_mismatch";
  const { rule } = draft;
  if (!Number.isInteger(rule.lookback) || rule.lookback < 5) return "spread_lab.blocker.lookback";
  if (rule.kind === "zscore" && !(rule.exit_z < rule.entry_z)) return "spread_lab.blocker.exit_above_entry";
  if (rule.kind === "threshold" && !(rule.low != null && rule.high != null && rule.low < rule.high)) {
    return "spread_lab.blocker.band_order";
  }
  return null;
}

export function spreadAnalysisRequest(
  draft: SpreadLabDraft,
  catalogue: readonly SpreadSeriesDTO[],
): { legs: SpreadLegInputDTO[]; date_from: string | null; date_to: string | null; rule: SpreadRuleInputDTO } {
  const byKey = new Map(catalogue.map((series) => [seriesKey(series), series]));
  return {
    legs: draft.legs.map((leg) => {
      const series = byKey.get(leg.seriesKey);
      return {
        hub: series?.hub ?? "",
        tenor: series?.tenor ?? "",
        source_system: series?.source_system ?? null,
        weight: leg.weight,
      };
    }),
    date_from: draft.dateFrom || null,
    date_to: draft.dateTo || null,
    rule: draft.rule,
  };
}

/** "+1 THE month-ahead −1 TTF month-ahead": the spread as the desk would say it. */
export function spreadFormula(draft: SpreadLabDraft, catalogue: readonly SpreadSeriesDTO[]): string {
  const byKey = new Map(catalogue.map((series) => [seriesKey(series), series]));
  return draft.legs
    .map((leg, index) => {
      const series = byKey.get(leg.seriesKey);
      const name = series ? `${series.hub} ${series.tenor}` : "?";
      const magnitude = Math.abs(leg.weight) === 1 ? "" : `${Math.abs(leg.weight)}×`;
      const sign = leg.weight < 0 ? "−" : index === 0 ? "" : "+";
      return `${sign}${magnitude}${name}`;
    })
    .join(" ");
}
