import { useEffect, useState } from "react";
import { Button, DataGrid, EvidenceBlock, PanelHeader, PeriodPicker, RecordPicker } from "@/components/ui";
import { api } from "@/api/client";
import { useCachedRead } from "@/app/data/readCache";
import { manualInputLabel, manualInputs, nominationDraftFrom, planningContractOptions } from "@/app/model/planningPrefill";
import { displayTime } from "@/app/time/displayTime";
import { describeFailure, presentError } from "@/app/experience/errorPresentation";
import {
  MAX_NOMINATION_INSTRUCTIONS,
  MAX_NOMINATION_WINDOWS,
  emptyNominationDraft,
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
import { PanelHelp } from "@/components/ui/PanelHelp";
import { serverWarningText } from "@/app/warningLabel";
import { enumLabel } from "@/app/model/enumLabels";

type Translate = (key: string, options?: Record<string, unknown>) => string;

interface NominationWindowPanelProps {
  readonly t: Translate;
  readonly assessment: AssessmentState<NominationDraft, NominationScheduleResultDTO>;
  readonly record: OptimizationRunRecord;
}

/** A volume in the column's unit (MWh, in the header). */
function formatQuantity(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "–";
  return value.toLocaleString("en-GB");
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
  // A blocker is said once the user has started, not on an untouched form.
  const [touched, setTouched] = useState(false);
  const edit: typeof updateDraft = (change) => {
    setTouched(true);
    updateDraft(change);
  };
  const failure = error ? presentError(t, describeFailure(error)) : null;

  // Live by default (AGENTS rule 19): the contract in execution is chosen from the book, and its
  // DCQ, the day's nomination and the TSO calendar's windows fill the form; anything typed after
  // that is said in the result. Planning only: nothing is nominated (rule 8).
  const planning = useCachedRead("/optimization/planning-inputs", (signal) => api.planningInputs(undefined, { signal }));
  const inputs = planning.data?.data ?? null;
  const [contractId, setContractId] = useState<string | null>(null);
  const [prefilled, setPrefilled] = useState<NominationDraft | null>(null);
  const choose = (id: string) => {
    const next = inputs ? nominationDraftFrom(inputs, id) : null;
    if (!next) return;
    updateDraft(() => next);
    setPrefilled(next);
    setContractId(id);
  };
  useEffect(() => {
    if (inputs && contractId === null && !touched && inputs.contracts[0]) choose(inputs.contracts[0].contract_id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inputs]);
  const manual = manualInputs(draft, prefilled ?? emptyNominationDraft());

  function updateInstruction(index: number, patch: Partial<NominationInstructionDraft>): void {
    edit((current) => ({
      ...current,
      instructions: current.instructions.map((instruction, position) =>
        position === index ? { ...instruction, ...patch } : instruction,
      ),
    }));
  }

  function updateWindow(index: number, patch: Partial<NominationWindowDraft>): void {
    edit((current) => ({
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
        <PanelHelp text={t("decision.nomination.note")} label={t("panel.how_to_read")} />

        <div className="decision-assessment-grid">
          <span className="decision-assessment-field">
            <RecordPicker
              id="nomination-contract"
              label={t("decision.planning.contract")}
              options={planningContractOptions(inputs)}
              value={contractId}
              emptyText={t("decision.planning.no_contracts")}
              onChange={(choice) => choice && choose(choice.id)}
            />
          </span>
          <span className="decision-assessment-field">
            <label className="field-label" htmlFor="nomination-initial">
              {t("decision.nomination.initial_quantity")}
            </label>
            <input
              id="nomination-initial"
              type="text"
              inputMode="decimal"
              value={draft.initialQuantity}
              onChange={(event) =>
                edit((current) => ({ ...current, initialQuantity: event.target.value }))
              }
            />
          </span>
        </div>

        <div className="section-heading">
          <span className="eyebrow">{t("decision.nomination.windows")}</span>
          {inputs && (
            <small className="muted" data-windows-basis={inputs.windows.basis} title={inputs.windows.windows.map((window) => window.source).join("\n")}>
              {t(inputs.windows.basis === "held" ? "decision.planning.windows_held" : "decision.planning.windows_assumption")}
            </small>
          )}
        </div>
        <DataGrid
          id="nomination-windows"
          className="decision-nomination-table"
          label={t("decision.nomination.windows")}
          rows={draft.windows.map((_, index) => index)}
          rowKey={(index) => `window-${index}`}
          density="compact"
          columns={[
            // Windows are numbered, not named by hand (design basis H.3; UX_REFERENCE rule 25).
            { id: "window", header: t("decision.nomination.window"), rowHeader: true, value: (index) => t("decision.nomination.window_n", { n: index + 1 }) },
            { id: "opens", header: t("decision.nomination.opens_at"), render: (index) => (
              <input aria-label={t("decision.nomination.opens_at")} type="text" inputMode="numeric" pattern="[0-2][0-9]:[0-5][0-9]" placeholder="HH:MM" maxLength={5} value={draft.windows[index].opensAt} onChange={(event) => updateWindow(index, { opensAt: event.target.value })} />
            ) },
            { id: "closes", header: t("decision.nomination.closes_at"), render: (index) => (
              <input aria-label={t("decision.nomination.closes_at")} type="text" inputMode="numeric" pattern="[0-2][0-9]:[0-5][0-9]" placeholder="HH:MM" maxLength={5} value={draft.windows[index].closesAt} onChange={(event) => updateWindow(index, { closesAt: event.target.value })} />
            ) },
            { id: "cap", header: t("decision.nomination.maximum_change"), render: (index) => (
              <input aria-label={t("decision.nomination.maximum_change")} type="text" inputMode="decimal" value={draft.windows[index].maximumChange} onChange={(event) => updateWindow(index, { maximumChange: event.target.value })} />
            ) },
          ]}
        />
        <div className="decision-assessment-actions">
          <button
            type="button"
            disabled={draft.windows.length >= MAX_NOMINATION_WINDOWS}
            onClick={() =>
              edit((current) => ({
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
              edit((current) => ({
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
        </div>
        <DataGrid
          id="nomination-instructions"
          className="decision-nomination-table"
          label={t("decision.nomination.instructions")}
          rows={draft.instructions.map((_, index) => index)}
          rowKey={(index) => `instruction-${index}`}
          density="compact"
          columns={[
            { id: "submitted", header: t("decision.nomination.submitted_at"), render: (index) => (
              <PeriodPicker kind="datetime" label={t("decision.nomination.submitted_at")} value={draft.instructions[index].submittedAt} onChange={(value) => updateInstruction(index, { submittedAt: value })} />
            ) },
            { id: "requested", header: t("decision.nomination.requested"), unit: "MWh", render: (index) => (
              <input aria-label={t("decision.nomination.requested")} type="text" inputMode="decimal" value={draft.instructions[index].requestedQuantity} onChange={(event) => updateInstruction(index, { requestedQuantity: event.target.value })} />
            ) },
          ]}
        />
        <div className="decision-assessment-actions">
          <button
            type="button"
            disabled={draft.instructions.length >= MAX_NOMINATION_INSTRUCTIONS}
            onClick={() =>
              edit((current) => ({
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
              edit((current) => ({
                ...current,
                instructions: current.instructions.slice(0, -1),
              }))
            }
          >
            {t("decision.nomination.remove_instruction")}
          </button>
        </div>

        {/* The page's action lives with the fields it uses, never in the tab row (UX_REFERENCE rule 26). */}
        <div className="decision-assessment-actions decision-assessment-run">
          <Button
            variant="primary"
            data-page-action="nomination-assess"
            disabled={!readiness.canRun || busy}
            title={t(readiness.firstBlockerKey ?? "decision.nomination.ready")}
            onClick={() => void assessment.run()}
          >
            {t("decision.nomination.assess")}
          </Button>
        </div>
        {touched && readiness.firstBlockerKey && (
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
            meta={`${enumLabel(result.status, t)} · ${formatQuantity(result.final_quantity_mwh)} MWh`}
          />
          {manual.length > 0 && (
            <p className="muted" data-manual-inputs="true">
              {t("decision.planning.manual_inputs", { inputs: manual.map((path) => manualInputLabel(path, t)).join(", ") })}
            </p>
          )}
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
                value: enumLabel(result.status, t),
                detail: `${t("decision.nomination.final_quantity")}: ${formatQuantity(result.final_quantity_mwh)} MWh`,
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
            <DataGrid
              id="nomination-decisions"
              label={t("decision.nomination.instructions")}
              rows={rows}
              rowKey={(row) => `${row.submittedAt}-${row.windowId ?? "none"}-${row.requested}`}
              density="compact"
              columns={[
                { id: "submitted", header: t("decision.nomination.submitted_at"), rowHeader: true, type: "date", value: (row) => row.submittedAt, format: (value) => displayTime(value as string) },
                { id: "requested", header: t("decision.nomination.requested"), unit: "MWh", type: "number", value: (row) => row.requested, format: (value) => formatQuantity(value as number) },
                {
                  id: "accepted",
                  header: t("decision.nomination.accepted"),
                  unit: "MWh",
                  type: "number",
                  value: (row) => row.accepted,
                  render: (row) => <span className={row.accepted_instruction ? "" : "status-badge status-blocked"}>{formatQuantity(row.accepted)}</span>,
                },
                { id: "window", header: t("decision.nomination.window_applied"), value: (row) => row.windowId ?? t("decision.nomination.outside_any_window") },
                { id: "reason", header: t("decision.nomination.reason"), value: (row) => row.reason, format: (value) => serverWarningText(String(value ?? ""), t), cellClassName: () => "muted" },
              ]}
            />
          )}

          {result.warnings.length > 0 && (
            <div className="route-cost-issues">
              <strong>{t("strategy.warnings")}</strong>
              <ul>
                {result.warnings.map((warning) => (
                  <li key={warning} title={warning}>{serverWarningText(warning, t)}</li>
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
                  {record.run.decision_context} · {displayTime(record.run.created_at_utc)}
                </span>
              )}
            </div>
          )}
        </section>
      )}
    </>
  );
}
