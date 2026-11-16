import { useEffect, useMemo, useState } from "react";

import { api, type OutageEventDTO } from "@/api/client";
import { DataGrid, type DataGridColumn } from "@/components/ui";
import { WhyButton } from "./WhyButton";
import { ReportLink } from "./ReportLink";

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
  return row.unavailable_capacity.toLocaleString("en-GB", { maximumFractionDigits: 1 });
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

  // One table (UX-06): the unit differs by message (GWh/d, MW), so it sits in the cell.
  const columns = useMemo<DataGridColumn<OutageEventDTO>[]>(
    () => [
      { id: "status", header: t("outages.status"), sortable: true, value: (row) => t(`outages.status_${row.status}`) },
      {
        id: "asset",
        header: t("outages.asset"),
        rowHeader: true,
        sortable: true,
        value: (row) => row.facility_name || row.facility_id,
        cellTitle: (row) => `${row.market_participant} · ${row.event_id} v${row.version ?? 1}`,
      },
      { id: "zone", header: t("outages.zone"), sortable: true, value: (row) => row.balancing_zone },
      { id: "type", header: t("outages.type"), value: (row) => t(`outages.type_${row.event_type}`) },
      {
        id: "unavailable",
        header: t("outages.unavailable"),
        type: "number",
        value: (row) => row.unavailable_capacity,
        render: (row) => (
          <>
            {capacity(row)} {row.unavailable_capacity == null ? null : <small className="ds-grid-unit">{row.unit}</small>}
          </>
        ),
      },
      { id: "start", header: t("outages.start"), type: "date", sortable: true, value: (row) => row.start_utc ?? "", format: (_, row) => gasTime(row.start_utc) },
      { id: "end", header: t("outages.end"), type: "date", sortable: true, value: (row) => row.end_utc ?? "", format: (_, row) => gasTime(row.end_utc) },
      { id: "reason", header: t("outages.reason"), value: (row) => row.description },
      {
        id: "why",
        header: <span className="visually-hidden">{t("why.button")}</span>,
        render: (row) => (
          <>
            <WhyButton subject="outage" id={row.event_id} label={row.facility_name || row.facility_id} t={t} />{" "}
            <ReportLink subject={{ kind: "outage", id: String(row.event_id) }} label={row.facility_name || row.facility_id} t={t} />
          </>
        ),
      },
    ],
    [t],
  );

  return (
    <section className="workspace-panel span-3 outages-panel" aria-labelledby="outages-title">
      <h2 id="outages-title">{t("outages.title")}</h2>
      {error && <p role="alert">{error}</p>}
      {rows && rows.length === 0 && <p className="muted">{notes[0] ?? t("outages.empty")}</p>}
      {rows && rows.length > 0 && (
        <DataGrid
          id="outages"
          label={t("outages.title")}
          columns={columns}
          rows={rows}
          rowKey={(row) => row.event_id}
          density="compact"
          defaultSort={{ columnId: "start", direction: "ascending" }}
          rowAttributes={(row) => ({ "data-record": "outage-row", "data-outage-status": row.status })}
          tableAttributes={{ "data-outages": "true" }}
        />
      )}
    </section>
  );
}
