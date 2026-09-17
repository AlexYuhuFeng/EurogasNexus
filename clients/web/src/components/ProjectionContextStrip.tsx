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

import type { SliceReading } from "@/app/model/projectionModel";
import { formatUtcTimestamp } from "@/app/model/evidencePresentation";
import { StatusBadge } from "@/components/ui";
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
}: ProjectionContextStripProps) {
  if (readings.length === 0) return null;

  const gasDay = typeof basis?.gas_day === "string" ? basis.gas_day : null;
  const basisId = typeof basis?.basis_id === "string" ? basis.basis_id : null;
  const key = (suffix: string) => `${namespace}.${suffix}`;

  return (
    <section
      className={className ? `projection-context ${className}` : "projection-context"}
      aria-label={t(key("title"))}
    >
      <div className="projection-context-summary">
        <span className="eyebrow">{t(key("title"))}</span>
        <strong>
          {asOf
            ? t(key("as_of"), { value: formatUtcTimestamp(asOf, asOf) })
            : t(key("as_of_unknown"))}
        </strong>
        <span>
          {t(key("time_basis"))}: {basisId ?? t(key("not_reported"))}
          {gasDay ? ` · ${gasDay}` : ""}
        </span>
        <span>
          {degraded.length === 0
            ? t(key("all_fresh"))
            : t(key("degraded"), { count: degraded.length })}
        </span>
      </div>

      <ul className="projection-context-slices">
        {readings.map((reading) => (
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
            {reading.lastObservedAtUtc && (
              <time>{formatUtcTimestamp(reading.lastObservedAtUtc, reading.lastObservedAtUtc)}</time>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
