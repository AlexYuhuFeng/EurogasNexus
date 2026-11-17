/**
 * Small multiples (F.2): one compact chart per entity (a country, a hub), on one y scale by
 * default so the panels compare, with "independent scales" as a toggle; each panel carries its
 * headline number and its own hover, touch and keyboard readout. At most `maxCells` panels are
 * shown before "Show all". In a narrow container (a phone) the panels become a list: the
 * headline and a sparkline per row, a tap opens the entity (F.2: small multiples become a list).
 * One CSV holds every panel's plotted data.
 */
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { Chart, Sparkline } from "./Chart";
import { chartCsv, sharedRange, type ChartComparison, type ChartData } from "./chartModel";

type Translate = (key: string, options?: Record<string, unknown>) => string;

export interface MultipleCell {
  id: string;
  /** "DE", "Germany": the panel's compact title. */
  title: string;
  /** The panel's headline ("71.4 % · −6.2 vs 5-yr · −0.31/d"). */
  headline?: ReactNode;
  data: ChartData;
  simulated?: boolean;
  compare?: ChartComparison;
  /** The list form's sparkline (phone): recent values by gas day. */
  spark?: { values: readonly (number | null)[]; days: readonly string[]; unit: string; decimals?: number };
  /** Select the entity (open its full chart). */
  onSelect?: () => void;
  selected?: boolean;
}

export interface SmallMultiplesProps {
  id: string;
  title: string;
  cells: readonly MultipleCell[];
  t: Translate;
  height?: number;
  maxCells?: number;
  /** Below this container width the panels become a list (px). */
  listBelow?: number;
  note?: ReactNode;
}

/** The container's width, measured (a phone is a narrow container, whatever the screen). */
export function useContainerWidth<T extends HTMLElement>(): [React.RefObject<T | null>, number] {
  const ref = useRef<T | null>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const element = ref.current;
    if (!element) return undefined;
    const measure = () => setWidth((current) => {
      const next = Math.round(element.clientWidth);
      return next === current ? current : next;
    });
    measure();
    if (typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
}

function csvOfCells(cells: readonly MultipleCell[]): string {
  return cells
    .map((cell, position) => {
      const body = chartCsv(cell.data).trimEnd().split("\n");
      const rows = body.map((line, index) => `${index === 0 ? "Entity" : cell.title},${line}`);
      return (position === 0 ? rows : rows.slice(1)).join("\n");
    })
    .join("\n") + "\n";
}

export function SmallMultiples({ id, title, cells, t, height = 120, maxCells = 8, listBelow = 560, note }: SmallMultiplesProps) {
  const [shared, setShared] = useState(true);
  const [all, setAll] = useState(false);
  const [ref, width] = useContainerWidth<HTMLElement>();
  const asList = width > 0 && width < listBelow;
  const shown = all ? cells : cells.slice(0, maxCells);
  const range = useMemo(() => (shared ? sharedRange(shown.map((cell) => cell.data)) : null), [shared, shown]);
  const download = () => {
    const blob = new Blob([csvOfCells(cells)], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${id}.csv`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  };
  return (
    <section ref={ref} className="ds-multiples" data-multiples={id} data-multiples-form={asList ? "list" : "grid"} data-multiples-scale={shared ? "shared" : "independent"} aria-labelledby={`${id}-title`}>
      <header className="ds-multiples-head">
        <h3 id={`${id}-title`}>{title}</h3>
        {!asList && <span className="ds-multiples-scale">{shared ? t("chart.multiples.shared") : t("chart.multiples.independent")}</span>}
        <span className="ds-chart-actions">
          {!asList && (
            <button type="button" className="ds-inline-link" aria-pressed={!shared} onClick={() => setShared(!shared)} data-multiples-toggle="scale">
              {shared ? t("chart.multiples.use_independent") : t("chart.multiples.use_shared")}
            </button>
          )}
          <button type="button" className="ds-inline-link" onClick={download} title={t("chart.csv_title")} data-chart-export="csv">
            {t("chart.csv")}
          </button>
        </span>
      </header>
      {asList ? (
        <ul className="ds-multiples-list">
          {shown.map((cell) => (
            <li key={cell.id} data-multiple={cell.id} aria-current={cell.selected ? "true" : undefined}>
              <button type="button" className="ds-multiples-row" onClick={cell.onSelect} disabled={!cell.onSelect}>
                <span className="ds-multiples-name">{cell.title}</span>
                <span className="ds-multiples-headline">{cell.headline}</span>
              </button>
              {cell.spark && cell.spark.values.length > 1 && (
                <Sparkline
                  values={cell.spark.values}
                  days={cell.spark.days}
                  label={cell.title}
                  unit={cell.spark.unit}
                  decimals={cell.spark.decimals ?? 1}
                  simulated={cell.simulated}
                  height={20}
                  t={t}
                  onOpen={cell.onSelect}
                />
              )}
            </li>
          ))}
        </ul>
      ) : (
        <div className="ds-multiples-grid">
          {shown.map((cell) => (
            <div key={cell.id} className={`ds-multiples-cell${cell.selected ? " is-selected" : ""}`} data-multiple={cell.id}>
              <Chart
                id={`${id}-${cell.id}`}
                title={cell.title}
                data={cell.data}
                t={t}
                height={height}
                simulated={cell.simulated}
                compare={cell.compare}
                yRange={range}
                compact
                controls={cell.onSelect ? (
                  <button type="button" className="ds-inline-link" onClick={cell.onSelect} aria-pressed={cell.selected ? "true" : "false"} data-multiple-open={cell.id}>
                    {t("chart.multiples.open")}
                  </button>
                ) : undefined}
                subtitle={cell.headline}
              />
            </div>
          ))}
        </div>
      )}
      {cells.length > maxCells && (
        <button type="button" className="ds-inline-link ds-multiples-more" onClick={() => setAll(!all)} aria-expanded={all}>
          {all ? t("chart.multiples.fewer", { count: maxCells }) : t("chart.multiples.all", { count: cells.length })}
        </button>
      )}
      {note && <p className="ds-chart-note">{note}</p>}
    </section>
  );
}
