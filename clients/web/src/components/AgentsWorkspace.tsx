import { useEffect, useMemo, useState } from "react";
import {
  AgentReplayDTO,
  AgentRunDTO,
  CapabilityDTO,
  api,
} from "@/api/client";
import { PanelHeader, WorkspaceTabs } from "@/components/ui";

type Translate = (key: string) => string;
type AgentsViewId = "capabilities" | "research" | "runs";

const VIEWS: AgentsViewId[] = ["capabilities", "research", "runs"];

interface AgentsWorkspaceProps {
  t: Translate;
}

export function AgentsWorkspace({ t }: AgentsWorkspaceProps) {
  const [activeView, setActiveView] = useState<AgentsViewId>("capabilities");
  const [capabilities, setCapabilities] = useState<CapabilityDTO[]>([]);
  const [runs, setRuns] = useState<AgentRunDTO[]>([]);
  const [selectedRun, setSelectedRun] = useState<AgentReplayDTO | null>(null);
  const [objective, setObjective] = useState("");
  const [allowStrategy, setAllowStrategy] = useState(false);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void Promise.all([api.capabilities(), api.agentRuns()])
      .then(([capabilityResult, runResult]) => {
        if (!active) return;
        setCapabilities(capabilityResult.data);
        setRuns(runResult.data);
      })
      .catch((reason) => active && setError(String(reason)));
    return () => {
      active = false;
    };
  }, []);

  const tabs = useMemo(
    () => VIEWS.map((id) => ({ id, label: t(`agents.tab.${id}`) })),
    [t],
  );

  async function runResearch() {
    if (!objective.trim()) return;
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const response = await api.runAgentResearch({
        objective: objective.trim(),
        agent_profile: "STRATEGY_RESEARCHER",
        strategy_generation_allowed: allowStrategy,
      });
      setResult(response.data);
      const refreshed = await api.agentRuns();
      setRuns(refreshed.data);
    } catch (reason) {
      setError(String(reason));
    } finally {
      setRunning(false);
    }
  }

  async function openRun(run: AgentRunDTO) {
    try {
      const response = await api.agentReplay(run.agent_run_id);
      setSelectedRun(response.data);
    } catch (reason) {
      setError(String(reason));
    }
  }

  return (
    <div className={`workspace-grid agents-page agents-view-${activeView}`}>
      <div className="workspace-panel span-3">
        <PanelHeader title={t("agents.title")} meta={t("agents.subtitle")} />
        <p className="muted">{t("agents.boundary")}</p>
      </div>

      <div className="workspace-panel span-3">
        <WorkspaceTabs
          idPrefix="agents-task"
          label={t("agents.title")}
          tabs={tabs}
          activeId={activeView}
          panelId="agents-task-panel"
          className="agents-task-tabs"
          onActivate={(view) => setActiveView(view as AgentsViewId)}
        />
      </div>

      {error && <div className="workspace-panel span-3 alert">{error}</div>}

      {activeView === "capabilities" && (
        <div className="workspace-panel span-3">
          <div className="research-table data-table">
            <div className="data-table-row header five">
              <span>{t("agents.capability")}</span>
              <span>{t("agents.domain")}</span>
              <span>{t("agents.determinism")}</span>
              <span>{t("agents.side_effect")}</span>
              <span>{t("agents.action_policy")}</span>
            </div>
            {capabilities.map((capability) => (
              <div key={capability.capability_id} className="data-table-row five">
                <strong>{capability.capability_id}</strong>
                <span>{capability.domain}</span>
                <span className="status-badge">{capability.determinism_class}</span>
                <span className="status-badge">{capability.side_effect_class}</span>
                <span className="status-badge">{capability.action_policy}</span>
              </div>
            ))}
            {capabilities.length === 0 && (
              <div className="data-table-row"><span>{t("status.loading")}</span></div>
            )}
          </div>
        </div>
      )}

      {activeView === "research" && (
        <div className="workspace-panel span-3">
          <label className="field-label" htmlFor="agents-objective">
            {t("agents.objective")}
          </label>
          <textarea
            id="agents-objective"
            className="textarea"
            value={objective}
            onChange={(event) => setObjective(event.target.value)}
            rows={3}
            placeholder={t("agents.objective_placeholder")}
          />
          <label className="field-inline">
            <input
              type="checkbox"
              checked={allowStrategy}
              onChange={(event) => setAllowStrategy(event.target.checked)}
            />
            {t("agents.allow_strategy")}
          </label>
          <button className="button primary" onClick={runResearch} disabled={running || !objective.trim()}>
            {running ? t("status.loading") : t("agents.run_research")}
          </button>

          {result && (
            <div className="agents-result-panel">
              <PanelHeader title={t("agents.result")} meta={String(result.stage ?? "")} />
              <p>{t("agents.run_id")}: {String(result.agent_run_id)}</p>
              <p>{t("agents.status")}: {String(result.status)}</p>
              {Array.isArray(result.blockers) && (result.blockers as string[]).length > 0 && (
                <p className="alert">{t("agents.blockers")}: {String(result.blockers)}</p>
              )}
              {Array.isArray(result.warnings) && (result.warnings as string[]).length > 0 && (
                <p className="muted">{t("agents.warnings")}: {String(result.warnings)}</p>
              )}
            </div>
          )}
        </div>
      )}

      {activeView === "runs" && (
        <div className="workspace-panel span-3">
          <div className="research-table data-table">
            <div className="data-table-row header six">
              <span>{t("agents.time")}</span>
              <span>{t("agents.objective")}</span>
              <span>{t("agents.profile")}</span>
              <span>{t("agents.status")}</span>
              <span>{t("agents.artifacts")}</span>
              <span>{t("agents.model")}</span>
            </div>
            {runs.map((run) => (
              <button
                key={run.agent_run_id}
                className="data-table-row six link-row"
                onClick={() => openRun(run)}
              >
                <span>{new Date(run.created_at).toLocaleString()}</span>
                <span>{run.user_objective}</span>
                <span>{run.agent_profile}</span>
                <span className="status-badge">{run.status}</span>
                <span>{run.artifacts_created.join(", ")}</span>
                <span>{run.model_provider}/{run.model_id}</span>
              </button>
            ))}
            {runs.length === 0 && (
              <div className="data-table-row"><span>{t("agents.no_runs")}</span></div>
            )}
          </div>
          {selectedRun && (
            <div className="agents-result-panel">
              <PanelHeader title={t("agents.replay")} meta={selectedRun.agent_run_id} />
              <p>{t("agents.objective")}: {selectedRun.user_objective}</p>
              <p>{t("agents.status")}: {selectedRun.status} / {selectedRun.current_stage}</p>
              <p>{t("agents.warnings")}: {selectedRun.warnings.join(", ")}</p>
              <p>{t("agents.blockers")}: {selectedRun.blockers.join(", ")}</p>
              <p>{t("agents.invocations")}: {selectedRun.tool_invocations.length}</p>
              <p>{t("agents.hidden_cot")}: {String(selectedRun.hidden_chain_of_thought)}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
