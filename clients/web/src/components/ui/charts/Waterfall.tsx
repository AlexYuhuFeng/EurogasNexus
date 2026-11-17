/**
 * Waterfall (F.1): a change between two states as floating bars, a start and subtotals from
 * zero. Vertical in a wide container, horizontal in a narrow one (a phone). Inline SVG with
 * tokens only. The figure is one Tab stop; the arrow keys step through the bars and the step is
 * read out; "Table" and "CSV" carry the same numbers. When a stated total does not equal the
 * running sum, the waterfall says so under the bars (`waterfallSteps.reconciles`).
 */
import { useMemo, useState, type KeyboardEvent, type ReactNode } from "react";

import { DataGrid, type DataGridColumn } from "../DataGrid";
import { StatusBadge } from "../StatusBadge";
import { formatChartValue, formatSigned } from "./chartModel";
import { useContainerWidth } from "./SmallMultiples";
import { waterfallCsv, waterfallGeometry, waterfallSteps, type WaterfallItem, type WaterfallStep } from "./waterfallModel";

type Translate = (key: string, options?: Record<string, unknown>) => string;

export interface WaterfallProps {
  id: string;
  title: string;
  unit: string;
  items: readonly WaterfallItem[];
  t: Translate;
  decimals?: number;
  simulated?: boolean;
  note?: ReactNode;
  /** Below this container width the bars run horizontally (px). */
  horizontalBelow?: number;
}

const LABEL_ROW = 30;

export function Waterfall({ id, title, unit, items, t, decimals = 2, simulated = false, note, horizontalBelow = 520 }: WaterfallProps) {
  const [view, setView] = useState<"chart" | "table">("chart");
  const [active, setActive] = useState(-1);
  const [ref, measured] = useContainerWidth<HTMLDivElement>();
  const model = useMemo(() => waterfallSteps(items), [items]);
  const width = Math.max(240, measured || 480);
  const vertical = width >= horizontalBelow;
  const valueText = (step: WaterfallStep) =>
    step.kind === "total" ? formatChartValue(step.value, decimals) : formatSigned(step.value, decimals);
  const anySimulated = simulated || items.some((item) => item.simulated);

  // Geometry: vertical bars over a label row; horizontal bars right of a label column.
  const labelColumn = vertical ? 0 : Math.min(160, Math.max(80, Math.max(...items.map((item) => item.label.length)) * 6.6));
  const plotHeight = vertical ? 180 : Math.max(1, items.length) * 28;
  const valueRoom = 64;
  const span = vertical ? width : plotHeight;
  const length = vertical ? plotHeight - 18 : width - labelColumn - valueRoom;
  const bars = useMemo(() => waterfallGeometry(model, span, length, vertical), [model, span, length, vertical]);
  const zero = (() => {
    const range = model.max - model.min || 1;
    const share = (0 - model.min) / range;
    return vertical ? 18 + length - share * length : labelColumn + share * length;
  })();
  const svgHeight = vertical ? plotHeight + LABEL_ROW : plotHeight;

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const count = model.steps.length;
    if (count === 0) return;
    const moves: Record<string, number> = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };
    let next: number | null = null;
    if (event.key in moves) next = active < 0 ? 0 : Math.min(count - 1, Math.max(0, active + moves[event.key]));
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = count - 1;
    else if (event.key === "Escape") next = -1;
    if (next == null) return;
    event.preventDefault();
    setActive(next);
  };

  const download = () => {
    const blob = new Blob([waterfallCsv(model, unit, { step: t("chart.waterfall.step"), change: t("chart.waterfall.change"), total: t("chart.waterfall.running") })], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${id}.csv`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  };

  const columns = useMemo<DataGridColumn<WaterfallStep>[]>(() => [
    { id: "step", header: t("chart.waterfall.step"), rowHeader: true, value: (step) => step.label },
    { id: "change", header: t("chart.waterfall.change"), unit, type: "number", value: (step) => (step.kind === "total" ? null : step.value), format: (value) => (value == null ? "" : formatSigned(value as number, decimals)) },
    { id: "total", header: t("chart.waterfall.running"), unit, type: "number", value: (step) => step.to, format: (value) => formatChartValue(value as number, decimals) },
  ], [decimals, t, unit]);

  const step = active >= 0 ? model.steps[active] : null;
  const readout = step ? t("chart.waterfall.readout", { step: step.label, value: valueText(step), total: formatChartValue(step.to, decimals), unit }) : "";

  return (
    <figure className="ds-chart ds-waterfall" data-chart={id} data-chart-view={view} data-waterfall-form={vertical ? "vertical" : "horizontal"} data-waterfall-reconciles={model.reconciles ? "true" : "false"} aria-labelledby={`${id}-title`}>
      <figcaption className="ds-chart-head">
        <span className="ds-chart-title" id={`${id}-title`}>{title}</span>
        <span className="ds-chart-unit">{unit}</span>
        {anySimulated && <StatusBadge tone="simulated" title={t("chart.simulated_long")}>{t("chart.simulated")}</StatusBadge>}
        <span className="ds-chart-actions">
          <button type="button" className="ds-inline-link" aria-pressed={view === "table"} onClick={() => setView(view === "chart" ? "table" : "chart")} data-chart-toggle="table">
            {view === "chart" ? t("chart.show_table") : t("chart.show_chart")}
          </button>
          <button type="button" className="ds-inline-link" onClick={download} title={t("chart.csv_title")} data-chart-export="csv">{t("chart.csv")}</button>
        </span>
      </figcaption>
      {view === "table" ? (
        <DataGrid id={`${id}-table`} label={title} columns={columns} rows={model.steps} rowKey={(row) => row.id} density="compact" />
      ) : (
        <div
          ref={ref}
          className="ds-waterfall-plot"
          tabIndex={0}
          role="group"
          aria-roledescription={t("chart.role")}
          aria-label={`${title} (${unit}). ${t("chart.waterfall.keyboard_hint")}`}
          onKeyDown={onKeyDown}
          onBlur={() => setActive(-1)}
        >
          <svg width={width} height={svgHeight} viewBox={`0 0 ${width} ${svgHeight}`} aria-hidden="true" focusable="false">
            <line className="ds-waterfall-zero" x1={vertical ? 0 : zero} x2={vertical ? width : zero} y1={vertical ? zero : 0} y2={vertical ? zero : plotHeight} />
            {bars.map((bar, position) => {
              const item = model.steps[position];
              const low = Math.min(bar.start, bar.end);
              const size = Math.max(1, Math.abs(bar.end - bar.start));
              const rect = vertical
                ? { x: bar.band, y: 18 + low, width: bar.thickness, height: size }
                : { x: labelColumn + low, y: bar.band, width: size, height: bar.thickness };
              const valueAt = vertical
                ? { x: bar.band + bar.thickness / 2, y: 18 + low - 4, anchor: "middle" as const }
                : { x: labelColumn + Math.max(bar.start, bar.end) + 4, y: bar.band + bar.thickness / 2 + 4, anchor: "start" as const };
              const next = bars[position + 1];
              return (
                <g key={bar.id} className={`ds-waterfall-step is-${bar.sign}${item.simulated ? " is-simulated" : ""}${position === active ? " is-active" : ""}`} onPointerEnter={() => setActive(position)} onPointerLeave={(event) => event.pointerType === "mouse" && setActive(-1)} onPointerDown={() => setActive(position)}>
                  <rect {...rect} />
                  {next && (
                    vertical
                      ? <line className="ds-waterfall-connector" x1={bar.band + bar.thickness} x2={next.band} y1={18 + bar.end} y2={18 + bar.end} />
                      : <line className="ds-waterfall-connector" y1={bar.band + bar.thickness} y2={next.band} x1={labelColumn + bar.end} x2={labelColumn + bar.end} />
                  )}
                  <text className="ds-waterfall-value" x={valueAt.x} y={valueAt.y} textAnchor={valueAt.anchor}>{valueText(item)}</text>
                  {vertical ? (
                    <text className="ds-waterfall-label" x={bar.band + bar.thickness / 2} y={plotHeight + 14} textAnchor="middle">{item.label.length > 14 ? `${item.label.slice(0, 13)}…` : item.label}</text>
                  ) : (
                    <text className="ds-waterfall-label" x={labelColumn - 6} y={bar.band + bar.thickness / 2 + 4} textAnchor="end">{item.label}</text>
                  )}
                </g>
              );
            })}
          </svg>
          {step && (
            <div className="ds-chart-tip ds-waterfall-tip" aria-hidden="true">
              <strong>{step.label}</strong>
              <span className="ds-chart-tip-value">{valueText(step)} {unit}</span>
              <small className="ds-chart-tip-meta">{t("chart.waterfall.running")} {formatChartValue(step.to, decimals)} {unit}{step.simulated ? ` · ${t("chart.simulated")}` : ""}</small>
            </div>
          )}
          <p className="visually-hidden" aria-live="polite">{readout}</p>
        </div>
      )}
      {!model.reconciles && (
        <p className="ds-chart-note ds-waterfall-mismatch" role="status">{t("chart.waterfall.mismatch", { difference: formatChartValue(model.difference, decimals), unit })}</p>
      )}
      {note && <p className="ds-chart-note">{note}</p>}
    </figure>
  );
}
