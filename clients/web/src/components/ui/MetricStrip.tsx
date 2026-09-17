import type { ReactNode } from "react";

export interface MetricStripItem {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  /** Unit of the value, so a headline number is never read as unitless. */
  unit?: string;
}

interface MetricStripProps {
  className?: string;
  items: readonly MetricStripItem[];
  /**
   * When the strip's values were taken, already formatted. A `metric-strip` owes `as-of`,
   * `units` and `time-basis` (see `app/experience/panelTaxonomy.ts`): the primitive carries
   * the slots so a surface can disclose them *through* the shared panel instead of hoping
   * every caller remembers. Omitting them renders nothing rather than an invented value.
   *
   * The items stay the strip's direct children and the disclosures render in a footer, so
   * existing metric-grid layouts (including their `> div` selectors) are unaffected.
   */
  asOf?: ReactNode;
  /** The declared time basis the as-of is expressed in, already formatted. */
  timeBasis?: ReactNode;
}

export function MetricStrip({ className, items, asOf, timeBasis }: MetricStripProps) {
  const showsAsOf = asOf !== undefined && asOf !== null;
  const showsTimeBasis = timeBasis !== undefined && timeBasis !== null;
  return (
    <div className={className ?? "metric-grid"}>
      {items.map((item, index) => (
        <div key={`${item.label}-${index}`}>
          <span>{item.label}</span>
          <strong>
            {item.value}
            {item.unit ? <small className="metric-strip-unit">{item.unit}</small> : null}
          </strong>
          {item.detail !== undefined && item.detail !== null ? <small>{item.detail}</small> : null}
        </div>
      ))}
      {(showsAsOf || showsTimeBasis) && (
        <footer className="metric-strip-disclosures">
          {showsAsOf ? <span data-disclosure="as-of">{asOf}</span> : null}
          {showsTimeBasis ? <span data-disclosure="time-basis">{timeBasis}</span> : null}
        </footer>
      )}
    </div>
  );
}
