import { useEffect, useRef, useState } from "react";

import { api, type SupportReportDTO } from "@/api/client";
import { resolveHostKind } from "@/app/host/hostCapabilities";
import { CLIENT_APPLICATION_VERSION } from "@/app/releaseMetadata";
import {
  REPORT_PROBLEM_EVENT,
  type ReportPrefill,
  safePage,
  supportClientContext,
} from "@/app/model/supportReport";
import { useApiStore } from "@/stores/api";

type Translate = (key: string, options?: Record<string, unknown>) => string;

const CATEGORIES = ["data", "wrong_figure", "access", "performance", "how_to", "other"] as const;
const SEVERITIES = ["P1", "P2", "P3", "P4"] as const;

/**
 * "Report a problem": one place for any user to tell the IT desk what went wrong, with the
 * page, versions, screen and failing reads attached automatically, and to follow up on
 * earlier reports. Opened from the top bar or by any panel through `requestProblemReport`.
 */
export function ReportProblemDialog({ t }: { t: Translate }) {
  const runtimeRelease = useApiStore((state) => state.runtimeRelease);
  const dataStatus = useApiStore((state) => state.dataStatus);
  const endpointErrorCodes = useApiStore((state) => state.endpointErrorCodes);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [tab, setTab] = useState<"new" | "mine">("new");
  const [severity, setSeverity] = useState<string>("P3");
  const [category, setCategory] = useState<string>("data");
  const [summary, setSummary] = useState("");
  const [description, setDescription] = useState("");
  const [sent, setSent] = useState<SupportReportDTO | null>(null);
  const [mine, setMine] = useState<SupportReportDTO[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const open = (prefill: ReportPrefill = {}) => {
    setSent(null);
    setError(null);
    setTab("new");
    if (prefill.summary) setSummary(prefill.summary);
    if (prefill.category) setCategory(prefill.category);
    if (prefill.severity) setSeverity(prefill.severity);
    dialogRef.current?.showModal();
  };

  useEffect(() => {
    const listener = (event: Event) => open((event as CustomEvent<ReportPrefill>).detail ?? {});
    window.addEventListener(REPORT_PROBLEM_EVENT, listener);
    return () => window.removeEventListener(REPORT_PROBLEM_EVENT, listener);
  }, []);

  useEffect(() => {
    if (tab !== "mine") return;
    api.supportReports().then((response) => setMine(response.data.rows)).catch(() => setMine([]));
  }, [tab, sent]);

  const submit = () => {
    setBusy(true);
    setError(null);
    const context = supportClientContext({
      clientVersion: CLIENT_APPLICATION_VERSION,
      serverVersion: runtimeRelease?.application_version ?? null,
      schemaRevision: runtimeRelease?.database_schema_revision ?? null,
      hostKind: resolveHostKind(),
      language: document.documentElement.lang || "en",
      location: { pathname: window.location.pathname, search: window.location.search },
      viewport: { width: window.innerWidth, height: window.innerHeight, devicePixelRatio: window.devicePixelRatio },
      userAgent: navigator.userAgent,
      dataStatus: dataStatus ?? null,
      endpointErrorCodes: { ...(endpointErrorCodes ?? {}) } as Record<string, string>,
    });
    api.reportProblem({
      severity,
      category,
      summary: summary.trim(),
      description: description.trim(),
      page: safePage({ pathname: window.location.pathname, search: window.location.search }),
      client_context: context,
    })
      .then((response) => {
        setSent(response.data);
        setSummary("");
        setDescription("");
      })
      .catch((caught: unknown) => setError(caught instanceof Error ? caught.message : String(caught)))
      .finally(() => setBusy(false));
  };

  return (
    <>
      <button type="button" className="topbar-help" onClick={() => open()} title={t("support.open")} aria-label={t("support.open")}>
        ?
      </button>
      <dialog ref={dialogRef} className="report-dialog" aria-labelledby="report-dialog-title">
        <header className="report-dialog-header">
          <h2 id="report-dialog-title">{t("support.title")}</h2>
          <button type="button" className="link-button" onClick={() => dialogRef.current?.close()}>{t("support.close")}</button>
        </header>
        <nav className="contract-task-tabs" aria-label={t("support.title")}>
          <button type="button" className={tab === "new" ? "active" : ""} onClick={() => setTab("new")}>{t("support.tab_new")}</button>
          <button type="button" className={tab === "mine" ? "active" : ""} onClick={() => setTab("mine")}>{t("support.tab_mine")}</button>
        </nav>
        {tab === "new" && !sent && (
          <form className="report-form" onSubmit={(event) => { event.preventDefault(); submit(); }}>
            <label>
              <span>{t("support.summary")}</span>
              <input value={summary} maxLength={200} onChange={(event) => setSummary(event.target.value)} placeholder={t("support.summary_hint")} required minLength={5} />
            </label>
            <div className="report-form-row">
              <label>
                <span>{t("support.category")}</span>
                <select value={category} onChange={(event) => setCategory(event.target.value)}>
                  {CATEGORIES.map((value) => <option key={value} value={value}>{t(`support.category_${value}`)}</option>)}
                </select>
              </label>
              <label>
                <span>{t("support.severity")}</span>
                <select value={severity} onChange={(event) => setSeverity(event.target.value)}>
                  {SEVERITIES.map((value) => <option key={value} value={value}>{t(`support.severity_${value}`)}</option>)}
                </select>
              </label>
            </div>
            <label>
              <span>{t("support.description")}</span>
              <textarea rows={5} value={description} maxLength={8000} onChange={(event) => setDescription(event.target.value)} placeholder={t("support.description_hint")} />
            </label>
            <p className="muted"><small>{t("support.attached")}</small></p>
            {error && <p role="alert" className="limit-breaches">{error}</p>}
            <div className="report-form-actions">
              <button type="submit" disabled={busy || summary.trim().length < 5}>{t("support.send")}</button>
            </div>
          </form>
        )}
        {tab === "new" && sent && (
          <div className="report-sent" role="status">
            <strong>{t("support.sent_title", { id: sent.report_id })}</strong>
            <p>{t("support.sent_body")}</p>
            <button type="button" className="secondary-button" onClick={() => setTab("mine")}>{t("support.tab_mine")}</button>
          </div>
        )}
        {tab === "mine" && (
          mine.length === 0 ? <p className="muted">{t("support.none")}</p> : (
            <table className="position-ladder">
              <thead>
                <tr>
                  <th scope="col">{t("support.report")}</th>
                  <th scope="col">{t("support.summary")}</th>
                  <th scope="col">{t("support.status")}</th>
                </tr>
              </thead>
              <tbody>
                {mine.map((row) => (
                  <tr key={row.report_id}>
                    <td><strong>{row.report_id}</strong> <small>{row.severity}</small></td>
                    <td>{row.summary}{row.resolution && <div className="muted"><small>{row.resolution}</small></div>}</td>
                    <td><span className="limit-badge" data-status={row.status === "resolved" ? "ok" : row.status === "acknowledged" ? "watch" : "breach"}>{t(`support.status_${row.status}`)}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )
        )}
      </dialog>
    </>
  );
}
