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
  ApiError,
  fetchReportHtml,
  type ReportAudience,
  type ReportCatalogueDTO,
  type ReportKind,
  type ReportMetadataDTO,
  type ReportPlanProposalDTO,
  type ReportRequestDTO,
  type ReportSummaryDTO,
} from "@/api/client";
import { WorkProgress } from "@/components/ui/WorkProgress";
import { Button, DataGrid, Dialog, EmptyState, Field, Panel, Segmented, Select, StatusBadge, type DataGridColumn } from "@/components/ui";
import {
  annexByDefault,
  editedByLabel,
  elapsedLabel,
  explainFailure,
  formIssues,
  REPORT_STAGES,
  reportCsv,
  reportPeriodLabel,
  reportQuestionFromSearch,
  reportRequestFromForm,
  reportStageAt,
  reportSubjectFromSearch,
  sendableSections,
  summaryOnlyHtml,
  type FormIssue,
  type ReportForm,
  type ReportStage,
} from "@/app/model/reportsModel";

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
  // Asked reports: the planner decides the scope; the user may open it to adjust.
  const [scopeOpen, setScopeOpen] = useState(false);
  const [stage, setStage] = useState<ReportStage | null>(null);
  const [manageOpen, setManageOpen] = useState(false);
  const [failure, setFailure] = useState<ReturnType<typeof explainFailure> | null>(null);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const abort = useRef<AbortController | null>(null);

  // A question from the answer bar ("Open as report"): Ask mode, its plan proposed once.
  const [handedQuestion, setHandedQuestion] = useState<string | null>(() =>
    typeof window === "undefined" ? null : reportQuestionFromSearch(window.location.search),
  );
  useEffect(() => {
    if (!handedQuestion) return;
    setMode("ask");
    setProposal(null);
    setForm((current) => ({ ...current, question: handedQuestion, sections: null }));
    setBusy("plan");
    setError(null);
    api.reportPlan(handedQuestion, form.audience)
      .then((response) => {
        setProposal(response.data);
        const plan = response.data.plan;
        if (plan) {
          setForm((current) => ({
            ...current,
            sections: plan.sections,
            hubs: plan.hubs.join(", "),
            periodStart: plan.period_start ?? "",
            periodEnd: plan.period_end ?? "",
          }));
        }
      })
      .catch(() => setError(t("reports.plan_failed")))
      .finally(() => setBusy(null));
    // The question is consumed: a reload does not propose it again.
    const url = new URL(window.location.href);
    url.searchParams.delete("ask");
    window.history.replaceState(window.history.state, "", url);
    // Only a new handed-over question proposes a plan.
  }, [handedQuestion]);

  const loadReports = useCallback(() => {
    api.marketReports().then((r) => setReports(r.data)).catch(() => setReports([]));
  }, []);

  useEffect(() => {
    // The reasons the form shows come back in the interface language.
    api.reportCatalogue(zh ? "zh-CN" : "en").then((r) => setCatalogue(r.data)).catch(() => setCatalogue(null));
  }, [zh]);

  useEffect(() => {
    loadReports();
    const sync = () => {
      const question = reportQuestionFromSearch(window.location.search);
      if (question) setHandedQuestion(question);
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
  // What is sent: only sections offered for the audience (the book never reaches a report
  // for distribution, so the server never refuses for it).
  const sendable = sendableSections(chosen, offered);
  const offer = catalogue?.availability ?? null;

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

  async function generate(useModel = true) {
    const controller = new AbortController();
    abort.current = controller;
    setBusy("generate");
    setError(null);
    setFailure(null);
    const language = form.language ?? (zh ? "zh-CN" : "en");
    let request: ReportRequestDTO = { ...reportRequestFromForm(form, mode, sendable, language), use_model: useModel };
    try {
      if (mode === "ask" && !(scopeOpen && proposal?.answerable)) {
        // The question decides the scope: plan it now (the user never has to fill a form).
        setStage("planning");
        const response = await api.reportPlan(form.question, form.audience);
        if (controller.signal.aborted) return;
        setProposal(response.data);
        const plan = response.data.plan;
        if (!plan || !response.data.answerable) {
          setScopeOpen(true);
          return;
        }
        const planned = { ...form, sections: plan.sections, hubs: plan.hubs.join(", "), periodStart: plan.period_start ?? "", periodEnd: plan.period_end ?? "" };
        setForm(planned);
        request = { ...reportRequestFromForm(planned, mode, plan.sections, language), use_model: useModel };
      }
      const started = Date.now();
      setStartedAt(started);
      setStage(reportStageAt(0));
      const timer = window.setInterval(() => {
        setStage(reportStageAt(Date.now() - started));
        setNow(Date.now());
      }, 500);
      try {
        const response = await api.generateReport(request, { signal: controller.signal });
        setSelected(response.data.report_id);
        loadReports();
      } finally {
        window.clearInterval(timer);
      }
    } catch (caught) {
      // Say what failed and what can be done; the form keeps everything that was entered.
      const status = caught instanceof ApiError ? caught.status : null;
      const detail = caught instanceof ApiError && caught.detail && typeof caught.detail === "object"
        ? (caught.detail as { code?: string; error?: string }) : null;
      setFailure(explainFailure(status, detail?.code ?? detail?.error ?? null, controller.signal.aborted));
    } finally {
      if (abort.current === controller) abort.current = null;
      setBusy(null);
      setStage(null);
    }
  }

  function cancel() {
    abort.current?.abort();
  }

  const kindOptions = KINDS.filter((kind) => kind !== "situation" || form.subject).map((kind) => ({
    value: kind,
    label: t(`reports.kind.${kind}`),
  }));
  const issues = formIssues(form, mode, sendable, catalogue, new Date().toISOString().slice(0, 10));
  const canGenerate = busy === null && issues.length === 0;
  const issueText = (field: FormIssue["field"]) => issues.filter((issue) => issue.field === field)
    .map((issue) => <p key={issue.key} className="reports-issue" data-report-issue={issue.key}>{t(issue.key, issue.values)}</p>);

  const columns: DataGridColumn<ReportSummaryDTO>[] = [
    { id: "created", header: t("reports.col.created"), type: "date", value: (row) => row.created_at ?? "", format: (value) => String(value).slice(0, 16).replace("T", " "), width: "128px" },
    { id: "kind", header: t("reports.col.kind"), value: (row) => t(`reports.kind.${row.kind}`) },
    { id: "title", header: t("reports.col.title"), rowHeader: true, value: (row) => row.question || row.title, render: (row) => <span title={row.headline}>{row.question || row.title}</span> },
    { id: "period", header: t("reports.col.period"), value: (row) => row.period_end ?? row.period_start ?? "", format: (_value, row) => reportPeriodLabel(row.period_start, row.period_end) || "–" },
    { id: "by", header: t("reports.col.by"), value: (row) => row.generated_by ?? "" },
    { id: "edited", header: t("reports.col.edited"), value: (row) => editedByLabel(row), format: (value) => (value === "model" ? t("reports.by_model") : t("reports.by_rule")) },
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

  function removed(ids: string[]) {
    if (selected && ids.includes(selected)) setSelected(null);
    loadReports();
  }

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
            <form className="reports-form" onSubmit={(event) => { event.preventDefault(); void generate(true); }} data-report-form={mode}>
              {mode === "ask" && (
                <div className="reports-ask">
                  <Field label={t("reports.question")} hint={t("reports.question_hint")}>
                    <textarea rows={3} maxLength={500} value={form.question} onChange={(event) => update({ question: event.target.value })} />
                  </Field>
                  <p className="reports-note">{t("reports.ask_scope_note")}</p>
                  <Button
                    size="sm"
                    variant="quiet"
                    aria-expanded={scopeOpen}
                    aria-controls="reports-scope"
                    data-report-scope-toggle=""
                    onClick={() => {
                      const next = !scopeOpen;
                      setScopeOpen(next);
                      if (next && !proposal && form.question.trim().length >= 3) void propose();
                    }}
                  >
                    {scopeOpen ? t("reports.scope_hide") : t("reports.scope_adjust")}
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
                <Field label={t("reports.language")}>
                  <Select<"en" | "zh-CN">
                    value={form.language ?? (zh ? "zh-CN" : "en")}
                    options={[{ value: "en", label: "English" }, { value: "zh-CN", label: "中文" }]}
                    onChange={(language) => update({ language })}
                  />
                </Field>
              </div>
              <div className="reports-row">
                <Field label={t("reports.currency")} hint={t("reports.conversion_hint")}>
                  <Select<"" | "EUR" | "GBP" | "USD">
                    value={form.currency ?? ""}
                    options={[{ value: "", label: t("reports.native") }, { value: "EUR", label: "EUR" }, { value: "GBP", label: "GBP" }, { value: "USD", label: "USD" }]}
                    onChange={(currency) => update({ currency })}
                  />
                </Field>
                <Field label={t("reports.energy_unit")}>
                  <Select<"" | "MWh" | "th" | "MMBtu">
                    value={form.energyUnit ?? ""}
                    options={[{ value: "", label: t("reports.native") }, { value: "MWh", label: "MWh" }, { value: "th", label: "th" }, { value: "MMBtu", label: "MMBtu" }]}
                    onChange={(energyUnit) => update({ energyUnit })}
                  />
                </Field>
              </div>
              {form.audience === "shareable" && (
                <p className="reports-note" data-report-audience-note="">{t("reports.no_book_for_distribution")}</p>
              )}
              {(mode === "standard" || scopeOpen) && (
              <div id="reports-scope" className="reports-scope">
              {mode === "ask" && (
                <Button size="sm" onClick={() => void propose()} loading={busy === "plan"} disabled={form.question.trim().length < 3}>
                  {t("reports.propose_plan")}
                </Button>
              )}
              {issueText("period")}
              {issueText("hubs")}
              <div className="reports-row">
                <Field label={t("reports.period_start")}>
                  <input type="date" value={form.periodStart} max={offer?.period.latest_end} onChange={(event) => update({ periodStart: event.target.value })} />
                </Field>
                <Field label={t("reports.period_end")}>
                  <input type="date" value={form.periodEnd} max={offer?.period.latest_end} onChange={(event) => update({ periodEnd: event.target.value })} />
                </Field>
                <Field label={t("reports.hubs")} hint={t("reports.hubs_hint")}>
                  <input value={form.hubs} maxLength={80} onChange={(event) => update({ hubs: event.target.value })} />
                </Field>
              </div>
              <fieldset className="reports-sections">
                <legend>{t("reports.sections")}</legend>
                {offered.map((section) => {
                  const state = offer?.sections[section.key];
                  const notHeld = state && state.state !== "ok";
                  return (
                    <label key={section.key} title={notHeld ? state.reason ?? section.data_source : section.data_source} data-section-state={state?.state ?? "unknown"}>
                      <input type="checkbox" checked={chosen.includes(section.key)} onChange={() => toggleSection(section.key)} />
                      <span>
                        {t(`reports.section.${section.key}`)}
                        {notHeld && <span className="reports-note"> · {t("reports.section_not_held")}{state.reason ? ` (${state.reason})` : ""}</span>}
                      </span>
                    </label>
                  );
                })}
              </fieldset>
              {issueText("sections")}
              <label className="reports-annex">
                <input
                  type="checkbox"
                  checked={form.annex ?? annexByDefault(mode === "ask" ? "ask" : form.kind)}
                  onChange={(event) => update({ annex: event.target.checked })}
                />
                <span>{t("reports.annex")}</span>
              </label>
              </div>
              )}
              {issueText("role")}
              {issueText("store")}
              {issueText("question")}
              {offer && !offer.ai.available && offer.can_generate && (
                <p className="reports-note" data-report-ai-note="">{offer.ai.reason}</p>
              )}
              {error && <p className="reports-error" role="alert">{error}</p>}
              {failure && (
                <div className="reports-failure" role="alert" data-report-failure={failure.key}>
                  <p>{t(failure.key)}</p>
                  <div className="reports-actions">
                    {failure.retry && <Button size="sm" onClick={() => void generate(true)}>{t("reports.retry")}</Button>}
                    {failure.withoutAi && offer?.ai.available !== false && <Button size="sm" variant="quiet" onClick={() => void generate(false)}>{t("reports.generate_without_ai")}</Button>}
                  </div>
                </div>
              )}
              {stage && <ReportProgress stage={stage} elapsed={startedAt ? now - startedAt : 0} onCancel={cancel} t={t} />}
              <div className="reports-actions">
                <Button type="submit" variant="primary" size="md" loading={busy === "generate"} disabled={!canGenerate}>
                  {t("reports.generate")}
                </Button>
                <span className="reports-note">{t("reports.no_advice")}</span>
              </div>
            </form>
          </Panel>
          <Panel
            title={t("reports.stored")}
            level={3}
            actions={
              <>
                <Button variant="quiet" onClick={() => setManageOpen(true)} disabled={!reports?.length} data-report-manage="">{t("reports.manage")}</Button>
                <Button variant="quiet" onClick={loadReports}>{t("reports.refresh")}</Button>
              </>
            }
          >
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
        <ReportViewer reportId={selected} t={t} onRemoved={removed} onRenamed={loadReports} />
      </div>
      <ManageReports open={manageOpen} onClose={() => setManageOpen(false)} reports={reports ?? []} t={t} onRemoved={removed} />
    </div>
  );
}

/** Staged progress while a report is planned, collected, written, checked and laid out. */
function ReportProgress({ stage, elapsed, onCancel, t }: { stage: ReportStage; elapsed: number; onCancel: () => void; t: Translate }) {
  // The shared stage indicator (UX_REFERENCE rule 18), with the time taken and Cancel beside it.
  return (
    <div className="reports-progress" data-report-stage={stage}>
      <WorkProgress
        stages={REPORT_STAGES.map((item) => t(`reports.stage.${item}`))}
        current={Math.max(0, REPORT_STAGES.indexOf(stage))}
        label={t("reports.generate")}
      />
      <span className="reports-note reports-elapsed" aria-label={t("reports.elapsed")}>{elapsedLabel(elapsed)}</span>
      <Button size="sm" variant="quiet" onClick={onCancel}>{t("reports.cancel")}</Button>
    </div>
  );
}

/** Delete stored reports, several at once, after a confirmation; the server checks each one. */
function ManageReports({ open, onClose, reports, t, onRemoved }: {
  open: boolean; onClose: () => void; reports: ReportSummaryDTO[]; t: Translate; onRemoved: (ids: string[]) => void;
}) {
  const [chosen, setChosen] = useState<string[]>([]);
  const [confirming, setConfirming] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setChosen([]);
      setConfirming(false);
      setMessage(null);
    }
  }, [open]);

  async function remove() {
    setBusy(true);
    try {
      const response = await api.deleteReports(chosen);
      const { deleted, refused } = response.data;
      onRemoved(deleted);
      setChosen(refused.map((item) => item.report_id));
      setConfirming(false);
      setMessage(refused.length
        ? t("reports.delete_partly", { deleted: deleted.length, refused: refused.length })
        : t("reports.deleted", { count: deleted.length }));
    } catch {
      setMessage(t("reports.delete_failed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={t("reports.manage")}
      closeLabel={t("reports.close")}
      id="report-manage"
      footer={
        confirming ? (
          <>
            <span className="reports-warn">{t("reports.delete_confirm", { count: chosen.length })}</span>
            <Button variant="quiet" onClick={() => setConfirming(false)}>{t("reports.cancel")}</Button>
            <Button variant="danger" loading={busy} onClick={() => void remove()} data-report-delete-confirm="">{t("reports.delete")}</Button>
          </>
        ) : (
          <Button variant="danger" disabled={!chosen.length} onClick={() => setConfirming(true)} data-report-delete="">
            {t("reports.delete_selected", { count: chosen.length })}
          </Button>
        )
      }
    >
      <fieldset className="reports-manage">
        <legend>{t("reports.manage_hint")}</legend>
        {reports.map((row) => (
          <label key={row.report_id}>
            <input
              type="checkbox"
              checked={chosen.includes(row.report_id)}
              onChange={() => setChosen((current) => (current.includes(row.report_id) ? current.filter((id) => id !== row.report_id) : [...current, row.report_id]))}
            />
            <span>{row.question || row.title}</span>
            <span className="reports-note">{(row.created_at ?? "").slice(0, 16).replace("T", " ")} · {row.generated_by ?? ""}</span>
          </label>
        ))}
      </fieldset>
      {message && <p className="reports-note" role="status">{message}</p>}
    </Dialog>
  );
}

function ReportViewer({ reportId, t, onRemoved, onRenamed }: {
  reportId: string | null; t: Translate; onRemoved: (ids: string[]) => void; onRenamed: () => void;
}) {
  const [html, setHtml] = useState<string | null>(null);
  const [dialog, setDialog] = useState<"rename" | "delete" | null>(null);
  const [title, setTitle] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
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

  async function rename() {
    if (!reportId || !title.trim()) return;
    try {
      const response = await api.renameReport(reportId, title.trim());
      setMeta((current) => (current ? { ...current, title: response.data.title } : current));
      setDialog(null);
      onRenamed();
    } catch (failure) {
      setProblem(String(failure instanceof Error ? failure.message : "").includes("not_owned") ? t("reports.not_owned") : t("reports.rename_failed"));
    }
  }

  async function remove() {
    if (!reportId) return;
    try {
      await api.deleteReport(reportId);
      setDialog(null);
      onRemoved([reportId]);
    } catch (failure) {
      setProblem(String(failure instanceof Error ? failure.message : "").includes("not_owned") ? t("reports.not_owned") : t("reports.delete_failed"));
    }
  }

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
            <Button size="sm" variant="quiet" onClick={() => { setTitle(meta?.title ?? ""); setProblem(null); setDialog("rename"); }} data-report-rename="">{t("reports.rename")}</Button>
            <Button size="sm" variant="quiet" onClick={() => { setProblem(null); setDialog("delete"); }} data-report-delete-one="">{t("reports.delete")}</Button>
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
      <Dialog
        open={dialog !== null}
        onClose={() => setDialog(null)}
        title={dialog === "rename" ? t("reports.rename") : t("reports.delete")}
        closeLabel={t("reports.close")}
        size="sm"
        id="report-edit"
        footer={
          <>
            <Button variant="quiet" onClick={() => setDialog(null)}>{t("reports.cancel")}</Button>
            {dialog === "rename"
              ? <Button variant="primary" onClick={() => void rename()} disabled={!title.trim()}>{t("reports.save")}</Button>
              : <Button variant="danger" onClick={() => void remove()} data-report-delete-confirm="">{t("reports.delete")}</Button>}
          </>
        }
      >
        {dialog === "rename" ? (
          <Field label={t("reports.title_label")}>
            <input value={title} maxLength={256} onChange={(event) => setTitle(event.target.value)} />
          </Field>
        ) : (
          <p>{t("reports.delete_one_confirm", { title: meta?.title ?? "" })}</p>
        )}
        {problem && <p className="reports-error" role="alert">{problem}</p>}
      </Dialog>
    </Panel>
  );
}
