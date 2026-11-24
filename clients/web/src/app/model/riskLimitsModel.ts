/**
 * Formatting and parsing shared by the limits, delivery and LNG bid panels. Desk units and
 * thousands separators; a missing figure prints as a dash, never as zero.
 */

import { formatGasDay } from "../time/timeFormat.ts";

const CURRENCY_SYMBOL: Record<string, string> = { EUR: "€", GBP: "£", USD: "$" };

export function formatMoney(value: number | null | undefined, currency: string): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "-";
  const magnitude = Math.abs(value);
  const symbol = CURRENCY_SYMBOL[currency] ?? `${currency} `;
  const sign = value < 0 ? "-" : "";
  if (magnitude >= 1_000_000) return `${sign}${symbol}${(magnitude / 1_000_000).toFixed(2)}m`;
  if (magnitude >= 10_000) return `${sign}${symbol}${(magnitude / 1_000).toFixed(0)}k`;
  return `${sign}${symbol}${magnitude.toLocaleString("en-GB", { maximumFractionDigits: 0 })}`;
}

export function formatQuantity(value: number | null | undefined, unit = "MWh"): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "-";
  return `${value.toLocaleString("en-GB", { maximumFractionDigits: 0 })} ${unit}`;
}

/** A price to three decimals with its unit, e.g. "33.125 EUR/MWh". */
export function formatPrice(value: number | null | undefined, unit: string): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "-";
  return `${value.toFixed(3)} ${unit}`;
}

/** "a, b  c" -> ["a", "b", "c"]; empties dropped. */
export function splitList(text: string): string[] {
  return text.split(/[\s,;]+/).map((item) => item.trim()).filter(Boolean);
}

/** The next calendar month as "YYYY-MM", the default arrival month for a cargo bid. */
export function nextMonth(today: Date = new Date()): string {
  const year = today.getUTCFullYear() + (today.getUTCMonth() === 11 ? 1 : 0);
  const month = (today.getUTCMonth() + 1) % 12 + 1;
  return `${year}-${String(month).padStart(2, "0")}`;
}


/**
 * QA-R-07: a risk figure is only as current as the daily close its marks come from. The server
 * judges it (`state`: current, late = one business day behind, stale = more, never); the client
 * only words it, so a late or stale row says so in text and not by colour alone.
 */
export interface MarksFreshness {
  marks_as_of?: string | null;
  state?: string | null;
}

/** Whether the row's marks are older than expected (late or stale). */
export function marksBehind(state: string | null | undefined): boolean {
  return state === "late" || state === "stale";
}

/** "18 Nov" for an ISO day: the close's own calendar day, never shifted by the reader's zone. */
export function formatMarksDay(iso: string, language = "en"): string {
  return formatGasDay(iso.slice(0, 10), language);
}

/** The translation key and day for a row's marks line; null when the row is not priced. */
export function marksLine(row: MarksFreshness, language = "en"): { key: string; day: string | null } | null {
  if (!row.state) return null;
  if (!row.marks_as_of) return row.state === "never" ? { key: "risk.marks.never", day: null } : null;
  const state = marksBehind(row.state) ? row.state : "current";
  return { key: `risk.marks.${state}`, day: formatMarksDay(row.marks_as_of, language) };
}
