import { useCallback, useEffect, useState } from "react";

import { api, type SupportReportDTO } from "@/api/client";
import { DataGrid } from "@/components/ui";

type Translate = (key: string, options?: Record<string, unknown>) => string;

/**
 * The IT desk's inbox: every problem report with the user's words, the client diagnostics
 * (page, versions, screen, failing reads and their correlation codes to grep the server
 * log for) and the server's view at that moment (failing and stale sources).
 */
export function SupportInboxPanel({ t }: { t: Translate }) {
  const [rows, setRows] = useState<SupportReportDTO[] | null>(null);
  const [scope, setScope] = useState<"all" | "mine">("mine");
  const [filter, setFilter] = useState<string>("open");
  const [open, setOpen] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const load = useCallback(() => {
    api.supportReports(filter || undefined)
      .then((response) => {
        setRows(response.data.rows);
        setScope(response.data.scope);
      })
      .catch(() => setRows(null));
  }, [filter]);
  useEffect(load, [load]);
  if (scope !== "all") return null;

  const update = (row: SupportReportDTO, status: string) => {
    api.updateSupportReport(row.report_id, { status, resolution: note || null })
      .then(() => {
        setNote("");
        setOpen(null);
        load();
      })
      .catch((caught: unknown) => setMessage(caught instanceof Error ? caught.message : String(caught)));
  };

  return (
    <section className="workspace-panel span-3 support-inbox" aria-labelledby="support-inbox-title">
      <div className="panel-title-row">
        <h2 id="support-inbox-title">{t("support.inbox")}</h2>
        <select value={filter} onChange={(event) => setFilter(event.target.value)} aria-label={t("support.status")}>
          {["open", "acknowledged", "resolved", ""].map((value) => (
            <option key={value || "all"} value={value}>{t(`support.filter_${value || "all"}`)}</option>
          ))}
        </select>
      </div>
      {rows && rows.length === 0 && <p className="muted">{t("support.inbox_empty")}</p>}
      {rows && rows.length > 0 && (
        <>
        <DataGrid
          id="support-inbox"
          label={t("support.report")}
          rows={rows}
          rowKey={(row) => row.report_id}
          density="compact"
          selectedKey={open}
          onRowAction={(row) => setOpen(open === row.report_id ? null : row.report_id)}
          rowAttributes={(row) => ({ "data-status": row.severity === "P1" || row.severity === "P2" ? "breach" : undefined })}
          columns={[
            { id: "report", header: t("support.report"), rowHeader: true, value: (row) => row.report_id, render: (row) => <>{row.report_id} <small>{row.severity} · {t(`support.category_${row.category}`)}</small></> },
            { id: "summary", header: t("support.summary"), value: (row) => row.summary },
            {
              id: "from",
              header: t("support.from"),
              type: "date",
              value: (row) => row.created_at_utc,
              render: (row) => <small>{row.reporter_name ?? row.reporter} · {row.reporter_role} · {row.created_at_utc.slice(0, 16).replace("T", " ")} UTC{row.assignee ? ` · ${row.assignee_name ?? row.assignee}` : ""}</small>,
            },
            { id: "status", header: t("support.status"), value: (row) => row.status, render: (row) => <span className="limit-badge" data-status={row.status === "resolved" ? "ok" : row.status === "acknowledged" ? "watch" : "breach"}>{t(`support.status_${row.status}`)}</span> },
          ]}
        />
        {rows.filter((row) => row.report_id === open).map((row) => (
          <div className="support-detail" key={row.report_id} data-support-detail={row.report_id}>
            <h3>{row.report_id} · {row.summary}</h3>
            {row.description && <p>{row.description}</p>}
            <details open>
              <summary>{t("support.client_context")}</summary>
              <pre>{JSON.stringify(row.client_context, null, 2)}</pre>
            </details>
            <details>
              <summary>{t("support.server_context")}</summary>
              <pre>{JSON.stringify(row.server_context, null, 2)}</pre>
            </details>
            <label className="support-note">
              <span>{t("support.resolution")}</span>
              <input value={note} onChange={(event) => setNote(event.target.value)} />
            </label>
            <div className="limit-actions">
              <button type="button" className="secondary-button" onClick={() => update(row, "acknowledged")}>{t("support.acknowledge")}</button>
              <button type="button" disabled={!note.trim()} onClick={() => update(row, "resolved")}>{t("support.resolve")}</button>
            </div>
          </div>
        ))}
        </>
      )}
      {message && <p role="status">{message}</p>}
    </section>
  );
}
