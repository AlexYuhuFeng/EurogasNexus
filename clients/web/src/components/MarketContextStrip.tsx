/**
 * Market context strip (Architecture V2 Wave 5, surface half).
 *
 * The projection gives the market surface one coherent reading: a single as-of
 * instant, one time basis, and per-slice freshness and entitlement. This strip
 * shows exactly that, so a trader can see which slices are usable before trusting
 * a number, instead of the surface reconciling several endpoint timestamps itself.
 *
 * It renders what the backend reported: a slice the backend could not serve reads
 * as unavailable rather than as an empty market, and a slice whose rows were
 * filtered reads as restricted rather than as a zero.
 */

import type { MarketContextProjectionDTO } from "@/api/client";
import {
  MARK_CONTEXT_SLICE_LABEL_KEYS,
  contextAsOf,
  contextTimeBasis,
  degradedSlices,
  sliceReadings,
} from "@/app/model/marketContextModel";
import { formatUtcTimestamp } from "@/app/model/evidencePresentation";
import { StatusBadge } from "@/components/ui";

type Translate = (key: string, options?: Record<string, unknown>) => string;

interface MarketContextStripProps {
  projection: MarketContextProjectionDTO | null;
  t: Translate;
}

export function MarketContextStrip({ projection, t }: MarketContextStripProps) {
  if (!projection) return null;

  const readings = sliceReadings(projection);
  const degraded = degradedSlices(projection);
  const asOf = contextAsOf(projection);
  const basis = contextTimeBasis(projection);
  const gasDay = typeof basis?.gas_day === "string" ? basis.gas_day : null;
  const basisId = typeof basis?.basis_id === "string" ? basis.basis_id : null;

  return (
    <section className="market-context-strip" aria-label={t("market_context.title")}>
      <div className="market-context-summary">
        <span className="eyebrow">{t("market_context.title")}</span>
        <strong>
          {asOf
            ? t("market_context.as_of", { value: formatUtcTimestamp(asOf, asOf) })
            : t("market_context.as_of_unknown")}
        </strong>
        <span>
          {t("market_context.time_basis")}: {basisId ?? t("market_context.not_reported")}
          {gasDay ? ` · ${gasDay}` : ""}
        </span>
        <span>
          {degraded.length === 0
            ? t("market_context.all_fresh")
            : t("market_context.degraded", { count: degraded.length })}
        </span>
      </div>

      <ul className="market-context-slices">
        {readings.map((reading) => (
          <li key={reading.key}>
            <span className="market-context-slice-label">
              {t(MARK_CONTEXT_SLICE_LABEL_KEYS[reading.key] ?? "market_context.title")}
            </span>
            <StatusBadge
              variant="source"
              status={reading.available ? reading.freshnessState.toLowerCase() : "unavailable"}
            >
              {reading.available
                ? t(`market_context.freshness.${reading.freshnessState}`)
                : t("market_context.freshness.UNAVAILABLE")}
            </StatusBadge>
            <span className="market-context-slice-count">
              {t("market_context.rows", { count: reading.rowCount })}
            </span>
            {reading.restricted && (
              <span className="market-context-slice-restricted">
                {t("market_context.restricted", { count: reading.filteredOut })}
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
