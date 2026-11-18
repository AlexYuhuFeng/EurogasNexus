/**
 * Prices charts (UX-09; design basis 2, F.3 #1 and #2, CP-20):
 *
 * - the term structure of one hub by delivery month in its own quotation, with the prior close
 *   and a week ago as grey ghost curves; "Compare" adds up to two more hubs, and then every hub
 *   is shown in EUR/MWh, each month converted on the server at the forward FX of that month
 *   (`termStructureCompare.ts`), stated under the chart;
 * - the spread by delivery month is no longer a bar chart: one line links to Research → Spreads
 *   with the pair's spread net of transport already described, where it is computed with
 *   forward FX and the published route tariffs.
 *
 * The hubs are chosen with the InstrumentPicker at hub level (type `nbp`, `英国`).
 */
import { useEffect, useMemo, useState } from "react";

import "@/styles/prices.css";

import { api, type NormalizedMarketObsDTO } from "@/api/client";
import { curveHubs, forwardCurve, termStructure, type CurveRow } from "@/app/model/priceCharts";
import {
  COMPARE_UNIT,
  MAX_COMPARED_HUBS,
  compareRequest,
  comparedCurves,
  spreadsLink,
  type ComparedCurves,
} from "@/app/model/termStructureCompare";
import { Button, InstrumentPicker } from "@/components/ui";
import { catalogueFromHubs } from "@/app/model/instrumentPicker";
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
  // The picker lists each hub in its quotation, with `sim` when its curve is simulated.
  const hubCatalogue = useMemo(
    () => catalogueFromHubs(hubs.map((code) => {
      const own = forwardCurve(rows, code, front);
      return { hub: code, nativeUnit: own.unit, simulated: own.simulated, lastAsOf: own.asOf ?? null };
    })),
    [rows, hubs, front],
  );
  const curve = useMemo(() => (hub ? termStructure(rows, hub, front) : null), [rows, hub, front]);
  // Compared hubs (at most two besides the chosen one), shown in one unit on the server's FX.
  const [compareWith, setCompareWith] = useState<string[]>([]);
  const compared = useMemo(
    () => compareWith.filter((code) => hubs.includes(code) && code !== hub).slice(0, MAX_COMPARED_HUBS - 1),
    [compareWith, hubs, hub],
  );
  const [comparison, setComparison] = useState<ComparedCurves | null>(null);
  useEffect(() => {
    if (!hub || compared.length === 0) {
      setComparison(null);
      return undefined;
    }
    let live = true;
    const curves = [hub, ...compared].map((code) => {
      const own = forwardCurve(rows, code, front);
      return { hub: code, months: own.months, values: own.values, unit: own.unit };
    });
    const { body, keys } = compareRequest(curves);
    api.normaliseMarket(body)
      .then((response) => { if (live) setComparison(comparedCurves(curves, keys, response.data)); })
      .catch(() => { if (live) setComparison(null); });
    return () => { live = false; };
  }, [rows, hub, compared, front]);
  const compareCatalogue = useMemo(
    () => ({ hubs: hubCatalogue.hubs.filter((item) => item.hub !== hub && !compared.includes(item.hub)) }),
    [hubCatalogue, hub, compared],
  );

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
  const compareData = useMemo<ChartData | null>(() => comparison ? {
    axis: "period",
    x: comparison.months,
    xTitle: t("chart.delivery_month"),
    unit: COMPARE_UNIT,
    series: comparison.series.map((item) => ({ id: item.hub.toLowerCase(), label: item.hub, values: item.values, simulated: comparison.simulated, decimals: 3 })),
  } : null, [comparison, t]);
  const spreadHref = hub ? spreadsLink(typeof window === "undefined" ? "" : window.location.search, hub) : null;
  const spreadPair = hub === "TTF" || !hub ? "NBP − TTF" : `${hub} − TTF`;

  if (hubs.length === 0) return null;
  return (
    <section className="workspace-panel span-3 price-charts" aria-label={t("prices.chart.region")} data-price-charts="true">
      {(compareData ?? curveData) && (
        <Chart
          id="forward-curve"
          title={compareData
            ? t("prices.chart.compare_title", { hubs: [hub, ...compared].join(", ") })
            : t("prices.chart.curve_title", { hub })}
          data={(compareData ?? curveData)!}
          t={t}
          height={220}
          asOf={curve?.asOf}
          simulated={compareData ? comparison?.simulated : curve?.simulated}
          controls={hubs.length > 1 ? (
            <div className="price-charts-controls">
              <InstrumentPicker
                id="forward-curve-hub"
                scope="hub"
                label={t("prices.chart.hub")}
                catalogue={hubCatalogue}
                value={hub}
                onChange={(selection) => setChosen(selection.hub)}
              />
              {compared.length < MAX_COMPARED_HUBS - 1 && compareCatalogue.hubs.length > 0 && (
                <InstrumentPicker
                  id="forward-curve-compare"
                  scope="hub"
                  label={t("prices.chart.compare")}
                  catalogue={compareCatalogue}
                  value={null}
                  onChange={(selection) => setCompareWith((current) => [...current.filter((code) => code !== selection.hub), selection.hub])}
                />
              )}
              {compared.length > 0 && (
                <Button variant="secondary" size="sm" onClick={() => setCompareWith([])}>
                  {t("prices.chart.compare_clear")}
                </Button>
              )}
            </div>
          ) : undefined}
          subtitle={!compareData && curve && !curve.priorClose && !curve.weekAgo ? t("prices.chart.no_prior_close") : undefined}
          note={compareData
            ? [
                t("prices.chart.compare_note", { unit: COMPARE_UNIT, fx: comparison?.fxLabels.join("; ") || t("prices.chart.compare_no_fx") }),
                comparison && comparison.beyondHorizon > 0 ? t("prices.chart.compare_beyond", { count: comparison.beyondHorizon }) : "",
                comparison && comparison.refused.length > 0 ? t("prices.chart.compare_refused", { reasons: comparison.refused.join("; ") }) : "",
              ].filter(Boolean).join(" ")
            : t("prices.chart.curve_note")}
        />
      )}
      {spreadHref && (
        <p className="price-charts-spread-link" data-spread-link="true">
          <span>{t("prices.chart.spread_link_text", { pair: spreadPair })}</span>{" "}
          <a
            className="ds-inline-link"
            href={spreadHref}
            onClick={(event) => {
              if (event.metaKey || event.ctrlKey || event.shiftKey) return;
              event.preventDefault();
              window.history.pushState({ workspace: "research" }, "", spreadHref);
              window.dispatchEvent(new PopStateEvent("popstate"));
            }}
          >
            {t("prices.chart.spread_link")}
          </a>
        </p>
      )}
    </section>
  );
}
