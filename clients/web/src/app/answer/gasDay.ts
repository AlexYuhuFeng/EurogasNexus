/**
 * Gas-day and date answers: "gas day", "D+2", "days to 1 Jan", "front month".
 *
 * The gas day is the product's own rule (`app/tradingContext.ts`, the corrected CAM calendar
 * `EU-CAM-UTC-2025`: 05:00–05:00 UTC in winter, 04:00–04:00 UTC in summer, 06:00 CET/CEST).
 * Day counts are gas days from the current gas day; the front month is the calendar month
 * after the current gas day's, named as the screens name it (`Dec-26`), as the Today read does.
 */

import { gasDayLabelForUtc, gasDayStartUtc } from "../tradingContext.ts";
import { normalizeTyped } from "./numbers.ts";

export type GasDayAnswer =
  | { kind: "gas-day"; gasDay: string; startUtc: string; endUtc: string; offset: number }
  | { kind: "days-to"; days: number; target: string; from: string }
  | { kind: "front-month"; label: string; start: string; end: string };

const MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"];
const MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function addDays(day: string, offset: number): string {
  const [year, month, date] = day.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, date + offset)).toISOString().slice(0, 10);
}

function daysBetween(from: string, to: string): number {
  return Math.round((Date.parse(`${to}T00:00:00Z`) - Date.parse(`${from}T00:00:00Z`)) / 86_400_000);
}

/** The screen's month name: `Dec-26`. */
export function monthLabel(year: number, monthIndex: number): string {
  return `${MONTH_LABELS[monthIndex]}-${String(year % 100).padStart(2, "0")}`;
}

/** A date typed as `1 Jan`, `Jan 1`, `1 January 2027`, `2027-01-01` or `1月1日`. */
export function parseDay(text: string, today: string): string | null {
  const clean = text.trim().toLowerCase().replace(/(\d)(st|nd|rd|th)\b/, "$1").replace(/,/g, " ");
  let year: number | null = null;
  let month = -1;
  let day = -1;
  const iso = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(clean);
  const zh = /^(?:(\d{4})年)?\s*(\d{1,2})月\s*(\d{1,2})[日号]?$/.exec(clean);
  const dayFirst = /^(\d{1,2})\s+([a-z]{3,9})(?:\s+(\d{4}))?$/.exec(clean);
  const monthFirst = /^([a-z]{3,9})\s+(\d{1,2})(?:\s+(\d{4}))?$/.exec(clean);
  if (iso) [year, month, day] = [Number(iso[1]), Number(iso[2]) - 1, Number(iso[3])];
  else if (zh) [year, month, day] = [zh[1] ? Number(zh[1]) : null, Number(zh[2]) - 1, Number(zh[3])];
  else if (dayFirst) [day, month, year] = [Number(dayFirst[1]), MONTHS.indexOf(dayFirst[2].slice(0, 3)), dayFirst[3] ? Number(dayFirst[3]) : null];
  else if (monthFirst) [month, day, year] = [MONTHS.indexOf(monthFirst[1].slice(0, 3)), Number(monthFirst[2]), monthFirst[3] ? Number(monthFirst[3]) : null];
  else return null;
  if (month < 0 || month > 11 || day < 1 || day > 31) return null;
  const thisYear = Number(today.slice(0, 4));
  const build = (y: number) => {
    const date = new Date(Date.UTC(y, month, day));
    return date.getUTCMonth() === month ? date.toISOString().slice(0, 10) : null;
  };
  if (year !== null) return build(year);
  // Without a year: the next such day on or after today.
  const candidate = build(thisYear);
  if (candidate && candidate >= today) return candidate;
  return build(thisYear + 1);
}

/** The gas-day answer `raw` asks for, or null. `now` is injectable for tests. */
export function gasDayAnswer(raw: string, now: Date = new Date()): GasDayAnswer | null {
  const text = normalizeTyped(raw).trim().toLowerCase().replace(/[?？]$/, "").trim();
  const today = gasDayLabelForUtc(now);
  const gasDay = (offset: number): GasDayAnswer => {
    const day = addDays(today, offset);
    return {
      kind: "gas-day",
      gasDay: day,
      startUtc: new Date(gasDayStartUtc(day)).toISOString(),
      endUtc: new Date(gasDayStartUtc(addDays(day, 1))).toISOString(),
      offset,
    };
  };
  if (/^(?:(?:what(?:'s| is)\s+)?(?:the\s+)?(?:gas\s*day|gd)(?:\s+(?:today|now))?|today'?s\s+gas\s*day|(?:今天的?)?(?:燃气日|气日)(?:是哪天)?)$/.test(text)) {
    return gasDay(0);
  }
  const relative = /^(?:gas\s*day\s+)?d\s*([+-])\s*(\d{1,3})$/.exec(text);
  if (relative) return gasDay((relative[1] === "-" ? -1 : 1) * Number(relative[2]));
  // "THE front month" is the German hub's price, not the calendar.
  if (!/^THE\s/.test(raw.trim()) && /^(?:the\s+)?(?:front[\s-]?month|fm|m\s*\+\s*1|近月|前月)(?:\s+(?:name|contract))?$/.test(text)) {
    const [year, month] = today.split("-").map(Number);
    const next = new Date(Date.UTC(year, month, 1));
    const end = new Date(Date.UTC(next.getUTCFullYear(), next.getUTCMonth() + 1, 0));
    return {
      kind: "front-month",
      label: monthLabel(next.getUTCFullYear(), next.getUTCMonth()),
      start: next.toISOString().slice(0, 10),
      end: end.toISOString().slice(0, 10),
    };
  }
  const daysTo =
    /^(?:how\s+many\s+)?(?:gas\s+)?days?\s+(?:to|until|till|before)\s+(.+)$/.exec(text) ??
    /^(?:距离?|到)\s*(.+?)\s*(?:还有)?(?:几天|多少天)$/.exec(text);
  if (daysTo) {
    const target = parseDay(daysTo[1], today);
    if (!target) return null;
    return { kind: "days-to", days: daysBetween(today, target), target, from: today };
  }
  return null;
}
