import { useEffect, useMemo, useState } from "react";
import { PanelHeader, WorkspaceHeader } from "@/components/ui";
import { ScenarioWorkspace } from "@/components/ScenarioWorkspace";
import { ReviewWorkspace } from "@/components/ReviewWorkspace";
import { ReviewContextStrip } from "@/components/ReviewContextStrip";
import type { AppController } from "@/app/hooks/useAppController";
import { warningLabel } from "@/app/warningLabel";
import { CommercialWarningList } from "@/components/CommercialWarningList";
import { DecisionCasePanel } from "@/components/DecisionCasePanel";
import { DayBoardPanel } from "@/components/decision/DayBoardPanel";
import { NominationWindowPanel } from "@/components/decision/NominationWindowPanel";
import { StorageDispatchPanel } from "@/components/decision/StorageDispatchPanel";
import {
  useNominationAssessment,
  useOptimizationRunRecord,
  useStorageDispatchAssessment,
} from "@/app/model/useOptimizationAssessment";
import { dayBoardModel } from "@/app/model/dayBoardModel";
import { reviewIsUsable } from "@/app/model/reviewContextModel";
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
  // Register C14/D8: the desk's two assessment engines. Each owns its own draft, and each is the
  // primary act of its own task, so the header's single slot starts the run the task configures.
  const nomination = useNominationAssessment();
  const dispatch = useStorageDispatchAssessment();
  const optimizationRun = useOptimizationRunRecord();

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

  // The day board (the desk's clock) is the workspace's, not one tab's: the deadline strip is
  // mounted above every task, so it has to be read when the workspace mount happens rather than
  // when a task is opened. Both reads coalesce in the store, so opening the review task on top of
  // this mount asks the same question once - and the register behind "no decision recorded" is
  // only answerable from the review projection, which is why the board asks for it too.
  //
  // The dependencies are the store's own actions rather than the whole controller state: the state
  // object is replaced on every write, so depending on it would re-ask on every store update.
  const fetchNominationWindows = api.fetchNominationWindows;
  const fetchReviewContext = api.fetchReviewContext;
  useEffect(() => {
    void fetchNominationWindows();
    void fetchReviewContext();
  }, [fetchNominationWindows, fetchReviewContext]);

  /**
   * The browser clock the countdowns are measured against, refreshed once a minute.
   *
   * The declared instants do not tick - they are the API's own resolution - but a countdown
   * captured at mount would keep claiming the same time remaining for as long as the workspace
   * stays open, which on a deadline board is worse than no countdown at all.
   */
  const [dayBoardNow, setDayBoardNow] = useState(() => new Date().toISOString());
  useEffect(() => {
    const timer = setInterval(() => setDayBoardNow(new Date().toISOString()), 60_000);
    return () => clearInterval(timer);
  }, []);

  // The composition lives here, not in the panel: the panel renders the three sections and claims
  // nothing of its own, so the same model is checked by the model tests without a renderer.
  const dayBoard = useMemo(
    () =>
      dayBoardModel({
        windowsRead: api.nominationWindowsRead,
        windowsMeta: api.nominationWindowsMeta,
        opportunities: api.intradayOpportunities,
        reviewDecisions: api.reviewDecisions,
        // "No decision is recorded" is a claim the register has to support: a payload whose
        // decisions slice the backend did not serve leaves the previous decisions in the store, so
        // the flag comes from the projection the store judged usable rather than from the list.
        reviewRegisterRead: reviewIsUsable(api.reviewContext),
        monitoringSummary: api.monitoringSummary,
        monitoringMeta: api.endpointMeta.monitoringSummary ?? null,
        monitoringAlerts: api.monitoringAlerts,
        now: dayBoardNow,
      }),
    [
      api.nominationWindowsRead,
      api.nominationWindowsMeta,
      api.intradayOpportunities,
      api.reviewDecisions,
      api.reviewContext,
      api.monitoringSummary,
      api.endpointMeta.monitoringSummary,
      api.monitoringAlerts,
      dayBoardNow,
    ],
  );

  function openTask(next: DecisionTask) {
    setTask(next);
    navigation.openWorkspace(next === "review" ? "review" : "scenario", next);
  }

  const tabs = DECISION_TASKS.map((id) => ({ id, label: t(`decision.task.${id}`) }));

  // Action geography (`app/experience/actionGeography.ts`): running the pool optimiser is the
  // primary act of the Optimize task and comparing route options is the primary act of the
  // Scenario task - both `compute` consequences - so each occupies the workspace's single
  // primary slot instead of sitting inside the panel it reports on. The panels keep the
  // preflight verdicts and the results the runs produced; the actions that start a run are not
  // panel furniture.
  const canCompareRoutes =
    portfolio.hasPortfolioResources && portfolio.saleOptions.length > 0;
  const primaryAction =
    task === "optimize" ? (
      <button
        type="button"
        disabled={!portfolio.canRunPoolOptimizer}
        onClick={portfolio.optimizeResourcePoolForCurrentContext}
      >
        {t("home.optimize_pool")}
      </button>
    ) : task === "scenario" ? (
      <button
        type="button"
        disabled={!canCompareRoutes}
        title={canCompareRoutes ? t("economics.compare_hint") : t("economics.compare_blocked")}
        onClick={portfolio.recommendRouteAllocationForCurrentContext}
      >
        {t("economics.compare")}
      </button>
    ) : task === "nomination" ? (
      <button
        type="button"
        disabled={!nomination.readiness.canRun || nomination.busy}
        title={t(nomination.readiness.firstBlockerKey ?? "decision.nomination.ready")}
        onClick={() => void nomination.run()}
      >
        {t("decision.nomination.assess")}
      </button>
    ) : task === "dispatch" ? (
      <button
        type="button"
        disabled={!dispatch.readiness.canRun || dispatch.busy}
        title={t(dispatch.readiness.firstBlockerKey ?? "decision.dispatch.ready")}
        onClick={() => void dispatch.run()}
      >
        {t("decision.dispatch.assess")}
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
        {/* The desk's clock sits above the tabs' panels: it is the workspace's, and burying it in
            one task would hide the deadline from a trader standing in another. It navigates - it
            computes nothing and records nothing - so it takes no primary action slot. */}
        <DayBoardPanel
          t={t}
          model={dayBoard}
          onOpenTask={openTask}
          onOpenAlerts={() => navigation.openWorkspace("market")}
        />
        {task === "review" && <ReviewContextStrip projection={api.reviewContext} t={t} />}
        {task === "scenario" && (
          <ScenarioWorkspace
            routeCandidates={api.routeCandidates}
            routeEconomics={portfolio.scenarioRouteEconomics}
            routeRecommendation={api.routeRecommendation}
            contract={contractEditor.contract}
            poolInputBlockers={portfolio.poolInputBlockers}
            resourcePoolResult={api.resourcePoolResult}
            saleOptionById={portfolio.saleOptionById}
            carriedRouteId={selection.routeId}
            contextMismatch={portfolio.optimizerContextMismatch}
            t={t}
            updateContractNumber={contractEditor.updateContractNumber}
          />
        )}
        {task === "optimize" && <OptimizeWorkspace controller={controller} />}
        {task === "nomination" && (
          <NominationWindowPanel t={t} assessment={nomination} record={optimizationRun} />
        )}
        {task === "dispatch" && (
          <StorageDispatchPanel t={t} assessment={dispatch} record={optimizationRun} />
        )}
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
