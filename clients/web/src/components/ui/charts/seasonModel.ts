/**
 * Seasonality against history (F.1, F.2), the pure part: the gas-year axis, the years a band
 * may be drawn from, and the band itself. No DOM; tested in tests/chartStandard.test.ts.
 *
 * The season axis has 365 days keyed "MM-DD" from the season's first month (October for the
 * gas year, January for a calendar year). 29 February has no slot: a leap year's 29 February
 * value is left out, so every year draws on the same 365 days and no ordinary year shows a
 * one-day gap where it has no 29 February.
 *
 * The history rule (F.2), applied by `historyPlan` so no caller words a band by hand:
 * - fewer than one complete prior year held: no band; the subtitle says "history from <date>";
 * - one to four complete prior years: each as a thin grey line, labelled "N prior years held";
 * - five or more: the min–max band and mean of the last five complete years, labelled
 *   "5-yr range 2021/22–2025/26"; last year stays a thin line.
 * The band is never drawn from fewer years than its label says: `bandFromYears` leaves a gap
 * at any day where one of the years has no value.
 */

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];

/** The gas year starts on 1 October. */
export const GAS_YEAR_START_MONTH = 10;
/** Most prior years a band is drawn from (F.2). */
export const BAND_YEARS = 5;

/** The 365 day keys of a season in order ("10-01" … "09-30" for a gas year). */
export function seasonKeys(startMonth = GAS_YEAR_START_MONTH): string[] {
  const keys: string[] = [];
  for (let step = 0; step < 12; step += 1) {
    const month = ((startMonth - 1 + step) % 12) + 1;
    for (let day = 1; day <= DAYS_IN_MONTH[month - 1]; day += 1) {
      keys.push(`${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`);
    }
  }
  return keys;
}

/** "11-17" -> "17 Nov" (a day of the season, any year). */
export function seasonLabel(key: string): string {
  const match = /^(\d{2})-(\d{2})$/.exec(key);
  if (!match) return key;
  return `${Number(match[2])} ${MONTHS[Number(match[1]) - 1]}`;
}

/** Month-start ticks of a season axis, at most `maxTicks` (every n-th month), with labels. */
export function seasonTicks(keys: readonly string[], maxTicks: number): { index: number; label: string }[] {
  const starts = keys
    .map((key, index) => ({ key, index }))
    .filter(({ key }) => key.endsWith("-01"));
  const every = Math.max(1, Math.ceil(starts.length / Math.max(2, Math.floor(maxTicks))));
  return starts
    .filter((_, position) => position % every === 0)
    .map(({ key, index }) => ({ index, label: MONTHS[Number(key.slice(0, 2)) - 1] }));
}

/** The season a calendar day belongs to: "2025/26" for a gas year, "2025" for a calendar year. */
export function seasonOf(day: string, startMonth = GAS_YEAR_START_MONTH): string {
  const year = Number(day.slice(0, 4));
  const month = Number(day.slice(5, 7));
  if (startMonth === 1) return String(year);
  const first = month >= startMonth ? year : year - 1;
  return `${first}/${String((first + 1) % 100).padStart(2, "0")}`;
}

/** Where a calendar day sits on the season axis; -1 for 29 February (no slot). */
export function seasonIndex(day: string, startMonth = GAS_YEAR_START_MONTH): number {
  const month = Number(day.slice(5, 7));
  const date = Number(day.slice(8, 10));
  if (month === 2 && date === 29) return -1;
  let index = 0;
  for (let step = 0; step < 12; step += 1) {
    const m = ((startMonth - 1 + step) % 12) + 1;
    if (m === month) return index + date - 1;
    index += DAYS_IN_MONTH[m - 1];
  }
  return -1;
}

/** Calendar days into seasons: values per season on the 365-day axis, null where not held. */
export function bySeason(
  points: readonly { day: string; value: number | null }[],
  startMonth = GAS_YEAR_START_MONTH,
): Map<string, (number | null)[]> {
  const seasons = new Map<string, (number | null)[]>();
  for (const point of points) {
    const at = seasonIndex(point.day, startMonth);
    if (at < 0 || point.value == null || !Number.isFinite(point.value)) continue;
    const key = seasonOf(point.day, startMonth);
    let values = seasons.get(key);
    if (!values) {
      values = new Array<number | null>(365).fill(null);
      seasons.set(key, values);
    }
    values[at] = point.value;
  }
  return seasons;
}

/** A season counts as held when at least this share of its days has a value. */
export const COMPLETE_SHARE = 0.95;

/** True when a season's values cover enough days to count as a complete year held. */
export function isCompleteSeason(values: readonly (number | null)[]): boolean {
  const held = values.filter((value) => value != null && Number.isFinite(value)).length;
  return held >= Math.ceil(COMPLETE_SHARE * 365);
}

export type HistoryMode = "none" | "lines" | "band";

export interface HistoryPlan {
  mode: HistoryMode;
  /** The prior seasons drawn (lines) or behind the band, oldest first. */
  years: string[];
  /** The label's i18n key and its values; the text says exactly `years.length` years. */
  label: { key: string; values: Record<string, string | number> };
}

/**
 * The F.2 rule. `complete` are the complete prior seasons held (any order); `historyFrom` is
 * the first day held, said when there is no complete prior year.
 */
export function historyPlan(complete: readonly string[], historyFrom: string | null = null): HistoryPlan {
  const years = [...new Set(complete)].sort();
  if (years.length === 0) {
    return { mode: "none", years: [], label: { key: "chart.history.from", values: { date: historyFrom ?? "" } } };
  }
  if (years.length < BAND_YEARS) {
    return { mode: "lines", years, label: { key: years.length === 1 ? "chart.history.one_year" : "chart.history.years_held", values: { count: years.length } } };
  }
  const used = years.slice(-BAND_YEARS);
  return {
    mode: "band",
    years: used,
    label: { key: "chart.history.range", values: { count: used.length, first: used[0], last: used[used.length - 1] } },
  };
}

export interface BandValues {
  low: (number | null)[];
  high: (number | null)[];
  mean: (number | null)[];
  /** How many years the band is drawn from: every non-null point uses exactly this many. */
  years: number;
}

/**
 * Min, max and mean across the years at each day; a day where any year has no value is a gap
 * in all three, so no point of the band rests on fewer years than `years`.
 */
export function bandFromYears(series: readonly (readonly (number | null)[])[]): BandValues {
  const length = Math.max(0, ...series.map((values) => values.length));
  const low: (number | null)[] = [];
  const high: (number | null)[] = [];
  const mean: (number | null)[] = [];
  for (let index = 0; index < length; index += 1) {
    const values = series.map((values) => values[index]);
    if (series.length === 0 || values.some((value) => value == null || !Number.isFinite(value))) {
      low.push(null);
      high.push(null);
      mean.push(null);
      continue;
    }
    const known = values as number[];
    low.push(Math.min(...known));
    high.push(Math.max(...known));
    mean.push(known.reduce((sum, value) => sum + value, 0) / known.length);
  }
  return { low, high, mean, years: series.length };
}

/**
 * A percentile band (for example p10–p90) by linear interpolation between ranks, with the
 * same gap rule as the min–max band.
 */
export function percentileBandFromYears(
  series: readonly (readonly (number | null)[])[],
  lowPct: number,
  highPct: number,
): { low: (number | null)[]; high: (number | null)[] } {
  const length = Math.max(0, ...series.map((values) => values.length));
  const low: (number | null)[] = [];
  const high: (number | null)[] = [];
  for (let index = 0; index < length; index += 1) {
    const values = series.map((values) => values[index]);
    if (series.length === 0 || values.some((value) => value == null || !Number.isFinite(value))) {
      low.push(null);
      high.push(null);
      continue;
    }
    const sorted = (values as number[]).slice().sort((a, b) => a - b);
    low.push(quantile(sorted, lowPct / 100));
    high.push(quantile(sorted, highPct / 100));
  }
  return { low, high };
}

/** Linear-interpolation quantile of sorted values (the spreadsheet PERCENTILE.INC rule). */
export function quantile(sorted: readonly number[], share: number): number {
  if (sorted.length === 0) return Number.NaN;
  const position = Math.min(1, Math.max(0, share)) * (sorted.length - 1);
  const below = Math.floor(position);
  const above = Math.ceil(position);
  return sorted[below] + (sorted[above] - sorted[below]) * (position - below);
}
