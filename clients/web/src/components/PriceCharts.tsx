/**
 * Prices charts (UX-09, F.3 #1): the term structure of one hub by delivery month, in its
 * quotation, with the prior close and a week ago as grey ghost curves; and
 * the NBP–TTF spread by delivery month in p/th. Both read the normalized rows the board reads,
 * so the charts and the board say the same prices; the preparation is `priceCharts.ts`.
 */
import { useMemo, useState } from "react";

import type { NormalizedMarketObsDTO } from "@/api/client";
import { curveHubs, nbpTtfSpread, termStructure, type CurveRow } from "@/app/model/priceCharts";
import { Segmented } from "@/components/ui";
import { Chart, type ChartData } from "@/components/ui/charts";

type Translate = (key: string, options?: Record<string, unknown>) => string;

/** "2026-11-16" -> "16 Nov": a close day in a ghost curve's label. */
function shortClose(day: string): string {
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${Number(day.slice(8, 10))} ${months[Number(day.slice(5, 7)) - 1] ?? ""}`;
}

/** The front delivery month: the month after the current one (UTC). */
function frontMonth(now = new Date()): string {
  const next = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() + 1, 1));
  return next.toISOString().slice(0, 7);
}

export function PriceCharts({ markets, t }: { markets: readonly NormalizedMarketObsDTO[]; t: Translate }) {
  const rows = markets as unknown as readonly CurveRow[];
  const hubs = useMemo(() => curveHubs(rows), [rows]);
  const [chosen, setChosen] = useState<string | null>(null);
  const hub = chosen && hubs.includes(chosen) ? chosen : hubs[0] ?? null;
  const front = frontMonth();
  const curve = useMemo(() => (hub ? termStructure(rows, hub, front) : null), [rows, hub, front]);
  const spread = useMemo(() => nbpTtfSpread(rows, front), [rows, front]);

  // The term structure (F.1): today's curve with a marker per delivery month, the prior close
  // and a week ago as grey ghost curves, one unit, labelled at the line ends.
  const curveData = useMemo<ChartData | null>(() => curve && hub ? {
    axis: "period",
    x: curve.months,
    xTitle: t("chart.delivery_month"),
    unit: curve.unit,
    series: [
      ...(curve.weekAgo
        ? [{ id: "week-ago", label: t("prices.chart.week_ago", { day: shortClose(curve.weekAgo.day) }), values: curve.weekAgo.values, ghost: true, simulated: curve.simulated, decimals: 3 }]
        : []),
      ...(curve.priorClose
        ? [{ id: "prior-close", label: t("prices.chart.prior_close", { day: shortClose(curve.priorClose.day) }), values: curve.priorClose.values, ghost: true, simulated: curve.simulated, decimals: 3 }]
        : []),
      { id: hub.toLowerCase(), label: hub, values: curve.current, simulated: curve.simulated, decimals: 3 },
    ],
  } : null, [curve, hub, t]);
  const spreadData = useMemo<ChartData>(() => ({
    axis: "period",
    x: spread.months,
    xTitle: t("chart.delivery_month"),
    unit: spread.unit,
    series: [{ id: "nbp-ttf", label: t("prices.chart.spread_series"), values: spread.values, style: "bar", simulated: spread.simulated, colour: 5, decimals: 3 }],
  }), [spread, t]);

  if (hubs.length === 0) return null;
  return (
    <section className="workspace-panel span-3 price-charts" aria-label={t("prices.chart.region")} data-price-charts="true">
      {curveData && (
        <Chart
          id="forward-curve"
          title={t("prices.chart.curve_title", { hub })}
          data={curveData}
          t={t}
          height={220}
          asOf={curve?.asOf}
          simulated={curve?.simulated}
          controls={hubs.length > 1 ? (
            <Segmented
              label={t("prices.chart.hub")}
              options={hubs.map((value) => ({ value, label: value }))}
              value={hub ?? ""}
              onChange={setChosen}
            />
          ) : undefined}
          subtitle={curve && !curve.priorClose && !curve.weekAgo ? t("prices.chart.no_prior_close") : undefined}
          note={t("prices.chart.curve_note")}
        />
      )}
      {spread.months.length > 0 && (
        <Chart
          id="nbp-ttf-spread"
          title={t("prices.chart.spread_title")}
          data={spreadData}
          t={t}
          height={180}
          asOf={spread.asOf}
          simulated={spread.simulated}
          note={t("prices.chart.spread_note")}
        />
      )}
    </section>
  );
}
