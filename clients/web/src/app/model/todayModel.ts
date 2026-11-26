/**
 * The Today screen's presentation rules (UX-05, FRESH-02). The figures come computed from
 * `GET /api/desk/today`; nothing here recomputes a figure. It decides only how a figure is
 * written: decimals by unit, the state in words when it is not current, and whether a section
 * is empty.
 */
import type { FigureStateDTO, TodayEmptyDTO, TodayFigureDTO } from "@/api/client";
import { formatGasDay } from "../time/timeFormat.ts";
import { unitLabel } from "./instrumentPicker.ts";

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
export function shortDay(day: string | null | undefined, language = "en"): string {
  if (!day) return "";
  const at = new Date(`${day.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(at.getTime())) return day;
  // Chinese reads the day in Chinese ("11月25日"), never an English month name.
  if (language.toLowerCase().startsWith("zh")) return `${at.getUTCMonth() + 1}月${at.getUTCDate()}日`;
  return at.toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
}

/**
 * An outage's window in UTC, as a desk reads it: "16 Nov 09:56 – 19 Nov 09:56" for a short
 * outage; a window of a week or more drops the clock ("1 Oct – 15 Nov"); the year is shown on
 * both ends whenever the window leaves the current year or spans years ("1 Oct 2026 –
 * 1 Oct 2029"). An open end reads "1 Oct 2026 –". `nowMs` fixes "the current year".
 */
export function timeWindow(startUtc: string, endUtc: string | null, nowMs: number = Date.now()): string {
  const start = new Date(startUtc);
  const end = endUtc ? new Date(endUtc) : null;
  if (Number.isNaN(start.getTime()) || (end && Number.isNaN(end.getTime()))) {
    return endUtc ? `${startUtc} – ${endUtc}` : startUtc;
  }
  const currentYear = new Date(nowMs).getUTCFullYear();
  const withYear = start.getUTCFullYear() !== currentYear || (end !== null && end.getUTCFullYear() !== start.getUTCFullYear());
  const long = end === null || end.getTime() - start.getTime() >= 7 * 24 * 3600 * 1000;
  const format = (at: Date) => {
    const day = at.toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC", ...(withYear ? { year: "numeric" } : {}) });
    return long ? day : `${day} ${at.toISOString().slice(11, 16)}`;
  };
  return end ? `${format(start)} – ${format(end)}` : `${format(start)} –`;
}

/**
 * Why a spread against TTF is not shown, as a plain sentence in the reader's language: the
 * cause's code through `today.spread.<code>` (or `today.spread.cause.<cause>`), the date through
 * the shell's day formatter. The server's own sentence is the detail (the line's tooltip); a
 * reply without a code falls back to it.
 */
export function spreadEmptyText(empty: TodayEmptyDTO, t: Translate, language: string): string {
  const params = empty.params ?? {};
  const values: Record<string, unknown> = {
    ...params,
    unit: params.unit ? unitLabel(params.unit) : "",
    date: params.as_of ? formatGasDay(params.as_of, language) : "",
  };
  const key = empty.code === "not_convertible" && empty.cause ? `today.spread.cause.${empty.cause}` : `today.spread.${empty.code}`;
  const fallback = empty.code === "not_convertible" ? t("today.spread.cause.not_convertible", values) : empty.reason;
  return t(key, { ...values, defaultValue: fallback });
}
