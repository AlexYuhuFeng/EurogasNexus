import { useMemo, useState } from "react";
import type { StrategyLabController, StrategyLabSelection } from "@/app/model/useStrategyLab";
import { StrategyLineChart } from "./StrategyLabCharts";

type Translate = (key: string) => string;

interface StrategyBacktestWorkspaceProps {
  controller: StrategyLabController;
  selection: StrategyLabSelection;
  gasDay: string;
  language: string;
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
  t,
}: StrategyBacktestWorkspaceProps) {
  const [start, setStart] = useState(controller.defaultPeriod.start);
  const [end, setEnd] = useState(controller.defaultPeriod.end);
  const [missingPolicy, setMissingPolicy] = useState("FAIL");
  const [transactionTreatment, setTransactionTreatment] = useState("UNAVAILABLE");
  const [transactionCost, setTransactionCost] = useState("");
  const [mode, setMode] = useState<"configure" | "result">("configure");

  const run = controller.selectedRun;
  const metrics = run?.backtest_metrics ?? null;
  const details = run ? controller.detailsByRun[run.run_id] : undefined;
  const frozen = controller.selectedVersion?.status === "FROZEN";

  const blockers = useMemo(() => {
    const result: string[] = [];
    if (!frozen) result.push(t("strategy_lab.blocker.frozen_required"));
    if (!start || !end || start >= end) result.push(t("strategy_lab.blocker.period"));
    if (transactionTreatment === "MODELED_COST" && Number.isNaN(Number(transactionCost))) {
      result.push(t("strategy_lab.blocker.transaction_cost"));
    }
    return result;
  }, [end, frozen, start, t, transactionCost, transactionTreatment]);

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
              <input type="date" value={start} onChange={(event) => setStart(event.target.value)} />
            </label>
            <label>{t("strategy_lab.period_end")}
              <input type="date" value={end} onChange={(event) => setEnd(event.target.value)} />
            </label>
            <label>{t("strategy_lab.gas_day_context")}
              <input value={gasDay} readOnly />
            </label>
            <label>{t("strategy_lab.missing_data_policy")}
              <select value={missingPolicy} onChange={(event) => setMissingPolicy(event.target.value)}>
                <option>FAIL</option><option>SKIP_DECISION</option><option>CARRY_FORWARD_WITH_MAX_AGE</option>
              </select>
            </label>
            <label>{t("strategy_lab.transaction_cost_treatment")}
              <select value={transactionTreatment} onChange={(event) => setTransactionTreatment(event.target.value)}>
                <option>UNAVAILABLE</option><option>MODELED_COST</option><option>EXCLUDED</option>
              </select>
            </label>
            <label>{t("strategy_lab.transaction_cost")} GBP/MWh
              <input type="number" step="0.01" value={transactionCost} onChange={(event) => setTransactionCost(event.target.value)} />
            </label>
          </div>
          <div className="strategy-preflight">
            <strong>{t("strategy_lab.preflight")}</strong>
            {blockers.length === 0 ? (
              <span className="status-badge status-complete">{t("strategy_lab.ready")}</span>
            ) : (
              blockers.map((blocker) => <span key={blocker} className="status-badge status-blocked">{blocker}</span>)
            )}
          </div>
          <button
            type="button"
            disabled={blockers.length > 0 || controller.loading}
            onClick={() =>
              void controller.runBacktest({
                strategy_version_id: controller.selectedVersion?.strategy_version_id,
                evaluation_period_start_utc: `${start}T00:00:00Z`,
                evaluation_period_end_utc: `${end}T00:00:00Z`,
                economic_assumptions: {
                  missing_data_policy: missingPolicy,
                  fill_price_policy: "NEXT_ELIGIBLE",
                  cost_components: [
                    {
                      code: "TRANSACTION_COST",
                      treatment: transactionTreatment,
                      amount_gbp_mwh: transactionTreatment === "MODELED_COST" ? Number(transactionCost) : null,
                    },
                  ],
                },
              })
            }
          >
            {t("strategy_lab.run_backtest")}
          </button>
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
