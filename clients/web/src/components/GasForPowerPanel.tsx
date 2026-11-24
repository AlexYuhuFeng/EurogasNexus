import { useEffect, useMemo, useState } from "react";

import { api, type GasForPowerDayDTO } from "@/api/client";
import { ReportExport } from "./ReportExport";
import { DataGrid, Field, Select, type DataGridColumn } from "@/components/ui";
import { pnlClass } from "@/app/model/pnlColor";
import { formatMeasure, type Measure } from "@/app/time/valueFormat";

type Translate = (key: string, options?: Record<string, unknown>) => string;

const ZONES = ["DE_LU", "NL", "BE", "FR", "GB"];

/** Each column's figure in its measure; the unit is named once in the header. */
function num(value: number | null | undefined, measure: Measure, decimals?: number): string {
  return formatMeasure(measure, value, { bare: true, decimals });
}

/**
 * Gas burned for power and the clean spark against the clean dark spread, per delivery day:
 * where power demand, renewables, carbon and coal leave gas in the merit order.
 */
export function GasForPowerPanel({ t }: { t: Translate }) {
  const [zone, setZone] = useState("DE_LU");
  const [rows, setRows] = useState<GasForPowerDayDTO[] | null>(null);
  const [notes, setNotes] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    api
      .gasForPower(zone, 14)
      .then((response) => {
        if (!live) return;
        setRows(response.data);
        setNotes(response.meta?.warnings ?? []);
      })
      .catch((caught: unknown) => live && setError(caught instanceof Error ? caught.message : String(caught)));
    return () => {
      live = false;
    };
  }, [zone]);
  const currency = rows?.[0]?.currency ?? "";
  const hasRows = Boolean(rows && rows.length > 0);
  const empty = rows !== null && !hasRows;

  // One table (UX-06); each figure column names its unit in the header.
  const columns = useMemo<DataGridColumn<GasForPowerDayDTO>[]>(() => {
    const first = rows?.[0];
    const figure = (id: string, header: string, pick: (row: GasForPowerDayDTO) => number | null | undefined, measure: Measure = "unit_value", signed = false, decimals?: number): DataGridColumn<GasForPowerDayDTO> => ({
      id,
      header,
      type: "number",
      value: (row) => pick(row) ?? null,
      format: (value) => num(value as number | null, measure, decimals),
      cellClassName: signed ? (row) => pnlClass(pick(row)) || undefined : undefined,
    });
    return [
      { id: "day", header: t("gfp.day"), rowHeader: true, value: (row) => row.day },
      figure("power", t("gfp.power", { currency }), (row) => row.power_price),
      figure("residual", t("gfp.residual"), (row) => row.residual_load_mw, "volume"),
      figure("burn", t("gfp.burn"), (row) => row.implied_gas_burn_gwh, "volume", false, 1),
      figure("gas", t("gfp.gas", { hub: first?.gas_hub ?? "" }), (row) => row.gas_price, "price"),
      figure("carbon", t("gfp.carbon", { market: first?.carbon_market ?? "" }), (row) => row.carbon_price),
      figure("css", t("gfp.css"), (row) => row.clean_spark_spread, "unit_value", true),
      figure("cds", t("gfp.cds"), (row) => row.clean_dark_spread, "unit_value", true),
      figure("switch", t("gfp.switch"), (row) => row.fuel_switch_gas_price, "price"),
    ];
  }, [rows, currency, t]);

  // The zone picker stays when the panel is empty, because another zone may have data; the
  // export buttons do not (#69).
  return (
    <section className={`workspace-panel span-3 gas-for-power-panel${empty ? " is-empty" : ""}`} aria-labelledby="gas-for-power-title">
      <div className="panel-title-row">
        <h2 id="gas-for-power-title" title={t("gfp.meaning")}>{t("gfp.title")}</h2>
        {hasRows && <ReportExport t={t} path="/market/gas-for-power" params={{ zone, days: "14" }} />}
        <Field inline label={t("gfp.zone")}>
          <Select value={zone} onChange={setZone} options={ZONES.map((code) => ({ value: code, label: code }))} />
        </Field>
      </div>
      {error && <p role="alert">{error}</p>}
      {empty ? (
        <p className="panel-empty-line">{notes[0] ?? t("gfp.empty")}</p>
      ) : (
        <p className="panel-meaning">{t("gfp.meaning")}</p>
      )}
      {rows && hasRows && (
        <DataGrid
          id="gas-for-power"
          label={t("gfp.title")}
          columns={columns}
          rows={rows}
          rowKey={(row) => row.day}
          density="compact"
          rowAttributes={() => ({ "data-record": "gas-for-power-day" })}
          tableAttributes={{ "data-gas-for-power": "true" }}
        />
      )}
      {hasRows && notes.length > 0 && (
        <ul className="position-notes">
          {notes.map((note) => <li key={note}>{note}</li>)}
        </ul>
      )}
    </section>
  );
}
