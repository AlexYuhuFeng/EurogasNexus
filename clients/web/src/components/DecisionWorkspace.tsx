import { useEffect, useState } from "react";
import { WorkspaceHeader } from "@/components/ui";
import { ScenarioWorkspace } from "@/components/ScenarioWorkspace";
import { ReviewWorkspace } from "@/components/ReviewWorkspace";
import type { AppController } from "@/app/hooks/useAppController";
import { warningLabel } from "@/app/warningLabel";
import {
  DECISION_TASKS,
  decisionTaskFromLocation,
  type DecisionTask,
} from "@/app/model/commercialWorkflowModel";
import "./commercial-workflow.css";

function money(value: number | null | undefined, suffix = ""): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return `GBP ${Math.round(value).toLocaleString()}${suffix}`;
}

function OptimizeWorkspace({ controller }: { controller: AppController }) {
  const { api, portfolio, t, navigation } = controller;
  const result = api.resourcePoolResult;
  const allocations = portfolio.poolAllocations;
  const blockers = portfolio.poolInputBlockers;
  const unallocated = result?.total_unallocated_mwh_per_day ?? 0;
  const unallocatedReasons = blockers.length
    ? blockers
    : unallocated > 0
      ? ["NO_ECONOMIC_DESTINATION_OR_CONSTRAINT_BOUND"]
      : [];

  return (
    <div className="commercial-overview">
      <section className="commercial-metric-strip" aria-label={t("decision.optimize")}>
        <span><small>{t("portfolio.allocated")}</small><strong>{result?.total_allocated_mwh_per_day?.toLocaleString() ?? "n/a"} MWh/d</strong></span>
        <span><small>{t("portfolio.unallocated")}</small><strong>{unallocated.toLocaleString()} MWh/d</strong></span>
        <span><small>{t("portfolio.net_indicative")}</small><strong>{money(result?.total_net_pnl_gbp_per_day, "/d")}</strong></span>
        <span><small>{t("portfolio.status")}</small><strong>{result?.status ?? t("home.pending")}</strong></span>
        <span><small>{t("portfolio.warnings")}</small><strong>{result?.warnings.length ?? 0}</strong></span>
      </section>
      <section className="workspace-panel">
        <h2>{t("decision.preflight")}</h2>
        {blockers.length === 0 ? (
          <span className="status-badge status-complete">{t("decision.ready")}</span>
        ) : (
          <ul className="commercial-warning-list">
            {blockers.map((blocker) => <li key={blocker}>{warningLabel(blocker, t)}</li>)}
          </ul>
        )}
        <button
          type="button"
          disabled={!portfolio.canRunPoolOptimizer}
          onClick={portfolio.optimizeResourcePoolForCurrentContext}
        >
          {t("home.optimize_pool")}
        </button>
      </section>
      <section className="workspace-panel">
        <h2>{t("decision.allocations")}</h2>
        <div className="data-table">
          <div className="data-table-row header five">
            <span>{t("portfolio.resource")}</span><span>{t("portfolio.destination")}</span>
            <span>{t("portfolio.quantity")}</span><span>{t("portfolio.margin")}</span>
            <span>{t("portfolio.pnl")}</span>
          </div>
          {allocations.map((allocation) => {
            const option = portfolio.saleOptionById.get(allocation.option_id);
            return (
              <div key={`${allocation.resource_id}-${allocation.option_id}`} className="data-table-row five">
                <strong>{allocation.resource_id}</strong>
                <span>{option?.label ?? allocation.option_id}</span>
                <span>{allocation.allocated_quantity_mwh_per_day.toLocaleString()} MWh/d</span>
                <span>{allocation.net_margin_gbp_mwh.toFixed(2)} GBP/MWh</span>
                <span>{money(allocation.net_pnl_gbp_per_day)}</span>
              </div>
            );
          })}
          {allocations.length === 0 && (
            <div className="data-table-row five"><span>{t("home.pending")}</span><span>n/a</span><span>n/a</span><span>n/a</span><span>n/a</span></div>
          )}
        </div>
      </section>
      <section className="workspace-panel">
        <h2>{t("decision.binding_constraints")}</h2>
        <div className="data-table">
          <div className="data-table-row header three">
            <span>{t("decision.constraint")}</span><span>{t("decision.state")}</span><span>{t("decision.evidence")}</span>
          </div>
          {blockers.map((blocker) => (
            <div key={blocker} className="data-table-row three">
              <strong>{blocker}</strong><span>BLOCKED</span><span>{blocker}</span>
            </div>
          ))}
          {(result?.warnings ?? []).map((warning) => {
            const label = warningLabel(warning, t);
            return (
              <div key={warning} className="data-table-row three">
                <strong>{label}</strong><span>WARN</span><span>{label}</span>
              </div>
            );
          })}
          {blockers.length === 0 && (result?.warnings.length ?? 0) === 0 && (
            <div className="data-table-row three"><span>{t("decision.no_binding")}</span><span>—</span><span>—</span></div>
          )}
        </div>
      </section>
      <section className="workspace-panel">
        <h2>{t("decision.unallocated_reasons")}</h2>
        {unallocatedReasons.length === 0 ? (
          <p className="muted">{t("decision.fully_allocated")}</p>
        ) : (
          <ul className="commercial-warning-list">
            {unallocatedReasons.map((reason) => <li key={reason}>{reason}</li>)}
          </ul>
        )}
      </section>
      <section className="workspace-panel">
        <h2>{t("decision.handoffs")}</h2>
        <div className="commercial-handoff-actions">
          <button type="button" onClick={() => navigation.openWorkspace("review")}>{t("decision.open_review")}</button>
          <button type="button" onClick={() => navigation.openWorkspace("market")}>{t("decision.inspect_market")}</button>
        </div>
      </section>
    </div>
  );
}

export function DecisionWorkspace({ controller }: { controller: AppController }) {
  const { t, api, portfolio, review, selection, i18n, contractEditor, navigation } = controller;
  const [task, setTask] = useState<DecisionTask>(() =>
    decisionTaskFromLocation(window.location.search),
  );

  useEffect(() => {
    setTask(decisionTaskFromLocation(window.location.search));
  }, [controller.navigation.locationRevision]);

  function openTask(next: DecisionTask) {
    setTask(next);
    navigation.openWorkspace(next === "review" ? "review" : "scenario", next);
  }

  const tabs = DECISION_TASKS.map((id) => ({ id, label: t(`decision.task.${id}`) }));

  return (
    <div className="commercial-workspace">
      <WorkspaceHeader
        title={t("nav.primary.decision")}
        taskLabel={t(`decision.task.${task}`)}
        idPrefix="decision-task"
        tabs={tabs}
        activeId={task}
        panelId="decision-task-panel"
        tabLabel={t("nav.primary.decision")}
        tabsClassName="commercial-task-tabs"
        onActivate={openTask}
      />
      <div id="decision-task-panel">
        {task === "scenario" && (
          <ScenarioWorkspace
            routeCandidates={api.routeCandidates}
            routeEconomics={portfolio.scenarioRouteEconomics}
            routeRecommendation={api.routeRecommendation}
            contract={contractEditor.contract}
            canRunPoolOptimizer={portfolio.canRunPoolOptimizer}
            canCompareRoutes={portfolio.hasPortfolioResources && portfolio.saleOptions.length > 0}
            poolInputBlockers={portfolio.poolInputBlockers}
            resourcePoolResult={api.resourcePoolResult}
            saleOptionById={portfolio.saleOptionById}
            carriedRouteId={selection.routeId}
            contextMismatch={portfolio.optimizerContextMismatch}
            t={t}
            updateContractNumber={contractEditor.updateContractNumber}
            onOptimize={portfolio.optimizeResourcePoolForCurrentContext}
            onCompare={portfolio.recommendRouteAllocationForCurrentContext}
          />
        )}
        {task === "optimize" && <OptimizeWorkspace controller={controller} />}
        {task === "review" && (
          <ReviewWorkspace
            allocations={portfolio.poolAllocations}
            saleOptionById={portfolio.saleOptionById}
            reviewWarnings={portfolio.reviewWarnings}
            resourcePoolResult={api.resourcePoolResult}
            analysisQuestion={review.analysisQuestion}
            invokeDeepSeek={review.invokeDeepSeek}
            analysisResult={api.analysisResult}
            language={i18n.language}
            reviewDecisions={api.reviewDecisions}
            reviewMessage={api.reviewMessage}
            latestStrategyRunId={api.strategyRuns[0]?.run_id ?? null}
            carriedStrategyRunId={selection.strategyRunId}
            t={t}
            onAnalysisQuestionChange={review.setAnalysisQuestion}
            onInvokeDeepSeekChange={review.setInvokeDeepSeek}
            onAnalyze={() => api.askAnalysis(review.analysisPayload)}
            onGenerateReport={() => api.generatePortfolioReport(review.analysisPayload)}
            onRecordDecision={api.recordReviewDecision}
          />
        )}
      </div>
    </div>
  );
}
