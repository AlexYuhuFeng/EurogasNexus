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

export type ChartAxis = "gas-day" | "period" | "time";
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
  /** Decimals in the tooltip, table and export (default 2). */
  decimals?: number;
}

export interface ChartData {
  axis: ChartAxis;
  /** One key per point: gas days, delivery periods or ISO instants. */
  x: readonly string[];
  /** The x column's name in the table and the export ("Gas day", "Delivery month"). */
  xTitle: string;
  /** The unit of every series ("GWh/d", "EUR/MWh", "%"): one axis, one unit. */
  unit: string;
  series: readonly ChartSeries[];
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
  if (data.axis === "period") return data.x.map((_, index) => index);
  if (data.axis === "gas-day") return data.x.map((day) => gasDayStartUtc(day) / 1000);
  return data.x.map((instant) => Date.parse(instant) / 1000);
}

/** How a point's x reads in a tooltip, a table row and the export. */
export function xLabel(axis: ChartAxis, key: string): string {
  if (axis === "period") return periodLabel(key);
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
  const header = [data.xTitle, ...data.series.map((item) => `${item.label}${item.simulated ? " [simulated]" : ""} (${data.unit})`)];
  const lines = [header.map(csvCell).join(",")];
  data.x.forEach((key, index) => {
    const cells = [key];
    for (const item of data.series) {
      const value = item.values[index];
      cells.push(value == null || !Number.isFinite(value) ? "" : String(Number(value.toFixed(item.decimals ?? 4))));
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
