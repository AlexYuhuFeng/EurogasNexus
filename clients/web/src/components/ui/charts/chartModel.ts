/**
 * The chart layer's pure part (UX-09): what is plotted, where the ticks go, how stacks are
 * built and what the CSV export says. No DOM and no uPlot here, so every rule is tested with
 * `node --test` and the drawing component only draws.
 *
 * Axes:
 * - `gas-day`: one value per gas day ("2026-11-16"). The x value is the gas day's start instant
 *   (05:00 UTC in winter, 04:00 UTC in summer, `gasDayStartUtc`), so ticks sit at gas-day
 *   starts, never at midnight, and the label is the gas day itself, whatever the viewer's zone.
 * - `period`: one value per delivery period ("2026-12" month, or any product label): ordinal
 *   positions with the desk's names ("Dec-26").
 * - `time`: instants (ISO strings) for intraday series.
 *
 * Missing data is `null` and is drawn as a gap, never as zero.
 */
import { gasDayStartUtc } from "../../../app/tradingContext.ts";
import { seasonLabel } from "./seasonModel.ts";

/**
 * `season`: one value per day of a gas (or calendar) year, keyed "MM-DD" in season order
 * (`seasonModel.seasonKeys`): years laid over each other on one Oct–Sep axis.
 */
export type ChartAxis = "gas-day" | "period" | "time" | "season";
export type SeriesStyle = "line" | "step" | "area" | "bar" | "points";

export interface ChartSeries {
  id: string;
  /** Legend and tooltip name ("Norway", "TTF"). */
  label: string;
  values: readonly (number | null)[];
  style?: SeriesStyle;
  /** Simulated (demo) values: drawn dashed and labelled, never read as a market price. */
  simulated?: boolean;
  /** Index of the first forecast point: from here the series is drawn dashed. */
  forecastFrom?: number;
  /** Stacked with the other stacked series of the chart (bars or areas). */
  stack?: boolean;
  /** Position in the token palette (`--ds-series-N`, 1-based); defaults to the order given. */
  colour?: number;
  /** A reference line (target, zero): drawn thin and neutral, not a data series. */
  reference?: boolean;
  /**
   * Context, not the subject: last year, a prior close, a week ago. Drawn as a thin grey line
   * under the data, labelled at its end like any other line (F.2 "context in grey").
   */
  ghost?: boolean;
  /** Decimals in the tooltip, table and export (default 2). */
  decimals?: number;
}

/**
 * A history band: the range of the prior years actually held at each x (min–max, or a
 * percentile range), and their mean. `years` is what the band was drawn from; a point where
 * any of those years is missing is a gap, so the band never claims more years than it has.
 */
export interface ChartBand {
  id: string;
  /** "5-yr range 2021/22–2025/26": built by `historyPlan`, never by hand. */
  label: string;
  /** The years behind the band ("2021/22" …), oldest first. */
  years: readonly string[];
  low: readonly (number | null)[];
  high: readonly (number | null)[];
  /** The mean of the same years, drawn as a thin grey line ("5-yr mean"). */
  mean?: readonly (number | null)[];
  meanLabel?: string;
}

/** A horizontal rule with a direct label: zero, a target, a cost threshold (F.2). */
export interface ChartRule {
  id: string;
  value: number;
  /** "target 90 %", "route cost 0.97"; the zero line needs none. */
  label?: string;
  kind?: "zero" | "target" | "threshold";
}

export interface ChartData {
  axis: ChartAxis;
  /** One key per point: gas days, delivery periods, ISO instants or season days ("10-01"). */
  x: readonly string[];
  /** The x column's name in the table and the export ("Gas day", "Delivery month"). */
  xTitle: string;
  /** The unit of every series ("GWh/d", "EUR/MWh", "%"): one axis, one unit. */
  unit: string;
  series: readonly ChartSeries[];
  /** History bands drawn under the series (at most one is usual). */
  bands?: readonly ChartBand[];
  /** Horizontal rules drawn over the grid, under the series. */
  rules?: readonly ChartRule[];
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-12" -> "Dec-26"; anything else is returned as it is (a product label). */
export function periodLabel(key: string): string {
  const match = /^(\d{4})-(\d{2})$/.exec(key);
  if (!match) return key;
  return `${MONTHS[Number(match[2]) - 1]}-${match[1].slice(2)}`;
}

/** "2026-11-16" -> "16 Nov" (the gas day, not a calendar instant). */
export function gasDayLabel(key: string, withYear = false): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(key);
  if (!match) return key;
  const label = `${Number(match[3])} ${MONTHS[Number(match[2]) - 1]}`;
  return withYear ? `${label} ${match[1]}` : label;
}

/** The x value uPlot plots: seconds for gas days and instants, the ordinal for periods. */
export function xValues(data: Pick<ChartData, "axis" | "x">): number[] {
  if (data.axis === "period" || data.axis === "season") return data.x.map((_, index) => index);
  if (data.axis === "gas-day") return data.x.map((day) => gasDayStartUtc(day) / 1000);
  return data.x.map((instant) => Date.parse(instant) / 1000);
}

/** How a point's x reads in a tooltip, a table row and the export. */
export function xLabel(axis: ChartAxis, key: string): string {
  if (axis === "period") return periodLabel(key);
  if (axis === "season") return seasonLabel(key);
  if (axis === "gas-day") return gasDayLabel(key, true);
  const instant = new Date(key);
  return Number.isNaN(instant.getTime()) ? key : `${instant.toISOString().slice(0, 16).replace("T", " ")} UTC`;
}

const GAS_DAY_STEPS = [1, 2, 3, 7, 14];

/**
 * Indices of the gas days that carry a tick, at most `maxTicks`: every day, every second …
 * every 14th, else the first gas day of each month (or of every second, third … month).
 * Weekly steps start on the series' last day and count back, so today always has a tick.
 */
export function gasDayTicks(days: readonly string[], maxTicks: number): number[] {
  const count = days.length;
  if (count === 0) return [];
  const budget = Math.max(2, Math.floor(maxTicks));
  for (const step of GAS_DAY_STEPS) {
    if (Math.ceil(count / step) <= budget) {
      const ticks: number[] = [];
      for (let index = count - 1; index >= 0; index -= step) ticks.unshift(index);
      return ticks;
    }
  }
  const monthStarts = days
    .map((day, index) => ({ day, index }))
    .filter(({ day, index }) => index === 0 ? day.endsWith("-01") : day.slice(0, 7) !== days[index - 1].slice(0, 7))
    .map(({ index }) => index);
  const every = Math.max(1, Math.ceil(monthStarts.length / budget));
  return monthStarts.filter((_, position) => position % every === 0);
}

/** Indices of the delivery periods that carry a tick, at most `maxTicks`, first one always. */
export function periodTicks(count: number, maxTicks: number): number[] {
  if (count <= 0) return [];
  const step = Math.max(1, Math.ceil(count / Math.max(2, Math.floor(maxTicks))));
  const ticks: number[] = [];
  for (let index = 0; index < count; index += step) ticks.push(index);
  return ticks;
}

/** How many labels fit across `widthPx` at about `labelPx` each. */
export function tickBudget(widthPx: number, labelPx = 64): number {
  return Math.max(2, Math.floor(widthPx / labelPx));
}

/**
 * Bases of the stacked series: positive values stack up from zero, negative values down from
 * zero (a storage injection under the supply bars), each series on the ones before it. A missing
 * value adds nothing and leaves its own point missing.
 */
export function stackBases(series: readonly ChartSeries[], length: number): Map<string, (number | null)[]> {
  const up = new Array<number>(length).fill(0);
  const down = new Array<number>(length).fill(0);
  const bases = new Map<string, (number | null)[]>();
  for (const item of series) {
    if (!item.stack) continue;
    const base: (number | null)[] = [];
    for (let index = 0; index < length; index += 1) {
      const value = item.values[index];
      if (value == null || !Number.isFinite(value)) {
        base.push(null);
      } else if (value >= 0) {
        base.push(up[index]);
        up[index] += value;
      } else {
        base.push(down[index]);
        down[index] += value;
      }
    }
    bases.set(item.id, base);
  }
  return bases;
}

/** The value range the y axis must show: every point, every stack top, zero under bars. */
export function valueRange(data: ChartData): [number, number] | null {
  let min = Infinity;
  let max = -Infinity;
  const bases = stackBases(data.series, data.x.length);
  for (const item of data.series) {
    const base = bases.get(item.id);
    item.values.forEach((value, index) => {
      if (value == null || !Number.isFinite(value)) return;
      const from = base?.[index] ?? 0;
      const to = base ? from + value : value;
      min = Math.min(min, to, base || item.style === "bar" ? from : to);
      max = Math.max(max, to, base || item.style === "bar" ? from : to);
    });
  }
  for (const band of data.bands ?? []) {
    for (const values of [band.low, band.high, band.mean ?? []]) {
      for (const value of values) {
        if (value == null || !Number.isFinite(value)) continue;
        min = Math.min(min, value);
        max = Math.max(max, value);
      }
    }
  }
  // A rule only widens a range that has data: a target alone is not a chart.
  if (Number.isFinite(min)) {
    for (const rule of data.rules ?? []) {
      if (!Number.isFinite(rule.value)) continue;
      min = Math.min(min, rule.value);
      max = Math.max(max, rule.value);
    }
  }
  if (!Number.isFinite(min) || !Number.isFinite(max)) return null;
  if (min === max) return [min - 1, max + 1];
  const pad = (max - min) * 0.06;
  return [min >= 0 && min - pad < 0 ? 0 : min - pad, max <= 0 && max + pad > 0 ? 0 : max + pad];
}

/** A value with its decimals, tabular, "–" when missing (the table and tooltip use this). */
export function formatChartValue(value: number | null | undefined, decimals = 2): string {
  if (value == null || !Number.isFinite(value)) return "–";
  return value.toLocaleString("en-GB", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

/** Axis tick labels: the fewest decimals that keep the ticks distinct. */
export function axisTickLabels(ticks: readonly number[]): string[] {
  for (let decimals = 0; decimals <= 4; decimals += 1) {
    const labels = ticks.map((tick) => tick.toLocaleString("en-GB", { minimumFractionDigits: decimals, maximumFractionDigits: decimals }));
    if (new Set(labels).size === labels.length) return labels;
  }
  return ticks.map((tick) => String(tick));
}

function csvCell(value: string): string {
  return /[",\n]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
}

/**
 * The plotted data as CSV: the x column, then one column per series with the unit in its name
 * ("Norway (GWh/d)"), simulated series named as such. Missing values are empty cells, never 0.
 * Numbers are written plainly (no grouping) so a spreadsheet reads them.
 */
export function chartCsv(data: ChartData): string {
  const bands = data.bands ?? [];
  const header = [
    data.xTitle,
    ...data.series.map((item) => `${item.label}${item.simulated ? " [simulated]" : ""} (${data.unit})`),
    ...bands.flatMap((band) => [
      `${band.label} low (${data.unit})`,
      `${band.label} high (${data.unit})`,
      ...(band.mean ? [`${band.meanLabel ?? `${band.label} mean`} (${data.unit})`] : []),
    ]),
  ];
  const lines = [header.map(csvCell).join(",")];
  const number = (value: number | null | undefined, decimals = 4) =>
    value == null || !Number.isFinite(value) ? "" : String(Number(value.toFixed(decimals)));
  data.x.forEach((key, index) => {
    const cells = [key];
    for (const item of data.series) cells.push(number(item.values[index], item.decimals ?? 4));
    for (const band of bands) {
      cells.push(number(band.low[index]), number(band.high[index]));
      if (band.mean) cells.push(number(band.mean[index]));
    }
    lines.push(cells.map(csvCell).join(","));
  });
  return `${lines.join("\n")}\n`;
}

/** The index of the point nearest `index` that any series has a value at, moving by `step`. */
export function nextPointIndex(data: ChartData, index: number, step: number): number {
  const count = data.x.length;
  if (count === 0) return -1;
  let next = Math.min(count - 1, Math.max(0, index + step));
  const has = (at: number) => data.series.some((item) => !item.reference && item.values[at] != null);
  while (next > 0 && next < count - 1 && !has(next)) next += Math.sign(step) || 1;
  return next;
}

/**
 * Split a series at its forecast start into a measured and a forecast part sharing the joining
 * point, so the line is continuous but the forecast is drawn dashed.
 */
export function splitForecast(item: ChartSeries): [ChartSeries, ChartSeries | null] {
  const from = item.forecastFrom;
  if (from == null || from <= 0 || from >= item.values.length) return [item, null];
  const measured = item.values.map((value, index) => (index < from ? value : null));
  const forecast = item.values.map((value, index) => (index >= from - 1 ? value : null));
  return [
    { ...item, values: measured, forecastFrom: undefined },
    { ...item, id: `${item.id}:forecast`, values: forecast, forecastFrom: undefined },
  ];
}

/* ------------------------------------------------------------------ chart standard (F.2) */

/** At most this many series are labelled at their line ends; more get a legend (F.2). */
export const MAX_END_LABELS = 4;

/** The series that take an end label: data and ghost lines with a value, not references. */
export function labelledSeries(data: Pick<ChartData, "series">): ChartSeries[] {
  return data.series.filter(
    (item) => !item.reference && item.style !== "bar" && !item.stack && item.values.some((value) => value != null),
  );
}

/** True when the chart labels its line ends instead of drawing a legend. */
export function usesEndLabels(data: Pick<ChartData, "series" | "bands">): boolean {
  const lines = labelledSeries(data).length + (data.bands ?? []).filter((band) => band.mean).length;
  return lines > 0 && lines <= MAX_END_LABELS && !data.series.some((item) => item.style === "bar" || item.stack);
}

export interface EndLabel {
  id: string;
  /** "TTF 31.20", or the value alone when one line is drawn (the title names it). */
  text: string;
  value: number;
  index: number;
  ghost: boolean;
}

/** The text and anchor of each end label: each line's last value. */
export function endLabels(data: ChartData): EndLabel[] {
  const lines: { id: string; label: string; values: readonly (number | null)[]; decimals?: number; ghost: boolean }[] = [
    ...labelledSeries(data).map((item) => ({ id: item.id, label: item.label, values: item.values, decimals: item.decimals, ghost: Boolean(item.ghost) })),
    ...(data.bands ?? []).filter((band) => band.mean).map((band) => ({
      id: `${band.id}:mean`,
      label: band.meanLabel ?? band.label,
      values: band.mean!,
      decimals: data.series.find((item) => !item.ghost && !item.reference)?.decimals,
      ghost: true,
    })),
  ];
  const out: EndLabel[] = [];
  for (const line of lines) {
    let index = -1;
    for (let at = line.values.length - 1; at >= 0; at -= 1) {
      if (line.values[at] != null && Number.isFinite(line.values[at] as number)) {
        index = at;
        break;
      }
    }
    if (index < 0) continue;
    const value = line.values[index] as number;
    const number = formatChartValue(value, line.decimals ?? 2);
    out.push({ id: line.id, text: lines.length === 1 ? number : `${line.label} ${number}`, value, index, ghost: line.ghost });
  }
  return out;
}

/**
 * Direct labels pushed apart so no two are closer than `gap` (px): down from the highest,
 * then the block lifted off the bottom and, if it then crosses the top, spread evenly. The
 * same rule as the report exhibits (`reports/charts.py` `_place_labels`), so labels never
 * collide in either.
 */
export function placeEndLabels<T extends { y: number }>(items: readonly T[], top: number, bottom: number, gap = 14): (T & { placedY: number })[] {
  const placed = [...items].sort((a, b) => a.y - b.y);
  if (placed.length === 0) return [];
  const ys = placed.map((item) => item.y);
  ys[0] = Math.max(ys[0], top + 4);
  for (let index = 1; index < ys.length; index += 1) ys[index] = Math.max(ys[index], ys[index - 1] + gap);
  const overflow = ys[ys.length - 1] - bottom;
  if (overflow > 0) {
    for (let index = 0; index < ys.length; index += 1) ys[index] -= overflow;
    for (let index = ys.length - 2; index >= 0; index -= 1) ys[index] = Math.min(ys[index], ys[index + 1] - gap);
  }
  if (ys[0] < top + 4) {
    const step = ys.length > 1 ? Math.max(gap * 0.82, (bottom - top - 4) / (ys.length - 1)) : 0;
    for (let index = 0; index < ys.length; index += 1) ys[index] = top + 4 + index * step;
  }
  return placed.map((item, index) => ({ ...item, placedY: ys[index] }));
}

/** Room right of the plot for the longest end label (px), within a budget. */
export function endLabelRoom(labels: readonly EndLabel[], charPx = 6.6, budget = 150): number {
  const longest = Math.max(0, ...labels.map((label) => label.text.length));
  return longest === 0 ? 0 : Math.min(budget, Math.max(28, Math.ceil(longest * charPx + 10)));
}

/** The band's values at one point, for the readout ("5-yr range 60.1–78.3, mean 70.2"). */
export function bandAt(band: ChartBand, index: number): { low: number; high: number; mean: number | null } | null {
  const low = band.low[index];
  const high = band.high[index];
  if (low == null || high == null || !Number.isFinite(low) || !Number.isFinite(high)) return null;
  const mean = band.mean?.[index];
  return { low, high, mean: mean == null || !Number.isFinite(mean) ? null : mean };
}

/** A comparison the readout states: a series against a band's mean or another series. */
export interface ChartComparison {
  series: string;
  /** A band id (its mean), or a series id. */
  against: string;
  /** "vs 5-yr mean", "vs last year". */
  label: string;
}

/** The comparison's difference at one point (series minus reference), or null. */
export function compareAt(data: ChartData, comparison: ChartComparison, index: number): number | null {
  const subject = data.series.find((item) => item.id === comparison.series)?.values[index];
  if (subject == null || !Number.isFinite(subject)) return null;
  const band = data.bands?.find((item) => item.id === comparison.against);
  const reference = band ? band.mean?.[index] : data.series.find((item) => item.id === comparison.against)?.values[index];
  if (reference == null || !Number.isFinite(reference)) return null;
  return subject - reference;
}

/** A signed difference with a true minus ("−6.2", "+0.4"). */
export function formatSigned(value: number, decimals = 1): string {
  const text = formatChartValue(Math.abs(value), decimals);
  if (Math.abs(value) < 0.5 * 10 ** -decimals) return formatChartValue(0, decimals);
  return `${value < 0 ? "−" : "+"}${text}`;
}

/** One range for every panel of a small multiple, so the panels compare (F.2 default). */
export function sharedRange(datas: readonly ChartData[]): [number, number] | null {
  let low = Infinity;
  let high = -Infinity;
  for (const data of datas) {
    const range = valueRange(data);
    if (!range) continue;
    low = Math.min(low, range[0]);
    high = Math.max(high, range[1]);
  }
  return Number.isFinite(low) && Number.isFinite(high) ? [low, high] : null;
}

export interface SeriesFacts {
  label: string;
  first: string;
  firstAt: string;
  last: string;
  lastAt: string;
  min: string;
  max: string;
  count: number;
  simulated: boolean;
  ghost: boolean;
}

/** What a screen reader is told about each line (the chart's summary). */
export function summaryFacts(data: ChartData): SeriesFacts[] {
  return data.series
    .filter((item) => !item.reference)
    .map((item) => {
      const known = item.values
        .map((value, index) => ({ value, index }))
        .filter((point): point is { value: number; index: number } => point.value != null && Number.isFinite(point.value));
      if (known.length === 0) return null;
      const first = known[0];
      const last = known[known.length - 1];
      const values = known.map((point) => point.value);
      const decimals = item.decimals ?? 2;
      return {
        label: item.label,
        first: formatChartValue(first.value, decimals),
        firstAt: xLabel(data.axis, data.x[first.index] ?? ""),
        last: formatChartValue(last.value, decimals),
        lastAt: xLabel(data.axis, data.x[last.index] ?? ""),
        min: formatChartValue(Math.min(...values), decimals),
        max: formatChartValue(Math.max(...values), decimals),
        count: known.length,
        simulated: Boolean(item.simulated),
        ghost: Boolean(item.ghost),
      };
    })
    .filter((facts): facts is SeriesFacts => facts !== null);
}

/** A stack of daily values: an area beyond 14 points, bars up to 14 (F.1). */
export function stackForm(points: number): "area" | "bar" {
  return points > 14 ? "area" : "bar";
}

/**
 * At most `most` stack members, ordered by size (largest first, at the bottom), the rest summed
 * as one grey "Other" member (F.1: never more than five members). Missing values stay missing
 * unless another summed member has a value there.
 */
export function limitStack(series: readonly ChartSeries[], otherLabel: string, most = 4): ChartSeries[] {
  const size = (item: ChartSeries) => item.values.reduce<number>((sum, value) => sum + Math.abs(value ?? 0), 0);
  const ranked = [...series].sort((a, b) => size(b) - size(a));
  if (ranked.length <= most + 1) return ranked;
  const keep = ranked.slice(0, most);
  const rest = ranked.slice(most);
  const length = Math.max(...rest.map((item) => item.values.length));
  const values = Array.from({ length }, (_, index) => {
    const parts = rest.map((item) => item.values[index]).filter((value): value is number => value != null && Number.isFinite(value));
    return parts.length ? parts.reduce((sum, value) => sum + value, 0) : null;
  });
  return [...keep, { ...rest[0], id: "other", label: otherLabel, values, colour: 8, simulated: rest.some((item) => item.simulated) }];
}

/**
 * Where a value sits in a range, 0–100 (0 at the low, 100 at the high), for the percentile
 * strip; outside the range it is clamped and said so.
 */
export function rangePosition(value: number, low: number, high: number): { position: number; outside: "below" | "above" | null } {
  if (!(high > low)) return { position: 50, outside: null };
  const raw = ((value - low) / (high - low)) * 100;
  if (raw < 0) return { position: 0, outside: "below" };
  if (raw > 100) return { position: 100, outside: "above" };
  return { position: raw, outside: null };
}

/** The share (0–100) of a sample strictly below a value, ties counted half (percentile rank). */
export function percentileRank(value: number, sample: readonly number[]): number | null {
  const known = sample.filter((item) => Number.isFinite(item));
  if (known.length === 0 || !Number.isFinite(value)) return null;
  const below = known.filter((item) => item < value).length;
  const equal = known.filter((item) => item === value).length;
  return ((below + equal / 2) / known.length) * 100;
}
