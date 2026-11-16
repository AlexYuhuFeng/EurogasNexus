/**
 * Research → Reports: generate a market report, ask a question that becomes an editable plan,
 * reopen stored reports and read one in a sandboxed frame (Print / Save as PDF, Download HTML).
 *
 * The server assembles every report from the catalogue's sections as the caller (its licences and
 * books) and stores it; the model may only reword a section's rule text under the checks. This
 * page sends a plan and shows what came back; it decides nothing about what a report may contain.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import "@/styles/reports.css";
import {
  api,
  fetchReportHtml,
  type ReportAudience,
  type ReportCatalogueDTO,
  type ReportKind,
  type ReportMetadataDTO,
  type ReportPlanProposalDTO,
  type ReportRequestDTO,
  type ReportSummaryDTO,
} from "@/api/client";
import { Button, DataGrid, EmptyState, Field, Panel, Segmented, Select, StatusBadge, type DataGridColumn } from "@/components/ui";
import { annexByDefault, reportCsv, reportSubjectFromSearch, reportRequestFromForm, summaryOnlyHtml, type ReportForm } from "@/app/model/reportsModel";

type Translate = (key: string, options?: Record<string, unknown>) => string;
type Mode = "standard" | "ask";

const KINDS: ReportKind[] = ["daily", "weekly", "monthly", "situation"];

function initialForm(): ReportForm {
  const subject = typeof window === "undefined" ? null : reportSubjectFromSearch(window.location.search);
  return {
    kind: subject ? "situation" : "daily",
    variant: "morning",
    audience: "internal",
    sections: null,
    hubs: "",
    periodStart: "",
    periodEnd: "",
    subject,
    question: "",
    annex: null,
  };
}

export function ReportsWorkspace({ t, language }: { t: Translate; language: string }) {
  const zh = language.toLowerCase().startsWith("zh");
  const [mode, setMode] = useState<Mode>("standard");
  const [catalogue, setCatalogue] = useState<ReportCatalogueDTO | null>(null);
  const [form, setForm] = useState<ReportForm>(initialForm);
  const [proposal, setProposal] = useState<ReportPlanProposalDTO | null>(null);
  const [busy, setBusy] = useState<"plan" | "generate" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reports, setReports] = useState<ReportSummaryDTO[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  const loadReports = useCallback(() => {
    api.marketReports().then((r) => setReports(r.data)).catch(() => setReports([]));
  }, []);

  useEffect(() => {
    api.reportCatalogue().then((r) => setCatalogue(r.data)).catch(() => setCatalogue(null));
    loadReports();
    const sync = () => {
      const subject = reportSubjectFromSearch(window.location.search);
      if (subject) {
        setMode("standard");
        setForm((current) => ({ ...current, kind: "situation", subject }));
      }
    };
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, [loadReports]);

  const sectionTypes = useMemo(() => catalogue?.sections ?? [], [catalogue]);
  const defaults = catalogue?.default_sections[form.kind] ?? [];
  const chosen = form.sections ?? defaults;
  const offered = sectionTypes.filter(
    (section) => section.key !== "situation_event" && (form.audience === "internal" || !section.internal_only),
  );

  function update(patch: Partial<ReportForm>) {
    setForm((current) => ({ ...current, ...patch }));
  }

  function toggleSection(key: string) {
    const current = chosen.filter((item) => offered.some((section) => section.key === item));
    update({ sections: current.includes(key) ? current.filter((item) => item !== key) : [...current, key] });
  }

  async function propose() {
    setBusy("plan");
    setError(null);
    try {
      const response = await api.reportPlan(form.question, form.audience);
      setProposal(response.data);
      const plan = response.data.plan;
      if (plan) {
        update({
          sections: plan.sections,
          hubs: plan.hubs.join(", "),
          periodStart: plan.period_start ?? "",
          periodEnd: plan.period_end ?? "",
        });
      }
    } catch {
      setError(t("reports.plan_failed"));
    } finally {
      setBusy(null);
    }
  }

  async function generate() {
    setBusy("generate");
    setError(null);
    const body: ReportRequestDTO = reportRequestFromForm(form, mode, chosen, zh ? "zh-CN" : "en");
    try {
      const response = await api.generateReport(body);
      setSelected(response.data.report_id);
      loadReports();
    } catch (failure) {
      const message = failure instanceof Error ? failure.message : "";
      setError(message.includes("licensed") ? t("reports.licensed_refused") : t("reports.generate_failed"));
    } finally {
      setBusy(null);
    }
  }

  const kindOptions = KINDS.filter((kind) => kind !== "situation" || form.subject).map((kind) => ({
    value: kind,
    label: t(`reports.kind.${kind}`),
  }));
  const canGenerate =
    busy === null && chosen.length > 0 && (mode === "standard" || (proposal?.answerable ?? false));

  const columns: DataGridColumn<ReportSummaryDTO>[] = [
    { id: "created", header: t("reports.col.created"), type: "date", value: (row) => row.created_at ?? "", format: (value) => String(value).slice(0, 16).replace("T", " "), width: "128px" },
    { id: "kind", header: t("reports.col.kind"), value: (row) => t(`reports.kind.${row.kind}`) },
    { id: "title", header: t("reports.col.title"), rowHeader: true, value: (row) => row.title, render: (row) => <span title={row.headline}>{row.title}</span> },
    {
      id: "audience",
      header: t("reports.col.audience"),
      value: (row) => row.audience,
      render: (row) => (
        <>
          {t(`reports.audience.${row.audience}`)}
          {row.simulated && <StatusBadge tone="simulated">{t("reports.simulated")}</StatusBadge>}
          {row.licensed_families.length > 0 && <StatusBadge tone="watch">{t("reports.licensed")}</StatusBadge>}
        </>
      ),
    },
  ];

  return (
    <div className="reports-page" id="research-task-panel" data-reports-workspace="">
      <h2 className="visually-hidden">{t("nav.mode.research.reports")}</h2>
      <div className="reports-layout">
        <div className="reports-side">
          <Panel
            title={t("reports.new")}
            level={3}
            actions={
              <Segmented
                label={t("reports.mode")}
                value={mode}
                onChange={(value) => { setMode(value); setProposal(null); update({ sections: null }); }}
                options={[
                  { value: "standard", label: t("reports.mode.standard") },
                  { value: "ask", label: t("reports.mode.ask") },
                ]}
              />
            }
          >
            <form className="reports-form" onSubmit={(event) => { event.preventDefault(); void generate(); }} data-report-form={mode}>
              {mode === "ask" && (
                <div className="reports-ask">
                  <Field label={t("reports.question")} hint={t("reports.question_hint")}>
                    <textarea rows={3} maxLength={500} value={form.question} onChange={(event) => update({ question: event.target.value })} />
                  </Field>
                  <Button size="sm" onClick={() => void propose()} loading={busy === "plan"} disabled={form.question.trim().length < 3}>
                    {t("reports.propose_plan")}
                  </Button>
                  {proposal && (
                    <div className="reports-proposal" role="status" data-plan-basis={proposal.basis}>
                      {proposal.answerable ? (
                        <p>{t(proposal.basis === "model" ? "reports.plan_model" : "reports.plan_rules")}</p>
                      ) : (
                        <p className="reports-warn">{t("reports.cannot_answer")}</p>
                      )}
                      {proposal.missing.length > 0 && (
                        <ul>{proposal.missing.map((item) => <li key={item}>{item}</li>)}</ul>
                      )}
                    </div>
                  )}
                </div>
              )}
              {mode === "standard" && (
                <div className="reports-row">
                  <Field label={t("reports.kind")}>
                    <Select value={form.kind} options={kindOptions} onChange={(kind) => update({ kind, sections: null })} />
                  </Field>
                  {form.kind === "daily" && (
                    <Field label={t("reports.variant")}>
                      <Select
                        value={form.variant}
                        options={[{ value: "morning", label: t("reports.variant.morning") }, { value: "eod", label: t("reports.variant.eod") }]}
                        onChange={(variant) => update({ variant })}
                      />
                    </Field>
                  )}
                </div>
              )}
              {form.kind === "situation" && form.subject && mode === "standard" && (
                <p className="reports-subject">{t(`reports.subject.${form.subject.kind}`, { id: form.subject.id })}</p>
              )}
              <div className="reports-row">
                <Field label={t("reports.audience")} hint={t(`reports.audience.${form.audience}.hint`)}>
                  <Select<ReportAudience>
                    value={form.audience}
                    options={[{ value: "internal", label: t("reports.audience.internal") }, { value: "shareable", label: t("reports.audience.shareable") }]}
                    onChange={(audience) => update({ audience, sections: form.sections?.filter((key) => audience === "internal" || !sectionTypes.find((s) => s.key === key)?.internal_only) ?? null })}
                  />
                </Field>
              </div>
              <div className="reports-row">
                <Field label={t("reports.period_start")}>
                  <input type="date" value={form.periodStart} onChange={(event) => update({ periodStart: event.target.value })} />
                </Field>
                <Field label={t("reports.period_end")}>
                  <input type="date" value={form.periodEnd} onChange={(event) => update({ periodEnd: event.target.value })} />
                </Field>
                <Field label={t("reports.hubs")} hint={t("reports.hubs_hint")}>
                  <input value={form.hubs} maxLength={80} onChange={(event) => update({ hubs: event.target.value })} />
                </Field>
              </div>
              <fieldset className="reports-sections">
                <legend>{t("reports.sections")}</legend>
                {offered.map((section) => (
                  <label key={section.key} title={section.data_source}>
                    <input type="checkbox" checked={chosen.includes(section.key)} onChange={() => toggleSection(section.key)} />
                    <span>{t(`reports.section.${section.key}`)}</span>
                  </label>
                ))}
              </fieldset>
              <label className="reports-annex">
                <input
                  type="checkbox"
                  checked={form.annex ?? annexByDefault(mode === "ask" ? "ask" : form.kind)}
                  onChange={(event) => update({ annex: event.target.checked })}
                />
                <span>{t("reports.annex")}</span>
              </label>
              {error && <p className="reports-error" role="alert">{error}</p>}
              <div className="reports-actions">
                <Button type="submit" variant="primary" size="md" loading={busy === "generate"} disabled={!canGenerate}>
                  {t("reports.generate")}
                </Button>
                <span className="reports-note">{t("reports.no_advice")}</span>
              </div>
            </form>
          </Panel>
          <Panel title={t("reports.stored")} level={3} actions={<Button variant="quiet" onClick={loadReports}>{t("reports.refresh")}</Button>}>
            <DataGrid
              label={t("reports.stored")}
              columns={columns}
              rows={reports ?? []}
              rowKey={(row) => row.report_id}
              loading={reports === null}
              loadingLabel={t("status.loading")}
              selectedKey={selected}
              onRowAction={(row) => setSelected(row.report_id)}
              rowAttributes={(row) => ({ "data-record": "market-report", "data-record-id": row.report_id })}
              empty={<EmptyState compact reason={t("reports.none")} />}
              density="compact"
              maxHeight="320px"
            />
          </Panel>
        </div>
        <ReportViewer reportId={selected} t={t} />
      </div>
    </div>
  );
}

function ReportViewer({ reportId, t }: { reportId: string | null; t: Translate }) {
  const [html, setHtml] = useState<string | null>(null);
  const [meta, setMeta] = useState<ReportMetadataDTO | null>(null);
  const [failed, setFailed] = useState(false);
  const printFrame = useRef<HTMLIFrameElement | null>(null);

  useEffect(() => {
    if (!reportId) return undefined;
    let live = true;
    setHtml(null);
    setMeta(null);
    setFailed(false);
    Promise.all([fetchReportHtml(reportId), api.marketReport(reportId)])
      .then(([text, response]) => {
        if (!live) return;
        setHtml(text);
        setMeta(response.data);
      })
      .catch(() => live && setFailed(true));
    return () => {
      live = false;
    };
  }, [reportId]);

  function print(summaryOnly = false) {
    const frame = printFrame.current;
    if (!frame || !html) return;
    // A same-origin frame without scripts: the report prints exactly as it reads, and nothing in it runs.
    frame.srcdoc = summaryOnly ? summaryOnlyHtml(html) : html;
    frame.onload = () => frame.contentWindow?.print();
  }

  function save(content: string, type: string, extension: string) {
    if (!meta) return;
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([content], { type }));
    link.download = `${meta.title.replace(/[^A-Za-z0-9-]+/g, "-")}.${extension}`;
    link.click();
    URL.revokeObjectURL(link.href);
  }

  const csv = html ? reportCsv(html) : "";
  const editorial = meta?.editorial;

  return (
    <Panel
      title={meta?.title ?? t("reports.viewer")}
      level={3}
      className="reports-viewer"
      meta={editorial ? (editorial.basis === "model"
        ? t("reports.edited_model", { model: editorial.model ?? "", directive: editorial.directive ?? "" })
          + (editorial.temperature != null ? t("reports.edited_temperature", { value: editorial.temperature }) : "")
        : t("reports.edited_rule")) : undefined}
      actions={
        reportId && html ? (
          <>
            <Button size="sm" onClick={() => print(false)}>{t("reports.print")}</Button>
            <Button size="sm" variant="quiet" onClick={() => print(true)}>{t("reports.print_summary")}</Button>
            <Button size="sm" variant="quiet" onClick={() => save(html, "text/html", "html")}>{t("reports.download")}</Button>
            {csv && <Button size="sm" variant="quiet" onClick={() => save(csv, "text/csv", "csv")}>{t("reports.download_csv")}</Button>}
          </>
        ) : undefined
      }
    >
      {!reportId && <EmptyState compact reason={t("reports.pick")} />}
      {reportId && failed && <EmptyState compact reason={t("reports.open_failed")} />}
      {reportId && !failed && !html && <p className="reports-note">{t("status.loading")}</p>}
      {html && (
        <iframe
          className="reports-frame"
          title={meta?.title ?? t("reports.viewer")}
          sandbox=""
          srcDoc={html}
          tabIndex={0}
          data-report-frame={reportId ?? ""}
        />
      )}
      <iframe ref={printFrame} className="reports-print-frame" title={t("reports.print")} sandbox="allow-modals allow-same-origin" aria-hidden="true" tabIndex={-1} />
      {meta && meta.findings && meta.findings.length > 0 && (
        <details className="reports-plan" data-report-plan="">
          <summary>{t("reports.plan_view")}</summary>
          <ol>
            {meta.findings.map((finding, index) => (
              <li key={index}>
                {finding.text}
                <span className="reports-note"> · {finding.basis === "model" ? t("reports.by_model") : t("reports.by_rule")}: {finding.why}</span>
              </li>
            ))}
          </ol>
          {meta.omitted.length > 0 && (
            <p className="reports-note">
              {t("reports.left_out")}: {meta.omitted.map((item) => `${item.title} (${item.reason})`).join("; ")}
            </p>
          )}
        </details>
      )}
      {meta && <p className="reports-note">{meta.pdf}</p>}
    </Panel>
  );
}
