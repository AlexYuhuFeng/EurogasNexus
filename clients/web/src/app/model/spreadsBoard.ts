/**
 * Research → Spreads: the spread board (what the page opens on) and the links that carry a
 * study along the analyst's path, Fundamentals → Spreads → Cargo & netback → Reports.
 *
 * Every figure on the board is the server's (`GET /api/research/spreads/board`); this module
 * only completes a row's spec, phrases its range and builds the next-step addresses. The
 * StrategySpec travels in the address (`spec=`, JSON), so the page a link opens starts from
 * the same object, not from a re-typed description.
 */
import type { BoardReasonDTO, BoardTenorDTO, StrategySpecDTO } from "../../api/spreads.ts";
import { formatDeliveryMonth } from "../time/timeFormat.ts";
import { humanizeEnum } from "./enumLabels.ts";

/** A row's spec, completed with the defaults the workbench needs. */
export function fullSpec(partial: Partial<StrategySpecDTO>): StrategySpecDTO {
  return {
    version: 1,
    kind: partial.kind ?? "curve",
    legs: (partial.legs ?? []).map((leg) => ({ hub: leg.hub, tenor: leg.tenor ?? null, weight: leg.weight })),
    unit: partial.unit ?? null,
    fx: partial.fx ?? "forward",
    cost: partial.cost ?? null,
    rule: partial.rule ?? null,
    lookback_days: partial.lookback_days ?? 365,
    volume_mwh_per_day: partial.volume_mwh_per_day ?? null,
  };
}

/** The spec a link carries (`?spec=`), or null when there is none or it does not read. */
export function specFromSearch(search: string): StrategySpecDTO | null {
  const raw = new URLSearchParams(search).get("spec");
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<StrategySpecDTO>;
    return Array.isArray(parsed.legs) && parsed.legs.length >= 1 ? fullSpec(parsed) : null;
  } catch {
    return null;
  }
}

function researchSearch(search: string, task: string, set: Record<string, string>): string {
  const next = new URLSearchParams(search);
  for (const key of ["view", "describe", "spec", "hub", "ask", "subject"]) next.delete(key);
  next.set("workspace", "research");
  next.set("task", task);
  for (const [key, value] of Object.entries(set)) next.set(key, value);
  return `?${next.toString()}`;
}

/** Spreads opened on one study. */
export function spreadsSearch(search: string, spec: StrategySpecDTO | Partial<StrategySpecDTO>): string {
  return researchSearch(search, "spreads", { spec: JSON.stringify(fullSpec(spec)) });
}

/** Cargo & netback opened against one hub (its terminals first). */
export function cargoSearch(search: string, hub: string): string {
  return researchSearch(search, "cargo", { hub });
}

/** The hub a cargo link carries (`?hub=`). */
export function hubFromSearch(search: string): string | null {
  const hub = (new URLSearchParams(search).get("hub") ?? "").trim().toUpperCase();
  return /^[A-Z]{2,8}$/.test(hub) ? hub : null;
}

/** Reports with a question to plan (the asked-report flow, `?ask=`). */
export function reportSearch(search: string, question: string): string {
  return researchSearch(search, "reports", { ask: question.slice(0, 500) });
}

/** The hub a spread is about for a cargo: the one that is not TTF, else TTF. */
export function cargoHubOf(spec: StrategySpecDTO): string {
  return spec.legs.find((leg) => leg.hub !== "TTF")?.hub ?? "TTF";
}

/** "NBP − TTF", as the desk writes the spread a spec describes. */
export function specName(spec: StrategySpecDTO): string {
  return spec.legs
    .map((leg, index) => `${index === 0 ? "" : leg.weight < 0 ? " − " : " + "}${leg.hub}${leg.tenor ? ` ${leg.tenor}` : ""}`)
    .join("");
}

/** The focus hubs a preference holds ("NBP, THE"), upper case, at most eight. */
export function focusHubs(text: string | null | undefined): string[] {
  return [...new Set((text ?? "").split(/[\s,;]+/).map((item) => item.trim().toUpperCase()).filter((item) => /^[A-Z]{2,8}$/.test(item)))].slice(0, 8);
}

/** Where today's gross sits in its own year: the position and words for the strip. */
export function rangePosition(tenor: BoardTenorDTO): { position: number; low: number; high: number; days: number } | null {
  if (tenor.percentile == null || !tenor.range) return null;
  return { position: tenor.percentile, low: tenor.range.low, high: tenor.range.high, days: tenor.range.days };
}

/** A route that is not fully priced: the legs named, else the issue. */
export function routeGap(tenor: BoardTenorDTO): string | null {
  const route = tenor.route;
  if (!route || route.complete) return null;
  if (route.missing.length > 0) return route.missing.join("; ");
  return route.issues.join("; ") || null;
}

/** The storage line on Fundamentals: EU fill against the 5-yr mean, and the Win–Sum link. */
export function storageStep(diffPts: number | null | undefined): { tone: "below" | "above" | "near"; pts: number } | null {
  if (diffPts == null || !Number.isFinite(diffPts)) return null;
  const pts = Math.round(diffPts * 10) / 10;
  return { tone: pts <= -1 ? "below" : pts >= 1 ? "above" : "near", pts: Math.abs(pts) };
}

type ReasonTranslate = (key: string, options?: Record<string, unknown>) => string;

/** A code the server sends ("no_hh_price") in words ("no HH price"): the fallback. */
function codeWords(code: string): string {
  const words = humanizeEnum(code);
  return words.charAt(0).toLowerCase() + words.slice(1);
}

/**
 * Why a board figure is not shown, in the reader's language: each reason code through
 * `spreads.reason.<code>` (a cargo's own reasons through `cargo.reason.<code>`), months as the
 * desk writes them ("Apr-27"). A reply without codes falls back to the server's sentence.
 */
export function boardReasonText(
  row: { reason?: string | null; reasons?: BoardReasonDTO[] },
  t: ReasonTranslate,
): string {
  const reasons = row.reasons ?? [];
  if (reasons.length === 0) return String(row.reason ?? "");
  return reasons
    .map(({ code, params = {} }) => {
      const values: Record<string, unknown> = { ...params };
      if (Array.isArray(params.months)) values.months = params.months.map((month) => formatDeliveryMonth(String(month))).join(", ");
      if (code.startsWith("cargo.")) {
        const cargoCode = code.slice("cargo.".length);
        return t(`cargo.reason.${cargoCode}`, { defaultValue: codeWords(cargoCode) });
      }
      return t(`spreads.reason.${code}`, { ...values, defaultValue: codeWords(code) });
    })
    .join(t("spreads.reason.separator"));
}
