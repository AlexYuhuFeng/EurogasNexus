/**
 * The PeriodPicker's pure parts: calendar grids, keyboard movement, value parsing and labels in the
 * app's language. Values are the same strings the native inputs produced ("2026-11-16",
 * "2026-12", "2026-11-16T09:30"), so a page swaps the control without changing its data.
 */

export type PeriodKind = "day" | "month" | "datetime";

export interface DayValue {
  year: number;
  month: number; // 1-12
  day: number;
}

const EN_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const EN_WEEKDAYS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"];
const ZH_WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"];

const pad = (value: number) => String(value).padStart(2, "0");
const isZh = (language: string) => String(language).toLowerCase().startsWith("zh");

export function dayKey(value: DayValue): string {
  return `${value.year}-${pad(value.month)}-${pad(value.day)}`;
}

export function parseDay(value: string | null | undefined): DayValue | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(value ?? ""));
  if (!match) return null;
  const parsed = { year: Number(match[1]), month: Number(match[2]), day: Number(match[3]) };
  return parsed.month >= 1 && parsed.month <= 12 && parsed.day >= 1 && parsed.day <= daysInMonth(parsed.year, parsed.month) ? parsed : null;
}

export function parseMonth(value: string | null | undefined): { year: number; month: number } | null {
  const match = /^(\d{4})-(\d{2})$/.exec(String(value ?? ""));
  if (!match) return null;
  const month = Number(match[2]);
  return month >= 1 && month <= 12 ? { year: Number(match[1]), month } : null;
}

export function parseTime(value: string | null | undefined): { hour: number; minute: number } | null {
  const match = /T(\d{2}):(\d{2})/.exec(String(value ?? ""));
  return match ? { hour: Number(match[1]), minute: Number(match[2]) } : null;
}

export function daysInMonth(year: number, month: number): number {
  return new Date(Date.UTC(year, month, 0)).getUTCDate();
}

/** Monday-first weeks covering the month; days outside it are null. */
export function monthGrid(year: number, month: number): (DayValue | null)[][] {
  const first = new Date(Date.UTC(year, month - 1, 1)).getUTCDay(); // 0 Sunday
  const lead = (first + 6) % 7;
  const cells: (DayValue | null)[] = Array.from({ length: lead }, () => null);
  for (let day = 1; day <= daysInMonth(year, month); day += 1) cells.push({ year, month, day });
  while (cells.length % 7) cells.push(null);
  const weeks: (DayValue | null)[][] = [];
  for (let index = 0; index < cells.length; index += 7) weeks.push(cells.slice(index, index + 7));
  return weeks;
}

export function addDays(value: DayValue, days: number): DayValue {
  const date = new Date(Date.UTC(value.year, value.month - 1, value.day + days));
  return { year: date.getUTCFullYear(), month: date.getUTCMonth() + 1, day: date.getUTCDate() };
}

export function addMonths(value: DayValue, months: number): DayValue {
  const target = new Date(Date.UTC(value.year, value.month - 1 + months, 1));
  const year = target.getUTCFullYear();
  const month = target.getUTCMonth() + 1;
  return { year, month, day: Math.min(value.day, daysInMonth(year, month)) };
}

/** The day a calendar key moves focus to (the WAI-ARIA date-picker grid), or null. */
export function moveDay(value: DayValue, key: string, shift = false): DayValue | null {
  const weekday = (new Date(Date.UTC(value.year, value.month - 1, value.day)).getUTCDay() + 6) % 7;
  switch (key) {
    case "ArrowLeft":
      return addDays(value, -1);
    case "ArrowRight":
      return addDays(value, 1);
    case "ArrowUp":
      return addDays(value, -7);
    case "ArrowDown":
      return addDays(value, 7);
    case "Home":
      return addDays(value, -weekday);
    case "End":
      return addDays(value, 6 - weekday);
    case "PageUp":
      return addMonths(value, shift ? -12 : -1);
    case "PageDown":
      return addMonths(value, shift ? 12 : 1);
    default:
      return null;
  }
}

export function clampDay(value: DayValue, min?: string, max?: string): DayValue {
  const key = dayKey(value);
  if (min && key < min) return parseDay(min) ?? value;
  if (max && key > max) return parseDay(max) ?? value;
  return value;
}

export function weekdayLabels(language: string): string[] {
  return isZh(language) ? ZH_WEEKDAYS : EN_WEEKDAYS;
}

export function monthLabel(month: number, language: string): string {
  return isZh(language) ? `${month}月` : EN_MONTHS[month - 1]!;
}

/** "Nov 2026" / "2026年11月": the calendar's heading and a month value's text. */
export function monthYearLabel(year: number, month: number, language: string): string {
  return isZh(language) ? `${year}年${month}月` : `${EN_MONTHS[month - 1]} ${year}`;
}

/** What the control shows for its value, in the app's language (never the device's). */
export function periodText(kind: PeriodKind, value: string | null | undefined, language: string): string {
  if (kind === "month") {
    const parsed = parseMonth(value);
    return parsed ? monthYearLabel(parsed.year, parsed.month, language) : "";
  }
  const day = parseDay(value);
  if (!day) return "";
  const date = isZh(language) ? `${day.year}年${day.month}月${day.day}日` : `${day.day} ${EN_MONTHS[day.month - 1]} ${day.year}`;
  if (kind !== "datetime") return date;
  const time = parseTime(value);
  return time ? `${date} ${pad(time.hour)}:${pad(time.minute)}` : date;
}

export function withTime(day: string, hour: number, minute: number): string {
  return `${day}T${pad(hour)}:${pad(minute)}`;
}

/** Today on this device's calendar (a gas day is chosen in the desk's terms, not a zone's). */
export function todayValue(now = new Date()): DayValue {
  return { year: now.getFullYear(), month: now.getMonth() + 1, day: now.getDate() };
}
