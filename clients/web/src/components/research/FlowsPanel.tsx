/**
 * Pipeline flows (CP-17; design basis 2, D.2 "Flows"): Norwegian gas landed in the EU and the
 * UK terminals, then each landing, against their own history (`GET /api/fundamentals/flows`),
 * and where north-west Europe's supply came from (pipeline, LNG, storage) as shares, from the
 * balance read.
 *
 * - The totals' figures: the 7-day mean landed and the day's value, vs the same gas day last
 *   year, vs the N-year mean (N stated) with the percentile strip.
 * - The CP-03 season chart of Norway, the UK terminals or the chosen landing.
 * - The landings as a sortable table with sparklines (a row opens its chart), then as small
 *   multiples.
 * - Supply shares over the last year as a stacked area (F.1: more than 14 days), with the
 *   days storage injected counted.
 */
import { useEffect, useMemo, useState } from "react";

import { api, type FlowEntityDTO, type FundamentalsFlowsDTO, type NweBalanceDTO } from "@/api/client";
import { supplyShares } from "@/app/model/flowsModel";
import { seasonChart } from "@/app/model/storageByCountry";
import { formatGasDay } from "@/app/time/timeFormat";
import { DataGrid, EmptyState, Skeleton, StatusBadge, type DataGridColumn } from "@/components/ui";
import { Chart, PercentileStrip, Sparkline, formatSigned, type ChartData } from "@/components/ui/charts";
import { CountryMultiples } from "./CountryMultiples";

type Translate = (key: string, options?: Record<string, unknown>) => string;

const num = (value: number | null | undefined, decimals = 0) =>
  value == null ? "–" : value.toLocaleString("en-GB", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
const signed = (value: number | null | undefined) => (value == null ? "–" : formatSigned(value, 0));
const sparkOf = (entity: FlowEntityDTO) => ({
  values: entity.spark.map((point) => point.flow_7d_gwh_d),
  days: entity.spark.map((point) => point.day),
});
export const LANDING_CODES = ["norway", "uk_terminal", "dornum", "emden", "zeebrugge", "dunkerque", "nybro", "easington", "st_fergus"];
const SHARE_DAYS = 365;

function TotalFigures({ entity, t, language }: { entity: FlowEntityDTO; t: Translate; language: string }) {
  const average = entity.vs_average;
  return (
    <div className="flows-total" data-flow-total={entity.code}>
      <h4>{t(`flows_panel.scope.${entity.code}`, { defaultValue: entity.name })}</h4>
      <dl className="storage-figures">
        <div>
          <dt>{t("flows_panel.flow_7d")}</dt>
          <dd data-figure={`flow_7d.${entity.code}`}>
            {num(entity.flow_7d_gwh_d)} <small>GWh/d</small>
            {entity.simulated && <StatusBadge tone="simulated" title={t("today.simulated_long")}>{t("today.simulated_short")}</StatusBadge>}
          </dd>
          <dd className="storage-figure-note">{t("lng_panel.day_value", { value: num(entity.flow_day_gwh_d), day: formatGasDay(entity.as_of, language, true) })}</dd>
        </div>
        <div>
          <dt>{t("storage_panel.vs_last_year")}</dt>
          <dd>{signed(entity.vs_last_year.diff_gwh_d)} <small>GWh/d</small></dd>
        </div>
        <div>
          <dt>{average.years ? t("storage_panel.vs_avg", { count: average.years }) : t("storage_panel.vs_avg_none")}</dt>
          <dd>{signed(average.diff_gwh_d)} <small>GWh/d</small></dd>
          {average.range_position != null && entity.history.mode === "band" && (
            <dd>
              <PercentileStrip t={t} position={average.range_position} outside={average.outside}
                caption={t("storage_panel.range_position", { pct: Math.round(average.range_position) })}
                window={entity.history.label} lowLabel={num(average.low_gwh_d)} highLabel={num(average.high_gwh_d)} />
            </dd>
          )}
        </div>
      </dl>
    </div>
  );
}

function SupplyShares({ t }: { t: Translate }) {
  const [balance, setBalance] = useState<NweBalanceDTO | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    api.nweBalanceHistory(SHARE_DAYS, { signal: controller.signal }).then((response) => setBalance(response.data)).catch(() => undefined);
    return () => controller.abort();
  }, []);
  const shares = useMemo(() => (balance ? supplyShares(balance.history) : null), [balance]);
  if (!shares || shares.days.length < 2) return null;
  const data: ChartData = {
    axis: "gas-day",
    x: shares.days,
    xTitle: t("chart.gas_day"),
    unit: "%",
    series: [
      { id: "pipeline", label: t("flows_panel.share_pipeline"), values: shares.pipeline, style: "area", stack: true, colour: 1, decimals: 1 },
      { id: "lng", label: t("flows_panel.share_lng"), values: shares.lng, style: "area", stack: true, colour: 2, decimals: 1 },
      { id: "storage", label: t("flows_panel.share_storage"), values: shares.storage, style: "area", stack: true, colour: 3, decimals: 1 },
    ],
  };
  return (
    <Chart
      id="supply-shares"
      title={t("flows_panel.shares_title")}
      data={data}
      t={t}
      height={200}
      note={t("flows_panel.shares_note", { count: shares.injectionDays })}
    />
  );
}

export function FlowsPanel({ t, language }: { t: Translate; language: string }) {
  const [selected, setSelected] = useState<string>("norway");
  const [data, setData] = useState<FundamentalsFlowsDTO | null>(null);
  const [attribution, setAttribution] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    api
      .fundamentalsFlows(LANDING_CODES, { signal: controller.signal })
      .then((response) => {
        setData(response.data);
        setAttribution((response.meta as { attribution?: string | null } | undefined)?.attribution ?? null);
      })
      .catch((caught: unknown) => !controller.signal.aborted && setError(caught instanceof Error ? caught.message : String(caught)));
    return () => controller.abort();
  }, []);
  const all = useMemo(() => (data ? [...data.totals, ...data.landings] : []), [data]);
  const shown = all.find((entity) => entity.code === selected) ?? all[0] ?? null;
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
  const columns = useMemo<DataGridColumn<FlowEntityDTO>[]>(() => [
    {
      id: "landing", header: t("flows_panel.landing"), rowHeader: true, sortable: true, priority: "primary", value: (row) => row.name,
      render: (row) => (
        <>
          {row.name} <small className="muted">{t(`flows_panel.scope_short.${row.scope ?? "norway"}`)}</small>
          {row.simulated && <span className="ds-cell-mark" data-state="simulated" title={t("today.simulated_long")}> {t("today.simulated_short")}</span>}
        </>
      ),
    },
    { id: "flow", header: t("lng_panel.send_out_short"), headerTitle: t("flows_panel.flow_7d"), unit: "GWh/d", type: "number", sortable: true, priority: "primary", value: (row) => row.flow_7d_gwh_d, format: (v) => num(v as number | null) },
    { id: "last-year", header: t("storage_panel.vs_last_year_short"), unit: "GWh/d", type: "number", sortable: true, priority: "secondary", value: (row) => row.vs_last_year.diff_gwh_d, format: (v) => signed(v as number | null) },
    { id: "average", header: t("storage_panel.vs_avg_column"), unit: "GWh/d", type: "number", sortable: true, value: (row) => row.vs_average.diff_gwh_d, format: (v) => signed(v as number | null), cellTitle: (row) => row.history.label },
    {
      id: "trend", header: t("storage_panel.trend"), width: "120px",
      render: (row) => <Sparkline {...sparkOf(row)} label={t("flows_panel.spark_label", { name: row.name })} unit="GWh/d" decimals={0} simulated={row.simulated} height={20} t={t} />,
    },
  ], [t]);

  if (!data) return error ? <EmptyState compact reason={t("flows_panel.failed")} next={error} /> : <Skeleton label={t("flows_panel.loading")} rows={4} />;
  if (all.length === 0) {
    return <EmptyState compact reason={data.warnings[0] ?? t("flows_panel.empty")} next={t("flows_panel.empty_next")} />;
  }
  return (
    <section className="storage-panel" aria-labelledby="flows-panel-title" data-flows-panel={data.simulated ? "simulated" : "provider"} data-flows-selected={shown?.code}>
      <header className="storage-panel-head">
        <h3 id="flows-panel-title">{t("flows_panel.title")}</h3>
      </header>
      <div className="flows-totals">
        {data.totals.map((entity) => <TotalFigures key={entity.code} entity={entity} t={t} language={language} />)}
      </div>
      {shown && chart && (
        <Chart
          id="flows-season"
          title={t("flows_panel.chart_title", { name: t(`flows_panel.scope.${shown.code}`, { defaultValue: shown.name }) })}
          data={chart.data}
          subtitle={chart.subtitle}
          compare={chart.compare}
          t={t}
          height={260}
          simulated={shown.simulated}
          asOf={shown.as_of}
          controls={data.totals.length > 1 ? (
            <span className="flows-scope-links">
              {data.totals.map((entity) => (
                <button key={entity.code} type="button" className="ds-inline-link" aria-pressed={shown.code === entity.code} onClick={() => setSelected(entity.code)}>
                  {t(`flows_panel.scope_short.${entity.code}`)}
                </button>
              ))}
            </span>
          ) : undefined}
          note={[t("flows_panel.note"), attribution && !shown.simulated ? attribution : null].filter(Boolean).join(" · ")}
        />
      )}
      <DataGrid
        id="flows-landings"
        label={t("flows_panel.landings")}
        columns={columns}
        rows={data.landings}
        rowKey={(row) => row.code}
        density="compact"
        selectedKey={selected}
        onRowAction={(row) => setSelected(selected === row.code ? "norway" : row.code)}
        rowAttributes={(row) => ({ "data-flow-landing": row.code })}
        caption={t("flows_panel.table_caption")}
      />
      <CountryMultiples
        id="flows-multiples"
        title={t("flows_panel.all_landings")}
        entities={data.landings}
        unit="GWh/d"
        headline={(entity) => `${num(entity.flow_7d_gwh_d)} GWh/d`}
        spark={sparkOf}
        onSelect={(code) => setSelected(code)}
        selected={selected}
        t={t}
      />
      <SupplyShares t={t} />
    </section>
  );
}
