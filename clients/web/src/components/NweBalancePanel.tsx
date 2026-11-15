import { useEffect, useMemo, useState } from "react";

import { api, type NweBalanceDTO, type NweBalanceDayDTO } from "@/api/client";
import { DataGrid, type DataGridColumn } from "@/components/ui";
import { ReportExport } from "./ReportExport";

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
   * The figures are simulated (the demo desk): every row carries the marker beside its values,
   * not only a banner, so no simulated balance reads as measured data (AGENTS.md rule 17).
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
        render: (row) => (
          <>
            {row.forecast ? <strong>{row.day}</strong> : row.day}
            {row.forecast && <small className="muted"> {t("nwe.forecast_short")}</small>}
          </>
        ),
      },
      { id: "call", header: t("nwe.call"), unit, type: "number", value: (row) => row.call_gwh, format: (value) => gwh(value as number), state: mark },
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
      { id: "fill", header: t("nwe.fill"), unit: "%", type: "number", value: (row) => row.fill_pct ?? null, format: (value) => (value == null ? "–" : (value as number).toFixed(1)) },
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
      {balance && hasRows && (
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
