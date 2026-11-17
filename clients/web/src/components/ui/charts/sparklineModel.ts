/**
 * The sparkline's pure part: where each point sits, which point a pointer or a key reaches,
 * and what the line says to assistive technology. No DOM, no chart library (the sparkline is a
 * light inline SVG that works before the chart library loads); tested in
 * tests/sparklineModel.test.ts.
 *
 * - x follows time, not the index: a missing gas day leaves a gap where it would be.
 * - A null value is a gap: the line breaks there, it is never interpolated.
 * - Only points with a value can be reached by the pointer or the keys.
 */
import { gasDayStartUtc } from "../../../app/tradingContext.ts";
import { gasDayLabel } from "./chartModel.ts";

export type SparkAxis = "gas-day" | "time";

export interface SparkPoint {
  /** Index into the series. */
  index: number;
  x: number;
  y: number;
  value: number;
  key: string;
}

export interface SparkGeometry {
  points: SparkPoint[];
  /** Runs of consecutive points with values (a null or a missing day breaks the run). */
  segments: SparkPoint[][];
  /** Positions in `points` of the lowest, highest and last values. */
  min: number;
  max: number;
  last: number;
}

function instantOf(axis: SparkAxis, key: string): number {
  return axis === "gas-day" ? gasDayStartUtc(key) : Date.parse(key);
}

/** The typical step between keys (the median), so a missing day can be told from a normal one. */
function typicalStep(instants: number[]): number {
  const steps = instants.slice(1).map((value, index) => value - instants[index]).filter((step) => step > 0).sort((a, b) => a - b);
  return steps.length ? steps[Math.floor(steps.length / 2)] : 0;
}

export function sparkGeometry(
  values: readonly (number | null)[],
  keys: readonly string[],
  options: { axis?: SparkAxis; width: number; height: number; pad?: number },
): SparkGeometry {
  const axis = options.axis ?? "gas-day";
  const pad = options.pad ?? 3;
  const count = Math.min(values.length, keys.length);
  const instants = keys.slice(0, count).map((key, index) => {
    const at = instantOf(axis, key);
    return Number.isFinite(at) ? at : index;
  });
  const known = values.slice(0, count).filter((value): value is number => value !== null && Number.isFinite(value));
  const empty: SparkGeometry = { points: [], segments: [], min: -1, max: -1, last: -1 };
  if (known.length === 0) return empty;
  const low = Math.min(...known);
  const high = Math.max(...known);
  const span = high - low || 1;
  const first = instants[0];
  const range = instants[count - 1] - first || 1;
  const innerWidth = Math.max(1, options.width - 2 * pad);
  const innerHeight = Math.max(1, options.height - 2 * pad);
  const step = typicalStep(instants);
  const points: SparkPoint[] = [];
  const segments: SparkPoint[][] = [];
  let run: SparkPoint[] = [];
  for (let index = 0; index < count; index += 1) {
    const value = values[index];
    if (value === null || value === undefined || !Number.isFinite(value)) {
      if (run.length) segments.push(run);
      run = [];
      continue;
    }
    const point: SparkPoint = {
      index,
      x: pad + ((instants[index] - first) / range) * innerWidth,
      y: pad + (1 - (value - low) / span) * innerHeight,
      value,
      key: keys[index],
    };
    // A day missing from the keys is a gap too: more than one and a half usual steps apart.
    const previous = run[run.length - 1];
    if (previous && step > 0 && instants[index] - instants[previous.index] > step * 1.5) {
      segments.push(run);
      run = [];
    }
    run.push(point);
    points.push(point);
  }
  if (run.length) segments.push(run);
  let min = 0;
  let max = 0;
  points.forEach((point, position) => {
    if (point.value < points[min].value) min = position;
    if (point.value > points[max].value) max = position;
  });
  return { points, segments, min, max, last: points.length - 1 };
}

/** SVG path data for the segments (one `M … L …` run per segment; a lone point is a dot). */
export function sparkPath(segments: readonly SparkPoint[][]): string {
  return segments
    .filter((segment) => segment.length > 1)
    .map((segment) => segment.map((point, index) => `${index === 0 ? "M" : "L"}${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(" "))
    .join(" ");
}

/** The point nearest a pointer's x (positions in `points`), snapping to data points. */
export function nearestPoint(points: readonly SparkPoint[], x: number): number {
  if (points.length === 0) return -1;
  let best = 0;
  for (let position = 1; position < points.length; position += 1) {
    if (Math.abs(points[position].x - x) < Math.abs(points[best].x - x)) best = position;
  }
  return best;
}

/** The point a key moves to from `current` (-1: none yet, the keys start at the last point). */
export function stepPoint(count: number, current: number, key: string): number | null {
  if (count === 0) return null;
  const from = current < 0 ? count - 1 : current;
  if (key === "ArrowLeft" || key === "ArrowDown") return current < 0 ? from : Math.max(0, from - 1);
  if (key === "ArrowRight" || key === "ArrowUp") return current < 0 ? from : Math.min(count - 1, from + 1);
  if (key === "Home") return 0;
  if (key === "End") return count - 1;
  return null;
}

/** "15 Nov 2026" for a gas day, "15 Nov 2026 09:00 UTC" for an instant. */
export function sparkWhen(axis: SparkAxis, key: string): string {
  if (axis === "gas-day") return gasDayLabel(key, true);
  const at = new Date(key);
  if (Number.isNaN(at.getTime())) return key;
  const day = at.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  return `${day} ${at.toISOString().slice(11, 16)} UTC`;
}

/** A value with its unit, in tabular-figure style ("72.6 %", "9,274 GWh/d"). */
export function sparkValue(value: number, unit: string, decimals: number): string {
  const text = value.toLocaleString("en-GB", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  return unit ? `${text} ${unit}` : text;
}

export interface SparkSummary {
  first: string;
  firstWhen: string;
  last: string;
  lastWhen: string;
  min: string;
  max: string;
  count: number;
}

/** The facts the accessible name states: first, last, low, high and the period. */
export function sparkSummary(geometry: SparkGeometry, axis: SparkAxis, unit: string, decimals: number): SparkSummary | null {
  const { points } = geometry;
  if (points.length === 0) return null;
  const first = points[0];
  const last = points[geometry.last];
  return {
    first: sparkValue(first.value, unit, decimals),
    firstWhen: sparkWhen(axis, first.key),
    last: sparkValue(last.value, unit, decimals),
    lastWhen: sparkWhen(axis, last.key),
    min: sparkValue(points[geometry.min].value, unit, decimals),
    max: sparkValue(points[geometry.max].value, unit, decimals),
    count: points.length,
  };
}
