import { useCallback, useEffect, useState } from "react";

import { api, type SupportReportDTO } from "@/api/client";

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
        <table className="position-ladder">
          <thead>
            <tr>
              <th scope="col">{t("support.report")}</th>
              <th scope="col">{t("support.summary")}</th>
              <th scope="col">{t("support.from")}</th>
              <th scope="col">{t("support.status")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.report_id} data-status={row.severity === "P1" || row.severity === "P2" ? "breach" : undefined}>
                <td>
                  <button type="button" className="link-button" onClick={() => setOpen(open === row.report_id ? null : row.report_id)}>
                    {row.report_id}
                  </button>{" "}
                  <small>{row.severity} · {t(`support.category_${row.category}`)}</small>
                </td>
                <td>
                  {row.summary}
                  {open === row.report_id && (
                    <div className="support-detail">
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
                  )}
                </td>
                <td><small>{row.reporter} · {row.reporter_role}<br />{row.created_at_utc.slice(0, 16).replace("T", " ")} UTC · {row.page}</small></td>
                <td><span className="limit-badge" data-status={row.status === "resolved" ? "ok" : row.status === "acknowledged" ? "watch" : "breach"}>{t(`support.status_${row.status}`)}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {message && <p role="status">{message}</p>}
    </section>
  );
}
