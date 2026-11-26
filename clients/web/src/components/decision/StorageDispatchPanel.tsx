import { useEffect, useState } from "react";
import { Button, DataGrid, EvidenceBlock, PanelHeader, RecordPicker } from "@/components/ui";
import { contractOptions } from "@/app/model/recordOptions";
import { useApiStore } from "@/stores/api";
import { api } from "@/api/client";
import { useCachedRead } from "@/app/data/readCache";
import { manualInputLabel, manualInputs, planningStorageOptions, storageDraftFrom } from "@/app/model/planningPrefill";
import { displayTime } from "@/app/time/displayTime";
import { describeFailure, presentError } from "@/app/experience/errorPresentation";
import {
  MAX_STORAGE_PERIODS,
  dispatchDecisionRows,
  emptyStorageDispatchDraft,
  type StorageDispatchDraft,
  type StorageFacilityDraft,
  type StoragePeriodDraft,
} from "@/app/model/optimizationAssessmentModel";
import type {
  AssessmentState,
  OptimizationRunRecord,
} from "@/app/model/useOptimizationAssessment";
import type { StorageDispatchResultDTO } from "@/api/client";
import { PanelHelp } from "@/components/ui/PanelHelp";
import { serverWarningText } from "@/app/warningLabel";
import { enumLabel } from "@/app/model/enumLabels";

type Translate = (key: string, options?: Record<string, unknown>) => string;

interface StorageDispatchPanelProps {
  readonly t: Translate;
  readonly assessment: AssessmentState<StorageDispatchDraft, StorageDispatchResultDTO>;
  readonly record: OptimizationRunRecord;
}

function formatQuantity(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return `${value.toLocaleString()} MWh`;
}

/** A volume in the column's unit (MWh, in the header). */
function quantity(value: number | null | undefined): string {
  return value === null || value === undefined || Number.isNaN(value) ? "–" : value.toLocaleString("en-GB");
}

function formatMoney(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  const sign = value > 0 ? "+" : "";
  return `${sign}${Math.round(value).toLocaleString()} GBP`;
}

/**
 * Storage injection, withdrawal and hold, assessed per period (register C14/D8).
 *
 * The question is the swing: given an inventory band, per-period inject/withdraw caps and a price
 * per period, what is the best schedule and what is it worth? The engine answers with one decision
 * per period - injected, withdrawn, ending inventory, period cashflow - and the objective value.
 *
 * It is an **assessment**: no booking and no nomination is submitted, and the panel says so. The
 * facility inputs are the operator's own, and the envelope's `source_references` names them as
 * `operator-input` rather than implying market data.
 */
export function StorageDispatchPanel({ t, assessment, record }: StorageDispatchPanelProps) {
  const contracts = useApiStore((state) => state.upstreamContracts);
  // Live by default (AGENTS rule 19): a facility from the store's masters, with its latest
  // inventory, fills the facility terms; the book's storage contracts stay choosable.
  const planning = useCachedRead("/optimization/planning-inputs", (signal) => api.planningInputs(undefined, { signal }));
  const inputs = planning.data?.data ?? null;
  const masters = planningStorageOptions(inputs);
  const storageChoices = [
    ...masters,
    ...contractOptions(contracts.filter((contract) => contract.resource_type === "STORAGE")).filter((option) => !masters.some((master) => master.id === option.id)),
  ];
  const [prefilled, setPrefilled] = useState<StorageDispatchDraft | null>(null);
  const { draft, updateDraft, readiness, result, busy, error, runId, recorded } = assessment;
  // A blocker is said once the user has started, not on an untouched form.
  const [touched, setTouched] = useState(false);
  const edit: typeof updateDraft = (change) => {
    setTouched(true);
    updateDraft(change);
  };
  const failure = error ? presentError(t, describeFailure(error)) : null;
  const prefillFrom = (facilityId: string): boolean => {
    const next = inputs ? storageDraftFrom(inputs, facilityId, draft) : null;
    if (!next) return false;
    updateDraft(() => next);
    setPrefilled(next);
    return true;
  };
  useEffect(() => {
    if (inputs && prefilled === null && !touched && inputs.storage[0]) prefillFrom(inputs.storage[0].facility_id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inputs]);
  const manual = manualInputs(draft, prefilled ?? emptyStorageDispatchDraft());

  const facilityFields: Array<{ key: keyof StorageFacilityDraft; labelKey: string }> = [
    { key: "initialInventory", labelKey: "decision.dispatch.initial_inventory" },
    { key: "minimumInventory", labelKey: "decision.dispatch.minimum_inventory" },
    { key: "maximumInventory", labelKey: "decision.dispatch.maximum_inventory" },
    { key: "maximumInjection", labelKey: "decision.dispatch.maximum_injection" },
    { key: "maximumWithdrawal", labelKey: "decision.dispatch.maximum_withdrawal" },
    { key: "injectionEfficiency", labelKey: "decision.dispatch.injection_efficiency" },
    { key: "withdrawalEfficiency", labelKey: "decision.dispatch.withdrawal_efficiency" },
    { key: "injectionCost", labelKey: "decision.dispatch.injection_cost" },
    { key: "withdrawalCost", labelKey: "decision.dispatch.withdrawal_cost" },
    { key: "terminalInventory", labelKey: "decision.dispatch.terminal_inventory" },
  ];

  function updatePeriod(index: number, patch: Partial<StoragePeriodDraft>): void {
    edit((current) => ({
      ...current,
      periods: current.periods.map((period, position) =>
        position === index ? { ...period, ...patch } : period,
      ),
    }));
  }

  const rows = dispatchDecisionRows(result?.decisions ?? null);

  return (
    <>
      <section className="workspace-panel span-3 decision-dispatch-form">
        <PanelHeader
          title={t("decision.dispatch.title")}
          meta={t("decision.dispatch.assessment_only")}
        />
        <PanelHelp text={t("decision.dispatch.note")} label={t("panel.how_to_read")} />

        <div className="decision-assessment-grid">
          {/* The live principle (UX_REFERENCE rule 25): the facility is one of the book's storage
              contracts; a facility outside the book can still be typed, and is marked so. */}
          <span className="decision-assessment-field">
            <RecordPicker
              id="dispatch-facility"
              label={t("decision.dispatch.facility")}
              options={storageChoices}
              value={draft.facilityId || null}
              allowManual
              emptyText={t("decision.dispatch.no_storage_contracts")}
              onChange={(choice) => {
                if (choice && !choice.manual && prefillFrom(choice.id)) return;
                edit((current) => ({ ...current, facilityId: choice?.id.slice(0, 128) ?? "" }));
              }}
            />
          </span>
          {facilityFields.map((field) => (
            <span key={field.key} className="decision-assessment-field">
              <label className="field-label" htmlFor={`dispatch-${field.key}`}>
                {t(field.labelKey)}
              </label>
              <input
                id={`dispatch-${field.key}`}
                type="text"
                inputMode="decimal"
                value={draft.facility[field.key]}
                onChange={(event) =>
                  edit((current) => ({
                    ...current,
                    facility: { ...current.facility, [field.key]: event.target.value },
                  }))
                }
              />
            </span>
          ))}
        </div>

        <div className="section-heading">
          <span className="eyebrow">{t("decision.dispatch.periods")}</span>
        </div>
        <DataGrid
          id="dispatch-periods"
          className="decision-dispatch-table"
          label={t("decision.dispatch.periods")}
          rows={draft.periods.map((_, index) => index)}
          rowKey={(index) => `period-${index}`}
          density="compact"
          columns={[
            { id: "period", header: t("decision.dispatch.period"), rowHeader: true, value: (index) => t("decision.dispatch.period_n", { n: index + 1 }) },
            { id: "price", header: t("decision.dispatch.market_price"), render: (index) => (
              <input aria-label={t("decision.dispatch.market_price")} type="text" inputMode="decimal" value={draft.periods[index].marketPrice} onChange={(event) => updatePeriod(index, { marketPrice: event.target.value })} />
            ) },
          ]}
        />
        <div className="decision-assessment-actions">
          <button
            type="button"
            disabled={draft.periods.length >= MAX_STORAGE_PERIODS}
            onClick={() =>
              edit((current) => ({
                ...current,
                periods: [...current.periods, { periodId: "", marketPrice: "" }],
              }))
            }
          >
            {t("decision.dispatch.add_period")}
          </button>
          <button
            type="button"
            disabled={draft.periods.length <= 1}
            onClick={() =>
              edit((current) => ({
                ...current,
                periods: current.periods.slice(0, -1),
              }))
            }
          >
            {t("decision.dispatch.remove_period")}
          </button>
        </div>

        {/* The page's action lives with the fields it uses, never in the tab row (UX_REFERENCE rule 26). */}
        <div className="decision-assessment-actions decision-assessment-run">
          <Button
            variant="primary"
            data-page-action="dispatch-assess"
            disabled={!readiness.canRun || busy}
            title={t(readiness.firstBlockerKey ?? "decision.dispatch.ready")}
            onClick={() => void assessment.run()}
          >
            {t("decision.dispatch.assess")}
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
        <section className="workspace-panel span-3 decision-dispatch-result">
          <PanelHeader
            title={t("decision.dispatch.result")}
            meta={`${enumLabel(result.status, t)} · ${formatMoney(result.objective_value_gbp)}`}
          />
          {manual.length > 0 && (
            <p className="muted" data-manual-inputs="true">
              {t("decision.planning.manual_inputs", { inputs: manual.map((path) => manualInputLabel(path, t)).join(", ") })}
            </p>
          )}
          <EvidenceBlock
            ariaLabel={t("decision.dispatch.result")}
            items={[
              {
                label: t("decision.assessment.objective"),
                value: formatMoney(result.objective_value_gbp),
                detail: t("decision.dispatch.objective_help"),
              },
              {
                label: t("decision.dispatch.terminal_inventory"),
                value: formatQuantity(result.terminal_inventory_mwh),
                detail: t("decision.dispatch.terminal_help"),
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
                label: t("evidence.review_boundary"),
                value: result.human_review_required
                  ? t("strategy.warning.human_review_required")
                  : t("decision.assessment.no_review_required"),
                detail: t("strategy.no_execution"),
              },
            ]}
          />

          {rows.length === 0 ? (
            <p className="muted">{t("decision.dispatch.no_periods")}</p>
          ) : (
            <DataGrid
              id="dispatch-decisions"
              label={t("decision.dispatch.periods")}
              rows={rows}
              rowKey={(row) => row.period_id}
              density="compact"
              columns={[
                { id: "period", header: t("decision.dispatch.period_id"), rowHeader: true, value: (row) => row.period_id },
                { id: "injection", header: t("decision.dispatch.injection"), unit: "MWh", type: "number", value: (row) => row.injection_mwh, format: (value) => quantity(value as number) },
                { id: "withdrawal", header: t("decision.dispatch.withdrawal"), unit: "MWh", type: "number", value: (row) => row.withdrawal_mwh, format: (value) => quantity(value as number) },
                { id: "inventory", header: t("decision.dispatch.ending_inventory"), unit: "MWh", type: "number", value: (row) => row.ending_inventory_mwh, format: (value) => quantity(value as number) },
                {
                  id: "cashflow",
                  header: t("decision.dispatch.cashflow"),
                  unit: "GBP",
                  type: "number",
                  value: (row) => row.cashflow_gbp,
                  render: (row) => <span className={row.cashflow_gbp < 0 ? "status-badge status-blocked" : ""}>{formatMoney(row.cashflow_gbp).replace(/ GBP$/, "")}</span>,
                },
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
