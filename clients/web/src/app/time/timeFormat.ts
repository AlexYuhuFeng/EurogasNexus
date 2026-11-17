/**
 * The one way an instant is shown (docs/product/UX_REFERENCE.md, "Time rule").
 *
 * Instants are stored and transported in UTC. On screen they are shown in the zone the reader
 * chose (Account → Preferences → "Times shown in"): their device's zone (the default), UTC, or the
 * gas market's time (CET/CEST, Europe/Berlin). The zone is always named next to a short time
 * ("00:57 CET", "23:57 UTC", "08:57 GMT+8"), because a desk compares times across offices and a
 * server's clock is not the reader's. The date appears only when it is not today in that zone;
 * seconds only when the screen asks for them. The full instant (date, seconds, zone, and its UTC
 * form) is the tooltip.
 *
 * Gas days are not instants: a gas day stays the gas day it is, whatever the zone (format it with
 * `formatGasDay`). Words and numbers follow the app's language, never the browser's.
 *
 * Pure: everything it needs is a parameter, so it is tested without a browser.
 */

export type TimeZonePreference = "device" | "utc" | "market";

export const TIME_ZONE_PREFERENCES: readonly TimeZonePreference[] = ["device", "utc", "market"];

/** The gas market's clock: CET in winter, CEST in summer (the gas day runs 06:00 to 06:00 CET). */
export const MARKET_TIME_ZONE = "Europe/Berlin";

export function isTimeZonePreference(value: unknown): value is TimeZonePreference {
  return value === "device" || value === "utc" || value === "market";
}

/** The IANA zone a preference resolves to on this device. */
export function resolveTimeZone(preference: TimeZonePreference, deviceZone?: string): string {
  if (preference === "utc") return "UTC";
  if (preference === "market") return MARKET_TIME_ZONE;
  if (deviceZone) return deviceZone;
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

/** The app language's formatting locale: English reads "16 Nov", Chinese "11月16日". */
export function formattingLocale(language: string | null | undefined): string {
  return String(language ?? "").toLowerCase().startsWith("zh") ? "zh-CN" : "en-GB";
}

export interface InstantFormatOptions {
  /** App language (i18n.language), never navigator.language. */
  language: string;
  preference: TimeZonePreference;
  /** Device zone override (tests); defaults to the runtime's. */
  deviceZone?: string;
  /** "Now", for "is it today?" (tests pass a fixed instant). */
  nowMs?: number;
  /** Show seconds (a screen that needs them: an audit trail, a fill time). */
  seconds?: boolean;
  /** `auto` (default): the date only when not today in the shown zone. */
  date?: "auto" | "always" | "never";
}

export interface FormattedInstant {
  /** What the line shows: "00:57 CET", "16 Nov 00:57 UTC". */
  text: string;
  /** The tooltip: the full instant in the shown zone, and in UTC when that is not the zone. */
  title: string;
  /** The instant itself (ISO 8601, UTC) for `<time dateTime>`. */
  iso: string;
  /** The zone label used ("CET", "UTC", "GMT+8"). */
  zone: string;
}

/**
 * A zone's short name at an instant. English names are used in both languages: "CET", "CEST",
 * "UTC" and "GMT+8" are what a desk writes, and a Chinese "GMT+8" reads the same.
 */
export function zoneAbbreviation(instant: Date, timeZone: string): string {
  try {
    const part = new Intl.DateTimeFormat("en-GB", { timeZone, timeZoneName: "short" })
      .formatToParts(instant)
      .find((item) => item.type === "timeZoneName");
    return part?.value ?? timeZone;
  } catch {
    return timeZone;
  }
}

/** The desk's month names in English ("Sep", never ICU's "Sept"); Chinese uses its own form. */
const EN_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function yearOf(instant: Date, timeZone: string): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric" }).format(instant);
}

function shortDate(instant: Date, timeZone: string, locale: string, withYear: boolean): string {
  if (locale === "zh-CN") {
    return new Intl.DateTimeFormat(locale, { timeZone, day: "numeric", month: "short", year: withYear ? "numeric" : undefined }).format(instant);
  }
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "numeric", day: "numeric" }).formatToParts(instant);
  const part = (type: string) => parts.find((item) => item.type === type)?.value ?? "";
  const text = `${Number(part("day"))} ${EN_MONTHS[Number(part("month")) - 1]}`;
  return withYear ? `${text} ${part("year")}` : text;
}

function dayKey(instant: Date, timeZone: string): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).format(instant);
}

function parse(value: string | number | Date | null | undefined): Date | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = value instanceof Date ? value : new Date(value);
  return Number.isFinite(parsed.getTime()) ? parsed : null;
}

/** The instant shown in the reader's zone, or null when there is no usable instant. */
export function formatInstant(
  value: string | number | Date | null | undefined,
  options: InstantFormatOptions,
): FormattedInstant | null {
  const instant = parse(value);
  if (!instant) return null;
  const timeZone = resolveTimeZone(options.preference, options.deviceZone);
  const locale = formattingLocale(options.language);
  const zone = zoneAbbreviation(instant, timeZone);
  const now = new Date(options.nowMs ?? Date.now());
  const showDate =
    options.date === "always" || (options.date !== "never" && dayKey(instant, timeZone) !== dayKey(now, timeZone));
  const time = new Intl.DateTimeFormat(locale, {
    timeZone,
    hour: "2-digit",
    minute: "2-digit",
    second: options.seconds ? "2-digit" : undefined,
    hourCycle: "h23",
  }).format(instant);
  const date = showDate
    ? shortDate(instant, timeZone, locale, options.date === "always" || yearOf(instant, timeZone) !== yearOf(now, timeZone))
    : "";
  const text = `${date ? `${date} ` : ""}${time} ${zone}`;
  const fullTime = new Intl.DateTimeFormat(locale, {
    timeZone,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).format(instant);
  const full = `${shortDate(instant, timeZone, locale, true)} ${fullTime} ${zone}`;
  const utc = `${instant.toISOString().slice(0, 19).replace("T", " ")} UTC`;
  return {
    text,
    title: timeZone === "UTC" ? utc : `${full} (${utc})`,
    iso: instant.toISOString(),
    zone,
  };
}

/** A gas day ("2026-11-16") as the desk writes it ("16 Nov", "11月16日"); never zone-shifted. */
export function formatGasDay(gasDay: string | null | undefined, language: string, withYear = false): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(gasDay ?? ""));
  if (!match) return String(gasDay ?? "");
  const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
  return shortDate(date, "UTC", formattingLocale(language), withYear);
}
