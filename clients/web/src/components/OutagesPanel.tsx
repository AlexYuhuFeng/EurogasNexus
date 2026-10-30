import { useEffect, useState } from "react";

import { api, type OutageEventDTO } from "@/api/client";

type Translate = (key: string, options?: Record<string, unknown>) => string;

function gasTime(value: string | null): string {
  if (!value) return "–";
  const moment = new Date(value);
  return Number.isNaN(moment.getTime())
    ? value
    : moment.toISOString().slice(0, 16).replace("T", " ");
}

function capacity(row: OutageEventDTO): string {
  if (row.unavailable_capacity == null) return "–";
  return `${row.unavailable_capacity.toLocaleString("en-GB", { maximumFractionDigits: 1 })} ${row.unit}`;
}

/**
 * Live and upcoming facility outages from REMIT urgent market messages: what is off, where,
 * how much and until when, as a desk reads the UMM feed.
 */
export function OutagesPanel({ t }: { t: Translate }) {
  const [rows, setRows] = useState<OutageEventDTO[] | null>(null);
  const [notes, setNotes] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    api
      .outages(90)
      .then((response) => {
        if (!live) return;
        setRows(response.data);
        setNotes(response.meta?.warnings ?? []);
      })
      .catch((caught: unknown) => live && setError(caught instanceof Error ? caught.message : String(caught)));
    return () => {
      live = false;
    };
  }, []);

  return (
    <section className="workspace-panel span-3 outages-panel" aria-labelledby="outages-title">
      <h2 id="outages-title">{t("outages.title")}</h2>
      {error && <p role="alert">{error}</p>}
      {rows && rows.length === 0 && <p className="muted">{notes[0] ?? t("outages.empty")}</p>}
      {rows && rows.length > 0 && (
        <table className="position-ladder" data-outages="true">
          <thead>
            <tr>
              <th scope="col">{t("outages.status")}</th>
              <th scope="col">{t("outages.asset")}</th>
              <th scope="col">{t("outages.zone")}</th>
              <th scope="col">{t("outages.type")}</th>
              <th scope="col" className="num">{t("outages.unavailable")}</th>
              <th scope="col">{t("outages.start")}</th>
              <th scope="col">{t("outages.end")}</th>
              <th scope="col">{t("outages.reason")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.event_id} data-record="outage-row" data-outage-status={row.status}>
                <td>{t(`outages.status_${row.status}`)}</td>
                <td title={`${row.market_participant} · ${row.event_id} v${row.version ?? 1}`}>
                  {row.facility_name || row.facility_id}
                </td>
                <td>{row.balancing_zone}</td>
                <td>{t(`outages.type_${row.event_type}`)}</td>
                <td className="num">{capacity(row)}</td>
                <td>{gasTime(row.start_utc)}</td>
                <td>{gasTime(row.end_utc)}</td>
                <td>{row.description}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
