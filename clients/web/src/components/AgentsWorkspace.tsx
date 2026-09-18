import { useEffect, useMemo, useState } from "react";
import {
  AgentReplayDTO,
  AgentRunDTO,
  CapabilityDTO,
  api,
} from "@/api/client";
import {
  agentIssueLabelKey,
  agentIssueRowFromText,
  agentReplayIssueRows,
  agentReviewDecisionInput,
  agentReviewGate,
  formatAgentTimestamp,
  nextAgentConfirmationState,
  type AgentConfirmationState,
  type AgentIssueDisplayRow,
  type AgentReviewDecisionValue,
} from "@/app/model/agentReplayModel";
import { AgentArtifactChain } from "@/components/agents/AgentArtifactChain";
import { AgentReviewGate } from "@/components/agents/AgentReviewGate";
import {
  AGENT_RUN_DISCLOSURES,
  agentResearchRequest,
  agentRunReadiness,
  agentStrategyDisclosure,
} from "@/app/model/agentRunModel";
import {
  capabilityInvocationReadiness,
  capabilityInvocationRequest,
  capabilityOutcome,
  capabilityPolicyKey,
  type CapabilityInvocationSubject,
  type CapabilityOutcome,
} from "@/app/model/capabilityInvocationModel";
import { inspectorSubjectFor } from "@/app/model/inspectorDetail";
import { useApiStore } from "@/stores/api";
import { useInspectorStore } from "@/stores/inspector";
import { MetricStrip, PanelHeader, WorkspaceHeader } from "@/components/ui";

type Translate = (key: string) => string;
type AgentsViewId = "capabilities" | "research" | "runs";

const VIEWS: AgentsViewId[] = ["capabilities", "research", "runs"];

interface AgentsWorkspaceProps {
  t: Translate;
  /** Authenticated principal recorded as the reviewer of a review pack. */
  principalId?: string | null;
  /**
   * Whether the runtime database can accept the rows a research run persists. The run is
   * refused with 503 without it, so the action is gated on the same fact the portfolio
   * optimiser uses rather than being offered and then failing.
   */
  runtimeDbReady: boolean;
}

function AgentIssueList({
  rows,
  t,
}: {
  rows: AgentIssueDisplayRow[];
  t: Translate;
}) {
  if (rows.length === 0) return null;
  return (
    <ul className="agents-issue-list">
      {rows.map((row, index) => (
        <li key={`${row.code}-${row.evidence}-${index}`}>
          <span>
            <strong>{t(agentIssueLabelKey(row.code))}</strong>
            {row.detail && <span>{row.detail}</span>}
            {row.evidence && <small>{t("agents.issue.affected_evidence")}: {row.evidence}</small>}
          </span>
          <code>{row.code || t("agents.issue.unknown_code")}</code>
        </li>
      ))}
    </ul>
  );
}

export function AgentsWorkspace({ t, principalId = null, runtimeDbReady }: AgentsWorkspaceProps) {
  const publishAgentRunsRead = useApiStore((state) => state.publishAgentRunsRead);
  const inspector = useInspectorStore();
  const [activeView, setActiveView] = useState<AgentsViewId>("capabilities");
  const [capabilities, setCapabilities] = useState<CapabilityDTO[]>([]);
  const [runs, setRuns] = useState<AgentRunDTO[]>([]);
  const [selectedRun, setSelectedRun] = useState<AgentReplayDTO | null>(null);
  const [objective, setObjective] = useState("");
  const [allowStrategy, setAllowStrategy] = useState(false);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [confirmation, setConfirmation] = useState<AgentConfirmationState>({ status: "idle" });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void Promise.all([api.capabilities(), api.agentRuns()])
      .then(([capabilityResult, runResult]) => {
        if (!active) return;
        setCapabilities(capabilityResult.data);
        setRuns(runResult.data);
        // The Inspector resolves detail from state the identity already received, so the runs
        // this read produced are published for the `agent-run` subject.
        publishAgentRunsRead(runResult.data);
      })
      .catch((reason) => active && setError(String(reason)));
    return () => {
      active = false;
    };
  }, [publishAgentRunsRead]);

  const tabs = useMemo(
    () => VIEWS.map((id) => ({ id, label: t(`agents.tab.${id}`) })),
    [t],
  );

  const reviewerIdentity = (principalId ?? "").trim();
  const gate = useMemo(
    () => agentReviewGate(selectedRun, reviewerIdentity),
    [selectedRun, reviewerIdentity],
  );

  const selectedBlockers = useMemo(
    () => (selectedRun ? agentReplayIssueRows(selectedRun, "blocker") : []),
    [selectedRun],
  );
  const selectedWarnings = useMemo(
    () => (selectedRun ? agentReplayIssueRows(selectedRun, "warning") : []),
    [selectedRun],
  );

  // Wave 9 action geography: starting a governed research run is a `compute` consequence, so
  // it sits in the workspace's single primary slot rather than among the form's own controls.
  // The panel configures the run and reports its readiness and outcome; the header starts it,
  // disabled by the same rule the panel lists.
  const readiness = useMemo(
    () => agentRunReadiness({ objective, runtimeDbReady, running }),
    [objective, runtimeDbReady, running],
  );
  const strategyDisclosure = useMemo(() => agentStrategyDisclosure(allowStrategy), [allowStrategy]);

  // Capability invocation (Wave 7 / CR-15). The catalogue was published to the surface and had no
  // consumer: it listed postures without offering the act they govern. The rule lives in
  // `app/model/capabilityInvocationModel.ts`, the panel edits the arguments, and the header runs
  // it - the same split the research run uses.
  const [invokeCapabilityId, setInvokeCapabilityId] = useState("");
  const [invokeArguments, setInvokeArguments] = useState("{}");
  const [invokeConfirmed, setInvokeConfirmed] = useState(false);
  const [invokeNote, setInvokeNote] = useState("");
  const [invoking, setInvoking] = useState(false);
  const [invokeOutcome, setInvokeOutcome] = useState<CapabilityOutcome | null>(null);
  const [invokeError, setInvokeError] = useState<string | null>(null);

  const invokeSubject = useMemo<CapabilityInvocationSubject | null>(() => {
    const definition = capabilities.find((item) => item.capability_id === invokeCapabilityId);
    if (!definition) return null;
    return {
      capabilityId: definition.capability_id,
      actionPolicy: definition.action_policy,
      sideEffectClass: definition.side_effect_class,
      determinismClass: definition.determinism_class,
    };
  }, [capabilities, invokeCapabilityId]);

  const invokeReadiness = useMemo(
    () =>
      capabilityInvocationReadiness({
        capability: invokeSubject,
        argumentsText: invokeArguments,
        confirmed: invokeConfirmed,
        running: invoking,
      }),
    [invokeSubject, invokeArguments, invokeConfirmed, invoking],
  );

  async function invokeSelectedCapability() {
    const request = capabilityInvocationRequest({
      capability: invokeSubject,
      argumentsText: invokeArguments,
      confirmed: invokeConfirmed,
      confirmationNote: invokeNote,
    });
    if (!invokeSubject || !request) return;
    setInvoking(true);
    setInvokeError(null);
    setInvokeOutcome(null);
    try {
      const response = await api.invokeCapability(invokeSubject.capabilityId, request.arguments, {
        humanConfirmation: request.humanConfirmation,
        confirmationNote: request.confirmationNote,
      });
      setInvokeOutcome(capabilityOutcome(response.data));
    } catch (reason) {
      setInvokeError(String(reason));
    } finally {
      setInvoking(false);
    }
  }

  async function runResearch() {
    if (!readiness.canRun) return;
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const response = await api.runAgentResearch(
        agentResearchRequest({ objective, allowStrategy }),
      );
      setResult(response.data);
      const refreshed = await api.agentRuns();
      setRuns(refreshed.data);
      publishAgentRunsRead(refreshed.data);
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
      setConfirmation({ status: "idle" });
    } catch (reason) {
      setError(String(reason));
    }
  }

  async function confirmReviewPack(decision: AgentReviewDecisionValue, note: string) {
    const body = agentReviewDecisionInput(gate, decision, note);
    if (!body) {
      setConfirmation((current) =>
        nextAgentConfirmationState(current, { type: "refused", httpStatus: 422 }),
      );
      return;
    }
    setError(null);
    setConfirmation((current) => nextAgentConfirmationState(current, { type: "submit", decision }));
    try {
      const outcome = await api.recordReviewDecisionOutcome(body);
      if (!outcome.ok) {
        setConfirmation((current) =>
          nextAgentConfirmationState(current, {
            type: "refused",
            httpStatus: outcome.failure.status,
          }),
        );
        return;
      }
      setConfirmation((current) =>
        nextAgentConfirmationState(current, {
          type: "recorded",
          decision,
          decisionId: outcome.data.decision_id,
        }),
      );
      // Re-read the replay so the recorded decision is shown from the backend,
      // never from the optimistic client state alone.
      if (selectedRun) {
        try {
          const refreshed = await api.agentReplay(selectedRun.agent_run_id);
          setSelectedRun(refreshed.data);
        } catch (reason) {
          setError(String(reason));
        }
      }
    } catch (reason) {
      setError(String(reason));
      setConfirmation((current) =>
        nextAgentConfirmationState(current, { type: "refused", httpStatus: 0 }),
      );
    }
  }

  const primaryAction =
    activeView === "research" ? (
      <button
        type="button"
        disabled={!readiness.canRun}
        title={
          readiness.firstBlockerKey
            ? t(readiness.firstBlockerKey)
            : t("agents.run_research_hint")
        }
        onClick={() => void runResearch()}
      >
        {t("agents.run_research")}
      </button>
    ) : activeView === "capabilities" ? (
      <button
        type="button"
        disabled={!invokeReadiness.canInvoke}
        title={
          invokeReadiness.firstBlockerKey
            ? t(invokeReadiness.firstBlockerKey)
            : t("capabilities.invoke_hint")
        }
        onClick={() => void invokeSelectedCapability()}
      >
        {t("capabilities.invoke")}
      </button>
    ) : undefined;

  return (
    <div className={`agents-workspace agents-view-${activeView}`}>
      <WorkspaceHeader
        title={t("agents.title")}
        taskLabel={t(`agents.tab.${activeView}`)}
        idPrefix="agents-task"
        tabs={tabs}
        activeId={activeView}
        panelId="agents-task-panel"
        tabLabel={t("agents.title")}
        tabsClassName="agents-task-tabs"
        primaryAction={primaryAction}
        onActivate={(view) => setActiveView(view as AgentsViewId)}
      />
      <p className="muted agents-boundary">{t("agents.boundary")}</p>

      <div className={`workspace-grid agents-page agents-view-${activeView}`}>
        {error && <div className="workspace-panel span-3 alert">{error}</div>}

      {activeView === "capabilities" && (
        <div
          className="workspace-panel span-3"
          id="agents-task-panel"
          role="tabpanel"
          aria-labelledby={`agents-task-${activeView}`}
        >
          <div className="research-table data-table" tabIndex={0}>
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

          {/* Wave 7 / CR-15: the catalogue listed each capability's posture and offered no way to
              act on it. The form below picks one, edits its arguments and states the confirmation
              a HUMAN_CONFIRMATION capability requires; the run itself is the workspace's primary
              action. */}
          <section className="capability-invocation" aria-label={t("capabilities.invoke_panel")}>
            <div className="section-heading">
              <span className="eyebrow">{t("capabilities.invoke_panel")}</span>
              <strong>
                {invokeSubject ? t(capabilityPolicyKey(invokeSubject.actionPolicy)) : t("capabilities.no_selection")}
              </strong>
            </div>
            <label className="field-label" htmlFor="capability-invoke-target">
              {t("capabilities.capability")}
            </label>
            <select
              id="capability-invoke-target"
              value={invokeCapabilityId}
              onChange={(event) => {
                setInvokeCapabilityId(event.target.value);
                // A confirmation belongs to the capability it was given for: changing the target
                // clears it, so nobody confirms one thing and runs another.
                setInvokeConfirmed(false);
                setInvokeOutcome(null);
              }}
            >
              <option value="">{t("capabilities.no_selection")}</option>
              {capabilities.map((capability) => (
                <option key={`capability-invoke-${capability.capability_id}`} value={capability.capability_id}>
                  {capability.capability_id} · {capability.action_policy}
                </option>
              ))}
            </select>
            {invokeSubject && (
              <p className="panel-copy">
                {t("capabilities.policy")}: <code>{invokeSubject.actionPolicy}</code> ·{" "}
                {t("capabilities.side_effect")}: <code>{invokeSubject.sideEffectClass}</code> ·{" "}
                {t("capabilities.determinism")}: <code>{invokeSubject.determinismClass}</code>
              </p>
            )}
            <label className="field-label" htmlFor="capability-invoke-arguments">
              {t("capabilities.arguments")}
            </label>
            <textarea
              id="capability-invoke-arguments"
              className="textarea"
              value={invokeArguments}
              onChange={(event) => setInvokeArguments(event.target.value)}
              rows={4}
            />
            {invokeReadiness.requiresConfirmation && (
              <>
                <label className="field-inline">
                  <input
                    type="checkbox"
                    checked={invokeConfirmed}
                    onChange={(event) => setInvokeConfirmed(event.target.checked)}
                  />
                  {t("capabilities.confirm")}
                </label>
                <label className="field-label" htmlFor="capability-invoke-note">
                  {t("capabilities.confirmation_note")}
                </label>
                <input
                  id="capability-invoke-note"
                  value={invokeNote}
                  onChange={(event) => setInvokeNote(event.target.value)}
                />
              </>
            )}
            <ul className="agents-disclosure-list">
              {invokeReadiness.blockerKeys.map((key) => (
                <li key={key}>{t(key)}</li>
              ))}
              {invokeReadiness.canInvoke && <li>{t("capabilities.ready")}</li>}
            </ul>
            {invokeError && (
              <p className="alert" role="alert">
                {invokeError}
              </p>
            )}
            {invokeOutcome && (
              <div className="agents-result-panel">
                {/* A BLOCKED result is a result: the surface shows the stable code and detail the
                    runtime reported rather than rewriting it as an error. */}
                <p>
                  {t("agents.status")}: <code>{invokeOutcome.status}</code>
                  {invokeOutcome.failureCode && (
                    <>
                      {" · "}
                      <code>{invokeOutcome.failureCode}</code>
                    </>
                  )}
                </p>
                {invokeOutcome.failureDetail && <p>{invokeOutcome.failureDetail}</p>}
                {invokeOutcome.blockers.length > 0 && (
                  <AgentIssueList
                    rows={invokeOutcome.blockers.map(agentIssueRowFromText)}
                    t={t}
                  />
                )}
                <p className="panel-copy">
                  {t("capabilities.quality")}: {invokeOutcome.qualityState} ·{" "}
                  {t("capabilities.entitlement")}: {invokeOutcome.entitlementState}
                  {invokeOutcome.asOf ? ` · ${invokeOutcome.asOf}` : ""}
                </p>
              </div>
            )}
          </section>
        </div>
      )}

      {activeView === "research" && (
        <div
          className="workspace-panel span-3"
          id="agents-task-panel"
          role="tabpanel"
          aria-labelledby={`agents-task-${activeView}`}
        >
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

          {/* The run starts from the workspace's primary action. What the panel owes is the
              verdict: what is missing before it can run, and what the run will and will not
              do once it does. */}
          <section className="agents-readiness" aria-label={t("agents.readiness.title")}>
            <div className="section-heading">
              <span className="eyebrow">{t("agents.readiness.title")}</span>
              <strong className={readiness.canRun ? "success-text" : "warning-text"}>
                {readiness.canRun ? t("agents.readiness.ready") : t("agents.readiness.blocked")}
              </strong>
            </div>
            {readiness.blockerKeys.length > 0 && (
              <ul className="agents-blocker-list">
                {readiness.blockerKeys.map((key) => (
                  <li key={key}>{t(key)}</li>
                ))}
              </ul>
            )}
            <ul className="agents-disclosure-list">
              {[...strategyDisclosure, ...AGENT_RUN_DISCLOSURES].map((key) => (
                <li key={key}>{t(key)}</li>
              ))}
            </ul>
          </section>

          {result && (
            <div className="agents-result-panel">
              <PanelHeader title={t("agents.result")} meta={String(result.stage ?? "")} />
              <p>{t("agents.run_id")}: {String(result.agent_run_id)}</p>
              <p>{t("agents.objective")}: {objective.trim()}</p>
              <p>{t("agents.status")}: {String(result.status)}</p>
              {Array.isArray(result.blockers) && (result.blockers as string[]).length > 0 && (
                <div className="agents-result-issues alert">
                  <strong>{t("agents.blockers")}</strong>
                  <AgentIssueList
                    rows={(result.blockers as string[]).map(agentIssueRowFromText)}
                    t={t}
                  />
                </div>
              )}
              {Array.isArray(result.warnings) && (result.warnings as string[]).length > 0 && (
                <div className="agents-result-issues">
                  <strong>{t("agents.warnings")}</strong>
                  <AgentIssueList
                    rows={(result.warnings as string[]).map(agentIssueRowFromText)}
                    t={t}
                  />
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {activeView === "runs" && (
        <div
          className="workspace-panel span-3"
          id="agents-task-panel"
          role="tabpanel"
          aria-labelledby={`agents-task-${activeView}`}
        >
          <div className="research-table data-table" tabIndex={0}>
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
                <span>{formatAgentTimestamp(run.created_at) || t("agents.value_absent")}</span>
                <span className="agents-run-objective">{run.user_objective}</span>
                <span>{run.agent_profile}</span>
                <span className="status-badge">{run.status}</span>
                <span>{run.artifacts_created.join(", ")}</span>
                <span className="agents-run-model">{run.model_provider}/{run.model_id}</span>
              </button>
            ))}
            {runs.length === 0 && (
              <div className="data-table-row"><span>{t("agents.no_runs")}</span></div>
            )}
          </div>

          {selectedRun && (
            <div className="agents-result-panel agents-replay-panel">
              <PanelHeader title={t("agents.replay")} meta={selectedRun.agent_run_id} />
              {/* Wave 9: the run's own record belongs to the canonical Inspector, so this panel
                  hands the subject over - next to the run it describes - rather than restating
                  the row's facts in a second detail surface. */}
              <div className="action-row">
                <button
                  type="button"
                  className="text-action"
                  onClick={() => {
                    const subject = inspectorSubjectFor(
                      "agent-run",
                      selectedRun.agent_run_id,
                      selectedRun.user_objective,
                      "agents",
                    );
                    if (subject) inspector.open(subject);
                  }}
                >
                  {t("agents.inspect_run")}
                </button>
              </div>
              <MetricStrip
                className="metric-grid agents-replay-metrics"
                items={[
                  { label: t("agents.status"), value: selectedRun.status || t("agents.value_absent") },
                  {
                    label: t("agents.stage"),
                    value: selectedRun.current_stage || t("agents.value_absent"),
                  },
                  {
                    label: t("agents.invocations"),
                    value: String(selectedRun.tool_invocations.length),
                  },
                  { label: t("agents.warnings"), value: String(selectedRun.warnings.length) },
                  { label: t("agents.blockers"), value: String(selectedRun.blockers.length) },
                  {
                    label: t("agents.evidence_deps"),
                    value: String(selectedRun.evidence_dependencies.length),
                  },
                ]}
                // A replay's headline numbers are evidence only with the instant they were
                // taken: the run's own creation time is reported under the strip.
                asOf={
                  selectedRun.created_at
                    ? `${t("agents.run_as_of")} ${formatAgentTimestamp(selectedRun.created_at)}`
                    : undefined
                }
              />
              <div className="agents-fact-grid">
                <div className="agents-fact">
                  <span className="agents-fact-key">{t("agents.objective")}</span>
                  <span className="agents-fact-value">{selectedRun.user_objective}</span>
                </div>
                <div className="agents-fact">
                  <span className="agents-fact-key">{t("agents.profile")}</span>
                  <span className="agents-fact-value">{selectedRun.agent_profile}</span>
                </div>
                <div className="agents-fact">
                  <span className="agents-fact-key">{t("agents.model")}</span>
                  <span className="agents-fact-value">
                    {selectedRun.model_provider}/{selectedRun.model_id}
                  </span>
                </div>
                <div className="agents-fact">
                  <span className="agents-fact-key">{t("agents.run_started_at")}</span>
                  <span className="agents-fact-value">
                    {formatAgentTimestamp(selectedRun.started_at) || t("agents.value_absent")}
                  </span>
                </div>
                <div className="agents-fact agents-fact-wide">
                  <span className="agents-fact-key">{t("agents.blockers")}</span>
                  <span className="agents-fact-value">
                    {selectedBlockers.length > 0
                      ? <AgentIssueList rows={selectedBlockers} t={t} />
                      : t("agents.value_absent")}
                  </span>
                </div>
                <div className="agents-fact agents-fact-wide">
                  <span className="agents-fact-key">{t("agents.warnings")}</span>
                  <span className="agents-fact-value">
                    {selectedWarnings.length > 0
                      ? <AgentIssueList rows={selectedWarnings} t={t} />
                      : t("agents.value_absent")}
                  </span>
                </div>
              </div>

              <AgentArtifactChain replay={selectedRun} t={t} />

              <AgentReviewGate
                gate={gate}
                state={confirmation}
                reviewerIdentity={reviewerIdentity}
                t={t}
                onConfirm={(decision, note) => {
                  void confirmReviewPack(decision, note);
                }}
              />
            </div>
          )}
        </div>
      )}
      </div>
    </div>
  );
}
