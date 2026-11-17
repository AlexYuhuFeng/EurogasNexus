/**
 * Two (or more) aligned panels on one x axis (F.2: two units, or a level and its difference,
 * are two aligned panels, never a dual axis). The panels share the cursor, so the readout moves
 * in both at once, and the same room for end labels, so their x positions line up. Used for
 * the spread by delivery month (both curves above, the spread with a zero line below) and the
 * delivery chart (volumes above, the signed shortfall below).
 */
import type { ReactNode } from "react";

import { Chart } from "./Chart";
import { endLabelRoom, endLabels, usesEndLabels, type ChartComparison, type ChartData } from "./chartModel";

type Translate = (key: string, options?: Record<string, unknown>) => string;

export interface AlignedPanel {
  id: string;
  title: string;
  data: ChartData;
  height?: number;
  compare?: ChartComparison;
  note?: ReactNode;
}

export interface AlignedPanelsProps {
  id: string;
  title: string;
  panels: readonly AlignedPanel[];
  t: Translate;
  asOf?: string | null;
  simulated?: boolean;
  subtitle?: ReactNode;
  note?: ReactNode;
  controls?: ReactNode;
}

/** The end-label room every panel takes: the widest panel's, so the plots align. */
export function alignedLabelRoom(panels: readonly Pick<AlignedPanel, "data">[]): number {
  return Math.max(12, ...panels.map((panel) => (usesEndLabels(panel.data) ? endLabelRoom(endLabels(panel.data)) : 0)));
}

export function AlignedPanels({ id, title, panels, t, asOf, simulated, subtitle, note, controls }: AlignedPanelsProps) {
  const room = alignedLabelRoom(panels);
  // A bar panel pads its x range by half a day; the others pad alike so the days line up.
  const xPad = panels.some((panel) => panel.data.series.some((item) => item.style === "bar"));
  return (
    <section className="ds-aligned" data-aligned={id} aria-labelledby={`${id}-title`}>
      <header className="ds-multiples-head">
        <h3 id={`${id}-title`}>{title}</h3>
        {controls && <span className="ds-chart-actions">{controls}</span>}
        {subtitle && <span className="ds-chart-subtitle">{subtitle}</span>}
      </header>
      {panels.map((panel, position) => (
        <Chart
          key={panel.id}
          id={`${id}-${panel.id}`}
          title={panel.title}
          data={panel.data}
          t={t}
          height={panel.height ?? (position === 0 ? 180 : 120)}
          asOf={position === 0 ? asOf : undefined}
          simulated={simulated}
          compare={panel.compare}
          syncKey={id}
          labelRoom={room}
          xPad={xPad}
          note={panel.note}
        />
      ))}
      {note && <p className="ds-chart-note">{note}</p>}
    </section>
  );
}
