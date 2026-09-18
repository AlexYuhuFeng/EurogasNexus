import { useEffect, useMemo, useState } from "react";
import { api as apiClient } from "@/api/client";
import type {
  ShadowAlertDTO,
  ShadowDriftDTO,
  ShadowEvaluationDTO,
  ShadowMonitorDTO,
  ShadowRuntimeStatusDTO,
} from "@/api/client";
import type { StrategyLabController } from "@/app/model/useStrategyLab";

type Translate = (key: string) => string;

interface StrategyShadowShellProps {
  controller: StrategyLabController;
  language: string;
  t: Translate;
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

function money(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toLocaleString(undefined, { maximumFractionDigits: 2 })} GBP`;
}

export function StrategyShadowShell({
  controller,
  language,
  t,
}: StrategyShadowShellProps) {
  const [monitors, setMonitors] = useState<ShadowMonitorDTO[]>([]);
  const [selectedMonitorId, setSelectedMonitorId] = useState<string | null>(null);
  const [evaluations, setEvaluations] = useState<ShadowEvaluationDTO[]>([]);
  const [alerts, setAlerts] = useState<ShadowAlertDTO[]>([]);
  const [drift, setDrift] = useState<ShadowDriftDTO[]>([]);
  const [runtime, setRuntime] = useState<ShadowRuntimeStatusDTO | null>(null);
  /**
   * The evaluation an operator opened, read on its own.
   *
   * `GET /api/shadow-evaluations/{id}` answers with the evaluation **and its risk checks**, which the
   * per-monitor list omits - so this is the read that shows why a candidate was blocked or flagged,
   * and it re-reads the monitor it belongs to because the row may be minutes old while the monitor's
   * health, next evaluation and cumulative shadow PnL have moved since.
   */
  const [openEvaluation, setOpenEvaluation] = useState<ShadowEvaluationDTO | null>(null);
  const [freshMonitor, setFreshMonitor] = useState<ShadowMonitorDTO | null>(null);
  const [scheduleType, setScheduleType] = useState("DAILY_AT");
  const [dailyAt, setDailyAt] = useState("05:00");
  const [intervalSeconds, setIntervalSeconds] = useState("3600");
  const [baselineRunId, setBaselineRunId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const selectedMonitor = useMemo(
    () => monitors.find((monitor) => monitor.shadow_monitor_id === selectedMonitorId) ?? null,
    [monitors, selectedMonitorId],
  );
  // The single-monitor read is the current state; the list entry is what the surface loaded.
  const monitorNow = freshMonitor ?? selectedMonitor;
  const latestEvaluation = evaluations[0] ?? null;
  const candidate = latestEvaluation?.candidate ?? null;
  const baselineRuns = controller.backtestRuns.filter(
    (run) => run.strategy_version_id === selectedMonitor?.strategy_version_id,
  );

  async function refresh() {
    try {
      const [monitorResult, alertResult, statusResult] = await Promise.all([
        apiClient.shadowMonitors(),
        apiClient.shadowAlerts(),
        apiClient.shadowRuntimeStatus(),
      ]);
      setMonitors(monitorResult.data);
      setAlerts(alertResult.data);
      setRuntime(statusResult.data);
    } catch (err) {
      setError(String(err));
    }
  }

  /**
   * Open one evaluation, with its risk checks, and re-read the monitor it belongs to.
   *
   * Two reads rather than one because they answer different questions: the evaluation says what
   * happened and which control flagged it, the monitor says where the run stands now.
   */
  async function openOneEvaluation(evaluationId: string, monitorId: string) {
    try {
      const [evaluationResult, monitorResult] = await Promise.all([
        apiClient.shadowEvaluation(evaluationId),
        apiClient.shadowMonitor(monitorId),
      ]);
      setOpenEvaluation(evaluationResult.data);
      setFreshMonitor(monitorResult.data);
    } catch (err) {
      setError(String(err));
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  useEffect(() => {
    if (!selectedMonitorId) {
      setEvaluations([]);
      setDrift([]);
      setOpenEvaluation(null);
      setFreshMonitor(null);
      return;
    }
    Promise.all([
      apiClient.shadowEvaluations(selectedMonitorId),
      apiClient.shadowDrift(selectedMonitorId),
      // The monitor itself, so the panel reads the selected monitor's current state rather than
      // only whatever the last list read happened to carry.
      apiClient.shadowMonitor(selectedMonitorId),
    ])
      .then(([evalResult, driftResult, monitorResult]) => {
        setEvaluations(evalResult.data);
        setDrift(driftResult.data);
        setFreshMonitor(monitorResult.data);
      })
      .catch((err) => setError(String(err)));
  }, [selectedMonitorId]);

  async function createMonitor() {
    if (!controller.selectedVersion || controller.selectedVersion.status !== "FROZEN") {
      setError(t("strategy_lab.blocker.frozen_required"));
      return;
    }
    setError(null);
    try {
      const result = await apiClient.createShadowMonitor({
        strategy_version_id: controller.selectedVersion.strategy_version_id,
        baseline_run_id: baselineRunId || null,
        schedule:
          scheduleType === "DAILY_AT"
            ? { type: "DAILY_AT", daily_at_utc: dailyAt, missed_policy: "SKIP" }
            : {
                type: "INTERVAL",
                interval_seconds: Number(intervalSeconds),
                missed_policy: "SKIP",
              },
        activate: true,
      });
      setSelectedMonitorId(result.data.shadow_monitor_id);
      await refresh();
    } catch (err) {
      setError(String(err));
    }
  }

  async function lifecycle(action: "pause" | "resume" | "retire") {
    if (!selectedMonitor) return;
    try {
      if (action === "pause") await apiClient.pauseShadowMonitor(selectedMonitor.shadow_monitor_id);
      if (action === "resume") await apiClient.resumeShadowMonitor(selectedMonitor.shadow_monitor_id);
      if (action === "retire") await apiClient.retireShadowMonitor(selectedMonitor.shadow_monitor_id);
      await refresh();
    } catch (err) {
      setError(String(err));
    }
  }

  return (
    <div className="strategy-shadow-runtime">
      <section className="workspace-panel">
        <h2>{t("strategy_lab.shadow")}</h2>
        <div className="strategy-shadow-state">
          <span className={`status-badge status-${runtime?.scheduler === "healthy" ? "complete" : "unavailable"}`}>
            {t("strategy_lab.scheduler")}: {runtime?.scheduler ?? "offline"}
          </span>
          <span>{t("strategy_lab.active_monitors")}: {runtime?.active_monitors ?? 0}</span>
          <span>{t("strategy_lab.pending_evaluations")}: {runtime?.pending_evaluations ?? 0}</span>
          <span>{t("strategy_lab.duplicate_claims_prevented")}: {runtime?.duplicate_claims_prevented ?? 0}</span>
        </div>
      </section>

      <section className="workspace-panel">
        <h2>{t("strategy_lab.activate_shadow")}</h2>
        <div className="strategy-form-grid">
          <label>
            {t("strategy_lab.version")}
            <input
              readOnly
              value={controller.selectedVersion ? `v${controller.selectedVersion.version_number} · ${controller.selectedVersion.status}` : ""}
            />
          </label>
          <label>
            {t("strategy_lab.schedule_type")}
            <select value={scheduleType} onChange={(event) => setScheduleType(event.target.value)}>
              <option value="DAILY_AT">DAILY_AT</option>
              <option value="INTERVAL">INTERVAL</option>
            </select>
          </label>
          {scheduleType === "DAILY_AT" ? (
            <label>{t("strategy_lab.daily_at_utc")}<input value={dailyAt} onChange={(event) => setDailyAt(event.target.value)} /></label>
          ) : (
            <label>{t("strategy_lab.interval_seconds")}<input value={intervalSeconds} onChange={(event) => setIntervalSeconds(event.target.value)} /></label>
          )}
          <label>
            {t("strategy_lab.baseline_backtest")}
            <select value={baselineRunId} onChange={(event) => setBaselineRunId(event.target.value)}>
              <option value="">{t("strategy_lab.none")}</option>
              {baselineRuns.map((run) => (
                <option key={run.run_id} value={run.run_id}>{run.run_id.slice(-12)}</option>
              ))}
            </select>
          </label>
        </div>
        <button type="button" onClick={() => void createMonitor()}>{t("strategy_lab.start_shadow_monitoring")}</button>
        <p className="muted">{t("strategy_lab.no_execution_boundary")}</p>
      </section>

      {monitors.length === 0 ? (
        <section className="workspace-panel">
          <p className="muted">{t("strategy_lab.shadow_not_configured")}</p>
        </section>
      ) : (
        <section className="workspace-panel">
          <h2>{t("strategy_lab.monitors")}</h2>
          <div className="data-table">
            <div className="data-table-row header four">
              <span>{t("strategy_lab.monitor")}</span><span>{t("strategy_lab.state")}</span>
              <span>{t("strategy_lab.next_evaluation")}</span><span>{t("strategy_lab.cumulative_shadow_pnl")}</span>
            </div>
            {monitors.map((monitor) => (
              <button
                key={monitor.shadow_monitor_id}
                type="button"
                className={`data-table-row four ${monitor.shadow_monitor_id === selectedMonitorId ? "selected" : ""}`}
                onClick={() => setSelectedMonitorId(monitor.shadow_monitor_id)}
              >
                <span>{monitor.shadow_monitor_id.slice(-16)}</span>
                <span>{monitor.state}</span>
                <span>{formatTimestamp(monitor.next_evaluation_at_utc, language)}</span>
                <span>{money(monitor.cumulative_shadow_pnl_gbp)}</span>
              </button>
            ))}
          </div>
        </section>
      )}

      {selectedMonitor && (
        <>
          <section className="workspace-panel">
            <h2>{t("strategy_lab.monitor_actions")}</h2>
            {/* The state shown is the monitor's own current record, not the list entry the surface
                loaded earlier: `GET /api/shadow-monitors/{id}` is the read that answers "right now". */}
            <div className="strategy-shadow-state">
              <span className={`status-badge status-${monitorNow?.health_state === "HEALTHY" ? "complete" : "warning"}`}>
                {t("strategy_lab.health")}: {monitorNow?.health_state ?? "n/a"}
              </span>
              <span>{t("strategy_lab.state")}: {monitorNow?.state ?? "n/a"}</span>
              <span>{t("strategy_lab.next_evaluation")}: {formatTimestamp(monitorNow?.next_evaluation_at_utc, language)}</span>
              <span>{t("strategy_lab.consecutive_failures")}: {monitorNow?.consecutive_failures ?? 0}</span>
            </div>
            <button type="button" onClick={() => void lifecycle("pause")}>{t("strategy_lab.pause")}</button>
            <button type="button" onClick={() => void lifecycle("resume")}>{t("strategy_lab.resume")}</button>
            <button type="button" onClick={() => void lifecycle("retire")}>{t("strategy_lab.retire")}</button>
          </section>
          {candidate && (
            <section className="workspace-panel">
              <h2>{t("strategy_lab.current_candidate")}</h2>
              <div className="strategy-form-grid">
                <span>{String(candidate.decision_time_utc ?? "")}</span>
                <span>{String(candidate.hypothetical_direction ?? "")}</span>
                <span>{String(candidate.hypothetical_quantity_mwh_per_day ?? "")} MWh/d</span>
                <span>{String(candidate.expected_indicative_pnl_gbp ?? "")} GBP</span>
                <span>{String(candidate.risk_state ?? "")}</span>
                <span>{String(candidate.evidence_state ?? "")}</span>
              </div>
            </section>
          )}
          <section className="workspace-panel">
            <h2>{t("strategy_lab.recent_evaluations")}</h2>
            {evaluations.length === 0 ? (
              <p className="muted">{t("strategy_lab.no_events")}</p>
            ) : (
              <div className="data-table strategy-event-table">
                <div className="data-table-row header five">
                  <span>{t("strategy_lab.time")}</span><span>{t("strategy_lab.gas_day")}</span>
                  <span>{t("strategy_lab.state")}</span><span>{t("strategy_lab.candidate")}</span>
                  <span>{t("strategy_lab.warnings")}</span>
                </div>
                {evaluations.map((evaluation) => (
                  <button
                    key={evaluation.shadow_evaluation_id}
                    type="button"
                    className={`data-table-row five ${
                      evaluation.shadow_evaluation_id === openEvaluation?.shadow_evaluation_id
                        ? "selected"
                        : ""
                    }`}
                    onClick={() =>
                      void openOneEvaluation(
                        evaluation.shadow_evaluation_id,
                        evaluation.shadow_monitor_id,
                      )
                    }
                  >
                    <span>{formatTimestamp(evaluation.decision_time_utc, language)}</span>
                    <span>{evaluation.gas_day ?? "n/a"}</span>
                    <span>{evaluation.state}</span>
                    <span>{evaluation.candidate_id ? "candidate" : "—"}</span>
                    <span>{evaluation.warnings.length}</span>
                  </button>
                ))}
              </div>
            )}
            {/* The risk checks are only in the single-evaluation read, so an evaluation the operator
                has not opened shows its state and the checks appear once it is read. */}
            {openEvaluation && (
              <div className="strategy-evaluation-detail">
                <p className="panel-copy">
                  {t("strategy_lab.evaluation_detail")}: {openEvaluation.shadow_evaluation_id}
                  {openEvaluation.failure_class ? ` · ${openEvaluation.failure_class}` : ""}
                </p>
                {(openEvaluation.risk_checks ?? []).length === 0 ? (
                  <p className="muted">{t("strategy_lab.no_risk_checks")}</p>
                ) : (
                  <div className="data-table">
                    <div className="data-table-row header five">
                      <span>{t("strategy_lab.control")}</span>
                      <span>{t("strategy_lab.observed")}</span>
                      <span>{t("strategy_lab.limit")}</span>
                      <span>{t("strategy_lab.state")}</span>
                      <span>{t("strategy_lab.severity")}</span>
                    </div>
                    {(openEvaluation.risk_checks ?? []).map((check) => (
                      <div key={check.risk_check_id} className="data-table-row five">
                        <span>{check.control_id}</span>
                        <span>{check.observed_value ?? "n/a"}</span>
                        <span>{check.limit_value ?? "n/a"}</span>
                        <span>{check.state}</span>
                        <span>{check.severity}</span>
                      </div>
                    ))}
                  </div>
                )}
                {(openEvaluation.missing_inputs ?? []).length > 0 && (
                  <p className="muted">
                    {t("strategy_lab.missing_inputs")}: {openEvaluation.missing_inputs.join(", ")}
                  </p>
                )}
              </div>
            )}
          </section>
          <section className="workspace-panel">
            <h2>{t("strategy_lab.drift")}</h2>
            {drift.length === 0 ? (
              <p className="muted">{t("strategy_lab.no_drift")}</p>
            ) : (
              <div className="data-table">
                <div className="data-table-row header four">
                  <span>{t("strategy_lab.state")}</span><span>{t("strategy_lab.sample_size")}</span>
                  <span>{t("strategy_lab.baseline_run")}</span><span>{t("strategy_lab.created")}</span>
                </div>
                {drift.map((row) => (
                  <div key={row.drift_snapshot_id} className="data-table-row four">
                    <span>{row.state}</span><span>{row.sample_size}</span>
                    <span>{row.baseline_run_id ?? "n/a"}</span>
                    <span>{formatTimestamp(row.created_at_utc, language)}</span>
                  </div>
                ))}
              </div>
            )}
          </section>
        </>
      )}

      <section className="workspace-panel">
        <h2>{t("strategy_lab.alerts")}</h2>
        {alerts.length === 0 ? (
          <p className="muted">{t("strategy_lab.no_alerts")}</p>
        ) : (
          <div className="data-table">
            <div className="data-table-row header five">
              <span>{t("strategy_lab.type")}</span><span>{t("strategy_lab.severity")}</span>
              <span>{t("strategy_lab.state")}</span><span>{t("strategy_lab.summary")}</span><span>{t("strategy_lab.actions")}</span>
            </div>
            {alerts.map((alert) => (
              <div key={alert.alert_id} className="data-table-row five">
                <span>{alert.alert_type}</span><span>{alert.severity}</span><span>{alert.state}</span>
                <span>{alert.summary}</span>
                <span>
                  <button
                    type="button"
                    onClick={() => void apiClient.acknowledgeShadowAlert(alert.alert_id).then(() => refresh())}
                  >
                    {t("strategy_lab.acknowledge")}
                  </button>
                </span>
              </div>
            ))}
          </div>
        )}
      </section>
      {error && <p className="strategy-error">{error}</p>}
    </div>
  );
}
