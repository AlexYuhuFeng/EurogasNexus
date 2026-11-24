/**
 * My gas day (Today row 6): presentation rules only. Every figure comes from the server
 * (`application/gas_day.py`); nothing is recomputed here except how long until a cut-off.
 */
import type { DailyBalanceDTO, GasDayCutoffDTO, GasDayHubDTO, GasDayLineDTO, GasDayQuantityDTO, TodayChecklistRowDTO, TodayGasDayRowDTO } from "@/api/client";

/** The next cut-off of the day that has not passed at `nowMs` (the end of the day last). */
export function nextCutoff(cutoffs: readonly GasDayCutoffDTO[], nowMs: number): GasDayCutoffDTO | null {
  return cutoffs.find((cut) => Date.parse(cut.at_utc) > nowMs) ?? null;
}

/** Whole hours and minutes until `atUtc` (never negative). */
export function timeLeft(atUtc: string, nowMs: number): { hours: number; minutes: number } {
  const minutes = Math.max(0, Math.floor((Date.parse(atUtc) - nowMs) / 60_000));
  return { hours: Math.floor(minutes / 60), minutes: minutes % 60 };
}

/** A day's quantity in the desk unit, grouped, signed when asked ("+781,264", "−503"). */
export function formatQuantity(quantity: GasDayQuantityDTO, signed = false): string {
  const value = quantity.value;
  const zero = Math.round(Math.abs(value)) === 0;
  const text = Math.round(Math.abs(value)).toLocaleString("en-GB");
  const sign = value < 0 && !zero ? "−" : signed && !zero ? "+" : "";
  return `${sign}${text}`;
}

/** "th/d" and "MWh/d" as the desk writes them; the MW figure for a continental hub. */
export function quantityUnit(quantity: GasDayQuantityDTO): string {
  return quantity.unit;
}

export function mwText(quantity: GasDayQuantityDTO, signed = false): string | null {
  if (quantity.mw === undefined || quantity.mw === null) return null;
  return formatQuantity({ value: quantity.mw, unit: "MWh/d", mwh: quantity.mwh }, signed);
}

/** Lines IN first then OUT, as the server ordered them within each side. */
export function sides(hub: GasDayHubDTO): { in: GasDayLineDTO[]; out: GasDayLineDTO[] } {
  return {
    in: hub.lines.filter((line) => line.direction === "in"),
    out: hub.lines.filter((line) => line.direction === "out"),
  };
}

/** The i18n key of a line's basis ("nominated", "contract quantity", ...). */
export function basisKey(basis: string): string {
  return `today.gas_day.basis.${basis}`;
}

/** The i18n key of a line's kind ("supply", "customer offtake", ...). */
export function kindKey(kind: string): string {
  return `today.gas_day.kind.${kind}`;
}

/** Whether the row has anything for the given day. */
export function hasHubs(day: { hubs: readonly GasDayHubDTO[] } | undefined): boolean {
  return Boolean(day && day.hubs.length > 0);
}

/** How close a cut-off is: amber within two hours, red within thirty minutes (design tokens). */
export function cutoffUrgency(atUtc: string, nowMs: number): "open" | "soon" | "imminent" | "none" {
  const minutes = (Date.parse(atUtc) - nowMs) / 60_000;
  if (!Number.isFinite(minutes) || minutes <= 0) return "none";
  if (minutes <= 30) return "imminent";
  if (minutes <= 120) return "soon";
  return "open";
}

type Translate = (key: string, options?: Record<string, unknown>) => string;

/**
 * The daily balance's cash-out rate and where it came from, read from the response: the
 * approved assumption set and version, or "entered by hand"; never a client default (QA-T-07).
 */
export function dailyBalanceRateText(balance: DailyBalanceDTO, t: Translate): string | null {
  const cost = balance.days.find((day) => day.cash_out?.rate != null)?.cash_out;
  if (cost?.rate != null) {
    const side = t(cost.side === "short_premium" ? "balance.side_short_premium" : "balance.side_long_discount");
    if (cost.basis === "entered") return t("balance.rate_entered", { rate: cost.rate, unit: cost.rate_unit ?? "", side });
    return t("balance.rate_source", {
      rate: cost.rate, unit: cost.rate_unit ?? "", side, set: cost.assumption_set ?? "", version: cost.assumption_version ?? "",
    });
  }
  return balance.days.some((day) => day.cash_out?.basis === "missing") ? t("balance.rate_missing") : null;
}


/** What the trader's gas-day strip says: the next cut-off, overdue steps and open nets. */
export interface GasDayAlert {
  next: { hub: string; cutoff: GasDayCutoffDTO } | null;
  overdue: number;
  open: { hub: string; state: "long" | "short"; net: GasDayQuantityDTO }[];
}

/**
 * The slim strip above a trader's market (owner, 2026-11-24): the trader reads prices first,
 * so the gas day's urgent parts sit above them in one line. Today's gas day only: the soonest
 * cut-off not yet passed across the hubs, how many checklist steps are overdue, and each hub
 * whose net is outside its band. Every figure is the server's; only the order is chosen here.
 */
export function gasDayAlert(
  gasDay: TodayGasDayRowDTO | null | undefined,
  checklist: TodayChecklistRowDTO | null | undefined,
  nowMs: number,
): GasDayAlert {
  const today = gasDay?.days.find((day) => day.which === "today");
  let next: GasDayAlert["next"] = null;
  const open: GasDayAlert["open"] = [];
  for (const hub of today?.hubs ?? []) {
    const cut = nextCutoff(hub.cutoffs.filter((item) => item.key !== "gas_day_end"), nowMs);
    if (cut && (!next || Date.parse(cut.at_utc) < Date.parse(next.cutoff.at_utc))) next = { hub: hub.hub, cutoff: cut };
    if (hub.state !== "balanced") open.push({ hub: hub.hub, state: hub.state, net: hub.net });
  }
  const overdue = (checklist?.days ?? [])
    .flatMap((day) => day.items)
    .filter((item) => item.urgency === "overdue").length;
  return { next, overdue, open };
}
