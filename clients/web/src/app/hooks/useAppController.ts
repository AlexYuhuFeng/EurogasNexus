import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import {
  useMarketViewPreference,
  useSelectionContext,
  useTraderContext,
} from "@/app/context";
import { useApiStore } from "@/stores/api";
import { startWarmUp, stopWarmUp } from "@/app/data/warmUp";
import { warmUpSteps } from "@/app/data/warmUpSteps";
import { useThemeStore } from "@/stores/theme";
import { usePortfolioDecisionModel } from "@/app/model/usePortfolioDecisionModel";
import { useCockpitControls } from "./useCockpitControls";
import { useContractEditor } from "./useContractEditor";
import { useGlossaryExplorer } from "./useGlossaryExplorer";
import { glossaryMapPlace, isEntityTerm } from "@/app/model/glossaryEntry";
import { useIdentitySignal } from "./useIdentitySignal";
import { useReviewAnalysis } from "./useReviewAnalysis";
import { useSourceCenterController } from "./useSourceCenterController";
import { useWorkspaceNavigation } from "./useWorkspaceNavigation";
import { useWorkspaceRuntime } from "./useWorkspaceRuntime";

export function useAppController() {
  const { t, i18n } = useTranslation();
  const api = useApiStore();
  const theme = useThemeStore();
  const navigation = useWorkspaceNavigation();
  const trader = useTraderContext();
  const selection = useSelectionContext();
  // The market view lives here, above the shell and the cockpit, because both read it: the
  // cockpit renders the task and the shell keys its layout class on it. Resolving it in the
  // cockpit alone left the shell guessing from the URL, and a second resolution would be a
  // second copy of the same per-principal preference.
  const marketView = useMarketViewPreference({
    search: window.location.search,
    activeWorkspace: navigation.activeWorkspace,
    principalId: api.currentUser?.principal_id ?? null,
  });
  const controls = useCockpitControls();
  // The editor receives the store's governed-save action and its feedback reset: the hook
  // folds the server's refreshed edit lease and preserved notes into the draft it owns, and
  // clears the previous draft's save notice when the editor moves to another one. The
  // principal id scopes the draft's persisted-payment-terms carrier to the identity session
  // that read it, so a sign-out or switch cannot present the previous session's declaration.
  const contractEditor = useContractEditor(
    t,
    api.saveDraftContract,
    api.clearContractSaveFeedback,
    api.currentUser?.principal_id ?? null,
  );

  // Identity resolution is published for the desktop shell (window signal).
  useIdentitySignal(api.authState, api.currentUser?.principal_id ?? null);

  // Once the workspace batch has answered, the heavy reads of the user's other tabs are asked for
  // one at a time while the browser is idle, so the server holds them when a tab is first opened
  // (app/data/warmUp.ts). Sign-out or another principal stops it.
  const warmPrincipal = api.authState === "authenticated" ? api.currentUser?.principal_id ?? null : null;
  const warmReady = warmPrincipal !== null && api.workspaceLoadsCommitted > 0;
  useEffect(() => {
    if (warmPrincipal === null) {
      stopWarmUp();
      return;
    }
    if (!warmReady) return;
    void startWarmUp(warmPrincipal, useApiStore.getState().currentUser?.permissions, warmUpSteps(i18n.language));
    // The language at the start is enough: a later change reads its own catalogue on the page.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [warmPrincipal, warmReady]);

  useWorkspaceRuntime({
    authState: api.authState,
    activeWorkspace: navigation.activeWorkspace,
    streamingActive: api.streamingActive,
    bootstrapIdentity: api.bootstrapIdentity,
    fetchWorkspace: api.fetchWorkspace,
    refreshMarketData: api.refreshMarketData,
    refreshMonitoring: api.refreshMonitoring,
  });

  const portfolio = usePortfolioDecisionModel({
    api,
    contract: contractEditor.contract,
    gasDay: trader.gasDay,
    deliveryProduct: trader.deliveryProduct,
    hubId: trader.hubId,
    selectedResourceId: selection.resourceId,
    selectedRouteId: selection.routeId,
    t,
  });
  // The report run takes the interface language and the snapshot it cites; the portfolio's
  // resource list is not an input, because the report is not scoped by a selection.
  const review = useReviewAnalysis(i18n.language, api.reviewSnapshotId);
  const glossary = useGlossaryExplorer({
    glossaryTerms: api.glossaryTerms,
    fetchGlossaryContext: api.fetchGlossaryContext,
    language: i18n.language,
    active: navigation.activeWorkspace === "glossary",
    locationRevision: navigation.locationRevision,
    // Only an entry that names an object (a hub, a venue, a point) reads figures.
    needsContext: (term) => isEntityTerm(term, glossaryMapPlace(term, api.nodes)),
  });
  const sources = useSourceCenterController({
    sources: api.sources,
    credentialProviders: api.credentialProviders,
    sourcePostureCategories: api.endpointMeta.sources?.source_posture_summary?.categories,
    saveProviderCredential: api.saveProviderCredential,
    testProviderConnection: api.testProviderConnection,
    credentialConnection: api.credentialConnection,
    // The Source Center's own read state: the batch's failure record for the sources endpoint,
    // whether a pass has committed this session, and the bounded retry's bookkeeping. The surface
    // renders a count only for a committed reading.
    registryRead: {
      loading: api.workspaceLoading,
      committedPasses: api.workspaceLoadsCommitted,
      error: api.endpointErrors.sources,
      errorCode: api.endpointErrorCodes.sources,
      retryBusy: api.endpointRetryBusy,
      retryAttempts: api.endpointRetryAttempts,
      retryLastAttemptAtUtc: api.endpointRetryLastAttemptAtUtc,
    },
    retryFailedWorkspaceEndpoints: api.retryFailedWorkspaceEndpoints,
    language: i18n.language,
    t,
  });

  return {
    t,
    i18n,
    api,
    theme,
    navigation,
    marketView,
    traderContext: trader,
    selection,
    controls,
    contractEditor,
    portfolio,
    review,
    glossary,
    sources,
  };
}

export type AppController = ReturnType<typeof useAppController>;
