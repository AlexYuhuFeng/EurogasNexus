import { useModeHeader } from "@/app/navigation/useModeHeader";
import { PRODUCT_MODES } from "@/app/navigation/modeNavigation";
import { tradingContextControlsFor } from "@/components/TradingContextControls";
import { useEffect, useMemo, useState } from "react";
import { Segmented, WorkspaceHeader } from "@/components/ui";
import { ReviewWorkspace } from "@/components/ReviewWorkspace";
import { ReviewContextStrip } from "@/components/ReviewContextStrip";
import type { AppController } from "@/app/hooks/useAppController";
import { DecisionCasePanel } from "@/components/DecisionCasePanel";
import { DayBoardPanel } from "@/components/decision/DayBoardPanel";
import { NominationWindowPanel } from "@/components/decision/NominationWindowPanel";
import { StorageDispatchPanel } from "@/components/decision/StorageDispatchPanel";
import {
  useNominationAssessment,
  useOptimizationRunRecord,
  useStorageDispatchAssessment,
} from "@/app/model/useOptimizationAssessment";
import { isIdentityGateOpen } from "@/stores/workspaceLoading";
import { dayBoardModel } from "@/app/model/dayBoardModel";
import { reviewIsUsable } from "@/app/model/reviewContextModel";
import { inspectorSubjectFor } from "@/app/model/inspectorDetail";
import {
  analysisSnapshotReadiness,
  snapshotContextFrom,
} from "@/app/model/analysisSnapshotModel";
import { useInspectorStore } from "@/stores/inspector";
import {
  decisionTaskFromLocation,
  type DecisionTask,
} from "@/app/model/commercialWorkflowModel";
import "./commercial-workflow.css";
import { PanelHelp } from "@/components/ui/PanelHelp";

export function DecisionWorkspace({ controller }: { controller: AppController }) {
  const { t, api, portfolio, review, selection, i18n, navigation, traderContext } = controller;
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
  // The gate is a dependency, and that is the correction of a real defect: the store refuses a read
  // while the identity gate is closed, and on a fresh page load this effect ran *before* the
  // session resolved, so the read was dropped and never retried - the board said "the nomination
  // windows were not read" and the register "has not been read" for a user who navigated normally,
  // while the endpoints themselves answered 200 with data. Depending on the gate (a primitive, so
  // no re-ask storm) makes the read happen when it can succeed.
  const fetchNominationWindows = api.fetchNominationWindows;
  const fetchReviewContext = api.fetchReviewContext;
  const identityReady = isIdentityGateOpen(api.authState);
  useEffect(() => {
    if (!identityReady) return;
    void fetchNominationWindows();
    void fetchReviewContext();
  }, [identityReady, fetchNominationWindows, fetchReviewContext]);

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

  // Decision Center is no longer an area (WF-05): Review is a Deals task; Nominations and Storage
  // are the two views of Book → Planning, behind one switch. The header is the row of the task's
  // mode. Scenario, Optimise and the desk replay left the product with CP-00.
  const mode = useModeHeader(navigation.activeWorkspace, task, navigation.openWorkspace, t);

  // Action geography (`app/experience/actionGeography.ts`): assessing the nominations or the
  // storage dispatch is the primary act of the Planning view on screen - a `compute`
  // consequence - so it occupies the workspace's single primary slot.
  const primaryAction =
    task === "nomination" ? (
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
        title={mode.title ?? t("nav.mode.deals")}
        taskLabel={t(`decision.task.${task}`)}
        idPrefix={`${mode.modeId ?? "deals"}-task`}
        tabs={mode.tabs}
        activeId={mode.activeId}
        panelId="decision-task-panel"
        tabLabel={mode.tabLabel}
        purpose={mode.purpose}
        tabsClassName="commercial-task-tabs"
        primaryAction={primaryAction}
        onActivate={(id) => {
          // A task on this page switches in place; one on another page opens it.
          const target = PRODUCT_MODES.flatMap((item) => item.tasks).find((item) => item.id === id && item.page === "scenario");
          if (target?.pageTask) openTask(target.pageTask as DecisionTask);
          else mode.onActivate(id);
        }}
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
        {task === "review" ? (
          <ReviewContextStrip
            projection={api.reviewContext}
            t={t}
            controls={tradingContextControlsFor(traderContext, t)}
          />
        ) : (
          // The other tasks have no projection line: the controls stand on their own.
          <div className="projection-context">{tradingContextControlsFor(traderContext, t)}</div>
        )}
        {task !== "review" && (
          <Segmented
            label={t("nav.mode.book.planning")}
            className="planning-switch"
            options={[
              { value: "nomination", label: t("nav.mode.book.nominations") },
              { value: "dispatch", label: t("nav.mode.book.storage") },
            ]}
            value={task}
            onChange={(next) => openTask(next)}
          />
        )}
        {task === "nomination" && (
          <NominationWindowPanel t={t} assessment={nomination} record={optimizationRun} />
        )}
        {task === "dispatch" && (
          <StorageDispatchPanel t={t} assessment={dispatch} record={optimizationRun} />
        )}
        {task === "review" && (
          <DecisionCasePanel
            canPrepare={Boolean(api.currentUser?.permissions.includes("scenario.create"))}
            canAssess={Boolean(api.currentUser?.permissions.includes("review.record"))}
            selectedCaseId={selection.decisionCaseId}
            onSelectCaseId={selection.setDecisionCaseId}
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
        {task === "review" && (
          /* The raw pool payload is handed to the review panel only so it can state that a stale
             run is being withheld; the panel gates its allocations and evidence pack with the
             same provenance flag (`poolResultContextMismatch`) and never presents the raw
             payload as current evidence. */
          <details className="review-supporting-tools" open={Boolean(selection.strategyRunId)}>
          <summary>{t("review.supporting_tools")}</summary>
          <PanelHelp text={t("review.supporting_tools_help")} label={t("panel.how_to_read")} />
          <ReviewWorkspace
            allocations={portfolio.poolAllocations}
            saleOptionById={portfolio.saleOptionById}
            reviewWarnings={portfolio.reviewWarnings}
            resourcePoolResult={api.resourcePoolResult}
            poolResultContextMismatch={portfolio.optimizerContextMismatch}
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
          </details>
        )}

      </div>
    </div>
  );
}
