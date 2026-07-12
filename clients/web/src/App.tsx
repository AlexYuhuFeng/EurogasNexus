import { useEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent, FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { ContractWorkbench } from "@/components/ContractWorkbench";
import type {
  ContractNumberKey,
  ContractTextKey,
} from "@/components/ContractWorkbench";
import { GlossaryWiki } from "@/components/GlossaryWiki";
import { CapacityWorkspace } from "@/components/CapacityWorkspace";
import { MarketTerminal } from "@/components/MarketTerminal";
import { MarketPositioningWorkspace } from "@/components/MarketPositioningWorkspace";
import { ManualWorkspace } from "@/components/ManualWorkspace";
import { NetworkWorkspace } from "@/components/NetworkWorkspace";
import { ReviewWorkspace } from "@/components/ReviewWorkspace";
import { RuntimeWorkspace } from "@/components/RuntimeWorkspace";
import { ScenarioWorkspace } from "@/components/ScenarioWorkspace";
import { SettingsCenter } from "@/components/SettingsCenter";
import { SourceCenter } from "@/components/SourceCenter";
import { StrategyShadowRunTerminal } from "@/components/StrategyShadowRunTerminal";
import { WorkspaceTopBar } from "@/components/WorkspaceTopBar";
import { hydrateApiBaseUrlFromDesktopDeployment } from "@/api/client";
import type { UpstreamContractDTO } from "@/api/client";
import {
  buildHighlightedResourcePoolRoute,
  buildContractPayload,
  buildNodeIdByPointName,
  buildReviewWarnings,
  buildResourcePoolMapPaths,
  buildResourcePoolOptimizationRequest,
  buildRouteRecommendationRequest,
  buildRouteGeometryEdgesByRouteId,
  buildSourceCategoryCounts,
  buildSourcePostureRows,
  buildSourcesByCategory,
  buildSourceStats,
  buildStrategyScenario,
  buildWorkspaceLatestRows,
  cloneDefaultContractDraft,
  contractDraftFromRecord,
  contractRecordFromImportedFile,
  DEFAULT_GAS_DAY,
  filterSourcesByCategory,
  marketMatchesTradingContext,
  resolveNetworkGeometryState,
  SOURCE_CATEGORIES,
  sourceNextActionKey,
} from "@/app/index";
import type { ContractDraft } from "@/app/index";
import { useApiStore } from "@/stores/api";
import { useThemeStore } from "@/stores/theme";
import {
  coerceWorkspacePageId,
  DEFAULT_WORKSPACE_PAGE_ID,
  type WorkspacePageId,
} from "@/workspaceNavigation";
import "./styles/app.css";

type LiveMarkNumberKey = "bid_gbp_mwh" | "ask_gbp_mwh" | "last_gbp_mwh";
const MARKET_REFRESH_INTERVAL_MS = 15_000;
function workspaceFromLocation(): WorkspacePageId {
  if (typeof window === "undefined") return DEFAULT_WORKSPACE_PAGE_ID;
  const requestedWorkspace = new URLSearchParams(window.location.search).get("workspace");
  return coerceWorkspacePageId(requestedWorkspace, DEFAULT_WORKSPACE_PAGE_ID);
}

export default function App() {
  const { t, i18n } = useTranslation();
  const { mode, setMode } = useThemeStore();
  const {
    nodes,
    edges,
    sources,
    markets,
    screenOrders,
    pnlSnapshots,
    portfolioSummary,
    fxRates,
    flows,
    capacity,
    storage,
    lng,
    tsoAccess,
    routes,
    routeCandidates,
    tsoTariffs,
    upstreamContracts,
    resourcePoolOptions,
    endpointMeta,
    routeRecommendation,
    resourcePoolResult,
    glossaryTerms,
    glossaryContext,
    analysisResult,
    credentialProviders,
    runtimeDb,
    dataStatus,
    meta,
    marketLastUpdatedAtUtc,
    loading,
    error,
    credentialMessage,
    contractSaveMessage,
    fetchWorkspace,
    refreshMarketData,
    saveProviderCredential,
    saveDraftContract,
    recommendRouteAllocation,
    optimizeResourcePool,
    strategyResult,
    evaluateStrategyLab,
    fetchGlossaryContext,
    askAnalysis,
    generatePortfolioReport,
  } = useApiStore();
  const [activeLayers, setActiveLayers] = useState(["hubs"]);
  const [gasDay, setGasDay] = useState(DEFAULT_GAS_DAY);
  const [deliveryProduct, setDeliveryProduct] = useState("all");
  const [searchTerm, setSearchTerm] = useState("");
  const [credentialProvider, setCredentialProvider] = useState("");
  const [credentialLabel, setCredentialLabel] = useState("default");
  const [credentialValue, setCredentialValue] = useState("");
  const [sourceCategory, setSourceCategory] = useState("all");
  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null);
  const [glossaryQuery, setGlossaryQuery] = useState("");
  const [glossaryCategory, setGlossaryCategory] = useState("all");
  const [selectedGlossaryTerm, setSelectedGlossaryTerm] = useState<string | null>(null);
  const [glossaryDurationStart, setGlossaryDurationStart] = useState("2026-05-31T06:00");
  const [glossaryDurationEnd, setGlossaryDurationEnd] = useState("2026-06-01T06:00");
  const [analysisQuestion, setAnalysisQuestion] = useState("Summarize current portfolio PnL, route, market, and strategy status.");
  const [invokeDeepSeek, setInvokeDeepSeek] = useState(false);
  const [activeWorkspace, setActiveWorkspace] = useState<WorkspacePageId>(() => workspaceFromLocation());
  const contractImportRef = useRef<HTMLInputElement>(null);
  const lastAutoOptimizerSignatureRef = useRef<string | null>(null);
  const [contractImportMessage, setContractImportMessage] = useState<string | null>(null);
  const selectedCredentialProvider = useMemo(
    () => credentialProviders.find((provider) => provider.provider_id === credentialProvider),
    [credentialProvider, credentialProviders],
  );
  const [contract, setContract] = useState<ContractDraft>(() => cloneDefaultContractDraft());
  const [liveMark, setLiveMark] = useState({
    venue: "ICE OCM",
    hub: "NBP",
    product: "Within-day",
    bid_gbp_mwh: null as number | null,
    ask_gbp_mwh: null as number | null,
    last_gbp_mwh: null as number | null,
    mark_time_utc: new Date().toISOString(),
    source_system: "operator-draft-live-mark",
  });
  const portfolioResources = useMemo(() => {
    return resourcePoolOptions?.portfolio_resources ?? [];
  }, [resourcePoolOptions]);

  const hasPortfolioResources = portfolioResources.length > 0;

  const totalPoolVolume = useMemo(
    () => portfolioResources.reduce((total, resource) => total + resource.available_quantity_mwh_per_day, 0),
    [portfolioResources],
  );

  const saleOptions = useMemo(() => {
    return resourcePoolOptions?.sale_options ?? [];
  }, [resourcePoolOptions]);

  const saleOptionById = useMemo(
    () => new Map(saleOptions.map((option) => [option.option_id, option])),
    [saleOptions],
  );

  const resourcePoolOptimizationRequest = useMemo(
    () => buildResourcePoolOptimizationRequest(contract, portfolioResources, saleOptions, upstreamContracts),
    [contract, portfolioResources, saleOptions, upstreamContracts],
  );

  const contextMarkets = useMemo(
    () => markets.filter((observation) => marketMatchesTradingContext(observation, gasDay, deliveryProduct)),
    [deliveryProduct, gasDay, markets],
  );
  const contractPayload = useMemo(() => buildContractPayload(contract), [contract]);

  const strategyScenario = useMemo(
    () => buildStrategyScenario(contract, liveMark, contextMarkets, portfolioResources, fxRates),
    [contextMarkets, contract, liveMark, portfolioResources, fxRates],
  );

  useEffect(() => {
    let active = true;
    void hydrateApiBaseUrlFromDesktopDeployment().then(() => {
      if (active) fetchWorkspace();
    });
    return () => {
      active = false;
    };
  }, [fetchWorkspace]);

  useEffect(() => {
    if (activeWorkspace !== "market") return;
    void refreshMarketData();
    const intervalId = window.setInterval(() => {
      void refreshMarketData();
    }, MARKET_REFRESH_INTERVAL_MS);
    return () => window.clearInterval(intervalId);
  }, [activeWorkspace, refreshMarketData]);

  useEffect(() => {
    function syncWorkspaceFromUrl() {
      setActiveWorkspace(workspaceFromLocation());
    }
    window.addEventListener("popstate", syncWorkspaceFromUrl);
    return () => window.removeEventListener("popstate", syncWorkspaceFromUrl);
  }, []);

  async function onCredentialSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedCredentialProvider?.credential_required || !credentialValue.trim()) return;
    await saveProviderCredential(credentialProvider, credentialValue, credentialLabel || "default");
    setCredentialValue("");
  }

  const visibleGlossaryCategories = useMemo(
    () => Array.from(new Set(glossaryTerms.map((term) => term.category))).sort(),
    [glossaryTerms],
  );

  const visibleGlossaryTerms = useMemo(() => {
    const trimmed = glossaryQuery.trim();
    const query = trimmed.toLowerCase();
    return glossaryTerms
      .filter((term) => glossaryCategory === "all" || term.category === glossaryCategory)
      .filter((term) => {
        if (!query) return true;
        return (
          term.term.toLowerCase().includes(query) ||
          term.category.toLowerCase().includes(query) ||
          term.definition_en.toLowerCase().includes(query) ||
          term.definition_zh_cn.includes(trimmed) ||
          term.aliases.some((alias) => alias.toLowerCase().includes(query))
        );
      })
      .slice(0, 40);
  }, [glossaryCategory, glossaryQuery, glossaryTerms]);

  const selectedGlossaryTermRecord = useMemo(
    () =>
      visibleGlossaryTerms.find((term) => term.term === selectedGlossaryTerm) ??
      glossaryTerms.find((term) => term.term === selectedGlossaryTerm) ??
      visibleGlossaryTerms[0] ??
      glossaryTerms[0] ??
      null,
    [glossaryTerms, selectedGlossaryTerm, visibleGlossaryTerms],
  );

  function updateContractNumber(key: ContractNumberKey, value: string) {
    setContract((current) => ({ ...current, [key]: value === "" ? 0 : Number(value) }));
  }

  function updateContractText(key: ContractTextKey, value: string) {
    setContract((current) => ({ ...current, [key]: value }));
  }

  function loadPersistedContract(saved: UpstreamContractDTO) {
    setContract((current) => contractDraftFromRecord(saved as unknown as Record<string, unknown>, current));
    setContractImportMessage(`${saved.contract_id} ${t("contracts.loaded_for_edit")}`);
  }

  function resetContractDraft() {
    setContract(cloneDefaultContractDraft());
    setContractImportMessage(t("contracts.new_draft_loaded"));
  }

  async function importContractDraftFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const record = contractRecordFromImportedFile(file.name, await file.text());
      if (!record) throw new Error(t("contracts.import_invalid"));
      setContract((current) => contractDraftFromRecord(record, current));
      setContractImportMessage(`${file.name} ${t("contracts.import_loaded")}`);
    } catch (e) {
      setContractImportMessage(`${t("contracts.import_failed")}: ${String(e)}`);
    } finally {
      event.target.value = "";
    }
  }

  function updateLiveMarkNumber(key: LiveMarkNumberKey, value: string) {
    setLiveMark((current) => ({ ...current, [key]: value === "" ? null : Number(value) }));
  }

  function toggleLayer(layer: string) {
    setActiveLayers((current) =>
      current.includes(layer) ? current.filter((item) => item !== layer) : [...current, layer],
    );
  }

  function openWorkspace(page: WorkspacePageId) {
    setActiveWorkspace(page);
    const nextUrl = new URL(window.location.href);
    nextUrl.searchParams.set("workspace", page);
    window.history.pushState({ workspace: page }, "", nextUrl);
  }

  const firstStrategyTarget = strategyResult?.allocation_targets[0];
  const glossaryLang = i18n.language.startsWith("zh") ? "zh-CN" : "en";
  const glossaryShortcutTerms = ["TTF", "NBP", "ICE OCM", "Entry Capacity"];
  const routeRecommendationRequest = useMemo(
    () => buildRouteRecommendationRequest(portfolioResources, saleOptions, totalPoolVolume, upstreamContracts),
    [portfolioResources, saleOptions, totalPoolVolume, upstreamContracts],
  );
  const analysisPayload = {
    question: analysisQuestion,
    task: "PORTFOLIO_REPORT",
    provider_id: "DEEPSEEK",
    model: "deepseek-chat",
    invoke_provider: invokeDeepSeek,
    selected_terms: ["TTF", "NBP", "ICE OCM"],
    selected_assets: ["TTF", "NBP", "BBL"],
    selected_contracts: portfolioResources.map((resource) => resource.resource_id),
    language: i18n.language.startsWith("zh") ? "zh-CN" : "en",
  };
  const selectedAllocation = routeRecommendation?.allocations[0] ?? null;
  const poolAllocations = resourcePoolResult?.allocations ?? [];
  const firstPoolAllocation = poolAllocations[0] ?? null;
  const firstPortfolioResource = portfolioResources[0] ?? null;
  const firstAllocationOption = firstPoolAllocation ? saleOptionById.get(firstPoolAllocation.option_id) : null;
  const rawDecisionPnl =
    resourcePoolResult?.total_net_pnl_gbp_per_day ??
    (selectedAllocation?.netback !== undefined && selectedAllocation?.netback !== null
      ? selectedAllocation.netback * selectedAllocation.allocated_mwh_per_day
      : null) ??
    portfolioSummary?.total_indicative_pnl_gbp ??
    null;
  const decisionPnl = hasPortfolioResources ? rawDecisionPnl : null;
  const decisionMargin = firstPoolAllocation?.net_margin_gbp_mwh ?? selectedAllocation?.netback ?? null;
  const salePrice = firstPoolAllocation?.gross_sale_price_gbp_mwh ?? selectedAllocation?.sale_price ?? saleOptions[0]?.sale_price_gbp_mwh ?? null;
  const purchasePrice = firstPortfolioResource?.contract_cost_gbp_mwh ?? null;
  const routeCharge = firstAllocationOption?.route_cost_gbp_mwh ?? selectedAllocation?.route_cost ?? null;
  const activeWarning = [...(strategyResult?.warnings ?? []), ...(meta?.warnings ?? [])][0] ?? null;
  const {
    latestCapacityRows,
  } = useMemo(
    () => buildWorkspaceLatestRows({ flows, capacity, tsoAccess, tsoTariffs, storage, lng }),
    [capacity, flows, lng, storage, tsoAccess, tsoTariffs],
  );
  const reviewWarnings = useMemo(
    () => buildReviewWarnings(
      resourcePoolResult,
      routeRecommendation,
      strategyResult,
      analysisResult,
      meta,
    ),
    [analysisResult, meta, resourcePoolResult, routeRecommendation, strategyResult],
  );
  const sourceStats = useMemo(() => buildSourceStats(sources), [sources]);
  const runtimeDbReady = runtimeDb?.database_url_present === true && runtimeDb.connectivity.ok;
  const optionBlockers = resourcePoolOptions?.blockers ?? [];
  const canRunPoolOptimizer =
    runtimeDbReady &&
    hasPortfolioResources &&
    saleOptions.length > 0 &&
    optionBlockers.length === 0;
  const autoOptimizerSignature = useMemo(
    () => JSON.stringify({
      resources: portfolioResources.map((resource) => [
        resource.resource_id,
        resource.available_quantity_mwh_per_day,
        resource.contract_cost_gbp_mwh,
        resource.location_point_name,
      ]),
      saleOptions: saleOptions.map((option) => [
        option.option_id,
        option.target_point_name,
        option.sale_price_gbp_mwh,
        option.route_cost_gbp_mwh,
        option.capacity_limit_mwh_per_day,
      ]),
      financingRate: resourcePoolOptimizationRequest.annual_financing_rate_pct,
    }),
    [portfolioResources, resourcePoolOptimizationRequest.annual_financing_rate_pct, saleOptions],
  );
  const poolInputBlockers = useMemo(() => {
    const blockers: string[] = [];
    if (!runtimeDbReady) blockers.push(t("home.blocker_runtime_db"));
    blockers.push(...(resourcePoolOptions?.blockers ?? []));
    return blockers;
  }, [resourcePoolOptions, runtimeDbReady, t]);

  useEffect(() => {
    if (!canRunPoolOptimizer || loading) return;
    if (lastAutoOptimizerSignatureRef.current === autoOptimizerSignature) return;
    lastAutoOptimizerSignatureRef.current = autoOptimizerSignature;
    void optimizeResourcePool(resourcePoolOptimizationRequest);
  }, [
    autoOptimizerSignature,
    canRunPoolOptimizer,
    loading,
    optimizeResourcePool,
    resourcePoolOptimizationRequest,
  ]);
  const routeGeometryEdgesByRouteId = useMemo(() => {
    return buildRouteGeometryEdgesByRouteId(edges);
  }, [edges]);
  const resourcePoolMapPaths = useMemo(
    () => buildResourcePoolMapPaths({
      portfolioResources,
      saleOptions,
      poolAllocations,
      routeCandidates,
      routeGeometryEdgesByRouteId,
      poolInputBlockers,
      t,
    }),
    [
      poolAllocations,
      poolInputBlockers,
      portfolioResources,
      routeCandidates,
      routeGeometryEdgesByRouteId,
      saleOptions,
      t,
    ],
  );
  const nodeIdByPointName = useMemo(() => buildNodeIdByPointName(nodes), [nodes]);
  const resourcePoolHighlightedRoute = useMemo(
    () => buildHighlightedResourcePoolRoute(resourcePoolMapPaths, nodeIdByPointName),
    [nodeIdByPointName, resourcePoolMapPaths],
  );
  const reviewEvidenceItems = useMemo(() => {
    const items: Array<{ kind: string; text: string }> = [];
    const add = (kind: string, text: string | null | undefined) => {
      if (!text || items.some((item) => item.kind === kind && item.text === text)) return;
      items.push({ kind, text });
    };

    reviewWarnings.forEach((warning) => add(t("home.evidence_warning"), warning));
    poolInputBlockers.forEach((blocker) => add(t("home.evidence_blocker"), blocker));
    (resourcePoolResult?.missing_inputs ?? []).forEach((input) => add(t("home.evidence_missing_input"), input));
    (routeRecommendation?.assumptions ?? []).forEach((assumption) => add(t("home.evidence_assumption"), assumption));
    [
      ...(resourcePoolResult?.source_refs ?? []),
      ...(meta?.source_references ?? []),
      ...Object.values(endpointMeta).flatMap((item) => item.source_references ?? []),
    ].forEach((sourceRef) => add(t("home.evidence_source"), sourceRef));

    return items.slice(0, 6);
  }, [endpointMeta, meta, poolInputBlockers, resourcePoolResult, reviewWarnings, routeRecommendation, t]);
  const networkGeometryState = useMemo(
    () => resolveNetworkGeometryState(runtimeDbReady, nodes, edges),
    [edges, nodes, runtimeDbReady],
  );
  const sourceCategories = SOURCE_CATEGORIES;
  const sourcePostureRows = useMemo(
    () => buildSourcePostureRows(
      sources,
      endpointMeta.sources?.source_posture_summary?.categories,
    ),
    [endpointMeta.sources?.source_posture_summary?.categories, sources],
  );
  const filteredSources = useMemo(
    () => filterSourcesByCategory(sources, sourceCategory),
    [sourceCategory, sources],
  );
  const selectedSource = useMemo(
    () => sources.find((source) => source.source_id === selectedSourceId) ?? filteredSources[0] ?? sources[0] ?? null,
    [filteredSources, selectedSourceId, sources],
  );
  const selectedSourceCredentialProvider = useMemo(
    () => {
      const providerId = credentialProviderIdForSource(selectedSource);
      return providerId
        ? credentialProviders.find((provider) => provider.provider_id === providerId) ?? null
        : null;
    },
    [credentialProviders, selectedSource],
  );
  useEffect(() => {
    if (!selectedSourceCredentialProvider?.provider_id) return;
    setCredentialProvider(selectedSourceCredentialProvider.provider_id);
  }, [selectedSourceCredentialProvider?.provider_id]);
  const sourceCategoryCounts = useMemo(() => buildSourceCategoryCounts(sources), [sources]);
  const sourcesByCategory = useMemo(() => buildSourcesByCategory(sources), [sources]);
  function glossaryContextParams() {
    return {
      lang: glossaryLang,
      duration_start_utc: glossaryDurationStart ? new Date(glossaryDurationStart).toISOString() : undefined,
      duration_end_utc: glossaryDurationEnd ? new Date(glossaryDurationEnd).toISOString() : undefined,
    };
  }

  function openGlossaryContext(term: string) {
    setSelectedGlossaryTerm(term);
    fetchGlossaryContext(term, glossaryContextParams());
  }

  function onSelectGlossaryTerm(term: { term: string }) {
    openGlossaryContext(term.term);
  }

  function selectSource(sourceId: string) {
    const source = sources.find((item) => item.source_id === sourceId);
    setSelectedSourceId(sourceId);
    const providerId = credentialProviderIdForSource(source);
    if (providerId) {
      setCredentialProvider(providerId);
    }
  }

  function credentialProviderIdForSource(source: typeof sources[number] | null | undefined) {
    if (!source) return null;
    if (source.credential_provider_id) return source.credential_provider_id;
    const sourceSystem = source.source_system.toLocaleLowerCase();
    return credentialProviders.find(
      (provider) => provider.provider_id.toLocaleLowerCase() === sourceSystem,
    )?.provider_id ?? null;
  }

  function selectSourceCategory(category: string, nextSourceId: string | null) {
    setSourceCategory(category);
    if (nextSourceId) selectSource(nextSourceId);
  }

  function sourceLabel(prefix: string, value: string | null | undefined) {
    if (!value) return "n/a";
    const key = `${prefix}.${value}`;
    const translated = t(key);
    return translated === key ? value.replace(/_/g, " ") : translated;
  }

  function categoryProviderSummary(category: string) {
    if (category === "all") return t("sources.all_categories");
    const systems = sourcesByCategory.get(category) ?? [];
    return systems.length > 0 ? systems.join(", ") : t("sources.no_registered_feeds");
  }

  function sourceNextAction(source: typeof sources[number] | null) {
    return t(sourceNextActionKey(source));
  }

  function formatSourceTimestamp(value: string | null | undefined) {
    if (!value) return "n/a";
    return new Intl.DateTimeFormat(i18n.language, {
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(value));
  }

  function formatContextValue(value: unknown) {
    if (value === null || value === undefined || value === "") return "n/a";
    if (typeof value === "number") return Number.isInteger(value) ? value.toLocaleString() : value.toFixed(2);
    if (Array.isArray(value)) return value.join(", ");
    return String(value);
  }

  function contextSource(item: Record<string, unknown>) {
    return formatContextValue(item.source_reference ?? item.source_system ?? item.source_refs);
  }

  return (
    <div className={`app cockpit-app workspace-${activeWorkspace}`}>
      <WorkspaceTopBar
        activeWorkspace={activeWorkspace}
        searchTerm={searchTerm}
        dataStatus={dataStatus}
        loading={loading}
        language={i18n.language}
        mode={mode}
        gasDay={gasDay}
        deliveryProduct={deliveryProduct}
        marketLastUpdatedAtUtc={marketLastUpdatedAtUtc}
        sourceIssueCount={sourceStats.issues}
        t={t}
        onSearchTermChange={setSearchTerm}
        onLanguageChange={(language) => i18n.changeLanguage(language)}
        onModeChange={setMode}
        onGasDayChange={setGasDay}
        onDeliveryProductChange={setDeliveryProduct}
      />

      <main className="app-main">
        <NetworkWorkspace
          t={t}
          nodes={nodes}
          edges={edges}
          routes={routes}
          mode={mode}
          activeLayers={activeLayers}
          searchTerm={searchTerm}
          highlightedRoute={resourcePoolHighlightedRoute}
          resourcePoolMapPaths={resourcePoolMapPaths}
          poolInputBlockers={poolInputBlockers}
          error={error}
          loading={loading}
          saleOptions={saleOptions}
          canRunPoolOptimizer={canRunPoolOptimizer}
          portfolioResources={portfolioResources}
          totalPoolVolume={totalPoolVolume}
          portfolioSummary={portfolioSummary}
          screenOrderCount={screenOrders.length}
          upstreamContractCount={upstreamContracts.length}
          networkGeometryState={networkGeometryState}
          routeRecommendation={routeRecommendation}
          decisionPnl={decisionPnl}
          resourcePoolResult={resourcePoolResult}
          poolAllocations={poolAllocations}
          saleOptionById={saleOptionById}
          hasPortfolioResources={hasPortfolioResources}
          selectedAllocation={selectedAllocation}
          purchasePrice={purchasePrice}
          salePrice={salePrice}
          routeCharge={routeCharge}
          firstPoolAllocation={firstPoolAllocation}
          firstStrategyTarget={firstStrategyTarget}
          strategyResult={strategyResult}
          activeWarning={activeWarning}
          reviewEvidenceItems={reviewEvidenceItems}
          gasDay={gasDay}
          deliveryProduct={deliveryProduct}
          marketLastUpdatedAtUtc={marketLastUpdatedAtUtc}
          sourceStats={sourceStats}
          onResetSearch={() => setSearchTerm("")}
          onToggleLayer={toggleLayer}
          onOptimizePool={() => optimizeResourcePool(resourcePoolOptimizationRequest)}
          onOpenReview={() => openWorkspace("review")}
        />
        <section className="workspace-page" aria-label={t(`nav.${activeWorkspace}`)}>
          <div className="workspace-page-header">
            <div>
              <span className="eyebrow">{t("app.title")}</span>
              <h1>{t(`nav.${activeWorkspace}`)}</h1>
            </div>
            <span className={`status-badge status-${dataStatus}`}>{t(`data.${dataStatus}`)}</span>
          </div>

          {activeWorkspace === "capacity" && (
            <CapacityWorkspace
              flows={flows}
              capacity={capacity}
              tsoAccess={tsoAccess}
              tsoTariffs={tsoTariffs}
              storage={storage}
              lng={lng}
              t={t}
            />
          )}

          {activeWorkspace === "market" && (
            <MarketTerminal
              markets={contextMarkets}
              fxRates={fxRates}
              sources={sources}
              lastUpdatedAtUtc={marketLastUpdatedAtUtc}
              onRefresh={refreshMarketData}
              t={t}
            />
          )}

          {activeWorkspace === "contracts" && (
            <ContractWorkbench
              contract={contract}
              contractPayload={contractPayload}
              upstreamContracts={upstreamContracts}
              portfolioResources={portfolioResources}
              totalPoolVolume={totalPoolVolume}
              firstPoolAllocation={firstPoolAllocation}
              runtimeDbReady={runtimeDbReady}
              loading={loading}
              contractImportRef={contractImportRef}
              contractImportMessage={contractImportMessage}
              contractSaveMessage={contractSaveMessage}
              t={t}
              updateContractText={updateContractText}
              updateContractNumber={updateContractNumber}
              saveDraftContract={saveDraftContract}
              resetContractDraft={resetContractDraft}
              importContractDraftFile={importContractDraftFile}
              loadPersistedContract={loadPersistedContract}
            />
          )}

          {activeWorkspace === "scenario" && (
            <ScenarioWorkspace
              routeCandidates={routeCandidates}
              purchasePrice={purchasePrice}
              salePrice={salePrice}
              routeCharge={routeCharge}
              routeRecommendation={routeRecommendation}
              contract={contract}
              canRunPoolOptimizer={canRunPoolOptimizer}
              canCompareRoutes={hasPortfolioResources && saleOptions.length > 0}
              poolInputBlockers={poolInputBlockers}
              resourcePoolResult={resourcePoolResult}
              saleOptionById={saleOptionById}
              t={t}
              updateContractNumber={updateContractNumber}
              onOptimize={() => optimizeResourcePool(resourcePoolOptimizationRequest)}
              onCompare={() => recommendRouteAllocation(routeRecommendationRequest)}
            />
          )}

          {activeWorkspace === "strategy" && (
            <StrategyShadowRunTerminal
              strategyScenario={strategyScenario}
              strategyResult={strategyResult}
              portfolioResources={portfolioResources}
              marketObservations={contextMarkets}
              fxRates={fxRates}
              language={i18n.language}
              loading={loading}
              t={t}
              onEvaluate={() => evaluateStrategyLab(strategyScenario)}
            />
          )}

          {activeWorkspace === "review" && (
            <ReviewWorkspace
              allocations={poolAllocations}
              saleOptionById={saleOptionById}
              reviewWarnings={reviewWarnings}
              analysisQuestion={analysisQuestion}
              invokeDeepSeek={invokeDeepSeek}
              analysisResult={analysisResult}
              language={i18n.language}
              t={t}
              onAnalysisQuestionChange={setAnalysisQuestion}
              onInvokeDeepSeekChange={setInvokeDeepSeek}
              onAnalyze={() => askAnalysis(analysisPayload)}
              onGenerateReport={() => generatePortfolioReport(analysisPayload)}
            />
          )}

          {activeWorkspace === "orders" && (
            <MarketPositioningWorkspace
              portfolioSummary={portfolioSummary}
              screenOrders={screenOrders}
              pnlSnapshots={pnlSnapshots}
              formatTimestamp={formatSourceTimestamp}
              t={t}
            />
          )}

          {activeWorkspace === "sources" && (
            <SourceCenter
              t={t}
              sources={sources}
              sourceCategories={sourceCategories}
              sourceCategory={sourceCategory}
              sourceCategoryCounts={sourceCategoryCounts}
              sourceStats={sourceStats}
              sourcePostureRows={sourcePostureRows}
              filteredSources={filteredSources}
              selectedSource={selectedSource}
              selectedCredentialProvider={selectedCredentialProvider}
              selectedSourceCredentialProvider={selectedSourceCredentialProvider ?? null}
              credentialProviders={credentialProviders}
              credentialProvider={credentialProvider}
              credentialLabel={credentialLabel}
              credentialValue={credentialValue}
              credentialMessage={credentialMessage}
              flows={flows}
              capacity={capacity}
              storage={storage}
              lng={lng}
              tsoAccessCount={tsoAccess.length}
              tsoTariffs={tsoTariffs}
              latestCapacityRows={latestCapacityRows}
              onSourceCategoryChange={selectSourceCategory}
              onSourceSelect={selectSource}
              onCredentialProviderChange={setCredentialProvider}
              onCredentialLabelChange={setCredentialLabel}
              onCredentialValueChange={setCredentialValue}
              onCredentialSubmit={onCredentialSubmit}
              sourceLabel={sourceLabel}
              categoryProviderSummary={categoryProviderSummary}
              sourceNextAction={sourceNextAction}
              formatSourceTimestamp={formatSourceTimestamp}
            />
          )}

          {activeWorkspace === "glossary" && (
            <GlossaryWiki
              terms={visibleGlossaryTerms}
              context={glossaryContext}
              selectedTerm={selectedGlossaryTermRecord}
              categories={visibleGlossaryCategories}
              activeCategory={glossaryCategory}
              query={glossaryQuery}
              language={i18n.language}
              durationStart={glossaryDurationStart}
              durationEnd={glossaryDurationEnd}
              shortcutTerms={glossaryShortcutTerms}
              loading={loading}
              t={t}
              onCategoryChange={setGlossaryCategory}
              onQueryChange={setGlossaryQuery}
              onDurationStartChange={setGlossaryDurationStart}
              onDurationEndChange={setGlossaryDurationEnd}
              onSelectTerm={onSelectGlossaryTerm}
              onOpenContext={openGlossaryContext}
              formatContextValue={formatContextValue}
            />
          )}

          {activeWorkspace === "runtime" && (
            <RuntimeWorkspace meta={meta} runtimeDb={runtimeDb} t={t} />
          )}

          {activeWorkspace === "settings" && (
            <SettingsCenter
              t={t}
              language={i18n.language}
              mode={mode}
              dataStatus={dataStatus}
              runtimeDb={runtimeDb}
              sources={sources}
              credentialProviders={credentialProviders}
              counts={{ nodes: nodes.length, edges: edges.length, routes: routes.length }}
              onLanguageChange={(language) => i18n.changeLanguage(language)}
              onModeChange={setMode}
              onOpenSources={() => openWorkspace("sources")}
              onBackendBaseChanged={fetchWorkspace}
            />
          )}

          {activeWorkspace === "manual" && (
            <ManualWorkspace
              runtimeDb={runtimeDb}
              activeSourceCount={sourceStats.active}
              tariffCount={tsoTariffs.length}
              openOrderCount={portfolioSummary?.open_order_count ?? screenOrders.length}
              t={t}
            />
          )}
        </section>
      </main>
    </div>
  );
}

