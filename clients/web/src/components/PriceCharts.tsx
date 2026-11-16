/**
 * Prices charts (UX-09): the forward curve of one hub by delivery month, in its quotation, and
 * the NBP–TTF spread by delivery month in p/th. Both read the normalized rows the board reads,
 * so the charts and the board say the same prices; the preparation is `priceCharts.ts`.
 */
import { useMemo, useState } from "react";

import type { NormalizedMarketObsDTO } from "@/api/client";
import { curveHubs, forwardCurve, nbpTtfSpread, type CurveRow } from "@/app/model/priceCharts";
import { Segmented } from "@/components/ui";
import { Chart, type ChartData } from "@/components/ui/charts";

type Translate = (key: string, options?: Record<string, unknown>) => string;

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
  const curve = useMemo(() => (hub ? forwardCurve(rows, hub, front) : null), [rows, hub, front]);
  const spread = useMemo(() => nbpTtfSpread(rows, front), [rows, front]);

  const curveData = useMemo<ChartData | null>(() => curve && hub ? {
    axis: "period",
    x: curve.months,
    xTitle: t("chart.delivery_month"),
    unit: curve.unit,
    series: [{ id: hub.toLowerCase(), label: hub, values: curve.values, simulated: curve.simulated, decimals: 3 }],
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
