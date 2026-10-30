import { useEffect, useState } from "react";

import { api, type NweBalanceDTO, type NweBalanceDayDTO } from "@/api/client";

type Translate = (key: string, options?: Record<string, unknown>) => string;

function gwh(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value) ? "–" : Math.round(value).toLocaleString("en-GB");
}

function Row({ row, forecast, t }: { row: NweBalanceDayDTO; forecast: boolean; t: Translate }) {
  return (
    <tr data-record="nwe-balance-day" data-forecast={forecast}>
      <td>{forecast ? <strong>{row.day}</strong> : row.day}</td>
      <td className="num">{gwh(row.call_gwh)}</td>
      <td className="num" title={row.norway_outage_gwh ? t("nwe.outage", { gwh: gwh(row.norway_outage_gwh) }) : undefined}>
        {gwh(row.norway_gwh)}{row.norway_outage_gwh ? " *" : ""}
      </td>
      <td className="num">{gwh(row.lng_gwh)}</td>
      <td className="num">{gwh(row.storage_net_withdrawal_gwh)}</td>
      <td className="num">{row.fill_pct == null ? "–" : `${row.fill_pct.toFixed(1)}%`}</td>
    </tr>
  );
}

/**
 * The north-west Europe balance a fundamentals desk tracks: what the region calls on from
 * Norway, LNG and storage, the last week measured and the next two weeks forecast.
 */
export function NweBalancePanel({ t }: { t: Translate }) {
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

  return (
    <section className="workspace-panel span-3 nwe-balance-panel" aria-labelledby="nwe-balance-title">
      <h2 id="nwe-balance-title">{t("nwe.title")}</h2>
      {error && <p role="alert">{error}</p>}
      {balance && (balance.history.length > 0 || balance.forecast.length > 0) && (
        <table className="position-ladder" data-nwe-balance="true">
          <thead>
            <tr>
              <th scope="col">{t("nwe.day")}</th>
              <th scope="col" className="num">{t("nwe.call")}</th>
              <th scope="col" className="num">{t("nwe.norway")}</th>
              <th scope="col" className="num">{t("nwe.lng")}</th>
              <th scope="col" className="num">{t("nwe.storage")}</th>
              <th scope="col" className="num">{t("nwe.fill")}</th>
            </tr>
          </thead>
          <tbody>
            {balance.history.slice(-7).map((row) => <Row key={row.day} row={row} forecast={false} t={t} />)}
            {balance.forecast.map((row) => <Row key={row.day} row={row} forecast t={t} />)}
          </tbody>
        </table>
      )}
      <ul className="position-notes">
        {methods && <li>{t("nwe.methods", { call: methods.call, norway: methods.norway, lng: methods.lng })}</li>}
        {notes.map((note) => <li key={note}>{note}</li>)}
      </ul>
    </section>
  );
}
