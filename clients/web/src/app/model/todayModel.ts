/**
 * The Today screen's presentation rules (UX-05, FRESH-02). The figures come computed from
 * `GET /api/desk/today`; nothing here recomputes a figure. It decides only how a figure is
 * written: decimals by unit, the state in words when it is not current, and whether a section
 * is empty.
 */
import type { FigureStateDTO, TodayEmptyDTO, TodayFigureDTO } from "@/api/client";

type Translate = (key: string, options?: Record<string, unknown>) => string;

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/** "12 min", "3 h", "2 d": how old a figure is, or null without a time. */
export function ageText(asOf: string | null | undefined, nowMs: number, t: Translate): string | null {
  if (!asOf) return null;
  const at = Date.parse(asOf.length === 10 ? `${asOf}T00:00:00Z` : asOf);
  if (!Number.isFinite(at)) return null;
  const elapsed = Math.max(0, nowMs - at);
  if (elapsed < HOUR) return t("today.age.minutes", { count: Math.max(1, Math.round(elapsed / MINUTE)) });
  if (elapsed < DAY) return t("today.age.hours", { count: Math.round(elapsed / HOUR) });
  return t("today.age.days", { count: Math.round(elapsed / DAY) });
}

/**
 * The state in words, or null when the figure is current: "late 3 h", "stale 2 d", "manual",
 * "not received". A simulated figure says "simulated" whatever its age: on the demo desk the
 * age of a static series is not news.
 */
export function stateWords(
  figure: { state: FigureStateDTO; as_of: string | null; simulated?: boolean },
  nowMs: number,
  t: Translate,
): string | null {
  if (figure.state === "current") return null;
  if (figure.state === "manual") return t("today.state.manual");
  if (figure.state === "never") return t("today.state.never");
  const age = ageText(figure.as_of, nowMs, t);
  return t(`today.state.${figure.state}`, { age: age ?? "" }).trim();
}

/** Decimal places by unit: prices to three, energy and money to whole units, shares to one. */
export function decimalsFor(unit: string): number {
  if (/\/(MWh|th|MMBtu)$/i.test(unit) || /^p\/th$/i.test(unit)) return 3;
  if (unit === "%") return 1;
  if (/TWh$/i.test(unit)) return 1;
  return 0;
}

/** A figure's value in desk format ("33.662", "46,000", "72.6"); a missing value is "–". */
export function formatValue(value: number | null | undefined, unit: string, signed = false): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "–";
  const decimals = decimalsFor(unit);
  const text = Math.abs(value).toLocaleString("en-GB", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  const zero = Number(Math.abs(value).toFixed(decimals)) === 0;
  const sign = value < 0 && !zero ? "−" : signed && !zero ? "+" : "";
  return `${sign}${text}`;
}

/** A day-change: always signed, same decimals as the price. */
export function formatChange(value: number | null | undefined, unit: string): string {
  return formatValue(value, unit, true);
}

export function isEmptyEntry<T extends object>(entry: T | { empty: TodayEmptyDTO }): entry is { empty: TodayEmptyDTO } {
  return "empty" in entry && Boolean((entry as { empty?: unknown }).empty);
}

/** A figure the caller may see: the server omits a section the caller is not entitled to. */
export function isFigure(value: unknown): value is TodayFigureDTO {
  return Boolean(value) && typeof value === "object" && "key" in (value as object) && "unit" in (value as object);
}

/** DOM id of a figure on the Today screen, so the stale list can lead to it. */
export function figureAnchorId(key: string): string {
  return `today-figure-${key.replace(/[^A-Za-z0-9_-]/g, "-")}`;
}

/** Short date of a close day ("14 Nov"). */
export function shortDay(day: string | null | undefined): string {
  if (!day) return "";
  const at = new Date(`${day.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(at.getTime())) return day;
  return at.toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
}

/** "06:00–10 Nov 04:00" style window for an outage, in UTC. */
export function timeWindow(startUtc: string, endUtc: string | null): string {
  const format = (value: string) => {
    const at = new Date(value);
    if (Number.isNaN(at.getTime())) return value;
    return `${at.toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" })} ${at.toISOString().slice(11, 16)}`;
  };
  return endUtc ? `${format(startUtc)} – ${format(endUtc)}` : format(startUtc);
}
