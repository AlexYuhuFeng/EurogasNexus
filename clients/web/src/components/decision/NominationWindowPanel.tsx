import { EvidenceBlock, PanelHeader } from "@/components/ui";
import { describeFailure, presentError } from "@/app/experience/errorPresentation";
import { formatUtcTimestamp } from "@/app/model/evidencePresentation";
import {
  MAX_NOMINATION_INSTRUCTIONS,
  MAX_NOMINATION_WINDOWS,
  nominationDecisionRows,
  type NominationDraft,
  type NominationInstructionDraft,
  type NominationWindowDraft,
} from "@/app/model/optimizationAssessmentModel";
import type {
  AssessmentState,
  OptimizationRunRecord,
} from "@/app/model/useOptimizationAssessment";
import type { NominationScheduleResultDTO } from "@/api/client";

type Translate = (key: string) => string;

interface NominationWindowPanelProps {
  readonly t: Translate;
  readonly assessment: AssessmentState<NominationDraft, NominationScheduleResultDTO>;
  readonly record: OptimizationRunRecord;
}

function formatQuantity(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return `${value.toLocaleString()} MWh`;
}

/**
 * Nomination and renomination windows, assessed (register C14/D8).
 *
 * This is the day's clock: an instruction is submitted at a time, a window opens and closes on the
 * gas-day clock, and the window's cap decides how much of the request survives. The engine returns
 * a decision per instruction with the window that applied and a machine-readable reason, which is
 * the answer to *"what will the operator actually be able to nominate, and into which window?"*
 *
 * Two things the panel refuses to blur:
 *
 * - it is an **assessment**, never a submission. The engine never submits a nomination, and the
 *   copy says so, because a screen that looks like it nominates would be a promise the platform
 *   does not make;
 * - an instruction outside every window is a legitimate question, not a form error - the engine
 *   reports it with a reason, and the panel renders that reason instead of refusing the run.
 */
export function NominationWindowPanel({ t, assessment, record }: NominationWindowPanelProps) {
  const { draft, updateDraft, readiness, result, busy, error, runId, recorded } = assessment;
  const failure = error ? presentError(t, describeFailure(error)) : null;

  function updateInstruction(index: number, patch: Partial<NominationInstructionDraft>): void {
    updateDraft((current) => ({
      ...current,
      instructions: current.instructions.map((instruction, position) =>
        position === index ? { ...instruction, ...patch } : instruction,
      ),
    }));
  }

  function updateWindow(index: number, patch: Partial<NominationWindowDraft>): void {
    updateDraft((current) => ({
      ...current,
      windows: current.windows.map((window, position) =>
        position === index ? { ...window, ...patch } : window,
      ),
    }));
  }

  const rows = nominationDecisionRows(result?.decisions ?? null);

  return (
    <>
      <section className="workspace-panel span-3 decision-nomination-form">
        <PanelHeader
          title={t("decision.nomination.title")}
          meta={t("decision.nomination.assessment_only")}
        />
        <p className="panel-copy">{t("decision.nomination.note")}</p>

        <div className="decision-assessment-grid">
          <label className="field-label" htmlFor="nomination-initial">
            {t("decision.nomination.initial_quantity")}
          </label>
          <input
            id="nomination-initial"
            type="text"
            inputMode="decimal"
            value={draft.initialQuantity}
            onChange={(event) =>
              updateDraft((current) => ({ ...current, initialQuantity: event.target.value }))
            }
          />
        </div>

        <div className="section-heading">
          <span className="eyebrow">{t("decision.nomination.windows")}</span>
          <strong>{draft.windows.length}</strong>
        </div>
        <div className="data-table decision-nomination-table" tabIndex={0}>
          <div className="data-table-row header four">
            <span>{t("decision.nomination.window_id")}</span>
            <span>{t("decision.nomination.opens_at")}</span>
            <span>{t("decision.nomination.closes_at")}</span>
            <span>{t("decision.nomination.maximum_change")}</span>
          </div>
          {draft.windows.map((window, index) => (
            <div key={`window-${index}`} className="data-table-row four">
              <input
                aria-label={t("decision.nomination.window_id")}
                type="text"
                maxLength={128}
                value={window.windowId}
                onChange={(event) => updateWindow(index, { windowId: event.target.value })}
              />
              <input
                aria-label={t("decision.nomination.opens_at")}
                type="time"
                value={window.opensAt}
                onChange={(event) => updateWindow(index, { opensAt: event.target.value })}
              />
              <input
                aria-label={t("decision.nomination.closes_at")}
                type="time"
                value={window.closesAt}
                onChange={(event) => updateWindow(index, { closesAt: event.target.value })}
              />
              <input
                aria-label={t("decision.nomination.maximum_change")}
                type="text"
                inputMode="decimal"
                value={window.maximumChange}
                onChange={(event) => updateWindow(index, { maximumChange: event.target.value })}
              />
            </div>
          ))}
        </div>
        <div className="decision-assessment-actions">
          <button
            type="button"
            disabled={draft.windows.length >= MAX_NOMINATION_WINDOWS}
            onClick={() =>
              updateDraft((current) => ({
                ...current,
                windows: [
                  ...current.windows,
                  { windowId: "", opensAt: "", closesAt: "", maximumChange: "" },
                ],
              }))
            }
          >
            {t("decision.nomination.add_window")}
          </button>
          <button
            type="button"
            disabled={draft.windows.length <= 1}
            onClick={() =>
              updateDraft((current) => ({
                ...current,
                windows: current.windows.slice(0, -1),
              }))
            }
          >
            {t("decision.nomination.remove_window")}
          </button>
        </div>

        <div className="section-heading">
          <span className="eyebrow">{t("decision.nomination.instructions")}</span>
          <strong>{draft.instructions.length}</strong>
        </div>
        <div className="data-table decision-nomination-table" tabIndex={0}>
          <div className="data-table-row header two">
            <span>{t("decision.nomination.submitted_at")}</span>
            <span>{t("decision.nomination.requested")}</span>
          </div>
          {draft.instructions.map((instruction, index) => (
            <div key={`instruction-${index}`} className="data-table-row two">
              <input
                aria-label={t("decision.nomination.submitted_at")}
                type="datetime-local"
                value={instruction.submittedAt}
                onChange={(event) => updateInstruction(index, { submittedAt: event.target.value })}
              />
              <input
                aria-label={t("decision.nomination.requested")}
                type="text"
                inputMode="decimal"
                value={instruction.requestedQuantity}
                onChange={(event) =>
                  updateInstruction(index, { requestedQuantity: event.target.value })
                }
              />
            </div>
          ))}
        </div>
        <div className="decision-assessment-actions">
          <button
            type="button"
            disabled={draft.instructions.length >= MAX_NOMINATION_INSTRUCTIONS}
            onClick={() =>
              updateDraft((current) => ({
                ...current,
                instructions: [
                  ...current.instructions,
                  { submittedAt: "", requestedQuantity: "" },
                ],
              }))
            }
          >
            {t("decision.nomination.add_instruction")}
          </button>
          <button
            type="button"
            disabled={draft.instructions.length <= 1}
            onClick={() =>
              updateDraft((current) => ({
                ...current,
                instructions: current.instructions.slice(0, -1),
              }))
            }
          >
            {t("decision.nomination.remove_instruction")}
          </button>
        </div>

        {readiness.firstBlockerKey && (
          <p className="strategy-error">{t(readiness.firstBlockerKey)}</p>
        )}
        {busy && <p className="muted">{t("status.loading")}</p>}
        {failure && (
          <div className="alert">
            <strong>{failure.title}</strong>
            <p>{failure.action}</p>
          </div>
        )}
      </section>

      {result && (
        <section className="workspace-panel span-3 decision-nomination-result">
          <PanelHeader
            title={t("decision.nomination.result")}
            meta={`${result.status} · ${formatQuantity(result.final_quantity_mwh)}`}
          />
          <EvidenceBlock
            ariaLabel={t("decision.nomination.result")}
            items={[
              {
                label: t("decision.assessment.as_of"),
                value: t("decision.assessment.not_reported"),
                detail: t("decision.assessment.engine_stateless"),
              },
              {
                label: t("decision.assessment.run_record"),
                value: recorded
                  ? (runId ?? t("data.unavailable"))
                  : t("decision.assessment.no_run_record"),
                detail: recorded
                  ? t("decision.assessment.run_record_help")
                  : t("decision.assessment.no_run_record_help"),
              },
              {
                label: t("decision.assessment.engine_status"),
                value: result.status,
                detail: `${t("decision.nomination.final_quantity")}: ${formatQuantity(result.final_quantity_mwh)}`,
              },
              {
                label: t("evidence.review_boundary"),
                value: result.human_review_required
                  ? t("strategy.warning.human_review_required")
                  : t("decision.assessment.no_review_required"),
                detail: t("strategy.no_execution"),
              },
            ]}
          />

          {rows.length === 0 ? (
            <p className="muted">{t("decision.nomination.no_instructions")}</p>
          ) : (
            <div className="research-table data-table" tabIndex={0}>
              <div className="data-table-row header five">
                <span>{t("decision.nomination.submitted_at")}</span>
                <span>{t("decision.nomination.requested")}</span>
                <span>{t("decision.nomination.accepted")}</span>
                <span>{t("decision.nomination.window_applied")}</span>
                <span>{t("decision.nomination.reason")}</span>
              </div>
              {rows.map((row, index) => (
                <div key={`decision-${index}`} className="data-table-row five">
                  <span>{formatUtcTimestamp(row.submittedAt)}</span>
                  <span>{formatQuantity(row.requested)}</span>
                  <span className={row.accepted_instruction ? "" : "status-badge status-blocked"}>
                    {formatQuantity(row.accepted)}
                  </span>
                  <span>
                    {row.windowId ?? t("decision.nomination.outside_any_window")}
                  </span>
                  <span className="muted">{row.reason}</span>
                </div>
              ))}
            </div>
          )}

          {result.warnings.length > 0 && (
            <div className="route-cost-issues">
              <strong>{t("strategy.warnings")}</strong>
              <ul>
                {result.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </div>
          )}

          {recorded && runId && (
            <div className="decision-assessment-actions">
              <button type="button" disabled={record.loading} onClick={() => void record.load(runId)}>
                {t("decision.assessment.read_run_record")}
              </button>
              {record.run && (
                <span className="muted">
                  {t("decision.assessment.record_read")}: {record.run.optimization_type} ·{" "}
                  {record.run.decision_context} · {formatUtcTimestamp(record.run.created_at_utc)}
                </span>
              )}
            </div>
          )}
        </section>
      )}
    </>
  );
}
