/**
 * Projection context strip (Architecture V2 Wave 5, shared surface half).
 *
 * Every projection the client reads reports the same three things a person needs
 * before trusting a number: when the payload was taken, on which time basis, and
 * which slices are fresh, stale, missing or withheld. This component renders that
 * reading for any projection, so the market and portfolio surfaces cannot drift
 * into two different definitions of "usable".
 *
 * It is presentational. It does not fetch, recompute or reconcile timestamps: the
 * as-of and the freshness are the backend's answers, and an unavailable slice reads
 * as unavailable rather than as an empty result.
 */

import { type ReactNode } from "react";

import {
  declaredGasDayCalendar,
  declaredTimeBasisKey,
  type SliceReading,
} from "@/app/model/projectionModel";
import { useCompactWidth } from "@/app/shell/useShellLayout";
import { useInstantFormatter } from "@/app/time/useInstant";
import { Popover, StatusBadge } from "@/components/ui";
import "@/components/projection-context.css";

type Translate = (key: string, options?: Record<string, unknown>) => string;

interface ProjectionContextStripProps {
  /** Root translation namespace, e.g. `portfolio_context`. */
  namespace: string;
  /** Extra class for the surface's own grid placement. */
  className?: string;
  readings: readonly SliceReading[];
  degraded: readonly SliceReading[];
  /** Slice key -> translation key, in the order the readings are rendered. */
  labelKeys: Readonly<Record<string, string>>;
  asOf: string | null;
  basis: Record<string, unknown> | null;
  t: Translate;
  /** Surface-specific qualification, rendered beside the shared summary. */
  children?: ReactNode;
  /** The page's own controls (gas day, product, hub), shown before the status. */
  controls?: ReactNode;
  /**
   * The page's own freshness line, in place of the feed count: the Today screen names its late
   * or stale figures, and a simulated desk adds no label of its own instead of counting feeds of a
   * deliberately static store as stale (FRESH-02).
   */
  freshness?: ReactNode;
}

export function ProjectionContextStrip({
  namespace,
  className,
  readings,
  degraded,
  labelKeys,
  asOf,
  basis,
  t,
  children,
  controls,
  freshness,
}: ProjectionContextStripProps) {
  const compact = useCompactWidth();
  const formatInstant = useInstantFormatter();
  if (readings.length === 0) return null;
  const shownAsOf = formatInstant(asOf);

  // The declared basis the backend actually reports (`time_basis.basis`), labelled through the
  // vocabulary the Data Product catalogue already uses; an unrecognised code is shown as itself.
  const basisKey = declaredTimeBasisKey(basis);
  const gasDay = typeof basis?.gas_day === "string" ? basis.gas_day : null;
  const gasDayCalendar = declaredGasDayCalendar(basis);
  const key = (suffix: string) => `${namespace}.${suffix}`;

  return (
    // The payload's own as-of instant is carried verbatim beside the formatted one it displays: the
    // browser sweep holds the displayed instant to the read it belongs to instead of parsing copy.
    <section
      className={className ? `projection-context ${className}` : "projection-context"}
      aria-label={t(key("title"))}
      data-projection-as-of={asOf ?? undefined}
    >
      {/* One line a trader reads: the page's own context controls, then whether the data
          behind the page is current, in words. The sentence is a link: it opens the feeds by
          name (the degraded ones first) with the as-of instant, time basis and calendar, so no
          page says "stale" without naming what is affected (FRESH-02). */}
      {controls}
      <div className="projection-context-status">
        {freshness}
        {/* The as-of instant stays on the line itself: a trader reads how old the page is without
            opening anything, and the browser sweep holds this text to the read it belongs to. */}
        {/* In the reader's zone, short ("as of 00:57 CET"); the full instant is the tooltip and the
            UTC instant the `dateTime` the sweep compares with the read. */}
        {shownAsOf ? (
          <time className="projection-context-asof" dateTime={shownAsOf.iso} title={shownAsOf.title}>
            {t(compact ? "context_line.as_of_short" : key("as_of"), { value: shownAsOf.text })}
          </time>
        ) : (
          <span className="projection-context-asof">{t(key("as_of_unknown"))}</span>
        )}
        <Popover
          label={t(key("title"))}
          id="feed-status"
          placement="bottom-end"
          trigger={(props) => (
            <button
              {...props}
              type="button"
              className={`projection-context-trigger ${degraded.length === 0 || freshness ? "is-ok" : "is-degraded"}`}
            >
              {freshness || (compact && degraded.length === 0)
                ? t("context_line.feeds")
                : degraded.length === 0
                  ? t("context_line.fresh")
                  : compact
                    ? t("context_line.stale_short", { count: degraded.length, total: readings.length })
                    : t("context_line.stale", { count: degraded.length, total: readings.length })}
            </button>
          )}
        >
          <p className="ds-popover-meta projection-context-basis">
            {t(key("time_basis"))}: {basisKey ? t(basisKey) : t(key("not_reported"))}
            {gasDay ? ` · ${gasDay}` : ""}
            {gasDayCalendar ? ` · ${t(key("gas_day_calendar"))} ${gasDayCalendar}` : ""}
          </p>
          <ul className="projection-context-slices">
            {[...degraded, ...readings.filter((reading) => !degraded.some((item) => item.key === reading.key))].map((reading) => (
              <li key={reading.key}>
                <span className="projection-slice-label">
                  {t(labelKeys[reading.key] ?? key("title"))}
                </span>
                <StatusBadge
                  variant="source"
                  status={reading.available ? reading.freshnessState.toLowerCase() : "unavailable"}
                >
                  {reading.available
                    ? t(key(`freshness.${reading.freshnessState}`))
                    : t(key("freshness.UNAVAILABLE"))}
                </StatusBadge>
                <span className="projection-slice-count">
                  {t(key("rows"), { count: reading.rowCount })}
                </span>
                {reading.restricted && (
                  <span className="projection-slice-restricted">
                    {t(key("restricted"), { count: reading.filteredOut })}
                  </span>
                )}
                {reading.lastObservedAtUtc && (() => {
                  const observed = formatInstant(reading.lastObservedAtUtc);
                  return observed ? <time dateTime={observed.iso} title={observed.title}>{observed.text}</time> : null;
                })()}
              </li>
            ))}
          </ul>
        </Popover>
        {children}
      </div>
    </section>
  );
}
