import { useEffect, useMemo, useState } from "react";
import type { StrategyLabController } from "@/app/model/useStrategyLab";
import { classifyRunCompatibility, MAX_COMPARE_RUNS } from "@/app/model/strategyLabModel";
import type { StrategyRunDTO } from "@/api/client";
import { StrategyLineChart } from "./StrategyLabCharts";

type Translate = (key: string) => string;

interface StrategyCompareWorkspaceProps {
  controller: StrategyLabController;
  language: string;
  t: Translate;
}



function money(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toLocaleString(undefined, { maximumFractionDigits: 2 })} GBP`;
}

function timestamp(value: string | null | undefined, language: string): string {
  if (!value) return "n/a";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "n/a";
  return new Intl.DateTimeFormat(language.startsWith("zh") ? "zh-CN" : "en-GB", {
    month: "short",
    day: "2-digit",
    year: "numeric",
  }).format(parsed);
}



export function StrategyCompareWorkspace({
  controller,
  language,
  t,
}: StrategyCompareWorkspaceProps) {
  const [selected, setSelected] = useState<string[]>([]);
  const runs = controller.backtestRuns;
  const selectedRuns = useMemo(
    () => selected.map((id) => runs.find((run) => run.run_id === id)).filter((run): run is StrategyRunDTO => Boolean(run)),
    [runs, selected],
  );
  const status = classifyRunCompatibility(selectedRuns);

  useEffect(() => {
    selected.forEach((runId) => {
      void controller.loadRunDetails(runId);
    });
  }, [controller, selected]);

  function toggle(runId: string): void {
    setSelected((current) => {
      if (current.includes(runId)) return current.filter((id) => id !== runId);
      if (current.length >= MAX_COMPARE_RUNS) return current;
      return [...current, runId];
    });
  }

  const parameters = useMemo(() => {
    const rows: Record<string, Array<string | null>> = {};
    selectedRuns.forEach((run) => {
      const manifest = (run.manifest_json ?? {}) as Record<string, unknown>;
      const strategy = (manifest.strategy_definition ?? {}) as Record<string, unknown>;
      const components = Array.isArray(strategy.components) ? strategy.components : [];
      const first = components[0] as Record<string, unknown> | undefined;
      const extension = (first?.extension_json ?? {}) as Record<string, unknown>;
      const assumptions = (manifest.economic_assumptions ?? {}) as Record<string, unknown>;
      const values: Record<string, string | null> = {
        version: run.strategy_version_id ?? "legacy",
        engine: run.backtest_engine_version ?? "n/a",
        period: `${timestamp(run.evaluation_start_utc, language)} → ${timestamp(run.evaluation_end_utc, language)}`,
        weight: String(extension.weight ?? "n/a"),
        day_ahead_names: Array.isArray(extension.day_ahead_price_names)
          ? (extension.day_ahead_price_names as string[]).join(", ")
          : "n/a",
        intraday_names: Array.isArray(extension.intraday_price_names)
          ? (extension.intraday_price_names as string[]).join(", ")
          : "n/a",
        positive_threshold: String(extension.positive_spread_threshold_gbp_mwh ?? "n/a"),
        missing_policy: String(assumptions.missing_data_policy ?? "n/a"),
        fill_policy: String(assumptions.fill_price_policy ?? "n/a"),
      };
      Object.entries(values).forEach(([key, value]) => {
        rows[key] = [...(rows[key] ?? []), value];
      });
    });
    return rows;
  }, [language, selectedRuns]);

  return (
    <div className="strategy-compare">
      <section className="workspace-panel">
        <h2>{t("strategy_lab.select_runs")} (2–5)</h2>
        {runs.length === 0 ? (
          <p className="muted">{t("strategy_lab.no_runs")}</p>
        ) : (
          <div className="strategy-compare-selector">
            {runs.map((run) => (
              <label key={run.run_id}>
                <input
                  type="checkbox"
                  checked={selected.includes(run.run_id)}
                  onChange={() => toggle(run.run_id)}
                />
                <span>{run.run_id.slice(-12)}</span>
                <span>{run.backtest_engine_version ?? "n/a"}</span>
                <span>{run.backtest_metrics?.net_indicative_pnl_gbp !== undefined ? money(run.backtest_metrics.net_indicative_pnl_gbp) : "n/a"}</span>
              </label>
            ))}
          </div>
        )}
        <p>
          {t("strategy_lab.compatibility")}:{" "}
          <strong className={`status-badge status-${status.toLowerCase().replaceAll("_", "-")}`}>{status}</strong>
        </p>
      </section>

      {selectedRuns.length >= 2 && (
        <>
          <section className="workspace-panel">
            <h2>{t("strategy_lab.parameter_matrix")}</h2>
            <div className="data-table strategy-compare-matrix">
              <div className="data-table-row header">
                <span>{t("strategy_lab.parameter")}</span>
                {selectedRuns.map((run) => <span key={run.run_id}>{run.run_id.slice(-8)}</span>)}
              </div>
              {Object.entries(parameters)
                .filter(([, values]) => new Set(values).size > 1)
                .map(([key, values]) => (
                  <div key={key} className="data-table-row">
                    <span>{key}</span>
                    {values.map((value, index) => <span key={`${key}-${index}`}>{value ?? "n/a"}</span>)}
                  </div>
                ))}
            </div>
          </section>

          <section className="workspace-panel">
            <h2>{t("strategy_lab.kpi_table")}</h2>
            <div className="data-table">
              <div className="data-table-row header">
                <span>{t("strategy_lab.kpi")}</span>
                {selectedRuns.map((run) => <span key={run.run_id}>{run.run_id.slice(-8)}</span>)}
              </div>
              {[
                ["strategy_lab.net_indicative_pnl", (run: StrategyRunDTO) => run.backtest_metrics?.net_indicative_pnl_gbp],
                ["strategy_lab.gross_indicative_pnl", (run: StrategyRunDTO) => run.backtest_metrics?.gross_indicative_pnl_gbp],
                ["strategy_lab.modeled_costs", (run: StrategyRunDTO) => run.backtest_metrics?.modeled_costs_gbp],
                ["strategy_lab.max_drawdown", (run: StrategyRunDTO) => run.backtest_metrics?.max_drawdown_gbp],
                ["strategy_lab.data_coverage", (run: StrategyRunDTO) => run.backtest_metrics?.data_coverage],
                ["strategy_lab.hit_ratio", (run: StrategyRunDTO) => run.backtest_metrics?.hit_ratio],
              ].map(([label, accessor]) => (
                <div key={String(label)} className="data-table-row">
                  <span>{t(String(label))}</span>
                  {selectedRuns.map((run) => {
                    const value = (
                      accessor as (run: StrategyRunDTO) => number | null | undefined
                    )(run);
                    const formatted =
                      label === "strategy_lab.data_coverage" || label === "strategy_lab.hit_ratio"
                        ? value === null || value === undefined
                          ? "n/a"
                          : `${(value * 100).toFixed(1)}%`
                        : money(value);
                    return <span key={run.run_id}>{formatted}</span>;
                  })}
                </div>
              ))}
            </div>
          </section>

          <section className="workspace-panel">
            <h2>{t("strategy_lab.synchronized_pnl")}</h2>
            <div className="strategy-compare-charts">
              {selectedRuns.map((run) => {
                const details = controller.detailsByRun[run.run_id];
                return (
                  <StrategyLineChart
                    key={run.run_id}
                    points={(details?.series ?? []).map((point) => ({
                      label: point.gas_day,
                      value: point.cumulative_net_indicative_pnl_gbp,
                    }))}
                    title={`${run.run_id.slice(-12)} · ${t("strategy_lab.cumulative_net_pnl")}`}
                    unit="GBP"
                  />
                );
              })}
            </div>
          </section>

          <section className="workspace-panel">
            <h2>{t("strategy_lab.data_quality_matrix")}</h2>
            <div className="data-table">
              <div className="data-table-row header">
                <span>{t("strategy_lab.quality_dimension")}</span>
                {selectedRuns.map((run) => <span key={run.run_id}>{run.run_id.slice(-8)}</span>)}
              </div>
              {[
                ["strategy_lab.temporal_integrity", (run: StrategyRunDTO) => run.backtest_metrics?.temporal_integrity ?? "n/a"],
                ["strategy_lab.coverage", (run: StrategyRunDTO) => run.backtest_metrics?.data_coverage],
                ["strategy_lab.warnings", (run: StrategyRunDTO) => run.backtest_metrics?.warning_counts ? Object.keys(run.backtest_metrics.warning_counts).length : 0],
              ].map(([label, accessor]) => (
                <div key={String(label)} className="data-table-row">
                  <span>{t(String(label))}</span>
                  {selectedRuns.map((run) => (
                    <span key={run.run_id}>{String((accessor as (run: StrategyRunDTO) => unknown)(run))}</span>
                  ))}
                </div>
              ))}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
