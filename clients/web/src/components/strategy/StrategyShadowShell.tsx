import type { StrategyLabController } from "@/app/model/useStrategyLab";

type Translate = (key: string) => string;

interface StrategyShadowShellProps {
  controller: StrategyLabController;
  t: Translate;
}

export function StrategyShadowShell({
  controller,
  t,
}: StrategyShadowShellProps) {
  return (
    <div className="strategy-shadow-shell">
      <section className="workspace-panel">
        <h3>{t("strategy_lab.shadow")}</h3>
        <div className="strategy-shadow-state">
          <span className="status-badge status-unavailable">{t("strategy_lab.shadow_not_configured")}</span>
          <p>{t("strategy_lab.shadow_prerequisite")}</p>
        </div>
      </section>
      <section className="workspace-panel">
        <h3>{t("strategy_lab.shadow_future_surface")}</h3>
        <ul className="strategy-shadow-checklist">
          {(t("strategy_lab.shadow_checklist") as unknown as string).split("|").map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </section>
      {controller.backtestRuns.length > 0 && (
        <section className="workspace-panel">
          <h3>{t("strategy_lab.existing_persisted_runs")}</h3>
          <div className="data-table">
            <div className="data-table-row header three">
              <span>{t("strategy_lab.run")}</span><span>{t("strategy_lab.status")}</span><span>{t("strategy_lab.created")}</span>
            </div>
            {controller.backtestRuns.map((run) => (
              <div key={run.run_id} className="data-table-row three">
                <span>{run.run_id}</span><span>{run.status}</span><span>{run.started_at_utc}</span>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
