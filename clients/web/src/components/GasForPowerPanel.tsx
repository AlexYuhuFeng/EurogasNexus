import { useEffect, useState } from "react";

import { api, type GasForPowerDayDTO } from "@/api/client";
import { ReportExport } from "./ReportExport";
import { pnlClass } from "@/app/model/pnlColor";

type Translate = (key: string, options?: Record<string, unknown>) => string;

const ZONES = ["DE_LU", "NL", "BE", "FR", "GB"];

function num(value: number | null | undefined, digits = 2): string {
  return value == null || !Number.isFinite(value) ? "–" : value.toFixed(digits);
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

  return (
    <section className="workspace-panel span-3 gas-for-power-panel" aria-labelledby="gas-for-power-title">
      <div className="panel-title-row">
        <h2 id="gas-for-power-title">{t("gfp.title")}</h2>
        <ReportExport t={t} path="/market/gas-for-power" params={{ zone, days: "14" }} />
        <label className="position-horizon">
          <span>{t("gfp.zone")}</span>
          <select value={zone} onChange={(event) => setZone(event.target.value)}>
            {ZONES.map((code) => <option key={code} value={code}>{code}</option>)}
          </select>
        </label>
      </div>
      {error && <p role="alert">{error}</p>}
      {rows && rows.length > 0 && (
        <table className="position-ladder" data-gas-for-power="true">
          <thead>
            <tr>
              <th scope="col">{t("gfp.day")}</th>
              <th scope="col" className="num">{t("gfp.power", { currency })}</th>
              <th scope="col" className="num">{t("gfp.residual")}</th>
              <th scope="col" className="num">{t("gfp.burn")}</th>
              <th scope="col" className="num">{t("gfp.gas", { hub: rows[0].gas_hub ?? "" })}</th>
              <th scope="col" className="num">{t("gfp.carbon", { market: rows[0].carbon_market ?? "" })}</th>
              <th scope="col" className="num">{t("gfp.css")}</th>
              <th scope="col" className="num">{t("gfp.cds")}</th>
              <th scope="col" className="num">{t("gfp.switch")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.day} data-record="gas-for-power-day">
                <td>{row.day}</td>
                <td className="num">{num(row.power_price)}</td>
                <td className="num">{num(row.residual_load_mw, 0)}</td>
                <td className="num">{num(row.implied_gas_burn_gwh, 1)}</td>
                <td className="num">{num(row.gas_price, 3)}</td>
                <td className="num">{num(row.carbon_price)}</td>
                <td className={`num ${pnlClass(row.clean_spark_spread)}`}>{num(row.clean_spark_spread)}</td>
                <td className={`num ${pnlClass(row.clean_dark_spread)}`}>{num(row.clean_dark_spread)}</td>
                <td className="num">{num(row.fuel_switch_gas_price, 3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {rows && (
        <ul className="position-notes">
          {(rows.length === 0 && notes.length === 0 ? [t("gfp.empty")] : notes).map((note) => <li key={note}>{note}</li>)}
        </ul>
      )}
    </section>
  );
}
