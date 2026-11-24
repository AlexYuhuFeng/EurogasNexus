/**
 * The waterfall's pure part (F.1 "change between two states": a cargo's FOB → freight → regas →
 * entry, a P&L attribution, a balance revision). No DOM; tested in tests/chartStandard.test.ts.
 *
 * A step is a start or subtotal (`total`: a bar from zero) or a change (`delta`: a bar from the
 * running total to the running total plus the change). A `total` row states a figure; the
 * model checks it against the running sum, so a waterfall whose bars do not add up says so
 * instead of drawing a convincing picture of a wrong sum.
 */
import { plainDecimal } from "../../../app/time/valueFormat.ts";

export interface WaterfallItem {
  id: string;
  label: string;
  value: number;
  kind?: "total" | "delta";
  /** Simulated or assumed input: drawn hatched and named in the readout. */
  simulated?: boolean;
}

export interface WaterfallStep extends WaterfallItem {
  kind: "total" | "delta";
  /** Bar from `from` to `to` on the value axis. */
  from: number;
  to: number;
  /** For a total: the running sum it should equal; null for the first total (a start). */
  expected: number | null;
}

export interface WaterfallModel {
  steps: WaterfallStep[];
  min: number;
  max: number;
  /** Every total equals the running sum within `tolerance`. */
  reconciles: boolean;
  /** The largest total's difference from its running sum. */
  difference: number;
}

export function waterfallSteps(items: readonly WaterfallItem[], tolerance = 1e-6): WaterfallModel {
  const steps: WaterfallStep[] = [];
  let running: number | null = null;
  let worst = 0;
  for (const item of items) {
    const kind = item.kind ?? (running === null ? "total" : "delta");
    if (kind === "total") {
      const expected = running;
      if (expected !== null) worst = Math.max(worst, Math.abs(item.value - expected));
      steps.push({ ...item, kind, from: 0, to: item.value, expected });
      running = item.value;
    } else {
      const base: number = running ?? 0;
      steps.push({ ...item, kind, from: base, to: base + item.value, expected: null });
      running = base + item.value;
    }
  }
  const ends = steps.flatMap((step) => [step.from, step.to]);
  return {
    steps,
    min: Math.min(0, ...ends),
    max: Math.max(0, ...ends),
    reconciles: worst <= tolerance,
    difference: worst,
  };
}

export interface WaterfallBar {
  id: string;
  /** Position along the category axis and the bar's extent along the value axis, in px. */
  band: number;
  thickness: number;
  start: number;
  end: number;
  sign: "up" | "down" | "total";
}

/**
 * Bar geometry: `vertical` puts categories along x (desktop), horizontal along y (phone). The
 * value axis runs from `model.min` to `model.max` over `length` px; categories share `span`.
 */
export function waterfallGeometry(model: WaterfallModel, span: number, length: number, vertical: boolean): WaterfallBar[] {
  const count = Math.max(1, model.steps.length);
  const slot = span / count;
  const thickness = Math.max(4, Math.min(slot * 0.66, 56));
  const range = model.max - model.min || 1;
  const pos = (value: number) => {
    const share = (value - model.min) / range;
    return vertical ? length - share * length : share * length;
  };
  return model.steps.map((step, index) => ({
    id: step.id,
    band: slot * index + (slot - thickness) / 2,
    thickness,
    start: pos(step.from),
    end: pos(step.to),
    sign: step.kind === "total" ? "total" : step.to >= step.from ? "up" : "down",
  }));
}

/** The waterfall as CSV: step, kind, change, running total (missing nothing, plain numbers). */
export function waterfallCsv(model: WaterfallModel, unit: string, header: { step: string; change: string; total: string }): string {
  const cell = (value: string) => (/[",\n]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value);
  const lines = [[header.step, `${header.change} (${unit})`, `${header.total} (${unit})`].map(cell).join(",")];
  for (const step of model.steps) {
    const change = step.kind === "total" ? "" : String(Number(plainDecimal(step.value, 6)));
    lines.push([cell(step.label + (step.simulated ? " [simulated]" : "")), change, String(Number(plainDecimal(step.to, 6)))].join(","));
  }
  return `${lines.join("\n")}\n`;
}
