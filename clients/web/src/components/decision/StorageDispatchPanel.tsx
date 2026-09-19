import { EvidenceBlock, PanelHeader } from "@/components/ui";
import { describeFailure, presentError } from "@/app/experience/errorPresentation";
import { formatUtcTimestamp } from "@/app/model/evidencePresentation";
import {
  MAX_STORAGE_PERIODS,
  dispatchDecisionRows,
  type StorageDispatchDraft,
  type StorageFacilityDraft,
  type StoragePeriodDraft,
} from "@/app/model/optimizationAssessmentModel";
import type {
  AssessmentState,
  OptimizationRunRecord,
} from "@/app/model/useOptimizationAssessment";
import type { StorageDispatchResultDTO } from "@/api/client";

type Translate = (key: string) => string;

interface StorageDispatchPanelProps {
  readonly t: Translate;
  readonly assessment: AssessmentState<StorageDispatchDraft, StorageDispatchResultDTO>;
  readonly record: OptimizationRunRecord;
}

function formatQuantity(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return `${value.toLocaleString()} MWh`;
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
  const { draft, updateDraft, readiness, result, busy, error, runId, recorded } = assessment;
  const failure = error ? presentError(t, describeFailure(error)) : null;

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
    updateDraft((current) => ({
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
        <p className="panel-copy">{t("decision.dispatch.note")}</p>

        <div className="decision-assessment-grid">
          <label className="field-label" htmlFor="dispatch-facility">
            {t("decision.dispatch.facility_id")}
          </label>
          <input
            id="dispatch-facility"
            type="text"
            maxLength={128}
            value={draft.facilityId}
            onChange={(event) =>
              updateDraft((current) => ({ ...current, facilityId: event.target.value }))
            }
          />
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
                  updateDraft((current) => ({
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
          <strong>{draft.periods.length}</strong>
        </div>
        <div className="data-table decision-dispatch-table" tabIndex={0}>
          <div className="data-table-row header two">
            <span>{t("decision.dispatch.period_id")}</span>
            <span>{t("decision.dispatch.market_price")}</span>
          </div>
          {draft.periods.map((period, index) => (
            <div key={`period-${index}`} className="data-table-row two">
              <input
                aria-label={t("decision.dispatch.period_id")}
                type="text"
                value={period.periodId}
                onChange={(event) => updatePeriod(index, { periodId: event.target.value })}
              />
              <input
                aria-label={t("decision.dispatch.market_price")}
                type="text"
                inputMode="decimal"
                value={period.marketPrice}
                onChange={(event) => updatePeriod(index, { marketPrice: event.target.value })}
              />
            </div>
          ))}
        </div>
        <div className="decision-assessment-actions">
          <button
            type="button"
            disabled={draft.periods.length >= MAX_STORAGE_PERIODS}
            onClick={() =>
              updateDraft((current) => ({
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
              updateDraft((current) => ({
                ...current,
                periods: current.periods.slice(0, -1),
              }))
            }
          >
            {t("decision.dispatch.remove_period")}
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
        <section className="workspace-panel span-3 decision-dispatch-result">
          <PanelHeader
            title={t("decision.dispatch.result")}
            meta={`${result.status} · ${formatMoney(result.objective_value_gbp)}`}
          />
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
            <div className="research-table data-table" tabIndex={0}>
              <div className="data-table-row header five">
                <span>{t("decision.dispatch.period_id")}</span>
                <span>{t("decision.dispatch.injection")}</span>
                <span>{t("decision.dispatch.withdrawal")}</span>
                <span>{t("decision.dispatch.ending_inventory")}</span>
                <span>{t("decision.dispatch.cashflow")}</span>
              </div>
              {rows.map((row) => (
                <div key={row.period_id} className="data-table-row five">
                  <strong>{row.period_id}</strong>
                  <span>{formatQuantity(row.injection_mwh)}</span>
                  <span>{formatQuantity(row.withdrawal_mwh)}</span>
                  <span>{formatQuantity(row.ending_inventory_mwh)}</span>
                  <span className={row.cashflow_gbp < 0 ? "status-badge status-blocked" : ""}>
                    {formatMoney(row.cashflow_gbp)}
                  </span>
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
