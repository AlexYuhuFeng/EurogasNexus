import { useEffect, useMemo, useState } from "react";

import { api, type NweBalanceDTO, type NweBalanceDayDTO } from "@/api/client";
import { DataGrid, type DataGridColumn } from "@/components/ui";
import { Chart, limitStack, stackForm, type ChartData } from "@/components/ui/charts";
import { ReportExport } from "./ReportExport";
import { formatMeasure } from "@/app/time/valueFormat";

type Translate = (key: string, options?: Record<string, unknown>) => string;

function gwh(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value) ? "–" : Math.round(value).toLocaleString("en-GB");
}

type BalanceRow = NweBalanceDayDTO & { forecast: boolean };

/**
 * The north-west Europe balance a fundamentals desk tracks: what the region calls on from
 * Norway, LNG and storage, the last week measured and the next two weeks forecast.
 */
export function NweBalancePanel({ t, simulated = false }: {
  t: Translate;
  /**
   * The figures are simulated (the demo desk): every row carries the marker once, at its gas
   * day, not only a banner, so no simulated balance reads as measured data (AGENTS.md rule 17).
   */
  simulated?: boolean;
}) {
  const [balance, setBalance] = useState<NweBalanceDTO | null>(null);
  const [notes, setNotes] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    api
      .nweBalance(14)
      .then((response) => {
        if (!live) return;
        setBalance(response.data);
        setNotes(response.meta?.warnings ?? []);
      })
      .catch((caught: unknown) => live && setError(caught instanceof Error ? caught.message : String(caught)));
    return () => {
      live = false;
    };
  }, []);
  const methods = balance?.forecast[0]?.methods;
  const hasRows = Boolean(balance && (balance.history.length > 0 || balance.forecast.length > 0));
  const empty = balance !== null && !hasRows;
  const rows = useMemo<BalanceRow[]>(
    () => [
      ...(balance?.history.slice(-7).map((row) => ({ ...row, forecast: false })) ?? []),
      ...(balance?.forecast.map((row) => ({ ...row, forecast: true })) ?? []),
    ],
    [balance],
  );
  // The chart: two weeks measured, then the forecast (dashed), supply stacked by source and the
  // call on that supply as a line, all in GWh/d on one axis. The stack is an area beyond 14 gas
  // days and bars up to 14, its members ordered by size, largest at the bottom (F.1).
  const chart = useMemo<ChartData | null>(() => {
    if (!balance) return null;
    const history = balance.history.slice(-14);
    const days = [...history, ...balance.forecast];
    const from = balance.forecast.length > 0 ? history.length : undefined;
    const series = (id: string, label: string, pick: (row: NweBalanceDayDTO) => number | null | undefined, extra: Partial<ChartData["series"][number]>) => ({
      id,
      label,
      values: days.map((row) => {
        const value = pick(row);
        return value == null || !Number.isFinite(value) ? null : value;
      }),
      forecastFrom: from,
      simulated,
      decimals: 0,
      ...extra,
    });
    return {
      axis: "gas-day",
      x: days.map((row) => row.day),
      xTitle: t("chart.gas_day"),
      unit: balance.unit ?? "GWh/d",
      series: [
        ...limitStack([
          series("norway", t("nwe.norway"), (row) => row.norway_gwh, { style: stackForm(days.length), stack: true, colour: 1 }),
          series("lng", t("nwe.lng"), (row) => row.lng_gwh, { style: stackForm(days.length), stack: true, colour: 2 }),
          series("storage", t("nwe.storage"), (row) => row.storage_net_withdrawal_gwh, { style: stackForm(days.length), stack: true, colour: 3 }),
        ], t("chart.other")),
        series("call", t("nwe.call"), (row) => row.call_gwh, { style: "line", colour: 4 }),
      ],
    };
  }, [balance, simulated, t]);
  const asOf = balance?.history.at(-1)?.day ?? null;
  const columns = useMemo<DataGridColumn<BalanceRow>[]>(() => {
    const unit = balance?.unit ?? "GWh/d";
    const mark = simulated
      ? () => ({ kind: "simulated" as const, label: t("today.simulated_short"), description: t("today.simulated_long") })
      : undefined;
    return [
      {
        id: "day",
        header: t("nwe.day"),
        rowHeader: true,
        value: (row) => row.day,
        // A simulated row is marked once, at its gas day: every figure on it is simulated.
        state: mark,
        render: (row) => (
          <>
            {row.forecast ? <strong>{row.day}</strong> : row.day}
            {row.forecast && <small className="muted"> {t("nwe.forecast_short")}</small>}
          </>
        ),
      },
      { id: "call", header: t("nwe.call"), unit, type: "number", value: (row) => row.call_gwh, format: (value) => gwh(value as number) },
      {
        id: "norway",
        header: t("nwe.norway"),
        unit,
        type: "number",
        value: (row) => row.norway_gwh,
        render: (row) => <>{gwh(row.norway_gwh)}{row.norway_outage_gwh ? " *" : ""}</>,
        cellTitle: (row) => (row.norway_outage_gwh ? t("nwe.outage", { gwh: gwh(row.norway_outage_gwh) }) : undefined),
      },
      { id: "lng", header: t("nwe.lng"), unit, type: "number", value: (row) => row.lng_gwh, format: (value) => gwh(value as number) },
      { id: "storage", header: t("nwe.storage"), unit, type: "number", value: (row) => row.storage_net_withdrawal_gwh, format: (value) => gwh(value as number) },
      { id: "fill", header: t("nwe.fill"), unit: "%", type: "number", value: (row) => row.fill_pct ?? null, format: (value) => formatMeasure("percent", value as number | null, { bare: true }) },
    ];
  }, [balance, simulated, t]);

  // With no rows the panel is one line: what it is, and the one reason it is empty. Export
  // buttons for an empty table are not offered (#69).
  return (
    <section className={`workspace-panel span-3 nwe-balance-panel${empty ? " is-empty" : ""}`} aria-labelledby="nwe-balance-title">
      <div className="panel-title-row">
        <h2 id="nwe-balance-title" title={t("nwe.meaning")}>{t("nwe.title")}</h2>
        {hasRows && <ReportExport t={t} path="/market/nwe-balance" params={{ days: "14" }} />}
      </div>
      {error && <p role="alert">{error}</p>}
      {empty ? (
        <p className="panel-empty-line">{notes.at(-1) ?? t("nwe.empty")}</p>
      ) : (
        <p className="panel-meaning">{t("nwe.meaning")}</p>
      )}
      {balance && hasRows && chart && (
        <Chart id="nwe-balance-chart" title={t("nwe.chart_title")} data={chart} t={t} height={220} asOf={asOf} simulated={simulated} />
      )}
      {balance && hasRows && (
        <details className="tool-fold">
        <summary>{t("nwe.daily_table")}</summary>
        <DataGrid
          id="nwe-balance"
          label={t("nwe.title")}
          columns={columns}
          rows={rows}
          rowKey={(row) => `${row.forecast ? "f" : "h"}-${row.day}`}
          density="compact"
          rowAttributes={(row) => ({ "data-record": "nwe-balance-day", "data-forecast": String(row.forecast) })}
          rowClassName={(row) => (row.forecast ? "is-forecast" : undefined)}
          tableAttributes={{ "data-nwe-balance": "true" }}
        />
        </details>
      )}
      {hasRows && (
        <ul className="position-notes">
          {methods && <li>{t("nwe.methods", { call: methods.call, norway: methods.norway, lng: methods.lng })}</li>}
          {notes.map((note) => <li key={note}>{note}</li>)}
        </ul>
      )}
    </section>
  );
}
