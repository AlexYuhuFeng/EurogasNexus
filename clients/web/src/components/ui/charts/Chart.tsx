/**
 * Chart (UX-09, chart standard F): the one chart. uPlot draws on a canvas; everything a reader
 * needs besides the shape is HTML around it.
 *
 * - One axis, one unit: the unit is in the head beside the title and on the y axis; tick labels
 *   in tabular (monospaced) numerals; gas-day series tick at gas-day starts, a season axis at
 *   month starts (`chartModel`, `seasonModel`).
 * - Colour: the token palette (`--ds-series-N`), re-read when the theme changes; the subject in
 *   the accent, context in grey: ghost lines (last year, a prior close), the history band and
 *   its mean. Simulated series are drawn dashed, named "simulated" in the tooltip and the
 *   export, and the chart carries a Simulated badge. A forecast is drawn dashed from its start.
 * - Labels: up to four lines are labelled at their ends (no legend), pushed apart so they never
 *   collide; more lines get a legend. Rules (zero, a target, a cost) are thin neutral lines with
 *   a direct label. Missing data is a gap.
 * - Readout: on hover, touch-and-drag or the arrow keys, the point's period, each series' value
 *   with its unit, the band's range and mean, the stated comparison ("−6.2 vs 5-yr mean") and
 *   the as-of; it never leaves the plot. A summary of every line is given to screen readers.
 * - "Table" swaps the plot for a DataGrid of the same data; "CSV" downloads exactly what is
 *   plotted, bands included.
 * - Resizes through a ResizeObserver, one `setSize` per frame, no layout reads while drawing.
 *   Nothing animates, so reduced motion needs no special case.
 */
import { displayTime } from "@/app/time/displayTime";
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent as ReactPointerEvent, type ReactNode } from "react";
import type uPlot from "uplot";
import { useUplot } from "./uplotLoader";
import { nearestPoint, sparkGeometry, sparkPath, sparkSummary, sparkValue, sparkWhen, stepPoint, type SparkAxis } from "./sparklineModel";
import { seasonTicks } from "./seasonModel";

import { DataGrid, type DataGridColumn } from "../DataGrid";
import { StatusBadge } from "../StatusBadge";
import {
  axisTickLabels,
  bandAt,
  chartCsv,
  compareAt,
  endLabelRoom,
  endLabels,
  formatChartValue,
  formatSigned,
  gasDayLabel,
  gasDayTicks,
  nextPointIndex,
  periodLabel,
  periodTicks,
  placeEndLabels,
  splitForecast,
  stackBases,
  summaryFacts,
  tickBudget,
  usesEndLabels,
  valueRange,
  xLabel,
  xValues,
  type ChartComparison,
  type ChartData,
  type ChartSeries,
} from "./chartModel";

type Translate = (key: string, options?: Record<string, unknown>) => string;

export interface ChartProps {
  /** Marker for acceptance checks (`data-chart`) and the export's file name. */
  id: string;
  title: string;
  data: ChartData;
  t: Translate;
  /** Plot height in px (the head, legend and actions are outside it). F.2: lead 260, standard 200, multiple 120. */
  height?: number;
  /** When the plotted data was observed or published (ISO), shown in the head and the tooltip. */
  asOf?: string | null;
  /** The data's state in words ("Current", "Late 3 h"), beside the as-of instant. */
  state?: string | null;
  /** Every series is simulated (demo data): one badge on the chart besides the series marks. */
  simulated?: boolean;
  /** A line under the title: what the context is ("5-yr range 2021/22–2025/26"). */
  subtitle?: ReactNode;
  /** A line under the plot (method, conversion, source). */
  note?: ReactNode;
  /** What the chart says when there is nothing to plot. */
  empty?: string;
  /** Extra controls in the head (a hub selector). */
  controls?: ReactNode;
  /** The comparison the readout states at every point. */
  compare?: ChartComparison;
  /** A fixed value range (small multiples share one). */
  yRange?: [number, number] | null;
  /** A panel of a small multiple: compact head, no table or CSV of its own. */
  compact?: boolean;
  /** Charts with the same key move one cursor together (aligned panels). */
  syncKey?: string;
  /** Room right of the plot for end labels, when panels must align (px). */
  labelRoom?: number;
  /** Pad the x range by half a step, as bars do (aligned panels beside a bar panel). */
  xPad?: boolean;
}

interface Palette {
  series: string[];
  text: string;
  muted: string;
  grid: string;
  axis: string;
  surface: string;
  ui: string;
  mono: string;
}

function readPalette(): Palette {
  const style = getComputedStyle(document.documentElement);
  const read = (name: string, fallback: string) => style.getPropertyValue(name).trim() || fallback;
  return {
    series: Array.from({ length: 8 }, (_, index) => read(`--ds-series-${index + 1}`, "#1d4ed8")),
    text: read("--ds-text-2", "#3f3f46"),
    muted: read("--ds-text-3", "#5f5f68"),
    grid: read("--ds-border-subtle", "#f0f0f2"),
    axis: read("--ds-border", "#e4e4e7"),
    surface: read("--ds-surface", "#ffffff"),
    ui: read("--ds-font-ui", "sans-serif"),
    mono: read("--ds-font-mono", "monospace"),
  };
}

/** The theme as a key: the chart is rebuilt with the new token colours when it changes. */
function useThemeKey(): string {
  const [key, setKey] = useState(() => (typeof document === "undefined" ? "" : document.documentElement.className));
  useEffect(() => {
    if (typeof MutationObserver === "undefined") return undefined;
    const root = document.documentElement;
    const observer = new MutationObserver(() => setKey(`${root.className}|${root.getAttribute("data-theme") ?? ""}`));
    observer.observe(root, { attributes: true, attributeFilter: ["class", "data-theme"] });
    return () => observer.disconnect();
  }, []);
  return key;
}

function withAlpha(colour: string, alpha: number): string {
  const hex = /^#([0-9a-f]{6})$/i.exec(colour);
  if (!hex) return colour;
  return `${colour}${Math.round(alpha * 255).toString(16).padStart(2, "0")}`;
}

/** A plotted uPlot series: what it shows and how. */
interface Plotted {
  /** The data series it draws (null for a band's edge or mean). */
  source: ChartSeries | null;
  values: (number | null)[];
  label: string;
  colour: string;
  role: "data" | "forecast" | "ghost" | "reference" | "band-low" | "band-high" | "band-mean";
  /** Position in `data.series` (palette order). */
  order: number;
}

/** Each series' palette position: data series in order, context lines none of their own. */
function paletteSlots(series: readonly ChartSeries[]): number[] {
  let next = 0;
  return series.map((item) => (item.reference || item.ghost ? -1 : next++));
}

function colourOf(item: ChartSeries, order: number, palette: Palette): string {
  if (item.reference || item.ghost) return palette.muted;
  return palette.series[((item.colour ?? order + 1) - 1) % palette.series.length];
}

/** The CSS colour of a series' swatch (tooltip, legend): grey for context, the token otherwise. */
function swatchOf(item: ChartSeries, order: number): string {
  return item.reference || item.ghost ? "var(--ds-text-3)" : `var(--ds-series-${item.colour ?? order + 1})`;
}

function asOfText(asOf: string | null | undefined): string | null {
  if (!asOf) return null;
  if (/^\d{4}-\d{2}-\d{2}$/.test(asOf)) return gasDayLabel(asOf, true);
  const instant = new Date(asOf);
  return Number.isNaN(instant.getTime()) ? asOf : displayTime(asOf, asOf);
}

/** Rectangles from each point's base to base + value: bars, stacked or not. */
function barPaths(bases: (number | null)[] | undefined, raw: readonly (number | null)[]) {
  return (u: uPlot, seriesIndex: number, first: number, last: number) => {
    const xs = u.data[0] as number[];
    const path = new Path2D();
    const count = xs.length;
    const span = count > 1 ? Math.abs(u.valToPos(xs[1], "x", true) - u.valToPos(xs[0], "x", true)) : u.bbox.width / 2;
    const width = Math.max(1, Math.min(span * 0.72, 48 * devicePixelRatio));
    for (let index = first; index <= last; index += 1) {
      const value = raw[index];
      if (value == null || !Number.isFinite(value)) continue;
      const base = bases?.[index] ?? 0;
      const x = u.valToPos(xs[index], "x", true);
      const y0 = u.valToPos(base, "y", true);
      const y1 = u.valToPos(base + value, "y", true);
      const top = Math.min(y0, y1);
      // A 1 px surface gap at each end separates stacked segments.
      const height = Math.max(1, Math.abs(y1 - y0) - (bases ? 2 * devicePixelRatio : 0));
      path.rect(x - width / 2, top + (bases ? devicePixelRatio : 0), width, height);
    }
    void seriesIndex;
    return { stroke: path, fill: path };
  };
}

/**
 * A stacked area: the polygon between the series' base and its top, broken at gaps. The line on
 * top is the stroke; the fill is the area itself (F.1, stacks of more than 14 points).
 */
function stackedAreaPaths(bases: (number | null)[], raw: readonly (number | null)[]) {
  return (u: uPlot, _seriesIndex: number, first: number, last: number) => {
    const xs = u.data[0] as number[];
    const stroke = new Path2D();
    const fill = new Path2D();
    let run: number[] = [];
    const close = () => {
      if (run.length === 0) return;
      run.forEach((at, position) => {
        const x = u.valToPos(xs[at], "x", true);
        const y = u.valToPos((bases[at] ?? 0) + (raw[at] as number), "y", true);
        if (position === 0) {
          stroke.moveTo(x, y);
          fill.moveTo(x, y);
        } else {
          stroke.lineTo(x, y);
          fill.lineTo(x, y);
        }
      });
      for (let position = run.length - 1; position >= 0; position -= 1) {
        const at = run[position];
        fill.lineTo(u.valToPos(xs[at], "x", true), u.valToPos(bases[at] ?? 0, "y", true));
      }
      fill.closePath();
      run = [];
    };
    for (let index = first; index <= last; index += 1) {
      const value = raw[index];
      if (value == null || !Number.isFinite(value)) close();
      else run.push(index);
    }
    close();
    return { stroke, fill };
  };
}

export function Chart({
  id,
  title,
  data,
  t,
  height = 220,
  asOf,
  state,
  simulated = false,
  subtitle,
  note,
  empty,
  controls,
  compare,
  yRange,
  compact = false,
  syncKey,
  labelRoom,
  xPad = false,
}: ChartProps) {
  const [view, setView] = useState<"chart" | "table">("chart");
  const [index, setIndex] = useState<number | null>(null);
  const plotRef = useRef<HTMLDivElement | null>(null);
  const tipRef = useRef<HTMLDivElement | null>(null);
  const plotInstance = useRef<uPlot | null>(null);
  const themeKey = useThemeKey();
  const summaryId = `chart-${useId().replace(/:/g, "")}-summary`;
  // Loaded on first use; when it cannot be used the table view carries the data.
  const UPlot = useUplot();
  useEffect(() => {
    if (UPlot === null) setView("table");
  }, [UPlot]);
  const titleId = `chart-${id}-title`;
  const hasData = data.x.length > 0 && data.series.some((item) => !item.reference && !item.ghost && item.values.some((value) => value != null));
  const anySimulated = simulated || data.series.some((item) => item.simulated);
  const allSimulated = simulated || data.series.filter((item) => !item.reference).every((item) => item.simulated);
  const asOfLabel = asOfText(asOf);
  const endLabelled = usesEndLabels(data);
  const slots = useMemo(() => paletteSlots(data.series), [data]);

  // The plot's x values, stacked tops and end labels depend only on the data.
  const prepared = useMemo(() => {
    const xs = xValues(data);
    const bases = stackBases(data.series, data.x.length);
    // A panel of a small multiple carries its numbers in its headline: no end labels there.
    const labels = endLabelled && !compact ? endLabels(data) : [];
    // Rules are labelled in the same gutter, so their labels and the lines' never collide.
    const ruleLabels = compact ? [] : (data.rules ?? []).filter((rule) => rule.label).map((rule) => ({
      id: `rule:${rule.id}`, text: rule.label as string, value: rule.value, index: xs.length - 1, ghost: true,
    }));
    // Only lines that reach the end of the axis take room right of the plot.
    const gutter = [...labels.filter((label) => label.index >= xs.length - 1 - Math.max(2, Math.round(xs.length * 0.08))), ...ruleLabels];
    return { xs, bases, range: valueRange(data), labels: [...labels, ...ruleLabels], room: labelRoom ?? endLabelRoom(gutter) };
  }, [data, endLabelled, labelRoom, compact]);

  useEffect(() => {
    const host = plotRef.current;
    if (!host || !UPlot || view !== "chart" || !hasData) return undefined;
    const palette = readPalette();
    const plotted: Plotted[] = [];
    const { xs, bases } = prepared;
    // Draw order: band edges and mean first (context under everything), then ghost lines,
    // rules-as-series, then the data.
    const bandPairs: [number, number][] = [];
    for (const band of data.bands ?? []) {
      const lowAt = plotted.length + 1;
      plotted.push({ source: null, values: [...band.low], label: `${band.label} low`, colour: palette.muted, role: "band-low", order: -1 });
      plotted.push({ source: null, values: [...band.high], label: `${band.label} high`, colour: palette.muted, role: "band-high", order: -1 });
      bandPairs.push([lowAt + 1, lowAt]);
      if (band.mean) plotted.push({ source: null, values: [...band.mean], label: band.meanLabel ?? band.label, colour: palette.muted, role: "band-mean", order: -1 });
    }
    // Context (ghost, reference) lines take no palette slot: the subject is always the accent.
    const slots = paletteSlots(data.series);
    const ordered = data.series.map((source, position) => ({ source, order: slots[position] }));
    const rank = (item: ChartSeries) => (item.ghost ? 0 : item.reference ? 1 : 2);
    ordered.sort((a, b) => rank(a.source) - rank(b.source));
    for (const { source, order } of ordered) {
      const colour = colourOf(source, order, palette);
      const base = bases.get(source.id);
      const lift = (values: readonly (number | null)[]) =>
        values.map((value, at) => (value == null ? null : base ? (base[at] ?? 0) + value : value));
      const [measured, forecast] = splitForecast(source);
      const role = source.ghost ? "ghost" : source.reference ? "reference" : "data";
      plotted.push({ source, values: lift(measured.values), label: measured.label, colour, role, order });
      if (forecast) plotted.push({ source, values: lift(forecast.values), label: forecast.label, colour, role: "forecast", order });
    }

    const tickFont = `${compact ? 10 : 11}px ${palette.mono}`;
    const labelFont = `${compact ? 10 : 11}px ${palette.ui}`;
    const width = Math.max(120, host.clientWidth);
    const hasBars = data.series.some((item) => item.style === "bar");
    const xRange: uPlot.Range.MinMax = data.axis === "period"
      ? [-0.5, Math.max(0.5, xs.length - 0.5)]
      : data.axis === "season"
        ? [0, Math.max(1, xs.length - 1)]
        : (hasBars || xPad) && xs.length > 1
          ? [xs[0] - (xs[1] - xs[0]) / 2, xs[xs.length - 1] + (xs[1] - xs[0]) / 2]
          : [xs[0], xs.length > 1 ? xs[xs.length - 1] : xs[0] + 1];

    const xSplits = (u: uPlot): number[] => {
      const budget = tickBudget(u.bbox.width / devicePixelRatio, data.axis === "time" ? 72 : compact ? 44 : 56);
      if (data.axis === "gas-day") return gasDayTicks(data.x, budget).map((at) => xs[at]);
      if (data.axis === "period") return periodTicks(data.x.length, budget);
      if (data.axis === "season") return seasonTicks(data.x, budget).map((tick) => tick.index);
      const step = Math.max(1, Math.ceil(xs.length / budget));
      return xs.filter((_, at) => at % step === 0);
    };
    const xLabels = (_u: uPlot, splits: number[]): string[] => splits.map((value) => {
      if (data.axis === "period") return periodLabel(data.x[Math.round(value)] ?? "");
      if (data.axis === "season") return seasonTicks(data.x, 99).find((tick) => tick.index === value)?.label ?? "";
      const at = xs.indexOf(value);
      if (data.axis === "gas-day") return at >= 0 ? gasDayLabel(data.x[at]) : "";
      return new Date(value * 1000).toISOString().slice(11, 16);
    });

    const series: uPlot.Series[] = [
      {},
      ...plotted.map(({ source, values: _values, label, colour, role }): uPlot.Series => {
        if (role === "band-low" || role === "band-high") {
          return { label, stroke: "transparent", width: 0, spanGaps: false, points: { show: false } };
        }
        if (role === "band-mean") {
          return { label, stroke: colour, width: 1, dash: [4, 3], spanGaps: false, points: { show: false } };
        }
        const item = source!;
        const style = item.style ?? "line";
        const dash = item.reference ? [2, 3] : role === "forecast" ? [6, 4] : item.simulated && !item.ghost ? [3, 3] : undefined;
        const markers = !item.ghost && (style === "points" || (data.axis === "period" && style === "line"));
        const base: uPlot.Series = {
          label,
          stroke: colour,
          width: item.reference ? 1 : item.ghost ? 1.25 : 2,
          dash,
          spanGaps: false,
          points: { show: markers, size: 6, stroke: colour, fill: palette.surface, width: 2 },
        };
        if (style === "bar") {
          return { ...base, width: 0, fill: role === "forecast" ? withAlpha(colour, 0.5) : colour, stroke: colour, paths: barPaths(bases.get(item.id), item.values), points: { show: false } };
        }
        if (style === "area" && item.stack) {
          const stackBase = bases.get(item.id) ?? [];
          const raw = role === "forecast" ? splitForecast(item)[1]?.values ?? item.values : splitForecast(item)[0].values;
          return { ...base, width: 1, fill: withAlpha(colour, role === "forecast" ? 0.35 : 0.7), paths: stackedAreaPaths(stackBase, raw), points: { show: false } };
        }
        if (style === "step") return { ...base, paths: UPlot.paths.stepped!({ align: 1 }) };
        if (style === "area") return { ...base, fill: withAlpha(colour, 0.16) };
        return base;
      }),
    ];

    const values = plotted.map((entry) => entry.values);
    const rules = data.rules ?? [];
    const labels = prepared.labels;
    // On a narrow chart the label gutter takes at most 30 % of the width; labels are shortened
    // to fit it (F.2 phone: the plot keeps the room).
    const room = labelRoom ?? Math.min(prepared.room, Math.round(width * 0.3));
    const opts: uPlot.Options = {
      width,
      height,
      legend: { show: false },
      padding: [10, room > 0 ? room : 12, 0, 0],
      cursor: {
        drag: { x: false, y: false, setScale: false },
        points: { size: 7, width: 2, fill: palette.surface },
        y: false,
        ...(syncKey ? { sync: { key: syncKey } } : {}),
      },
      scales: {
        x: { time: false, range: () => xRange },
        y: { range: () => (yRange ?? prepared.range ?? [0, 1]) as uPlot.Range.MinMax },
      },
      bands: bandPairs.map(([high, low]) => ({ series: [high, low] as [number, number], fill: withAlpha(palette.muted, 0.18) })),
      axes: [
        {
          stroke: palette.muted,
          font: labelFont,
          grid: { show: false },
          ticks: { stroke: palette.axis, width: 1, size: 4 },
          splits: xSplits,
          values: xLabels,
          size: compact ? 22 : 28,
          gap: 4,
        },
        {
          stroke: palette.muted,
          font: tickFont,
          grid: { stroke: palette.grid, width: 1 },
          ticks: { show: false },
          values: (_u: uPlot, splits: number[]) => axisTickLabels(splits),
          size: compact ? 40 : 52,
          gap: 6,
        },
      ],
      series,
      hooks: {
        setCursor: [(u) => setIndex(u.cursor.idx ?? null)],
        // Rules under the series: a thin neutral line, its label just above it at the left.
        drawAxes: [
          (u) => {
            if (rules.length === 0) return;
            const ctx = u.ctx;
            const dpr = devicePixelRatio;
            ctx.save();
            ctx.font = `${Math.round(10 * dpr)}px ${palette.ui}`;
            ctx.textBaseline = "bottom";
            ctx.textAlign = "left";
            for (const rule of rules) {
              const y = Math.round(u.valToPos(rule.value, "y", true)) + 0.5;
              if (y < u.bbox.top - 1 || y > u.bbox.top + u.bbox.height + 1) continue;
              ctx.strokeStyle = rule.kind === "zero" ? palette.text : palette.muted;
              ctx.lineWidth = dpr;
              ctx.setLineDash(rule.kind === "zero" ? [] : [3 * dpr, 3 * dpr]);
              ctx.beginPath();
              ctx.moveTo(u.bbox.left, y);
              ctx.lineTo(u.bbox.left + u.bbox.width, y);
              ctx.stroke();
            }
            ctx.restore();
          },
        ],
        // End labels after the series: in the room right of the plot, pushed apart.
        draw: [
          (u) => {
            const dpr = devicePixelRatio;
            const ctx = u.ctx;
            if (labels.length === 0) return;
            const colourFor = (labelId: string) =>
              plotted.find((item) => (item.source?.id ?? "") === labelId && item.role !== "forecast")?.colour ?? palette.muted;
            // Positions in CSS px inside the plotting area, then onto the canvas.
            // A line that ends well before the axis does (this gas year in November) is labelled
            // beside its last point; the others in the room right of the plot, pushed apart.
            const lastX = xs.length - 1;
            const early = (label: (typeof labels)[number]) => label.index < lastX - Math.max(2, Math.round(xs.length * 0.08));
            const items = labels.filter((label) => !early(label)).map((label) => ({ ...label, y: u.valToPos(label.value, "y") }));
            const placed = placeEndLabels(items, 0, u.bbox.height / dpr, 14);
            ctx.save();
            ctx.textBaseline = "middle";
            ctx.textAlign = "left";
            ctx.lineJoin = "round";
            const fit = (text: string, space: number): string => {
              if (ctx.measureText(text).width <= space) return text;
              let cut = text;
              while (cut.length > 1 && ctx.measureText(`${cut}…`).width > space) cut = cut.slice(0, -1);
              return `${cut}…`;
            };
            for (const label of placed) {
              ctx.font = `${label.ghost ? "" : "600 "}${Math.round(11 * dpr)}px ${palette.ui}`;
              ctx.fillStyle = label.ghost ? palette.muted : colourFor(label.id);
              ctx.fillText(fit(label.text, (room - 8) * dpr), u.bbox.left + u.bbox.width + 6 * dpr, u.bbox.top + label.placedY * dpr);
            }
            for (const label of labels.filter(early)) {
              const x = u.valToPos(xs[label.index], "x", true) + 6 * dpr;
              const y = u.valToPos(label.value, "y", true);
              ctx.font = `${label.ghost ? "" : "600 "}${Math.round(11 * dpr)}px ${palette.ui}`;
              ctx.strokeStyle = palette.surface;
              ctx.lineWidth = 3 * dpr;
              ctx.strokeText(label.text, x, y);
              ctx.fillStyle = label.ghost ? palette.muted : colourFor(label.id);
              ctx.fillText(label.text, x, y);
            }
            ctx.restore();
          },
        ],
      },
    };
    host.replaceChildren();
    const plot = new UPlot(opts, [xs, ...values] as uPlot.AlignedData, host);
    plotInstance.current = plot;
    // The canvas is a picture; the table, the summary and the live region carry the data.
    plot.root.setAttribute("aria-hidden", "true");

    let frame = 0;
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver((entries) => {
      const next = Math.round(entries[0]?.contentRect.width ?? 0);
      if (!next || next === Math.round(plot.width)) return;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => plot.setSize({ width: Math.max(120, next), height }));
    });
    observer?.observe(host);
    return () => {
      cancelAnimationFrame(frame);
      observer?.disconnect();
      plot.destroy();
      plotInstance.current = null;
    };
  }, [data, prepared, height, hasData, themeKey, view, UPlot, yRange, compact, syncKey, xPad, labelRoom]);

  /** Move the cursor to a point (keyboard), as a pointer would. */
  function focusPoint(at: number) {
    const plot = plotInstance.current;
    if (!plot || at < 0) return;
    const left = plot.valToPos(prepared.xs[at], "x");
    const values = plot.data.slice(1).map((column) => column[at]).filter((value): value is number => value != null);
    const top = values.length ? plot.valToPos(values[values.length - 1], "y") : plot.bbox.height / devicePixelRatio / 2;
    plot.setCursor({ left, top });
  }

  /** Touch-and-drag reads the chart as hovering does (F.2: no hover-only information). */
  function onPointer(event: ReactPointerEvent<HTMLDivElement>) {
    const plot = plotInstance.current;
    if (!plot || event.pointerType === "mouse") return;
    const box = plot.over.getBoundingClientRect();
    const left = Math.min(Math.max(event.clientX - box.left, 0), box.width);
    plot.setCursor({ left, top: Math.min(Math.max(event.clientY - box.top, 0), box.height) });
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const last = data.x.length - 1;
    const current = index ?? last;
    const moves: Record<string, number> = { ArrowRight: 1, ArrowLeft: -1, PageUp: -7, PageDown: 7 };
    let next: number | null = null;
    if (event.key in moves) next = nextPointIndex(data, current, moves[event.key]);
    else if (event.key === "Home") next = nextPointIndex(data, 0, 0);
    else if (event.key === "End") next = nextPointIndex(data, last, 0);
    else if (event.key === "Escape") {
      plotInstance.current?.setCursor({ left: -10, top: -10 });
      return;
    }
    if (next == null) return;
    event.preventDefault();
    focusPoint(next);
  }

  const bandText = (at: number): string[] =>
    (data.bands ?? []).flatMap((band) => {
      const values = bandAt(band, at);
      if (!values) return [];
      const range = `${band.label} ${formatChartValue(values.low, 1)}–${formatChartValue(values.high, 1)} ${data.unit}`;
      return values.mean == null ? [range] : [range, `${band.meanLabel ?? band.label} ${formatChartValue(values.mean, 1)} ${data.unit}`];
    });
  const compareText = (at: number): string | null => {
    if (!compare) return null;
    const difference = compareAt(data, compare, at);
    return difference == null ? null : `${formatSigned(difference, 1)} ${data.unit} ${compare.label}`;
  };

  const pointText = (at: number): string => {
    const parts = data.series
      .filter((item) => item.values[at] != null || !item.reference)
      .map((item) => {
        const flags = [
          item.forecastFrom != null && at >= item.forecastFrom ? t("chart.forecast") : null,
          item.simulated ? t("chart.simulated") : null,
        ].filter(Boolean);
        return `${item.label} ${formatChartValue(item.values[at] ?? null, item.decimals)} ${data.unit}${flags.length ? ` (${flags.join(", ")})` : ""}`;
      });
    const extra = [...bandText(at), compareText(at)].filter(Boolean);
    return `${xLabel(data.axis, data.x[at])}: ${[...parts, ...extra].join("; ")}`;
  };

  const summary = useMemo(() => {
    const facts = summaryFacts(data).map((fact) => t("chart.summary.series", { ...fact }));
    const bands = (data.bands ?? []).map((band) => t("chart.summary.band", { label: band.label, count: band.years.length }));
    const rules = (data.rules ?? []).filter((rule) => rule.label).map((rule) => rule.label as string);
    return [t("chart.summary.head", { title, unit: data.unit, count: data.x.length }), ...facts, ...bands, ...rules].join(" ");
  }, [data, t, title]);

  const download = () => {
    const blob = new Blob([chartCsv(data)], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${id}.csv`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  };

  const columns = useMemo<DataGridColumn<number>[]>(
    () => [
      { id: "x", header: data.xTitle, rowHeader: true, value: (at) => data.x[at], format: (_value, at) => xLabel(data.axis, data.x[at]) },
      ...data.series.map((item): DataGridColumn<number> => ({
        id: item.id.replace(/[^a-z0-9-]/gi, "-"),
        header: item.simulated ? `${item.label} (${t("chart.simulated")})` : item.label,
        unit: data.unit,
        type: "number",
        value: (at) => item.values[at] ?? null,
        format: (value) => formatChartValue(value as number | null, item.decimals),
        state: (at) =>
          item.forecastFrom != null && at >= item.forecastFrom
            ? { kind: "revised", label: t("chart.forecast_short"), description: t("chart.forecast") }
            : null,
      })),
      ...(data.bands ?? []).flatMap((band): DataGridColumn<number>[] => [
        { id: `${band.id}-low`.replace(/[^a-z0-9-]/gi, "-"), header: `${band.label} ${t("chart.band.low")}`, unit: data.unit, type: "number", value: (at) => band.low[at] ?? null, format: (value) => formatChartValue(value as number | null, 1) },
        { id: `${band.id}-high`.replace(/[^a-z0-9-]/gi, "-"), header: `${band.label} ${t("chart.band.high")}`, unit: data.unit, type: "number", value: (at) => band.high[at] ?? null, format: (value) => formatChartValue(value as number | null, 1) },
        ...(band.mean
          ? [{ id: `${band.id}-mean`.replace(/[^a-z0-9-]/gi, "-"), header: band.meanLabel ?? `${band.label} ${t("chart.band.mean")}`, unit: data.unit, type: "number" as const, value: (at: number) => band.mean?.[at] ?? null, format: (value: unknown) => formatChartValue(value as number | null, 1) }]
          : []),
      ]),
    ],
    [data, t],
  );
  const rows = useMemo(() => data.x.map((_, at) => at), [data]);
  const tipSide = index != null && plotInstance.current
    ? (plotInstance.current.valToPos(prepared.xs[index], "x") > plotInstance.current.bbox.width / devicePixelRatio / 2 ? "start" : "end")
    : "end";
  const tipLeft = index != null && plotInstance.current
    ? plotInstance.current.valToPos(prepared.xs[index], "x") + plotInstance.current.bbox.left / devicePixelRatio
    : 0;
  const legendShown = hasData && view === "chart" && !compact && !endLabelled && data.series.length > 1;
  const forecastKey = hasData && view === "chart" && !compact && endLabelled && data.series.some((item) => item.forecastFrom != null);

  return (
    <figure
      className={`ds-chart${compact ? " is-compact" : ""}`}
      data-chart={id}
      data-chart-points={data.x.length}
      data-chart-view={view}
      data-chart-simulated={anySimulated ? "true" : undefined}
      data-chart-bands={data.bands?.length ? data.bands.map((band) => band.years.length).join(",") : undefined}
      data-chart-end-labels={endLabelled ? prepared.labels.length : undefined}
      aria-labelledby={titleId}
    >
      <figcaption className="ds-chart-head">
        <span className="ds-chart-title" id={titleId}>{title}</span>
        <span className="ds-chart-unit">{data.unit}</span>
        {anySimulated && (
          <StatusBadge tone="simulated" title={t("chart.simulated_long")}>{t("chart.simulated")}</StatusBadge>
        )}
        {asOfLabel && !compact && (
          <span className="ds-chart-asof">
            {t("chart.as_of", { time: asOfLabel })}
            {state ? ` · ${state}` : ""}
          </span>
        )}
        {(controls || (hasData && !compact)) && (
          <span className="ds-chart-actions">
            {controls}
            {hasData && !compact && (
              <>
                <button type="button" className="ds-inline-link" aria-pressed={view === "table"} onClick={() => setView(view === "chart" ? "table" : "chart")} data-chart-toggle="table">
                  {view === "chart" ? t("chart.show_table") : t("chart.show_chart")}
                </button>
                <button type="button" className="ds-inline-link" onClick={download} title={t("chart.csv_title")} data-chart-export="csv">
                  {t("chart.csv")}
                </button>
              </>
            )}
          </span>
        )}
        {subtitle && <span className="ds-chart-subtitle">{subtitle}</span>}
      </figcaption>
      {legendShown && (
        <ul className="ds-chart-legend">
          {data.series.map((item, order) => (
            <li key={item.id} data-series-style={item.reference ? "reference" : item.ghost ? "ghost" : item.simulated ? "simulated" : item.style ?? "line"}>
              <span className="ds-chart-swatch" style={{ ["--ds-chart-swatch" as string]: swatchOf(item, slots[order]) }} aria-hidden="true" />
              {item.label}
              {item.simulated && !allSimulated && <small> {t("chart.simulated")}</small>}
            </li>
          ))}
          {data.series.some((item) => item.forecastFrom != null) && (
            <li data-series-style="forecast"><span className="ds-chart-swatch" aria-hidden="true" />{t("chart.forecast")}</li>
          )}
        </ul>
      )}
      {forecastKey && (
        <ul className="ds-chart-legend">
          <li data-series-style="forecast"><span className="ds-chart-swatch" aria-hidden="true" />{t("chart.forecast")}</li>
        </ul>
      )}
      {!hasData ? (
        <p className="ds-chart-empty">{empty ?? t("chart.no_data")}</p>
      ) : view === "table" ? (
        <DataGrid
          id={`${id}-table`}
          label={title}
          columns={columns}
          rows={rows}
          rowKey={(at) => data.x[at]}
          density="compact"
          maxHeight="min(50vh, 420px)"
          rowAttributes={(at) => ({ "data-chart-row": data.x[at] })}
        />
      ) : (
        <div className="ds-chart-frame">
          <div
            className="ds-chart-plot"
            ref={plotRef}
            style={{ minHeight: `${height}px` }}
            tabIndex={0}
            role="group"
            aria-roledescription={t("chart.role")}
            aria-label={`${title} (${data.unit}). ${t("chart.keyboard_hint")}`}
            aria-describedby={summaryId}
            onKeyDown={onKeyDown}
            onPointerDown={onPointer}
            onPointerMove={onPointer}
            onFocus={() => index == null && focusPoint(nextPointIndex(data, data.x.length - 1, 0))}
          />
          {index != null && (
            <div className="ds-chart-tip" ref={tipRef} data-side={tipSide} style={{ ["--ds-chart-tip-x" as string]: `${tipLeft}px` }} aria-hidden="true">
              <strong>{xLabel(data.axis, data.x[index])}</strong>
              {data.series.map((item, order) =>
                item.values[index] == null && (item.reference || item.ghost) ? null : (
                  <span key={item.id} className={`ds-chart-tip-row${item.ghost ? " is-ghost" : ""}`}>
                    <span className="ds-chart-swatch" style={{ ["--ds-chart-swatch" as string]: swatchOf(item, slots[order]) }} />
                    <span>{item.label}</span>
                    <span className="ds-chart-tip-value">
                      {formatChartValue(item.values[index] ?? null, item.decimals)} {data.unit}
                      {item.forecastFrom != null && index >= item.forecastFrom && <small> {t("chart.forecast_short")}</small>}
                      {/* The head already says the whole chart is simulated; a mixed chart says it per row. */}
                      {item.simulated && !allSimulated && <small> {t("chart.simulated")}</small>}
                    </span>
                  </span>
                ),
              )}
              {(data.bands ?? []).map((band) => {
                const values = bandAt(band, index);
                if (!values) return null;
                return (
                  <span key={band.id} className="ds-chart-tip-row is-ghost" data-chart-tip="band">
                    <span className="ds-chart-swatch is-band" />
                    <span>{band.label}</span>
                    <span className="ds-chart-tip-value">
                      {formatChartValue(values.low, 1)}–{formatChartValue(values.high, 1)} {data.unit}
                      {values.mean != null && <small> · {band.meanLabel ?? t("chart.band.mean")} {formatChartValue(values.mean, 1)}</small>}
                    </span>
                  </span>
                );
              })}
              {compareText(index) && <span className="ds-chart-tip-compare" data-chart-tip="compare">{compareText(index)}</span>}
              {asOfLabel && <small className="ds-chart-tip-meta">{t("chart.as_of", { time: asOfLabel })}{state ? ` · ${state}` : ""}</small>}
            </div>
          )}
          <p className="visually-hidden" id={summaryId}>{summary}</p>
          <p className="visually-hidden" aria-live="polite">{index != null ? pointText(index) : ""}</p>
        </div>
      )}
      {note && <p className="ds-chart-note">{note}</p>}
    </figure>
  );
}

export interface SparklineProps {
  /** The figure's series, oldest first; null is a gap (never interpolated). */
  values: readonly (number | null)[];
  /** Gas days of the values (`axis` "gas-day") or ISO instants (`axis` "time"). */
  days: readonly string[];
  axis?: SparkAxis;
  /** What the line is ("NW Europe storage fill"): the start of its accessible name. */
  label: string;
  /** The series' unit ("%", "GWh/d", "EUR/MWh"), shown with every value. */
  unit?: string;
  decimals?: number;
  simulated?: boolean;
  height?: number;
  t: (key: string, options?: Record<string, unknown>) => string;
  /** Click or Enter: open the full chart of this series. */
  onOpen?: () => void;
}

/**
 * A small line beside a figure that answers "what is this value and when": pointing at it (or
 * touching, or stepping with the arrow keys once it has focus) shows the date and value of the
 * nearest point, with the low and high marked; the last point is always marked. Click or Enter
 * opens the full chart. A light inline SVG with tokens only: no chart library, so it draws
 * before uPlot loads, in both themes.
 */
export function Sparkline({
  values,
  days,
  axis = "gas-day",
  label,
  unit = "",
  decimals = 1,
  simulated = false,
  height = 28,
  t,
  onOpen,
}: SparklineProps) {
  const host = useRef<HTMLSpanElement | null>(null);
  const [width, setWidth] = useState(120);
  const [active, setActive] = useState(-1);
  useEffect(() => {
    const element = host.current;
    if (!element || typeof ResizeObserver === "undefined") return undefined;
    const measure = () => {
      const next = Math.round(element.clientWidth);
      if (next > 0) setWidth((current) => (current === next ? current : next));
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const geometry = useMemo(() => sparkGeometry(values, days, { axis, width, height }), [axis, days, height, values, width]);
  const summary = useMemo(() => sparkSummary(geometry, axis, unit, decimals), [axis, decimals, geometry, unit]);
  if (!summary || geometry.points.length < 2) return null;
  const { points } = geometry;
  const point = active >= 0 ? points[active] : null;
  const sim = simulated ? ` ${t("today.simulated_short")}` : "";
  const readout = point ? t("chart.spark.readout", { day: sparkWhen(axis, point.key), value: sparkValue(point.value, unit, decimals) }) + sim : "";
  const name = t("chart.spark.summary", { label, ...summary }) + (simulated ? ` ${t("today.simulated_long")}.` : "") + (onOpen ? ` ${t("chart.spark.open")}` : "");
  const choose = (position: number) => setActive(position);
  const fromPointer = (clientX: number) => {
    const box = host.current?.getBoundingClientRect();
    if (!box) return;
    choose(nearestPoint(points, clientX - box.left));
  };
  const onKeyDown = (event: KeyboardEvent<HTMLSpanElement>) => {
    if ((event.key === "Enter" || event.key === " ") && onOpen) {
      event.preventDefault();
      onOpen();
      return;
    }
    if (event.key === "Escape") {
      setActive(-1);
      return;
    }
    const next = stepPoint(points.length, active, event.key);
    if (next === null) return;
    event.preventDefault();
    choose(next);
  };
  const last = points[geometry.last];
  const low = points[geometry.min];
  const high = points[geometry.max];
  // The readout sits over the line, away from the edge it would run off.
  const tipLeft = point ? Math.min(Math.max(point.x, 0), width) : 0;
  return (
    <span
      className={`ds-sparkline${onOpen ? " is-openable" : ""}${point ? " is-reading" : ""}`}
      ref={host}
      role={onOpen ? "button" : "img"}
      tabIndex={0}
      aria-label={name}
      style={{ height: `${height}px` }}
      data-sparkline-points={values.length}
      data-sparkline-active={point ? point.index : undefined}
      onPointerMove={(event) => fromPointer(event.clientX)}
      onPointerDown={(event) => fromPointer(event.clientX)}
      onPointerLeave={(event) => {
        if (event.pointerType === "mouse") setActive(-1);
      }}
      onBlur={() => setActive(-1)}
      onKeyDown={onKeyDown}
      onClick={onOpen}
    >
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true" focusable="false">
        <path className={`ds-sparkline-line${simulated ? " is-simulated" : ""}`} d={sparkPath(geometry.segments)} />
        {/* A point standing alone between gaps still shows. */}
        {geometry.segments.filter((segment) => segment.length === 1).map(([alone]) => (
          <circle key={`alone-${alone.index}`} className="ds-sparkline-dot" cx={alone.x} cy={alone.y} r={1.5} />
        ))}
        {point && (
          <>
            <circle className="ds-sparkline-extreme" cx={low.x} cy={low.y} r={2} />
            <circle className="ds-sparkline-extreme" cx={high.x} cy={high.y} r={2} />
            <line className="ds-sparkline-cursor" x1={point.x} x2={point.x} y1={0} y2={height} />
          </>
        )}
        <circle className="ds-sparkline-last" cx={last.x} cy={last.y} r={2.5} />
        {point && <circle className="ds-sparkline-marker" cx={point.x} cy={point.y} r={3} />}
      </svg>
      {point && (
        <span
          className={`ds-sparkline-tip${tipLeft > width / 2 ? " is-left" : ""}`}
          style={{ ["--ds-spark-x" as string]: `${tipLeft}px` }}
          aria-hidden="true"
        >
          <strong>{sparkValue(point.value, unit, decimals)}</strong>
          {simulated && <span className="ds-sparkline-sim">{t("today.simulated_short")}</span>}
          <span>{sparkWhen(axis, point.key)}</span>
          <span className="ds-sparkline-range">
            {t("chart.spark.low")} {sparkValue(low.value, unit, decimals)} · {t("chart.spark.high")} {sparkValue(high.value, unit, decimals)}
          </span>
        </span>
      )}
      <span className="ds-visually-hidden" aria-live="polite">{readout}</span>
    </span>
  );
}
