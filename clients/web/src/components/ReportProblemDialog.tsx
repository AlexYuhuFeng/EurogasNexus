import { useEffect, useState } from "react";

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
import { Button, Dialog, Field, Select, StatusBadge, Tabs } from "@/components/ui";

type Translate = (key: string, options?: Record<string, unknown>) => string;

const CATEGORIES = ["data", "wrong_figure", "access", "performance", "how_to", "other"] as const;
const SEVERITIES = ["P1", "P2", "P3", "P4"] as const;

/**
 * "Report a problem": one place for any user to tell the IT desk what went wrong, with the
 * page, versions, screen and failing reads attached automatically, and to follow up on
 * earlier reports. Opened from the account menu, the answer bar ("report a problem") or by any
 * panel through `requestProblemReport`; it has no button of its own on the top bar.
 */
export function ReportProblemDialog({ t }: { t: Translate }) {
  const runtimeRelease = useApiStore((state) => state.runtimeRelease);
  const dataStatus = useApiStore((state) => state.dataStatus);
  const endpointErrorCodes = useApiStore((state) => state.endpointErrorCodes);
  const [isOpen, setIsOpen] = useState(false);
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
    setIsOpen(true);
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
      <Dialog
        open={isOpen}
        onClose={() => setIsOpen(false)}
        title={t("support.title")}
        closeLabel={t("support.close")}
        size="md"
        className="report-dialog"
        id="report-problem"
      >
        <Tabs
          idPrefix="report-tab"
          label={t("support.title")}
          tabs={[
            { id: "new", label: t("support.tab_new") },
            { id: "mine", label: t("support.tab_mine") },
          ]}
          activeId={tab}
          panelId="report-tab-panel"
          onChange={setTab}
          className="report-tabs"
        />
        <div id="report-tab-panel" role="tabpanel" aria-labelledby={`report-tab-${tab}`} className="report-tab-panel">
        {tab === "new" && !sent && (
          <form className="report-form" onSubmit={(event) => { event.preventDefault(); submit(); }}>
            <Field label={t("support.summary")}>
              <input value={summary} maxLength={200} onChange={(event) => setSummary(event.target.value)} placeholder={t("support.summary_hint")} required minLength={5} />
            </Field>
            <div className="report-form-row">
              <Field label={t("support.category")}>
                <Select size="md" value={category} onChange={setCategory} options={CATEGORIES.map((value) => ({ value, label: t(`support.category_${value}`) }))} />
              </Field>
              <Field label={t("support.severity")}>
                <Select size="md" value={severity} onChange={setSeverity} options={SEVERITIES.map((value) => ({ value, label: t(`support.severity_${value}`) }))} />
              </Field>
            </div>
            <Field label={t("support.description")} hint={t("support.attached")}>
              <textarea rows={5} value={description} maxLength={8000} onChange={(event) => setDescription(event.target.value)} placeholder={t("support.description_hint")} />
            </Field>
            {error && <p role="alert" className="limit-breaches">{error}</p>}
            <div className="report-form-actions">
              <Button variant="primary" size="md" type="submit" disabled={busy || summary.trim().length < 5} loading={busy}>{t("support.send")}</Button>
            </div>
          </form>
        )}
        {tab === "new" && sent && (
          <div className="report-sent" role="status">
            <strong>{t("support.sent_title", { id: sent.report_id })}</strong>
            <p>{t("support.sent_body")}</p>
            <Button onClick={() => setTab("mine")}>{t("support.tab_mine")}</Button>
          </div>
        )}
        {tab === "mine" && (
          mine.length === 0 ? <p className="muted">{t("support.none")}</p> : (
            <table className="ds-grid">
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
                    <td><StatusBadge tone={row.status === "resolved" ? "ok" : row.status === "acknowledged" ? "watch" : "breach"}>{t(`support.status_${row.status}`)}</StatusBadge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )
        )}
        </div>
      </Dialog>
    </>
  );
}
