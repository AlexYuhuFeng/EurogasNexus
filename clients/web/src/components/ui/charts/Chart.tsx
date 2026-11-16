/**
 * Chart (UX-09): the one chart. uPlot draws on a canvas; everything a reader needs besides the
 * shape is HTML around it.
 *
 * - One axis, one unit: the unit is in the head beside the title and on the y axis; tick labels
 *   in tabular (monospaced) numerals; gas-day series tick at gas-day starts (`chartModel`).
 * - Series colours are the token palette (`--ds-series-N`), re-read when the theme changes.
 *   Simulated series are drawn dashed, named "simulated" in the legend, the tooltip and the
 *   export, and the chart carries a Simulated badge. A forecast is drawn dashed from its start.
 * - Missing data is a gap. Reference lines (a target) are thin and neutral.
 * - Tooltip: the point's period, each series' value with its unit, and the as-of instant and
 *   state. It never leaves the plot (it flips to the cursor's other side; no measuring).
 * - Keyboard: the plot is one Tab stop; Left/Right step through points (Home/End, PageUp/Down
 *   by seven), the point is read out in a live region. "Table" swaps the plot for a DataGrid of
 *   the same data; "CSV" downloads exactly what is plotted.
 * - Resizes through a ResizeObserver, one `setSize` per frame, no layout reads while drawing.
 *   Nothing animates, so reduced motion needs no special case.
 */
import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";

import { DataGrid, type DataGridColumn } from "../DataGrid";
import { StatusBadge } from "../StatusBadge";
import {
  axisTickLabels,
  chartCsv,
  formatChartValue,
  gasDayLabel,
  gasDayTicks,
  nextPointIndex,
  periodLabel,
  periodTicks,
  splitForecast,
  stackBases,
  tickBudget,
  valueRange,
  xLabel,
  xValues,
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
  /** Plot height in px (the head, legend and actions are outside it). */
  height?: number;
  /** When the plotted data was observed or published (ISO), shown in the head and the tooltip. */
  asOf?: string | null;
  /** The data's state in words ("Current", "Late 3 h"), beside the as-of instant. */
  state?: string | null;
  /** Every series is simulated (demo data): one badge on the chart besides the series marks. */
  simulated?: boolean;
  /** A line under the plot (method, conversion, source). */
  note?: ReactNode;
  /** What the chart says when there is nothing to plot. */
  empty?: string;
  /** Extra controls in the head (a hub selector). */
  controls?: ReactNode;
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
    const observer = new MutationObserver(() => setKey(root.className));
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

/** A plotted series: the source series it shows, and whether it is the forecast part. */
interface Plotted {
  source: ChartSeries;
  item: ChartSeries;
  forecast: boolean;
  colour: string;
}

function colourOf(item: ChartSeries, order: number, palette: Palette): string {
  if (item.reference) return palette.muted;
  return palette.series[((item.colour ?? order + 1) - 1) % palette.series.length];
}

function asOfText(asOf: string | null | undefined): string | null {
  if (!asOf) return null;
  if (/^\d{4}-\d{2}-\d{2}$/.test(asOf)) return gasDayLabel(asOf, true);
  const instant = new Date(asOf);
  return Number.isNaN(instant.getTime()) ? asOf : `${instant.toISOString().slice(0, 16).replace("T", " ")} UTC`;
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

export function Chart({ id, title, data, t, height = 220, asOf, state, simulated = false, note, empty, controls }: ChartProps) {
  const [view, setView] = useState<"chart" | "table">("chart");
  const [index, setIndex] = useState<number | null>(null);
  const plotRef = useRef<HTMLDivElement | null>(null);
  const tipRef = useRef<HTMLDivElement | null>(null);
  const plotInstance = useRef<uPlot | null>(null);
  const themeKey = useThemeKey();
  const titleId = `chart-${id}-title`;
  const hasData = data.x.length > 0 && data.series.some((item) => !item.reference && item.values.some((value) => value != null));
  const anySimulated = simulated || data.series.some((item) => item.simulated);
  const allSimulated = simulated || data.series.filter((item) => !item.reference).every((item) => item.simulated);
  const asOfLabel = asOfText(asOf);

  // The plot's x values and stacked tops depend only on the data.
  const prepared = useMemo(() => {
    const xs = xValues(data);
    const bases = stackBases(data.series, data.x.length);
    return { xs, bases, range: valueRange(data) };
  }, [data]);

  useEffect(() => {
    const host = plotRef.current;
    if (!host || view !== "chart" || !hasData) return undefined;
    const palette = readPalette();
    const plotted: Plotted[] = [];
    data.series.forEach((source, order) => {
      const colour = colourOf(source, order, palette);
      const [measured, forecast] = splitForecast(source);
      plotted.push({ source, item: measured, forecast: false, colour });
      if (forecast) plotted.push({ source, item: forecast, forecast: true, colour });
    });
    const { xs, bases } = prepared;
    const values = plotted.map(({ source, item }) => {
      const base = bases.get(source.id);
      return item.values.map((value, at) => (value == null ? null : base ? (base[at] ?? 0) + value : value));
    });
    const tickFont = `11px ${palette.mono}`;
    const labelFont = `11px ${palette.ui}`;
    const width = Math.max(120, host.clientWidth);
    const hasBars = data.series.some((item) => item.style === "bar");
    const xRange: uPlot.Range.MinMax = data.axis === "period"
      ? [-0.5, Math.max(0.5, xs.length - 0.5)]
      : hasBars && xs.length > 1
        ? [xs[0] - (xs[1] - xs[0]) / 2, xs[xs.length - 1] + (xs[1] - xs[0]) / 2]
        : [xs[0], xs.length > 1 ? xs[xs.length - 1] : xs[0] + 1];

    const xSplits = (u: uPlot): number[] => {
      const budget = tickBudget(u.bbox.width / devicePixelRatio, data.axis === "time" ? 72 : 56);
      if (data.axis === "gas-day") return gasDayTicks(data.x, budget).map((at) => xs[at]);
      if (data.axis === "period") return periodTicks(data.x.length, budget);
      const step = Math.max(1, Math.ceil(xs.length / budget));
      return xs.filter((_, at) => at % step === 0);
    };
    const xLabels = (_u: uPlot, splits: number[]): string[] => splits.map((value) => {
      if (data.axis === "period") return periodLabel(data.x[Math.round(value)] ?? "");
      const at = xs.indexOf(value);
      if (data.axis === "gas-day") return at >= 0 ? gasDayLabel(data.x[at]) : "";
      return new Date(value * 1000).toISOString().slice(11, 16);
    });

    const series: uPlot.Series[] = [
      {},
      ...plotted.map(({ source, item, forecast, colour }, order): uPlot.Series => {
        const style = source.style ?? "line";
        const dash = source.reference ? [2, 3] : forecast ? [6, 4] : source.simulated ? [3, 3] : undefined;
        const base: uPlot.Series = {
          label: item.label,
          stroke: colour,
          width: source.reference ? 1 : 2,
          dash,
          spanGaps: false,
          points: { show: style === "points" || (data.axis === "period" && style === "line"), size: 6, stroke: colour, fill: palette.surface, width: 2 },
        };
        if (style === "bar") {
          return { ...base, width: 0, fill: forecast ? withAlpha(colour, 0.5) : colour, stroke: colour, paths: barPaths(bases.get(source.id), item.values), points: { show: false } };
        }
        if (style === "step") return { ...base, paths: uPlot.paths.stepped!({ align: 1 }) };
        if (style === "area") return { ...base, fill: withAlpha(colour, 0.16) };
        void order;
        return base;
      }),
    ];

    const opts: uPlot.Options = {
      width,
      height,
      legend: { show: false },
      cursor: {
        drag: { x: false, y: false, setScale: false },
        points: { size: 7, width: 2, fill: palette.surface },
        y: false,
      },
      scales: {
        x: { time: false, range: () => xRange },
        y: { range: () => prepared.range ?? [0, 1] },
      },
      axes: [
        {
          stroke: palette.muted,
          font: labelFont,
          grid: { show: false },
          ticks: { stroke: palette.axis, width: 1, size: 4 },
          splits: xSplits,
          values: xLabels,
          size: 28,
          gap: 4,
        },
        {
          stroke: palette.muted,
          font: tickFont,
          grid: { stroke: palette.grid, width: 1 },
          ticks: { show: false },
          values: (_u: uPlot, splits: number[]) => axisTickLabels(splits),
          size: 52,
          gap: 6,
        },
      ],
      series,
      hooks: {
        setCursor: [(u) => setIndex(u.cursor.idx ?? null)],
      },
    };
    host.replaceChildren();
    const plot = new uPlot(opts, [xs, ...values] as uPlot.AlignedData, host);
    plotInstance.current = plot;
    // The canvas is a picture; the table and the live region carry the data.
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
  }, [data, prepared, height, hasData, themeKey, view]);

  /** Move the cursor to a point (keyboard), as a pointer would. */
  function focusPoint(at: number) {
    const plot = plotInstance.current;
    if (!plot || at < 0) return;
    const left = plot.valToPos(prepared.xs[at], "x");
    const values = plot.data.slice(1).map((column) => column[at]).filter((value): value is number => value != null);
    const top = values.length ? plot.valToPos(values[0], "y") : plot.bbox.height / devicePixelRatio / 2;
    plot.setCursor({ left, top });
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
    return `${xLabel(data.axis, data.x[at])}: ${parts.join("; ")}`;
  };

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

  return (
    <figure
      className="ds-chart"
      data-chart={id}
      data-chart-points={data.x.length}
      data-chart-view={view}
      data-chart-simulated={anySimulated ? "true" : undefined}
      aria-labelledby={titleId}
    >
      <figcaption className="ds-chart-head">
        <span className="ds-chart-title" id={titleId}>{title}</span>
        <span className="ds-chart-unit">{data.unit}</span>
        {anySimulated && (
          <StatusBadge tone="simulated" title={t("chart.simulated_long")}>{t("chart.simulated")}</StatusBadge>
        )}
        {asOfLabel && (
          <span className="ds-chart-asof">
            {t("chart.as_of", { time: asOfLabel })}
            {state ? ` · ${state}` : ""}
          </span>
        )}
        <span className="ds-chart-actions">
          {controls}
          {hasData && (
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
      </figcaption>
      {hasData && view === "chart" && data.series.length > 1 && (
        <ul className="ds-chart-legend">
          {data.series.map((item, order) => (
            <li key={item.id} data-series-style={item.reference ? "reference" : item.simulated ? "simulated" : item.style ?? "line"}>
              <span className="ds-chart-swatch" style={{ ["--ds-chart-swatch" as string]: item.reference ? "var(--ds-text-3)" : `var(--ds-series-${item.colour ?? order + 1})` }} aria-hidden="true" />
              {item.label}
              {item.simulated && !allSimulated && <small> {t("chart.simulated")}</small>}
            </li>
          ))}
          {data.series.some((item) => item.forecastFrom != null) && (
            <li data-series-style="forecast"><span className="ds-chart-swatch" aria-hidden="true" />{t("chart.forecast")}</li>
          )}
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
            onKeyDown={onKeyDown}
            onFocus={() => index == null && focusPoint(nextPointIndex(data, data.x.length - 1, 0))}
          />
          {index != null && (
            <div className="ds-chart-tip" ref={tipRef} data-side={tipSide} style={{ ["--ds-chart-tip-x" as string]: `${tipLeft}px` }} aria-hidden="true">
              <strong>{xLabel(data.axis, data.x[index])}</strong>
              {data.series.map((item, order) =>
                item.values[index] == null && item.reference ? null : (
                  <span key={item.id} className="ds-chart-tip-row">
                    <span className="ds-chart-swatch" style={{ ["--ds-chart-swatch" as string]: item.reference ? "var(--ds-text-3)" : `var(--ds-series-${item.colour ?? order + 1})` }} />
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
              {asOfLabel && <small className="ds-chart-tip-meta">{t("chart.as_of", { time: asOfLabel })}{state ? ` · ${state}` : ""}</small>}
            </div>
          )}
          <p className="visually-hidden" aria-live="polite">{index != null ? pointText(index) : ""}</p>
        </div>
      )}
      {note && <p className="ds-chart-note">{note}</p>}
    </figure>
  );
}

export interface SparklineProps {
  /** The figure's daily series, oldest first; null is a gap. */
  values: readonly (number | null)[];
  /** Gas days of the values (for the gas-day x positions). */
  days: readonly string[];
  /** What the line is, for assistive technology ("NW Europe fill, last 30 gas days"). */
  label: string;
  simulated?: boolean;
  height?: number;
}

/**
 * A small line beside a figure: shape only, the figure carries the number. Same renderer, same
 * gas-day x positions, same simulated dash as the full chart; no axes, no interaction.
 */
export function Sparkline({ values, days, label, simulated = false, height = 28 }: SparklineProps) {
  const host = useRef<HTMLSpanElement | null>(null);
  const themeKey = useThemeKey();
  useEffect(() => {
    const element = host.current;
    if (!element || values.filter((value) => value != null).length < 2) return undefined;
    const palette = readPalette();
    const xs = xValues({ axis: "gas-day", x: days });
    const plot = new uPlot(
      {
        width: Math.max(40, element.clientWidth),
        height,
        legend: { show: false },
        cursor: { show: false },
        axes: [{ show: false }, { show: false }],
        scales: { x: { time: false } },
        padding: [2, 1, 2, 1],
        series: [{}, { stroke: palette.series[0], width: 1.5, dash: simulated ? [3, 2] : undefined, spanGaps: false, points: { show: false } }],
      },
      [xs, [...values]] as uPlot.AlignedData,
      element,
    );
    plot.root.setAttribute("aria-hidden", "true");
    let frame = 0;
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver((entries) => {
      const next = Math.round(entries[0]?.contentRect.width ?? 0);
      if (!next || next === Math.round(plot.width)) return;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => plot.setSize({ width: Math.max(40, next), height }));
    });
    observer?.observe(element);
    return () => {
      cancelAnimationFrame(frame);
      observer?.disconnect();
      plot.destroy();
    };
  }, [values, days, simulated, height, themeKey]);
  if (values.filter((value) => value != null).length < 2) return null;
  return <span className="ds-sparkline" ref={host} role="img" aria-label={label} style={{ height: `${height}px` }} data-sparkline-points={values.length} />;
}
