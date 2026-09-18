import { useMemo, useState } from "react";
import type { StrategyLabController, StrategyLabSelection } from "@/app/model/useStrategyLab";
import { inspectorSubjectFor } from "@/app/model/inspectorDetail";
import {
  MISSING_DATA_POLICIES,
  TRANSACTION_COST_TREATMENTS,
  type StrategyBacktestDraft,
  type StrategyBacktestReadiness,
} from "@/app/model/strategyBacktestModel";
import {
  experimentPeriod,
  experimentReadiness,
  EXPERIMENT_HYPOTHESIS_MAX_LENGTH,
  EXPERIMENT_NAME_MAX_LENGTH,
  runsInExperiment,
  unloadedRunIds,
} from "@/app/model/strategyExperimentModel";
import { useInspectorStore } from "@/stores/inspector";
import { StrategyLineChart } from "./StrategyLabCharts";

type Translate = (key: string) => string;

interface StrategyBacktestWorkspaceProps {
  controller: StrategyLabController;
  selection: StrategyLabSelection;
  gasDay: string;
  language: string;
  /**
   * The run configuration and its readiness, owned by the workspace that hosts the run action
   * (Wave 9 action geography). This panel renders the fields and the preflight verdict; it no
   * longer decides whether a run is allowed, and it no longer starts one.
   */
  draft: StrategyBacktestDraft;
  readiness: StrategyBacktestReadiness;
  onDraftChange: (draft: StrategyBacktestDraft) => void;
  t: Translate;
}

function formatSignedMoney(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  const sign = value > 0 ? "+" : "";
  return `${sign}${Math.round(value).toLocaleString()} GBP`;
}

function formatTimestamp(value: string | null | undefined, language: string): string {
  if (!value) return "n/a";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "n/a";
  return new Intl.DateTimeFormat(language.startsWith("zh") ? "zh-CN" : "en-GB", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
}

export function StrategyBacktestWorkspace({
  controller,
  gasDay,
  language,
  draft,
  readiness,
  onDraftChange,
  t,
}: StrategyBacktestWorkspaceProps) {
  // Wave 9: the selected run's own record belongs to the canonical Inspector. The KPI
  // strip and the charts stay here - they are this surface's analysis - while the run's
  // facts and provenance are handed over rather than duplicated.
  const inspector = useInspectorStore();
  const [mode, setMode] = useState<"configure" | "result">("configure");
  // The experiment form's own view state stays with the panel; what would be *written* is decided
  // by `strategyExperimentModel` and sent by the controller.
  const [experimentName, setExperimentName] = useState("");
  const [experimentHypothesis, setExperimentHypothesis] = useState("");
  const [experimentPeriodDraft, setExperimentPeriodDraft] = useState(() => ({
    start: draft.start,
    end: draft.end,
  }));

  const run = controller.selectedRun;
  const metrics = run?.backtest_metrics ?? null;
  const details = run ? controller.detailsByRun[run.run_id] : undefined;

  const experimentDraft = useMemo(
    () => ({
      name: experimentName,
      hypothesis: experimentHypothesis,
      period: experimentPeriodDraft,
    }),
    [experimentHypothesis, experimentName, experimentPeriodDraft],
  );
  const experimentReadinessNow = useMemo(
    () =>
      experimentReadiness({
        subject: {
          strategyId: controller.selectedStrategy?.strategy_id ?? null,
          version: controller.selectedVersion
            ? {
                strategy_version_id: controller.selectedVersion.strategy_version_id,
                status: controller.selectedVersion.status,
              }
            : null,
        },
        draft: experimentDraft,
      }),
    [controller.selectedStrategy?.strategy_id, controller.selectedVersion, experimentDraft],
  );
  const selectedExperiment = controller.selectedExperiment;
  const experimentRuns = useMemo(
    () => runsInExperiment(controller.backtestRuns, selectedExperiment),
    [controller.backtestRuns, selectedExperiment],
  );
  const missingExperimentRuns = useMemo(
    () => unloadedRunIds(selectedExperiment, controller.backtestRuns),
    [controller.backtestRuns, selectedExperiment],
  );

  const updateDraft = (patch: Partial<StrategyBacktestDraft>) =>
    onDraftChange({ ...draft, ...patch });

  const seriesPoints = useMemo(
    () =>
      (details?.series ?? []).map((point) => ({
        label: point.gas_day,
        value: point.cumulative_net_indicative_pnl_gbp,
      })),
    [details?.series],
  );
  const drawdownPoints = useMemo(
    () =>
      (details?.series ?? []).map((point) => ({
        label: point.gas_day,
        value: -(point.drawdown_gbp ?? 0),
      })),
    [details?.series],
  );

  return (
    <div className="strategy-backtest">
      <div className="strategy-mode-tabs">
        <button type="button" className={mode === "configure" ? "active" : undefined} onClick={() => setMode("configure")}>
          {t("strategy_lab.configure")}
        </button>
        <button type="button" className={mode === "result" ? "active" : undefined} onClick={() => setMode("result")} disabled={!run}>
          {t("strategy_lab.result")}
        </button>
      </div>

      {mode === "configure" && (
        <section className="workspace-panel strategy-backtest-config">
          <h2>{t("strategy_lab.backtest_config")}</h2>
          <div className="strategy-form-grid">
            <label>{t("strategy_lab.version")}
              <input value={controller.selectedVersion ? `v${controller.selectedVersion.version_number} · ${controller.selectedVersion.status}` : ""} readOnly />
            </label>
            <label>{t("strategy_lab.period_start")}
              <input type="date" value={draft.start} onChange={(event) => updateDraft({ start: event.target.value })} />
            </label>
            <label>{t("strategy_lab.period_end")}
              <input type="date" value={draft.end} onChange={(event) => updateDraft({ end: event.target.value })} />
            </label>
            <label>{t("strategy_lab.gas_day_context")}
              <input value={gasDay} readOnly />
            </label>
            <label>{t("strategy_lab.missing_data_policy")}
              <select
                value={draft.missingDataPolicy}
                onChange={(event) =>
                  updateDraft({ missingDataPolicy: event.target.value as StrategyBacktestDraft["missingDataPolicy"] })
                }
              >
                {MISSING_DATA_POLICIES.map((policy) => <option key={policy}>{policy}</option>)}
              </select>
            </label>
            <label>{t("strategy_lab.transaction_cost_treatment")}
              <select
                value={draft.transactionCostTreatment}
                onChange={(event) =>
                  updateDraft({
                    transactionCostTreatment: event.target.value as StrategyBacktestDraft["transactionCostTreatment"],
                  })
                }
              >
                {TRANSACTION_COST_TREATMENTS.map((treatment) => <option key={treatment}>{treatment}</option>)}
              </select>
            </label>
            <label>{t("strategy_lab.transaction_cost")} GBP/MWh
              <input
                type="number"
                step="0.01"
                value={draft.transactionCost}
                onChange={(event) => updateDraft({ transactionCost: event.target.value })}
              />
            </label>
          </div>
          {/* The panel reports the verdict; the run itself is the workspace's primary action,
              disabled by this same rule. */}
          <div className="strategy-preflight">
            <strong>{t("strategy_lab.preflight")}</strong>
            {readiness.blockerKeys.length === 0 ? (
              <span className="status-badge status-complete">{t("strategy_lab.ready")}</span>
            ) : (
              readiness.blockerKeys.map((key) => <span key={key} className="status-badge status-blocked">{t(key)}</span>)
            )}
          </div>
        </section>
      )}

      {mode === "result" && run && (
        <div className="strategy-result-layout">
          <section className="workspace-panel strategy-result-strip">
            <span>{run.run_id}</span>
            <span>v{run.strategy_version_id ? controller.selectedVersion?.version_number ?? "?" : "?"}</span>
            <span>{formatTimestamp(run.started_at_utc, language)}</span>
            <span>{run.backtest_engine_version ?? "n/a"}</span>
            <span>{metrics?.temporal_integrity ?? "n/a"}</span>
            <button
              type="button"
              className="text-action"
              onClick={() => {
                const subject = inspectorSubjectFor(
                  "strategy-run",
                  run.run_id,
                  run.strategy_name ?? run.run_id,
                  "strategy",
                );
                if (subject) inspector.open(subject);
              }}
            >
              {t("strategy_lab.inspect_run")}
            </button>
          </section>
          {metrics && (
            <section className="workspace-panel strategy-kpi-strip">
              <div><span>{t("strategy_lab.net_indicative_pnl")}</span><strong>{formatSignedMoney(metrics.net_indicative_pnl_gbp)}</strong></div>
              <div><span>{t("strategy_lab.gross_indicative_pnl")}</span><strong>{formatSignedMoney(metrics.gross_indicative_pnl_gbp)}</strong></div>
              <div><span>{t("strategy_lab.modeled_costs")}</span><strong>{formatSignedMoney(metrics.modeled_costs_gbp)}</strong></div>
              <div><span>{t("strategy_lab.max_drawdown")}</span><strong>{formatSignedMoney(metrics.max_drawdown_gbp)}</strong></div>
              <div><span>{t("strategy_lab.data_coverage")}</span><strong>{((metrics.data_coverage ?? 0) * 100).toFixed(1)}%</strong></div>
              <div><span>{t("strategy_lab.evaluations")}</span><strong>{metrics.evaluation_count}</strong></div>
              <div><span>{t("strategy_lab.blocked_decisions")}</span><strong>{metrics.blocked_decision_count}</strong></div>
            </section>
          )}
          {details?.series.length ? (
            <section className="workspace-panel">
              <StrategyLineChart
                points={seriesPoints}
                title={t("strategy_lab.cumulative_net_pnl")}
                unit="GBP"
              />
              <StrategyLineChart
                points={drawdownPoints}
                title={t("strategy_lab.drawdown")}
                unit="GBP"
              />
            </section>
          ) : (
            <section className="workspace-panel strategy-chart-empty">
              {t("strategy_lab.no_series")}
            </section>
          )}
          <section className="workspace-panel">
            <h2>{t("strategy_lab.attribution")}</h2>
            {details?.attribution.length ? (
              <div className="data-table">
                <div className="data-table-row header four">
                  <span>{t("strategy_lab.dimension")}</span><span>{t("strategy_lab.key")}</span>
                  <span>{t("strategy_lab.net_pnl")}</span><span>{t("strategy_lab.cost")}</span>
                </div>
                {details.attribution.map((row) => (
                  <div key={row.attribution_id} className="data-table-row four">
                    <span>{row.dimension}</span><span>{row.key}</span>
                    <span>{row.net_indicative_pnl_gbp.toFixed(2)}</span>
                    <span>{row.modeled_costs_gbp.toFixed(2)}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="muted">{t("strategy_lab.no_attribution")}</p>
            )}
          </section>
          <section className="workspace-panel">
            <h2>{t("strategy_lab.decision_events")}</h2>
            {details?.events.length ? (
              <div className="data-table strategy-event-table">
                <div className="data-table-row header five">
                  <span>{t("strategy_lab.time")}</span><span>{t("strategy_lab.gas_day")}</span>
                  <span>{t("strategy_lab.outcome")}</span><span>{t("strategy_lab.net_pnl")}</span>
                  <span>{t("strategy_lab.warnings")}</span>
                </div>
                {details.events.map((event) => (
                  <div key={event.event_id} className="data-table-row five">
                    <span>{formatTimestamp(event.decision_time_utc, language)}</span>
                    <span>{event.gas_day}</span>
                    <span>{event.outcome}</span>
                    <span>{event.net_indicative_pnl_gbp.toFixed(2)}</span>
                    <span>{event.warnings.length}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="muted">{t("strategy_lab.no_events")}</p>
            )}
          </section>
        </div>
      )}

      {/* Experiments. The route has grouped runs into experiments since the strategy registry
          shipped and no surface ever created one, so a run could only be grouped by calling the
          API. Creating an experiment is a `persist`, which the geography places in the workspace's
          primary slot - and that slot holds the backtest run, the task's `compute` act. It lives
          here, bounded next to the runs it groups, for the same reason the version acts do: one
          task has one primary act, and a second persist is a bounded act beside its object rather
          than a rival for the slot. The run itself still carries the experiment id, so choosing an
          experiment here groups the run this task starts. */}
      <section className="workspace-panel strategy-experiments" aria-label={t("strategy_lab.experiments")}>
        <h2>{t("strategy_lab.experiments")}</h2>
        <p className="panel-copy">{t("strategy_lab.experiments_note")}</p>
        <div className="strategy-form-grid">
          <label>{t("strategy_lab.experiment.name")}
            <input
              value={experimentName}
              maxLength={EXPERIMENT_NAME_MAX_LENGTH}
              placeholder={t("strategy_lab.experiment.name_placeholder")}
              onChange={(event) => setExperimentName(event.target.value)}
            />
          </label>
          <label>{t("strategy_lab.experiment.period_start")}
            <input
              type="date"
              value={experimentPeriodDraft.start}
              onChange={(event) =>
                setExperimentPeriodDraft((current) => ({ ...current, start: event.target.value }))
              }
            />
          </label>
          <label>{t("strategy_lab.experiment.period_end")}
            <input
              type="date"
              value={experimentPeriodDraft.end}
              onChange={(event) =>
                setExperimentPeriodDraft((current) => ({ ...current, end: event.target.value }))
              }
            />
          </label>
        </div>
        <label>
          {t("strategy_lab.experiment.hypothesis")}
          <textarea
            value={experimentHypothesis}
            maxLength={EXPERIMENT_HYPOTHESIS_MAX_LENGTH}
            onChange={(event) => setExperimentHypothesis(event.target.value)}
          />
        </label>
        <div className="strategy-preflight">
          <strong>{t("strategy_lab.preflight")}</strong>
          {experimentReadinessNow.blockerKeys.length === 0 ? (
            <span className="status-badge status-complete">{t("strategy_lab.ready")}</span>
          ) : (
            experimentReadinessNow.blockerKeys.map((key) => (
              <span key={key} className="status-badge status-blocked">{t(key)}</span>
            ))
          )}
        </div>
        <div className="strategy-design-actions">
          <button
            type="button"
            disabled={!experimentReadinessNow.canCreate || controller.loading}
            title={
              experimentReadinessNow.firstBlockerKey
                ? t(experimentReadinessNow.firstBlockerKey)
                : t("strategy_lab.experiment.create_hint")
            }
            onClick={() => void controller.createExperiment(experimentDraft)}
          >
            {t("strategy_lab.experiment.create")}
          </button>
        </div>
        {controller.experiments.length === 0 ? (
          <p className="muted">{t("strategy_lab.experiment.empty")}</p>
        ) : (
          <div className="data-table strategy-experiment-table">
            <div className="data-table-row header five">
              <span>{t("strategy_lab.experiment.name")}</span>
              <span>{t("strategy_lab.experiment.type")}</span>
              <span>{t("strategy_lab.period")}</span>
              <span>{t("strategy_lab.experiment.runs")}</span>
              <span>{t("strategy_lab.status")}</span>
            </div>
            {controller.experiments.map((experiment) => {
              const period = experimentPeriod(experiment);
              return (
                <button
                  key={experiment.experiment_id}
                  type="button"
                  className={`data-table-row five ${
                    experiment.experiment_id === selectedExperiment?.experiment_id ? "selected" : ""
                  }`}
                  onClick={() => controller.selectExperiment(experiment.experiment_id)}
                >
                  <span>{experiment.name}</span>
                  <span>{experiment.experiment_type}</span>
                  <span>
                    {period.start ? `${period.start.slice(0, 10)} → ${period.end.slice(0, 10)}` : "n/a"}
                  </span>
                  <span>{experiment.run_ids.length}</span>
                  <span>{experiment.status}</span>
                </button>
              );
            })}
          </div>
        )}
        {selectedExperiment && (
          <div className="strategy-experiment-detail">
            <p className="panel-copy">
              {t("strategy_lab.experiment.selected")}: {selectedExperiment.experiment_id}
            </p>
            {selectedExperiment.hypothesis && <p className="muted">{selectedExperiment.hypothesis}</p>}
            {experimentRuns.length === 0 && missingExperimentRuns.length === 0 && (
              <p className="muted">{t("strategy_lab.experiment.no_runs")}</p>
            )}
            {experimentRuns.map((item) => (
              <button
                key={item.run_id}
                type="button"
                className="text-action"
                onClick={() => {
                  controller.selectRun(item.run_id);
                  setMode("result");
                }}
              >
                {t("strategy_lab.experiment.open_run")}: {item.run_id}
              </button>
            ))}
            {/* An experiment may group runs older than the bounded run history. They are counted
                and read on demand through the registry rather than dropped from the view. */}
            {missingExperimentRuns.map((runId) => (
              <button
                key={runId}
                type="button"
                className="text-action"
                onClick={() => {
                  void controller.loadRegistryRun(runId).then((loaded) => {
                    if (loaded) {
                      controller.selectRun(runId);
                      setMode("result");
                    }
                  });
                }}
              >
                {t("strategy_lab.experiment.open_older_run")}: {runId}
              </button>
            ))}
          </div>
        )}
      </section>

      <section className="workspace-panel strategy-run-history">
        <h2>{t("strategy_lab.run_history")}</h2>
        {controller.backtestRuns.length === 0 ? (
          <p className="muted">{t("strategy_lab.no_runs")}</p>
        ) : (
          <div className="data-table strategy-run-table">
            <div className="data-table-row header eight">
              <span>{t("strategy_lab.run")}</span><span>{t("strategy_lab.version")}</span>
              <span>{t("strategy_lab.period")}</span><span>{t("strategy_lab.status")}</span>
              <span>{t("strategy_lab.net_pnl")}</span><span>{t("strategy_lab.max_drawdown")}</span>
              <span>{t("strategy_lab.data_quality")}</span><span>{t("strategy_lab.engine")}</span>
            </div>
            {controller.backtestRuns.map((item) => (
              <button
                key={item.run_id}
                type="button"
                className={`data-table-row eight ${item.run_id === run?.run_id ? "selected" : ""}`}
                onClick={() => {
                  controller.selectRun(item.run_id);
                  setMode("result");
                }}
              >
                <span>{item.run_id.slice(-12)}</span>
                <span>{item.strategy_version_id ? item.strategy_version_id.slice(-8) : "legacy"}</span>
                <span>{formatTimestamp(item.evaluation_start_utc, language)}</span>
                <span>{item.status}</span>
                <span>{item.backtest_metrics ? formatSignedMoney(item.backtest_metrics.net_indicative_pnl_gbp) : "n/a"}</span>
                <span>{item.backtest_metrics ? formatSignedMoney(item.backtest_metrics.max_drawdown_gbp) : "n/a"}</span>
                <span>{item.backtest_metrics?.temporal_integrity ?? "n/a"}</span>
                <span>{item.backtest_engine_version ?? "n/a"}</span>
              </button>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
