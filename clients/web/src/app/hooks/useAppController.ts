import { useTranslation } from "react-i18next";
import { useApiStore } from "@/stores/api";
import { useThemeStore } from "@/stores/theme";
import { usePortfolioDecisionModel } from "@/app/model/usePortfolioDecisionModel";
import { useCockpitControls } from "./useCockpitControls";
import { useContractEditor } from "./useContractEditor";
import { useGlossaryExplorer } from "./useGlossaryExplorer";
import { useReviewAnalysis } from "./useReviewAnalysis";
import { useSourceCenterController } from "./useSourceCenterController";
import { useWorkspaceNavigation } from "./useWorkspaceNavigation";
import { useWorkspaceRuntime } from "./useWorkspaceRuntime";

export function useAppController() {
  const { t, i18n } = useTranslation();
  const api = useApiStore();
  const theme = useThemeStore();
  const navigation = useWorkspaceNavigation();
  const controls = useCockpitControls();
  const contractEditor = useContractEditor(t);

  useWorkspaceRuntime({
    activeWorkspace: navigation.activeWorkspace,
    fetchWorkspace: api.fetchWorkspace,
    refreshMarketData: api.refreshMarketData,
    refreshMonitoring: api.refreshMonitoring,
  });

  const portfolio = usePortfolioDecisionModel({
    api,
    contract: contractEditor.contract,
    gasDay: controls.gasDay,
    deliveryProduct: controls.deliveryProduct,
    t,
  });
  const review = useReviewAnalysis(i18n.language, portfolio.portfolioResources);
  const glossary = useGlossaryExplorer({
    glossaryTerms: api.glossaryTerms,
    fetchGlossaryContext: api.fetchGlossaryContext,
    language: i18n.language,
  });
  const sources = useSourceCenterController({
    sources: api.sources,
    credentialProviders: api.credentialProviders,
    sourcePostureCategories: api.endpointMeta.sources?.source_posture_summary?.categories,
    saveProviderCredential: api.saveProviderCredential,
    testProviderConnection: api.testProviderConnection,
    language: i18n.language,
    t,
  });

  return {
    t,
    i18n,
    api,
    theme,
    navigation,
    controls,
    contractEditor,
    portfolio,
    review,
    glossary,
    sources,
  };
}

export type AppController = ReturnType<typeof useAppController>;
