import { useEffect, useState } from "react";
import { PanelHeader, WorkspaceHeader } from "@/components/ui";
import { ScenarioWorkspace } from "@/components/ScenarioWorkspace";
import { ReviewWorkspace } from "@/components/ReviewWorkspace";
import { ReviewContextStrip } from "@/components/ReviewContextStrip";
import type { AppController } from "@/app/hooks/useAppController";
import { warningLabel } from "@/app/warningLabel";
import { CommercialWarningList } from "@/components/CommercialWarningList";
import { DecisionCasePanel } from "@/components/DecisionCasePanel";
import { inspectorSubjectFor } from "@/app/model/inspectorDetail";
import {
  analysisSnapshotReadiness,
  snapshotContextFrom,
} from "@/app/model/analysisSnapshotModel";
import { useInspectorStore } from "@/stores/inspector";
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
        <PanelHeader
          title={t("decision.preflight")}
          meta={blockers.length === 0 ? t("decision.ready") : `${blockers.length} ${t("portfolio.warnings")}`}
        />
        <p className="panel-copy">{t("decision.preflight_help")}</p>
        {blockers.length === 0 ? (
          <span className="status-badge status-complete">{t("decision.ready")}</span>
        ) : (
          <ul className="commercial-warning-list">
            {blockers.map((blocker) => <li key={blocker}>{warningLabel(blocker, t)}</li>)}
          </ul>
        )}
      </section>
      <section className="workspace-panel">
        <PanelHeader title={t("decision.allocations")} meta={String(allocations.length)} />
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
        <PanelHeader
          title={t("decision.binding_constraints")}
          meta={String(portfolio.commercialDiagnostics.length)}
        />
        <CommercialWarningList
          items={portfolio.commercialDiagnostics}
          t={t}
          emptyLabel={t("decision.no_binding")}
        />
      </section>
      <section className="workspace-panel">
        <PanelHeader title={t("decision.unallocated_reasons")} meta={String(unallocatedReasons.length)} />
        {unallocatedReasons.length === 0 ? (
          <p className="muted">{t("decision.fully_allocated")}</p>
        ) : (
          <ul className="commercial-warning-list">
            {unallocatedReasons.map((reason) => <li key={reason}>{reason}</li>)}
          </ul>
        )}
      </section>
      <section className="workspace-panel">
        <PanelHeader title={t("decision.handoffs")} />
        <div className="commercial-handoff-actions">
          <button type="button" onClick={() => navigation.openWorkspace("review")}>{t("decision.open_review")}</button>
          <button type="button" onClick={() => navigation.openWorkspace("market")}>{t("decision.inspect_market")}</button>
        </div>
      </section>
    </div>
  );
}

export function DecisionWorkspace({ controller }: { controller: AppController }) {
  const { t, api, portfolio, review, selection, i18n, contractEditor, navigation, traderContext } = controller;
  const inspector = useInspectorStore();
  const [task, setTask] = useState<DecisionTask>(() =>
    decisionTaskFromLocation(window.location.search),
  );

  useEffect(() => {
    setTask(decisionTaskFromLocation(window.location.search));
  }, [controller.navigation.locationRevision]);

  // Wave 5: the review surface reads its own projection when it opens. Resolving review
  // evidence is per-entity work, so it belongs here rather than on every workspace load;
  // the store coalesces repeat opens through the review lane.
  useEffect(() => {
    if (task !== "review") return;
    void api.fetchReviewContext();
    // The reproducibility references a report can cite are only needed here, so the read is
    // task-scoped rather than part of the workspace startup batch.
    void api.fetchAnalysisSnapshots();
  }, [api, task]);

  function openTask(next: DecisionTask) {
    setTask(next);
    navigation.openWorkspace(next === "review" ? "review" : "scenario", next);
  }

  const tabs = DECISION_TASKS.map((id) => ({ id, label: t(`decision.task.${id}`) }));

  // Action geography (`app/experience/actionGeography.ts`): running the pool optimiser is the
  // primary act of the Optimize task - a `compute` consequence - so it sits in the
  // workspace's single primary slot instead of inside the panel it reports on. The panel
  // keeps the preflight verdict and the allocations the run produced; the action that
  // starts a run is not panel furniture.
  const primaryAction =
    task === "optimize" ? (
      <button
        type="button"
        disabled={!portfolio.canRunPoolOptimizer}
        onClick={portfolio.optimizeResourcePoolForCurrentContext}
      >
        {t("home.optimize_pool")}
      </button>
    ) : undefined;

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
        primaryAction={primaryAction}
        onActivate={openTask}
      />
      <div id="decision-task-panel">
        {task === "review" && <ReviewContextStrip projection={api.reviewContext} t={t} />}
        {task === "scenario" && (
          <ScenarioWorkspace
            routeCandidates={api.routeCandidates}
            routeEconomics={portfolio.scenarioRouteEconomics}
            routeRecommendation={api.routeRecommendation}
            contract={contractEditor.contract}
            canCompareRoutes={portfolio.hasPortfolioResources && portfolio.saleOptions.length > 0}
            poolInputBlockers={portfolio.poolInputBlockers}
            resourcePoolResult={api.resourcePoolResult}
            saleOptionById={portfolio.saleOptionById}
            carriedRouteId={selection.routeId}
            contextMismatch={portfolio.optimizerContextMismatch}
            t={t}
            updateContractNumber={contractEditor.updateContractNumber}
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
            analysisResult={api.analysisResult}
            language={i18n.language}
            reviewDecisions={api.reviewDecisions}
            reviewProjection={api.reviewContext}
            reviewMessage={api.reviewMessage}
            latestStrategyRunId={api.strategyRuns[0]?.run_id ?? null}
            carriedStrategyRunId={selection.strategyRunId}
            analysisSnapshots={api.analysisSnapshots}
            analysisSnapshotSource={api.analysisSnapshotSource}
            reviewSnapshotId={api.reviewSnapshotId}
            snapshotReadiness={analysisSnapshotReadiness({
              context: snapshotContextFrom({
                workspace: "review",
                task,
                gas_day: traderContext.gasDay,
                product: traderContext.deliveryProduct,
                hub: traderContext.hubId,
                strategy_run_id: selection.strategyRunId ?? "",
              }),
              runtimeDbReady:
                api.runtimeDb?.database_url_present === true && api.runtimeDb.connectivity.ok,
              recording: api.loading,
            })}
            snapshotMessage={api.snapshotMessage}
            onRecordSnapshot={() =>
              void api.recordAnalysisSnapshot(
                {
                  workspace: "review",
                  task,
                  gas_day: traderContext.gasDay,
                  product: traderContext.deliveryProduct,
                  hub: traderContext.hubId,
                  strategy_run_id: selection.strategyRunId ?? "",
                },
                api.runtimeDb?.database_url_present === true && api.runtimeDb.connectivity.ok,
              )
            }
            onSelectSnapshot={api.setReviewSnapshotId}
            t={t}
            onGenerateReport={() => api.generatePortfolioReport(review.analysisPayload)}
            onRecordDecision={api.recordReviewDecision}
            onInspectEvidence={(ref, label) => {
              // Wave 9: the review page declares decision-evidence, so the decision history
              // can hand the evidence behind a decision to the canonical Inspector.
              const subject = inspectorSubjectFor("decision-evidence", ref, label, "review");
              if (subject) inspector.open(subject);
            }}
          />
        )}
        {task === "review" && (
          <DecisionCasePanel
            gasDay={traderContext.gasDay}
            deliveryProduct={traderContext.deliveryProduct}
            hubId={traderContext.hubId}
            routeId={selection.routeId}
            strategyRunId={selection.strategyRunId ?? api.strategyRuns[0]?.run_id ?? null}
            // The Decision Case chain cites AI findings and challenges, so the run this
            // identity last completed is offered as evidence by reference.
            analysisId={api.analysisResult?.analysis_id ?? null}
            t={t}
          />
        )}
      </div>
    </div>
  );
}
