/**
 * Decision Case panel (Architecture V2 Wave 6, product surface).
 *
 * A self-contained surface over `/api/decision-cases`, following the pattern the
 * agent workspace already uses: it loads its own data, keeps its own state and
 * receives only the Active Context and the translator from the shell.
 *
 * What it deliberately does *not* do:
 *
 * - it never decides whether a case is decidable - the backend returns `decidable`
 *   and the blockers, and the panel renders them;
 * - it never claims reproducibility the payload does not report;
 * - it never sends an actor: the backend records the authenticated identity;
 * - it renders every failure through the product error taxonomy, so a refusal is
 *   explained rather than shown as a raw status.
 *
 * A Decision Record is evidence and rationale, never approval to execute anything.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import { ApiError, api } from "@/api/client";
import type {
  DecisionCaseDTO,
  DecisionCaseEvidenceInputDTO,
  DecisionCaseSummaryDTO,
} from "@/api/client";
import {
  DECISION_EVIDENCE_KINDS,
  DECISION_OUTCOMES,
  blockerLabelKey,
  canRecordDecision,
  canReopen,
  caseCounts,
  caseStatusLabelKey,
  evidenceKindLabelKey,
  isDecided,
  isReproducible,
  outcomeLabelKey,
  splitCases,
  suggestedEvidenceRef,
} from "@/app/model/decisionCaseModel";
import { describeFailure, presentError } from "@/app/experience/errorPresentation";
import { MetricStrip, PanelHeader, WorkspaceTabs } from "@/components/ui";

type Translate = (key: string, options?: Record<string, unknown>) => string;

interface DecisionCasePanelProps {
  gasDay: string;
  deliveryProduct: string;
  hubId: string | null;
  routeId: string | null;
  strategyRunId: string | null;
  /**
   * The last governed AI analysis run this identity completed, if any. The Decision Case
   * chain cites AI findings and challenges, so the panel offers that run by reference
   * rather than asking the user to copy an identifier.
   */
  analysisId?: string | null;
  t: Translate;
}

type PanelView = "open" | "decided";

export function DecisionCasePanel({
  gasDay,
  deliveryProduct,
  hubId,
  routeId,
  strategyRunId,
  analysisId,
  t,
}: DecisionCasePanelProps) {
  const [cases, setCases] = useState<DecisionCaseSummaryDTO[]>([]);
  const [selected, setSelected] = useState<DecisionCaseDTO | null>(null);
  const [view, setView] = useState<PanelView>("open");
  const [objective, setObjective] = useState("");
  const [evidenceKind, setEvidenceKind] =
    useState<DecisionCaseEvidenceInputDTO["kind"]>("MARKET_CONTEXT");
  const [evidenceRef, setEvidenceRef] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [errorText, setErrorText] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const response = await api.decisionCases({ limit: "50" });
      setCases(response.data);
    } catch (error) {
      setErrorText(explainError(error, t));
    }
  }, [t]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const grouped = useMemo(() => splitCases(cases), [cases]);
  const counts = caseCounts(selected);

  async function run(operation: () => Promise<{ data: DecisionCaseDTO }>) {
    setBusy(true);
    setErrorText(null);
    try {
      const response = await operation();
      setSelected(response.data);
      await refresh();
    } catch (error) {
      setErrorText(explainError(error, t));
    } finally {
      setBusy(false);
    }
  }

  async function openCase() {
    if (!objective.trim()) return;
    setBusy(true);
    setErrorText(null);
    try {
      const response = await api.createDecisionCase({
        objective: objective.trim(),
        gas_day: gasDay,
        delivery_product: deliveryProduct,
        hub_id: hubId ?? "",
      });
      setSelected(response.data);
      setObjective("");
      await refresh();
    } catch (error) {
      setErrorText(explainError(error, t));
    } finally {
      setBusy(false);
    }
  }

  async function attachEvidence() {
    if (!selected || !evidenceRef.trim()) return;
    const caseId = selected.case_id;
    await run(() =>
      api.attachDecisionCaseEvidence(caseId, {
        kind: evidenceKind,
        ref: evidenceRef.trim(),
        snapshot_id: selected.snapshot_id || "",
      }),
    );
    setEvidenceRef("");
  }

  async function selectCase(caseId: string) {
    setBusy(true);
    setErrorText(null);
    try {
      const response = await api.decisionCase(caseId);
      setSelected(response.data);
    } catch (error) {
      setErrorText(explainError(error, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="decision-case-panel" aria-label={t("decision_case.title")}>
      <PanelHeader
        title={t("decision_case.title")}
        meta={t("decision_case.subtitle")}
      />

      <div className="decision-case-create">
        <label>
          <span>{t("decision_case.objective")}</span>
          <input
            type="text"
            value={objective}
            maxLength={500}
            placeholder={t("decision_case.objective_placeholder")}
            onChange={(event) => setObjective(event.target.value)}
          />
        </label>
        <button type="button" disabled={busy || !objective.trim()} onClick={() => void openCase()}>
          {t("decision_case.create")}
        </button>
      </div>

      <WorkspaceTabs
        idPrefix="decision-case-view"
        label={t("decision_case.title")}
        tabs={[
          { id: "open", label: `${t("decision_case.view.open")} (${grouped.open.length})` },
          { id: "decided", label: `${t("decision_case.view.decided")} (${grouped.decided.length})` },
        ]}
        activeId={view}
        panelId="decision-case-panel"
        className="decision-case-views"
        onActivate={(id) => setView(id as PanelView)}
      />

      <div className="decision-case-list" id="decision-case-panel">
        {(view === "open" ? grouped.open : grouped.decided).map((row) => (
          <button
            key={row.case_id}
            type="button"
            className={selected?.case_id === row.case_id ? "active" : undefined}
            onClick={() => void selectCase(row.case_id)}
          >
            <strong>{row.objective}</strong>
            <span>{t(caseStatusLabelKey(row.status))}</span>
            <span>
              {t("decision_case.evidence_count", { count: row.evidence_count })}
            </span>
            {row.last_record && (
              <span>{t(outcomeLabelKey(row.last_record.outcome))}</span>
            )}
          </button>
        ))}
        {(view === "open" ? grouped.open : grouped.decided).length === 0 && (
          <p className="decision-case-empty">{t("decision_case.empty")}</p>
        )}
      </div>

      {selected && (
        <article className="decision-case-detail">
          <header>
            <h3>{selected.objective}</h3>
            <span className="eyebrow">{t(caseStatusLabelKey(selected.status))}</span>
          </header>

          <MetricStrip
            items={[
              { label: t("decision_case.evidence"), value: String(counts.evidence) },
              { label: t("decision_case.alternatives"), value: String(counts.alternatives) },
              { label: t("decision_case.assumptions"), value: String(counts.assumptions) },
              { label: t("decision_case.records"), value: String(counts.records) },
            ]}
          />

          <dl className="decision-case-facts">
            <div>
              <dt>{t("decision_case.context")}</dt>
              <dd>
                {selected.gas_day || t("decision_case.not_recorded")} ·{" "}
                {selected.delivery_product || t("decision_case.not_recorded")} ·{" "}
                {selected.hub_id || t("decision_case.not_recorded")}
              </dd>
            </div>
            <div>
              <dt>{t("decision_case.snapshot")}</dt>
              <dd>
                {isReproducible(selected)
                  ? selected.snapshot_id
                  : t("decision_case.not_reproducible")}
              </dd>
            </div>
          </dl>

          <ul className="decision-case-evidence">
            {selected.evidence.map((item) => (
              <li key={`${item.kind}:${item.ref}`}>
                <span>{t(evidenceKindLabelKey(item.kind))}</span>
                <code>{item.ref}</code>
              </li>
            ))}
          </ul>

          <div className="decision-case-attach">
            <label>
              <span>{t("decision_case.evidence_kind")}</span>
              <select
                value={evidenceKind}
                onChange={(event) => {
                  const next = event.target.value as DecisionCaseEvidenceInputDTO["kind"];
                  setEvidenceKind(next);
                  // The reference the Active Context (or the last AI run) already carries is
                  // offered instead of asking the user to copy an identifier.
                  const suggestion = suggestedEvidenceRef(next, {
                    routeId,
                    strategyRunId,
                    analysisId,
                  });
                  if (suggestion) setEvidenceRef(suggestion);
                }}
              >
                {DECISION_EVIDENCE_KINDS.map((kind) => (
                  <option key={kind} value={kind}>
                    {t(evidenceKindLabelKey(kind))}
                  </option>
                ))}
              </select>
            </label>
            <label>
              <span>{t("decision_case.evidence_ref")}</span>
              <input
                type="text"
                value={evidenceRef}
                maxLength={128}
                placeholder={routeId ?? strategyRunId ?? t("decision_case.evidence_ref_placeholder")}
                onChange={(event) => setEvidenceRef(event.target.value)}
              />
            </label>
            <button
              type="button"
              disabled={busy || !evidenceRef.trim()}
              onClick={() => void attachEvidence()}
            >
              {t("decision_case.attach")}
            </button>
          </div>

          {selected.blockers.length > 0 && (
            <ul className="decision-case-blockers" role="status">
              {selected.blockers.map((blocker) => (
                <li key={blocker}>{t(blockerLabelKey(blocker))}</li>
              ))}
            </ul>
          )}

          <div className="decision-case-record">
            <label>
              <span>{t("decision_case.note")}</span>
              <textarea
                value={note}
                maxLength={2000}
                onChange={(event) => setNote(event.target.value)}
              />
            </label>
            <div className="decision-case-actions">
              {DECISION_OUTCOMES.map((outcome) => (
                <button
                  key={outcome}
                  type="button"
                  disabled={busy || !canRecordDecision(selected)}
                  onClick={() =>
                    void run(() =>
                      api.recordDecisionCaseDecision(selected.case_id, { outcome, note }),
                    )
                  }
                >
                  {t(outcomeLabelKey(outcome))}
                </button>
              ))}
              {canReopen(selected) && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void run(() => api.reopenDecisionCase(selected.case_id))}
                >
                  {t("decision_case.reopen")}
                </button>
              )}
            </div>
          </div>

          {selected.records.length > 0 && (
            <ol className="decision-case-history">
              {selected.records.map((record) => (
                <li key={`${record.actor}:${record.recorded_at_utc}`}>
                  <strong>{t(outcomeLabelKey(record.outcome))}</strong>
                  <span>{record.actor}</span>
                  <time>{record.recorded_at_utc}</time>
                  {record.note && <p>{record.note}</p>}
                </li>
              ))}
            </ol>
          )}

          {isDecided(selected) && (
            <p className="decision-case-boundary">{t("decision_case.boundary")}</p>
          )}
        </article>
      )}

      {errorText && (
        <p className="decision-case-error" role="alert">
          {errorText}
        </p>
      )}
    </section>
  );
}

/** Render a failure through the product error taxonomy, never as a raw status. */
function explainError(error: unknown, t: Translate): string {
  const { title, action } = presentError(t, describeFailure(error));
  // The backend names the blockers it refused on; keep them visible.
  const detail =
    error instanceof ApiError && error.detail && typeof error.detail === "object"
      ? (error.detail as Record<string, unknown>)
      : null;
  const blockers = Array.isArray(detail?.blockers)
    ? (detail?.blockers as string[]).map((blocker) => t(blockerLabelKey(blocker))).join(", ")
    : "";
  return blockers ? `${title} (${blockers}). ${action}` : `${title}. ${action}`;
}
