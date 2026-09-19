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
  DecisionCaseDecisionInputDTO,
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
import { decisionPackPresentation } from "@/app/model/decisionPackModel";
import { describeFailure, presentError } from "@/app/experience/errorPresentation";
import { DecisionPackPanel } from "@/components/decision/DecisionPackPanel";
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
  /**
   * The blockers a governed refusal named.
   *
   * A case that cannot be decided yet answers 409 with its blocker codes; they are rendered as the
   * answer (with their labels) rather than as an error string, because "not decidable yet, and here
   * is why" is a statement about the case.
   */
  const [refusalBlockers, setRefusalBlockers] = useState<string[]>([]);

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

  /**
   * The case as the pack rides with it.
   *
   * The pack is composed by the single-case read (`GET /api/decision-cases/{case_id}`), because the
   * pack *is* that resource in a citable form - a write answers with the case it wrote and cannot
   * compose the artefact it has just changed. So a write here is followed by that read, which keeps
   * the pack beside the case the reviewer is deciding on instead of leaving them signing from a case
   * whose artefact has vanished. It is a read: nothing here composes, stores or signs a pack. When
   * the follow-up read fails, the case the write returned is still shown and the pack panel states
   * that this read carried no pack rather than showing the one from before the write.
   */
  async function withPack(caseDto: DecisionCaseDTO): Promise<DecisionCaseDTO> {
    try {
      const read = await api.decisionCase(caseDto.case_id);
      return read.data;
    } catch {
      return caseDto;
    }
  }

  async function run(operation: () => Promise<{ data: DecisionCaseDTO }>) {
    setBusy(true);
    setErrorText(null);
    try {
      const response = await operation();
      setSelected(await withPack(response.data));
      await refresh();
    } catch (error) {
      setErrorText(explainError(error, t));
    } finally {
      setBusy(false);
    }
  }

  /**
   * Record a decision outcome through the call that treats a refusal as an outcome.
   *
   * `POST /decision-cases/{id}/decisions` answers 409 `case_not_decidable` with the blockers when a
   * case cannot be decided yet. That is a governed answer about the case, not a transport failure,
   * so this uses `recordDecisionCaseDecisionOutcome` - the `apiOutcome` variant of the same route -
   * and renders the blockers the payload names. The throwing call is still what every other action
   * here uses, because their failures are failures.
   */
  async function recordOutcome(outcome: string, noteText: string) {
    if (!selected) return;
    setBusy(true);
    setErrorText(null);
    setRefusalBlockers([]);
    const result = await api.recordDecisionCaseDecisionOutcome(selected.case_id, {
      outcome: outcome as DecisionCaseDecisionInputDTO["outcome"],
      note: noteText,
    });
    if (result.ok) {
      setSelected(await withPack(result.data));
      await refresh();
    } else {
      const detail =
        result.failure.detail && typeof result.failure.detail === "object"
          ? (result.failure.detail as Record<string, unknown>)
          : null;
      const blockers = Array.isArray(detail?.blockers)
        ? (detail?.blockers as string[])
        : [];
      if (blockers.length > 0) {
        // The blockers are the answer: the case is not decidable yet, and these are the reasons.
        setRefusalBlockers(blockers);
        setErrorText(result.failure.message);
      } else {
        setErrorText(explainError({ status: result.failure.status, detail: result.failure.detail, body: result.failure.body }, t));
      }
    }
    setBusy(false);
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
      setSelected(await withPack(response.data));
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

          {/*
            The decision pack sits directly above the decision controls, because it is the artefact
            the reviewer signs: the context, the evidence with each snapshot's resolvability
            measured, the assumptions, the alternatives, the AI findings, the warnings, the recorded
            decision with its actor, the acts recorded against the case and the content hash. It is
            composed by the same read this detail comes from (`selected.pack`) and it records
            nothing - the outcome controls below are still the only act on this surface.
          */}
          <DecisionPackPanel t={t} model={decisionPackPresentation(selected.pack)} />

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
                  onClick={() => void recordOutcome(outcome, note)}
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
            {refusalBlockers.length > 0 && (
              <div className="decision-case-refusal" role="status">
                <strong>{t("decision_case.not_decidable")}</strong>
                <ul>
                  {refusalBlockers.map((blocker) => (
                    <li key={blocker}>{t(blockerLabelKey(blocker))}</li>
                  ))}
                </ul>
              </div>
            )}
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
