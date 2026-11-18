/**
 * LNG send-out by country (CP-17; design basis 2, D.2 "LNG"): the EU total first, then each
 * country GIE ALSI publishes, against their own history. One server read
 * (`GET /api/fundamentals/lng`); send-out is the 7-day mean (daily send-out moves with
 * cargoes), the day's own figure beside it.
 *
 * - The EU total's figures: send-out (7-day mean and the day), vs the same gas day last year,
 *   vs the N-year mean (N stated) with the percentile strip, inventory and its share of the
 *   declared maximum.
 * - The CP-03 season chart of the EU total or the chosen country (band or the years held as
 *   lines; a terminal opened recently has fewer years and says so).
 * - The countries as a compact sortable table with sparklines; a row opens its chart; then
 *   every country as small multiples.
 */
import { useEffect, useMemo, useState } from "react";

import { api, type FundamentalsLngDTO, type LngEntityDTO } from "@/api/client";
import { seasonChart } from "@/app/model/storageByCountry";
import { formatGasDay } from "@/app/time/timeFormat";
import { DataGrid, EmptyState, Skeleton, StatusBadge, type DataGridColumn } from "@/components/ui";
import { Chart, PercentileStrip, Sparkline, formatSigned } from "@/components/ui/charts";
import { CountryMultiples } from "./CountryMultiples";

type Translate = (key: string, options?: Record<string, unknown>) => string;

const num = (value: number | null | undefined, decimals = 0) =>
  value == null ? "–" : value.toLocaleString("en-GB", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
const signed = (value: number | null | undefined, decimals = 0) => (value == null ? "–" : formatSigned(value, decimals));
const sparkOf = (entity: LngEntityDTO) => ({
  values: entity.spark.map((point) => point.send_out_7d_gwh_d),
  days: entity.spark.map((point) => point.day),
});

export function LngByCountryPanel({ t, language }: { t: Translate; language: string }) {
  const [selected, setSelected] = useState<string | null>(null);
  const [data, setData] = useState<FundamentalsLngDTO | null>(null);
  const [attribution, setAttribution] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Every country's season once (the small multiples need them all); a row only switches view.
  useEffect(() => {
    const controller = new AbortController();
    api
      .fundamentalsLng(["EU", "BE", "DE", "ES", "FI", "FR", "GR", "HR", "IT", "LT", "NL", "PL", "PT"], { signal: controller.signal })
      .then((response) => {
        setData(response.data);
        setAttribution((response.meta as { attribution?: string | null } | undefined)?.attribution ?? null);
      })
      .catch((caught: unknown) => !controller.signal.aborted && setError(caught instanceof Error ? caught.message : String(caught)));
    return () => controller.abort();
  }, []);

  const shown = useMemo(() => (data ? (selected ? data.countries.find((c) => c.code === selected) : null) ?? data.region : null), [data, selected]);
  const chart = useMemo(() => shown && seasonChart(
    shown,
    {
      lastYear: (year) => t("storage_panel.last_year", { year }),
      thisYear: (year) => year,
      mean: (count) => t("chart.history.mean", { count }),
      target: (pct) => String(pct),
      xTitle: t("storage_panel.day_of_gas_year"),
    },
    shown.season?.band ? t("storage_panel.compare_mean", { count: shown.season.band.years.length }) : t("storage_panel.compare_last_year"),
    "GWh/d",
  ), [shown, t]);

  const columns = useMemo<DataGridColumn<LngEntityDTO>[]>(() => [
    {
      id: "country", header: t("storage_panel.country"), rowHeader: true, sortable: true, priority: "primary", value: (row) => row.name,
      render: (row) => (
        <>
          {row.name} <small className="muted">{row.code}</small>
          {row.simulated && <span className="ds-cell-mark" data-state="simulated" title={t("today.simulated_long")}> {t("today.simulated_short")}</span>}
        </>
      ),
    },
    { id: "send-out", header: t("lng_panel.send_out_short"), headerTitle: t("lng_panel.send_out_7d"), unit: "GWh/d", type: "number", sortable: true, priority: "primary", value: (row) => row.send_out_7d_gwh_d, format: (v) => num(v as number | null) },
    { id: "last-year", header: t("storage_panel.vs_last_year_short"), unit: "GWh/d", type: "number", sortable: true, priority: "secondary", value: (row) => row.vs_last_year.diff_gwh_d, format: (v) => signed(v as number | null) },
    {
      id: "average", header: t("storage_panel.vs_avg_column"), unit: "GWh/d", type: "number", sortable: true,
      value: (row) => row.vs_average.diff_gwh_d, format: (v) => signed(v as number | null), cellTitle: (row) => row.history.label,
    },
    { id: "inventory", header: t("lng_panel.inventory"), unit: "%", type: "number", sortable: true, value: (row) => row.inventory_pct_of_dtmi, format: (v) => num(v as number | null, 1) },
    {
      id: "trend", header: t("storage_panel.trend"), width: "120px",
      render: (row) => <Sparkline {...sparkOf(row)} label={t("lng_panel.spark_label", { name: row.name })} unit="GWh/d" decimals={0} simulated={row.simulated} height={20} t={t} />,
    },
  ], [t]);

  if (!data) {
    return error ? <EmptyState compact reason={t("lng_panel.failed")} next={error} /> : <Skeleton label={t("lng_panel.loading")} rows={4} />;
  }
  const region = data.region;
  const average = region?.vs_average;
  return (
    <section className="storage-panel" aria-labelledby="lng-panel-title" data-lng-panel={data.simulated ? "simulated" : "provider"} data-lng-selected={selected ?? "EU"}>
      <header className="storage-panel-head">
        <h3 id="lng-panel-title">{t("lng_panel.title")}</h3>
      </header>
      {region ? (
        <dl className="storage-figures" data-figure-entity="EU">
          <div>
            <dt>{t("lng_panel.send_out_7d")}</dt>
            <dd data-figure="send_out_7d">
              {num(region.send_out_7d_gwh_d)} <small>GWh/d</small>
              {region.simulated && <StatusBadge tone="simulated" title={t("today.simulated_long")}>{t("today.simulated_short")}</StatusBadge>}
            </dd>
            <dd className="storage-figure-note">{t("lng_panel.day_value", { value: num(region.send_out_day_gwh_d), day: formatGasDay(region.as_of, language, true) })}</dd>
          </div>
          <div>
            <dt>{t("storage_panel.vs_last_year")}</dt>
            <dd>{signed(region.vs_last_year.diff_gwh_d)} <small>GWh/d</small></dd>
          </div>
          <div>
            <dt>{average?.years ? t("storage_panel.vs_avg", { count: average.years }) : t("storage_panel.vs_avg_none")}</dt>
            <dd>{signed(average?.diff_gwh_d)} <small>GWh/d</small></dd>
            {average && average.range_position != null && region.history.mode === "band" && (
              <dd>
                <PercentileStrip t={t} position={average.range_position} outside={average.outside}
                  caption={t("storage_panel.range_position", { pct: Math.round(average.range_position) })}
                  window={region.history.label} lowLabel={num(average.low_gwh_d)} highLabel={num(average.high_gwh_d)} />
              </dd>
            )}
          </div>
          <div>
            <dt>{t("lng_panel.inventory")}</dt>
            <dd>{num(region.inventory_twh, 1)} <small>TWh</small></dd>
            <dd className="storage-figure-note">{t("lng_panel.of_dtmi", { pct: num(region.inventory_pct_of_dtmi, 1) })}</dd>
          </div>
        </dl>
      ) : (
        <EmptyState compact reason={t("storage_panel.no_region")} />
      )}
      {shown && chart && (
        <Chart
          id="lng-season"
          title={t("lng_panel.chart_title", { name: shown.name })}
          data={chart.data}
          subtitle={chart.subtitle}
          compare={chart.compare}
          t={t}
          height={260}
          simulated={shown.simulated}
          asOf={shown.as_of}
          controls={selected ? (
            <button type="button" className="ds-inline-link" onClick={() => setSelected(null)}>{t("storage_panel.back_to_region", { name: region?.name ?? "EU" })}</button>
          ) : undefined}
          note={[t("lng_panel.note"), attribution && !shown.simulated ? attribution : null].filter(Boolean).join(" · ")}
        />
      )}
      <DataGrid
        id="lng-countries"
        label={t("lng_panel.title")}
        columns={columns}
        rows={data.countries}
        rowKey={(row) => row.code}
        density="compact"
        selectedKey={selected}
        onRowAction={(row) => setSelected(selected === row.code ? null : row.code)}
        rowAttributes={(row) => ({ "data-lng-country": row.code })}
        caption={t("storage_panel.table_caption")}
      />
      <CountryMultiples
        id="lng-multiples"
        title={t("lng_panel.all_countries")}
        entities={data.countries}
        unit="GWh/d"
        headline={(entity) => `${num(entity.send_out_7d_gwh_d)} GWh/d`}
        spark={sparkOf}
        onSelect={(code) => setSelected(code)}
        selected={selected}
        t={t}
      />
      {data.missing.length > 0 && (
        <p className="storage-panel-missing">{t("storage_panel.missing")} {data.missing.map((m) => m.code).join(", ")}</p>
      )}
    </section>
  );
}
