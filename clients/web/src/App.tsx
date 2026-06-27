import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { GasNetworkMap } from "@/components/GasNetworkMap";
import { useApiStore } from "@/stores/api";
import { useThemeStore } from "@/stores/theme";
import "./styles/app.css";

type ContractNumberKey =
  | "delivery_quantity_mwh_per_day"
  | "contract_price_gbp_mwh"
  | "nbp_sale_price_gbp_mwh"
  | "physical_exit_sale_price_gbp_mwh"
  | "delivery_tolerance_pct"
  | "nomination_tolerance_pct"
  | "tolerance_risk_allowance_gbp_mwh"
  | "upstream_payment_lag_days"
  | "screen_sale_cash_lag_days"
  | "annual_financing_rate_pct";

type LiveMarkNumberKey = "bid_gbp_mwh" | "ask_gbp_mwh" | "last_gbp_mwh";
type WorkspacePageId = "network" | "market" | "scenario" | "strategy" | "sources" | "glossary" | "runtime" | "settings";

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
    ukTariffs,
    upstreamContracts,
    endpointMeta,
    routeOptions,
    livePnl,
    glossaryTerms,
    glossaryContext,
    analysisResult,
    credentialProviders,
    runtimeDb,
    dataStatus,
    meta,
    loading,
    error,
    credentialMessage,
    fetchWorkspace,
    saveProviderCredential,
    compareEasingtonOptions,
    markEasingtonLivePnl,
    strategyResult,
    evaluateStrategyLab,
    fetchGlossaryContext,
    askAnalysis,
    generatePortfolioReport,
  } = useApiStore();
  const [activeLayers, setActiveLayers] = useState(["network", "lng", "ips", "hubs"]);
  const [searchTerm, setSearchTerm] = useState("");
  const [credentialProvider, setCredentialProvider] = useState("GIE");
  const [credentialLabel, setCredentialLabel] = useState("default");
  const [credentialValue, setCredentialValue] = useState("");
  const [sourceCategory, setSourceCategory] = useState("all");
  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null);
  const [glossaryQuery, setGlossaryQuery] = useState("");
  const [glossaryDurationStart, setGlossaryDurationStart] = useState("2026-05-31T06:00");
  const [glossaryDurationEnd, setGlossaryDurationEnd] = useState("2026-06-01T06:00");
  const [analysisQuestion, setAnalysisQuestion] = useState("Summarize current portfolio PnL, route, market, and strategy status.");
  const [invokeDeepSeek, setInvokeDeepSeek] = useState(false);
  const [activeWorkspace, setActiveWorkspace] = useState<WorkspacePageId>("network");
  const selectedCredentialProvider = useMemo(
    () => credentialProviders.find((provider) => provider.provider_id === credentialProvider),
    [credentialProvider, credentialProviders],
  );
  const [contract, setContract] = useState({
    contract_id: "operator-test-easington-contract",
    gas_year: "2025/26",
    delivery_quantity_mwh_per_day: 10000,
    contract_price_gbp_mwh: 25,
    nbp_sale_price_gbp_mwh: 28,
    physical_exit_sale_price_gbp_mwh: 28.5,
    physical_exit_point_name: "Bacton GDN (EA)",
    delivery_tolerance_pct: 2,
    nomination_tolerance_pct: 1,
    tolerance_risk_allowance_gbp_mwh: 0.1,
    settlement_frequency: "monthly",
    upstream_payment_lag_days: 20,
    screen_sale_cash_lag_days: 1,
    annual_financing_rate_pct: 6,
    owned_entry_capacity_mwh_per_day: null as number | null,
    owned_exit_capacity_mwh_per_day: null as number | null,
    allowed_exit_points: ["Bacton GDN (EA)"],
    eligible_sale_modes: ["VIRTUAL_HUB_SALE", "PHYSICAL_DELIVERY"],
  });
  const [liveMark, setLiveMark] = useState({
    venue: "ICE OCM",
    hub: "NBP",
    product: "Within-day",
    bid_gbp_mwh: 28.2,
    ask_gbp_mwh: 28.4,
    last_gbp_mwh: 28.3,
    mark_time_utc: new Date().toISOString(),
    source_system: "operator-entered-live-mark",
  });
  const strategyScenario = useMemo(() => {
    const deliveryStart = "2026-01-16T00:00:00Z";
    const deliveryEnd = "2026-01-17T00:00:00Z";
    const ocmMid = liveMark.last_gbp_mwh ?? liveMark.bid_gbp_mwh ?? liveMark.ask_gbp_mwh ?? 0;
    return {
      strategy_id: "nbp-sap-icis-ocm-window",
      strategy_name: "NBP SAP/ICIS day-ahead versus ICE OCM window",
      run_mode: "SHADOW_RUN",
      resource_contexts: [
        {
          resource_id: contract.contract_id,
          resource_name: "Easington gas year contract",
          available_quantity_mwh_per_day: contract.delivery_quantity_mwh_per_day,
          all_in_cost_gbp_mwh: contract.contract_price_gbp_mwh + contract.tolerance_risk_allowance_gbp_mwh,
          delivery_tolerance_pct: contract.delivery_tolerance_pct,
          nomination_tolerance_pct: contract.nomination_tolerance_pct,
          booked_entry_capacity_mwh_per_day: contract.owned_entry_capacity_mwh_per_day,
          balancing_allowance_gbp_mwh: contract.tolerance_risk_allowance_gbp_mwh,
          required_tso_access: ["National Gas NTS"],
          company_accessible_tsos: ["National Gas NTS"],
        },
      ],
      price_observations: [
        {
          observation_id: "operator-sap-reference",
          source_system: "operator-entered",
          venue: "SAP",
          hub: "NBP",
          product: "day-ahead",
          price_name: "SAP",
          price_gbp_mwh: contract.nbp_sale_price_gbp_mwh - 0.4,
          observed_at_utc: "2026-01-15T16:00:00Z",
          delivery_start_utc: deliveryStart,
          delivery_end_utc: deliveryEnd,
          bar_minutes: 5,
          source_reference: "operator:SAP",
        },
        {
          observation_id: "operator-icis-reference",
          source_system: "operator-entered",
          venue: "ICIS Heren",
          hub: "NBP",
          product: "day-ahead",
          price_name: "ICIS_HEREN_DAY_AHEAD",
          price_gbp_mwh: contract.nbp_sale_price_gbp_mwh,
          observed_at_utc: "2026-01-15T16:30:00Z",
          delivery_start_utc: deliveryStart,
          delivery_end_utc: deliveryEnd,
          bar_minutes: 5,
          source_reference: "operator:ICIS_HEREN_DAY_AHEAD",
        },
        {
          observation_id: "operator-ocm-reference",
          source_system: liveMark.source_system,
          venue: liveMark.venue,
          hub: liveMark.hub,
          product: liveMark.product,
          price_name: "ICE_OCM",
          price_gbp_mwh: ocmMid,
          observed_at_utc: "2026-01-15T16:45:00Z",
          delivery_start_utc: deliveryStart,
          delivery_end_utc: deliveryEnd,
          bar_minutes: 5,
          source_reference: liveMark.source_system,
        },
      ],
      components: [
        {
          component_id: "sap-icis-ocm-1500-1700",
          component_type: "OCM_VS_DAY_AHEAD",
          weight: 1,
          day_ahead_price_names: ["SAP", "ICIS_HEREN_DAY_AHEAD"],
          intraday_price_names: ["ICE_OCM"],
          positive_spread_threshold_gbp_mwh: 0.2,
          negative_spread_threshold_gbp_mwh: 0.2,
          time_window_start: "15:00",
          time_window_end: "17:00",
          target_bar_minutes: 5,
        },
      ],
      risk_control: {
        max_ocm_allocation_pct: 70,
        min_day_ahead_allocation_pct: 20,
        max_single_market_volume_mwh_per_day: contract.delivery_quantity_mwh_per_day * 0.6,
        min_expected_margin_gbp_mwh: 0,
        require_tso_access: true,
      },
      existing_shadow_pnl_gbp: 0,
      research_only: true,
    };
  }, [contract, liveMark]);

  useEffect(() => {
    fetchWorkspace();
  }, [fetchWorkspace]);

  async function onCredentialSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedCredentialProvider?.credential_required || !credentialValue.trim()) return;
    await saveProviderCredential(credentialProvider, credentialValue, credentialLabel || "default");
    setCredentialValue("");
  }

  const visibleGlossaryTerms = useMemo(() => {
    const trimmed = glossaryQuery.trim();
    const query = trimmed.toLowerCase();
    if (!query) return glossaryTerms.slice(0, 10);
    return glossaryTerms
      .filter((term) =>
        term.term.toLowerCase().includes(query) ||
        term.category.toLowerCase().includes(query) ||
        term.definition_en.toLowerCase().includes(query) ||
        term.definition_zh_cn.includes(trimmed) ||
        term.aliases.some((alias) => alias.toLowerCase().includes(query)),
      )
      .slice(0, 10);
  }, [glossaryQuery, glossaryTerms]);

  function updateContractNumber(key: ContractNumberKey, value: string) {
    setContract((current) => ({ ...current, [key]: value === "" ? 0 : Number(value) }));
  }

  function updateLiveMarkNumber(key: LiveMarkNumberKey, value: string) {
    setLiveMark((current) => ({ ...current, [key]: value === "" ? null : Number(value) }));
  }

  function toggleLayer(layer: string) {
    setActiveLayers((current) =>
      current.includes(layer) ? current.filter((item) => item !== layer) : [...current, layer],
    );
  }

  const primaryLiveMark = livePnl?.live_marks[0];
  const firstStrategyTarget = strategyResult?.allocation_targets[0];
  const glossaryLang = i18n.language.startsWith("zh") ? "zh-CN" : "en";
  const glossaryShortcutTerms = ["Easington Entry Point", "ICIS Heren", "NBP", "ICE OCM"];
  const analysisPayload = {
    question: analysisQuestion,
    task: "PORTFOLIO_REPORT",
    provider_id: "DEEPSEEK",
    model: "deepseek-chat",
    invoke_provider: invokeDeepSeek,
    selected_terms: ["Easington Entry Point", "ICIS Heren", "ICE OCM"],
    selected_assets: [contract.physical_exit_point_name, "NBP"],
    selected_contracts: [contract.contract_id],
    language: i18n.language.startsWith("zh") ? "zh-CN" : "en",
  };
  const workflowSteps = ["discover", "compose", "price", "evaluate", "review"];
  const workspacePages: WorkspacePageId[] = ["network", "market", "scenario", "strategy", "sources", "glossary", "runtime", "settings"];
  const destinationHubs = ["NBP", "TTF", "ZTP", "PEG", "THE"];
  const selectedOption = (livePnl ?? routeOptions)?.options[0] ?? null;
  const decisionPnl =
    primaryLiveMark?.live_net_pnl_gbp_per_day ??
    selectedOption?.net_pnl_gbp_per_day ??
    portfolioSummary?.total_indicative_pnl_gbp ??
    null;
  const decisionMargin =
    primaryLiveMark?.live_net_margin_gbp_mwh ?? selectedOption?.net_margin_gbp_mwh ?? null;
  const salePrice = liveMark.bid_gbp_mwh ?? liveMark.last_gbp_mwh ?? contract.nbp_sale_price_gbp_mwh;
  const routeCharge = selectedOption?.total_charges_gbp_mwh ?? null;
  const activeWarning = [...(strategyResult?.warnings ?? []), ...(meta?.warnings ?? [])][0] ?? null;
  const tsoAccessByCountry = useMemo(() => {
    const buckets = new Map<string, {
      country: string;
      accessCount: number;
      dayAheadCount: number;
      dailyCount: number;
      monthlyCount: number;
    }>();
    tsoAccess.forEach((item) => {
      const country = item.country || "--";
      const bucket = buckets.get(country) ?? {
        country,
        accessCount: 0,
        dayAheadCount: 0,
        dailyCount: 0,
        monthlyCount: 0,
      };
      bucket.accessCount += 1;
      bucket.dayAheadCount += item.day_ahead_contracts_available ? 1 : 0;
      bucket.dailyCount += item.daily_contracts_available ? 1 : 0;
      bucket.monthlyCount += item.monthly_contracts_available ? 1 : 0;
      buckets.set(country, bucket);
    });
    return [...buckets.values()]
      .sort((a, b) => b.accessCount - a.accessCount)
      .slice(0, 6);
  }, [tsoAccess]);
  const latestOfficialFlows = useMemo(() => flows
    .filter((item) => item.source_system === "ENTSOG")
    .slice(0, 5), [flows]);
  const capacityByType = useMemo(() => {
    const buckets = new Map<string, { capacityType: string; rows: number; totalMcmD: number }>();
    capacity.forEach((item) => {
      const bucket = buckets.get(item.capacity_type) ?? {
        capacityType: item.capacity_type,
        rows: 0,
        totalMcmD: 0,
      };
      bucket.rows += 1;
      bucket.totalMcmD += item.capacity_mcm_d;
      buckets.set(item.capacity_type, bucket);
    });
    return [...buckets.values()].sort((a, b) => b.rows - a.rows).slice(0, 5);
  }, [capacity]);
  const latestCapacityRows = useMemo(() => capacity.slice(0, 5), [capacity]);
  const runtimeSourceSummary = Object.entries(endpointMeta).slice(0, 6);
  const dataIssueText = dataStatus === "runtime"
    ? null
    : dataStatus === "partial"
      ? "Runtime DB is partially populated. Review missing sources and lineage before using decisions."
      : "Runtime DB is unavailable or empty. Configure and populate the database.";
  const sourceStats = useMemo(() => {
    const issueStatuses = new Set(["failed", "needs_credential", "credential_disabled", "runtime_unconfigured"]);
    return {
      total: sources.length,
      active: sources.filter((source) => source.connectivity_status === "active").length,
      issues: sources.filter((source) => issueStatuses.has(source.connectivity_status)).length,
      records: sources.reduce((total, source) => total + source.live_record_count, 0),
      missingCredentials: sources.filter((source) => source.credential_state === "missing").length,
    };
  }, [sources]);
  const sourceCategories = useMemo(() => {
    const order = ["price", "fx", "infrastructure", "tariff", "weather", "ai"];
    const present = new Set(sources.map((source) => source.category));
    return ["all", ...order.filter((category) => present.has(category))];
  }, [sources]);
  const filteredSources = useMemo(
    () => sourceCategory === "all"
      ? sources
      : sources.filter((source) => source.category === sourceCategory),
    [sourceCategory, sources],
  );
  const selectedSource = useMemo(
    () => sources.find((source) => source.source_id === selectedSourceId) ?? filteredSources[0] ?? sources[0] ?? null,
    [filteredSources, selectedSourceId, sources],
  );
  const selectedSourceCredentialProvider = useMemo(
    () => selectedSource?.credential_provider_id
      ? credentialProviders.find((provider) => provider.provider_id === selectedSource.credential_provider_id)
      : null,
    [credentialProviders, selectedSource],
  );
  const sourceCategoryCounts = useMemo(() => {
    const counts = new Map<string, number>();
    sources.forEach((source) => counts.set(source.category, (counts.get(source.category) ?? 0) + 1));
    return counts;
  }, [sources]);

  function glossaryContextParams() {
    return {
      lang: glossaryLang,
      duration_start_utc: glossaryDurationStart ? new Date(glossaryDurationStart).toISOString() : undefined,
      duration_end_utc: glossaryDurationEnd ? new Date(glossaryDurationEnd).toISOString() : undefined,
    };
  }

  function openGlossaryContext(term: string) {
    fetchGlossaryContext(term, glossaryContextParams());
  }

  function selectSource(sourceId: string) {
    const source = sources.find((item) => item.source_id === sourceId);
    setSelectedSourceId(sourceId);
    if (source?.credential_provider_id) {
      setCredentialProvider(source.credential_provider_id);
    }
  }

  function sourceLabel(prefix: string, value: string | null | undefined) {
    if (!value) return "n/a";
    const key = `${prefix}.${value}`;
    const translated = t(key);
    return translated === key ? value.replace(/_/g, " ") : translated;
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
      <header className="app-header cockpit-topbar">
        <button className="topbar-icon-button" type="button" aria-label={t("topbar.menu")}><span className="topbar-menu-glyph" aria-hidden="true" /></button>
        <div className="workspace-pill" aria-label={t("topbar.workspace_label")}>
          <span>{t("topbar.workspace_label")}</span>
          <strong>{t(`nav.${activeWorkspace}`)}</strong>
        </div>
        <input
          className="topbar-search"
          value={searchTerm}
          onChange={(event) => setSearchTerm(event.target.value)}
          placeholder={t("map.search")}
        />
        <div className="header-controls">
          <span className={`status-badge status-${dataStatus}`}>{t(`data.${dataStatus}`)}</span>
          <select value={i18n.language} onChange={(event) => i18n.changeLanguage(event.target.value)}>
            <option value="en">EN</option>
            <option value="zh-CN">{t("settings.chinese")}</option>
          </select>
          <select value={mode} onChange={(event) => setMode(event.target.value as typeof mode)}>
            <option value="light">{t("theme.light")}</option>
            <option value="dark">{t("theme.dark")}</option>
            <option value="system">{t("theme.system")}</option>
          </select>
        </div>
      </header>

      <nav className="workspace-nav" aria-label={t("topbar.workspace_label")}>
        {workspacePages.map((page) => (
          <button
            key={page}
            type="button"
            className={activeWorkspace === page ? "workspace-nav-item active" : "workspace-nav-item"}
            onClick={() => setActiveWorkspace(page)}
          >
            {t(`nav.${page}`)}
          </button>
        ))}
      </nav>
      <nav className="workflow-strip" aria-label={t("workflow.label")}>
        {workflowSteps.map((step, index) => (
          <button key={step} className={index === 2 ? "workflow-step active" : "workflow-step"} type="button">
            <span>{index + 1}</span>
            {t(`workflow.${step}`)}
          </button>
        ))}
      </nav>

      <main className="app-main">
        <section className="map-container map-stage" id="map">
          <div className="map-toolbar">
            <button className="chip reset-chip" type="button" onClick={() => setSearchTerm("")}>
              {t("map.reset")}
            </button>
            {["network", "lng", "ips", "hubs"].map((layer) => (
              <button
                key={layer}
                type="button"
                className={activeLayers.includes(layer) ? "chip active" : "chip"}
                onClick={() => toggleLayer(layer)}
              >
                {t(`map.layer.${layer}`)}
              </button>
            ))}
          </div>
          <div className="map-price-strip">
            <div>
              <span>{t("home.portfolio")}</span>
              <strong>{contract.delivery_quantity_mwh_per_day.toLocaleString()} MWh/d</strong>
            </div>
            <div>
              <span>{t("home.nbp_day_ahead")}</span>
              <strong>{contract.nbp_sale_price_gbp_mwh.toFixed(2)} GBP/MWh</strong>
            </div>
            <div>
              <span>{liveMark.venue} {liveMark.product}</span>
              <strong>{(liveMark.last_gbp_mwh ?? liveMark.bid_gbp_mwh ?? 0).toFixed(2)} GBP/MWh</strong>
            </div>
            <div>
              <span>{t("home.live_pnl")}</span>
              <strong>
                {primaryLiveMark
                  ? `GBP ${Math.round(primaryLiveMark.live_net_pnl_gbp_per_day ?? 0).toLocaleString()}/d`
                  : portfolioSummary
                    ? `GBP ${Math.round(portfolioSummary.total_indicative_pnl_gbp).toLocaleString()}`
                    : t("home.pending")}
              </strong>
            </div>
            <div>
              <span>{t("home.strategy_process")}</span>
              <strong>{firstStrategyTarget ? `${firstStrategyTarget.market_bucket} ${firstStrategyTarget.target_allocation_pct.toFixed(1)}%` : t("home.not_running")}</strong>
            </div>
          </div>
          <GasNetworkMap
            nodes={nodes}
            edges={edges}
            routes={routes}
            themeMode={mode}
            activeLayers={activeLayers}
            searchTerm={searchTerm}
          />
          <div className="map-overlay">
            <span>{t("map.nodes")}: {nodes.length}</span>
            <span>{t("map.edges")}: {edges.length}</span>
            <span>{t("map.routes")}: {routes.length}</span>
          </div>
          <div className="map-alert-stack">
            <div className="map-alert">
              <strong>{t("home.signal")}</strong>
              <span>{strategyResult?.candidate_action_for_review ?? t("home.signal_idle")}</span>
            </div>
            <div className="map-alert">
              <strong>{t("home.warning")}</strong>
              <span>{activeWarning ?? t("home.warning_clear")}</span>
            </div>
          </div>
        </section>

        <aside className="scenario-rail">
          {error && <div className="panel alert">{error}</div>}
          {loading && <div className="panel">{t("status.loading")}</div>}

          <div className="panel scenario-intro">
            <span className="eyebrow">{t("scenario.eyebrow")}</span>
            <h2>{t("scenario.title")}</h2>
            <p>{t("scenario.description")}</p>
          </div>

          <div className="panel route-selector-panel">
            <div className="section-heading">
              <span className="eyebrow">{t("scenario.active_route")}</span>
              <strong>{t("panel.routes")}</strong>
            </div>
            <div className="route-list">
              {routeCandidates.map((route) => (
                <div key={route.route_id} className="route-row route-candidate">
                  <span>{route.route_name}</span>
                  <strong>{route.required_tso_access.join(", ")}</strong>
                </div>
              ))}
            </div>
            <div className="route-list">
              {routes.map((route) => (
                <div key={route.route_id} className="route-row">
                  <span>
                    {route.from_node_id} {"->"} {route.to_node_id}
                  </span>
                  <strong>{Math.round(route.confidence * 100)}%</strong>
                </div>
              ))}
            </div>
          </div>

          <div className="panel home-portfolio-panel">
            <div className="section-heading">
              <span className="eyebrow">{t("home.portfolio")}</span>
              <strong>{upstreamContracts.length || 1} resource</strong>
            </div>
            <div className="metric-grid two-column compact-metrics">
              <div>
                <span>{t("economics.volume")}</span>
                <strong>{contract.delivery_quantity_mwh_per_day.toLocaleString()} MWh/d</strong>
              </div>
              <div>
                <span>{t("portfolio.open_orders")}</span>
                <strong>{portfolioSummary?.open_order_count ?? screenOrders.length}</strong>
              </div>
            </div>
            <div className="route-list compact-route-list">
              {latestOfficialFlows.slice(0, 4).map((flow) => (
                <div key={`home-flow-${flow.observation_id}`} className="route-row route-candidate">
                  <span>{flow.point_name}</span>
                  <strong>{flow.flow_mcm_d.toFixed(2)} mcm/d</strong>
                  <small>{flow.direction.toUpperCase()} / {flow.source_system}</small>
                </div>
              ))}
              {latestOfficialFlows.length === 0 && (
                <div className="route-row route-candidate">
                  <span>{t("status.source")}</span>
                  <strong>{t("data.unavailable")}</strong>
                  <small>Run ENTSOG flow ingestion into PostgreSQL.</small>
                </div>
              )}
            </div>
          </div>

        </aside>

        <aside className="decision-rail">
          <div className="panel trade-result-panel">
            <div className="panel-title-row">
              <div>
                <span className="eyebrow">{t("result.eyebrow")}</span>
                <h3>{t("result.title")}</h3>
              </div>
              <span className="status-pill">{primaryLiveMark ? t("result.live") : t("result.snapshot")}</span>
            </div>
            <div className="net-pnl-card">
              <span>{t("result.net_pnl")}</span>
              <strong>
                {decisionPnl === null ? t("home.pending") : `GBP ${Math.round(decisionPnl).toLocaleString()}`}
              </strong>
              <small>
                {t("result.net_margin")} {decisionMargin === null ? "n/a" : `${decisionMargin.toFixed(2)} GBP/MWh`}
              </small>
            </div>
          </div>

          <div className="panel route-alpha-panel">
            <div className="panel-title-row">
              <h3>{t("result.route_alpha")}</h3>
              <span>{t("result.delta")}</span>
            </div>
            <div className="route-alpha-card">
              <span>{t("result.optimal")}</span>
              <strong>{selectedOption?.label ?? routeCandidates[0]?.route_name ?? t("home.pending")}</strong>
              <small>
                {selectedOption
                  ? `${selectedOption.route_legs.length} ${t("result.legs")} / ${t("result.route_cost")} ${
                      routeCharge === null ? "n/a" : `${routeCharge.toFixed(2)} GBP/MWh`
                    }`
                  : t("result.no_route")}
              </small>
            </div>
            <div className="destination-switcher">
              {destinationHubs.map((hub) => (
                <button key={hub} type="button" className={hub === "NBP" ? "chip active" : "chip"}>
                  {hub}
                </button>
              ))}
            </div>
          </div>

          <div className="panel economics-snapshot">
            <h3>{t("result.economics_snapshot")}</h3>
            <div className="metric-grid two-column">
              <div>
                <span>{t("result.purchase")}</span>
                <strong>GBP {contract.contract_price_gbp_mwh.toFixed(2)}/MWh</strong>
              </div>
              <div>
                <span>{t("result.sale")}</span>
                <strong>GBP {salePrice.toFixed(2)}/MWh</strong>
              </div>
              <div>
                <span>{t("result.route_cost")}</span>
                <strong>{routeCharge === null ? "n/a" : `GBP ${routeCharge.toFixed(2)}/MWh`}</strong>
              </div>
              <div>
                <span>{t("result.cash_value")}</span>
                <strong>
                  {selectedOption?.early_cash_value_gbp_mwh === undefined
                    ? "n/a"
                    : `GBP ${selectedOption.early_cash_value_gbp_mwh.toFixed(3)}/MWh`}
                </strong>
              </div>
            </div>
          </div>

          <div className="panel network-operations-panel">
            <div className="panel-title-row">
              <h3>{t("panel.infrastructure")}</h3>
              <span>{t("data.runtime")}</span>
            </div>
            <div className="data-table compact-table country-ops-table">
              <div className="data-table-row header four"><span>{t("panel.country")}</span><span>{t("panel.access")}</span><span>{t("panel.day_ahead")}</span><span>{t("panel.daily")}</span></div>
              {tsoAccessByCountry.length > 0 ? tsoAccessByCountry.map((country) => (
                <div key={`country-op-${country.country}`} className="data-table-row four">
                  <strong>{country.country}</strong>
                  <span>{country.accessCount.toLocaleString()}</span>
                  <span>{country.dayAheadCount.toLocaleString()}</span>
                  <span>{country.dailyCount.toLocaleString()}</span>
                </div>
              )) : (
                <div className="data-table-row four"><strong>n/a</strong><span>No DB rows</span><span>n/a</span><span>n/a</span></div>
              )}
            </div>
            <div className="metric-grid four-column compact-metrics">
              <div><span>{t("panel.flows")}</span><strong>{flows.length}</strong></div>
              <div><span>{t("panel.capacity")}</span><strong>{capacity.length}</strong></div>
              <div><span>{t("panel.storage")}</span><strong>{storage.length}</strong></div>
              <div><span>{t("panel.lng")}</span><strong>{lng.length}</strong></div>
            </div>
            {capacityByType.length > 0 && (
              <div className="data-table compact-table capacity-summary-table">
                <div className="data-table-row header three"><span>{t("panel.capacity_type")}</span><span>{t("panel.rows")}</span><span>mcm/d</span></div>
                {capacityByType.map((bucket) => (
                  <div key={`capacity-bucket-${bucket.capacityType}`} className="data-table-row three">
                    <strong>{bucket.capacityType}</strong>
                    <span>{bucket.rows.toLocaleString()}</span>
                    <span>{bucket.totalMcmD.toFixed(1)}</span>
                  </div>
                ))}
              </div>
            )}
            <div className="route-list compact-route-list">
              {tsoAccess.slice(0, 3).map((item) => (
                <div key={`tso-access-${item.access_id}`} className="route-row route-candidate">
                  <span>{item.point_name}</span>
                  <strong>{item.direction.toUpperCase()}</strong>
                  <small>{item.operator_name} / {item.booking_platform ?? "booking platform n/a"}</small>
                </div>
              ))}
              {tsoAccess.length === 0 && (
                <div className="route-row route-candidate">
                  <span>No TSO access rows</span>
                  <strong>n/a</strong>
                  <small>Run ENTSOG reference ingestion</small>
                </div>
              )}
            </div>
          </div>

          <div className="panel data-health-panel">
            <div className="panel-title-row">
              <h3>Data health</h3>
              <span>{t(`data.${dataStatus}`)}</span>
            </div>
            {dataIssueText && <p className="data-warning">{dataIssueText}</p>}
            <div className="metric-grid two-column compact-metrics">
              <div><span>Resources</span><strong>{upstreamContracts.length}</strong></div>
              <div><span>Sources</span><strong>{sources.length}</strong></div>
              <div><span>Runtime DB</span><strong>{runtimeDb?.connectivity.ok ? "ok" : "check"}</strong></div>
              <div><span>Missing tables</span><strong>{runtimeDb?.missing_tables.length ?? "n/a"}</strong></div>
            </div>
            <div className="source-list compact-source-list">
              {runtimeSourceSummary.map(([name, sourceMeta]) => (
                <span key={`source-meta-${name}`}>{name}: {sourceMeta.source_references.join(", ") || "none"}</span>
              ))}
            </div>
          </div>

        </aside>
        <section className="workspace-page" aria-label={t(`nav.${activeWorkspace}`)}>
          <div className="workspace-page-header">
            <div>
              <span className="eyebrow">{t("app.title")}</span>
              <h1>{t(`nav.${activeWorkspace}`)}</h1>
            </div>
            <span className={`status-badge status-${dataStatus}`}>{t(`data.${dataStatus}`)}</span>
          </div>

          {activeWorkspace === "market" && (
            <div className="workspace-grid market-page">
              <div className="workspace-panel span-2">
                <div className="section-heading">
                  <span className="eyebrow">{t("panel.market")}</span>
                  <strong>{t("home.live_pnl")}</strong>
                </div>
                <div className="metric-grid four-column">
                  {markets.slice(0, 4).map((market) => (
                    <div key={market.observation_id}>
                      <span>{market.market_venue} {market.product}</span>
                      <strong>{market.price} {market.currency}</strong>
                    </div>
                  ))}
                </div>
                <div className="data-table">
                  <div className="data-table-row header"><span>Venue</span><span>Hub/Product</span><span>Price</span><span>Freshness</span></div>
                  {markets.slice(0, 8).map((market) => (
                    <div key={`market-row-${market.observation_id}`} className="data-table-row">
                      <span>{market.market_venue}</span><span>{market.product}</span><strong>{market.price} {market.unit}</strong><span>{market.freshness ?? "n/a"}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div className="workspace-panel">
                <h3>{t("panel.positioning")}</h3>
                {portfolioSummary && (
                  <div className="metric-grid">
                    <div><span>{t("portfolio.indicative_pnl")}</span><strong>GBP {Math.round(portfolioSummary.total_indicative_pnl_gbp).toLocaleString()}</strong></div>
                    <div><span>{t("portfolio.cash_value")}</span><strong>GBP {Math.round(portfolioSummary.total_cash_value_gbp).toLocaleString()}</strong></div>
                    <div><span>{t("portfolio.open_orders")}</span><strong>{portfolioSummary.open_order_count}</strong></div>
                  </div>
                )}
              </div>
              <div className="workspace-panel span-3">
                <h3>{t("panel.positioning")}</h3>
                <div className="data-table orders-table">
                  <div className="data-table-row header six"><span>Venue</span><span>Side</span><span>Hub</span><span>Qty</span><span>Price</span><span>Status</span></div>
                  {screenOrders.map((order) => (
                    <div key={`orders-${order.order_observation_id}`} className="data-table-row six">
                      <span>{order.venue}</span><span>{order.side}</span><span>{order.hub}</span><strong>{order.remaining_quantity_mwh.toLocaleString()} MWh</strong><span>{order.price.toFixed(2)} {order.unit}</span><span>{order.status}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {activeWorkspace === "scenario" && (
            <div className="workspace-grid scenario-page">
              <div className="workspace-panel span-2">
                <div className="section-heading"><span className="eyebrow">{t("scenario.active_route")}</span><strong>{t("panel.routes")}</strong></div>
                <div className="route-list">
                  {routeCandidates.map((route) => (
                    <div key={`scenario-route-${route.route_id}`} className="route-row route-candidate"><span>{route.route_name}</span><strong>{route.required_tso_access.join(", ")}</strong></div>
                  ))}
                </div>
              </div>
              <div className="workspace-panel">
                <h3>{t("result.economics_snapshot")}</h3>
                <div className="metric-grid two-column">
                  <div><span>{t("result.purchase")}</span><strong>GBP {contract.contract_price_gbp_mwh.toFixed(2)}/MWh</strong></div>
                  <div><span>{t("result.sale")}</span><strong>GBP {salePrice.toFixed(2)}/MWh</strong></div>
                  <div><span>{t("result.route_cost")}</span><strong>{routeCharge === null ? "n/a" : `GBP ${routeCharge.toFixed(2)}/MWh`}</strong></div>
                  <div><span>{t("result.cash_value")}</span><strong>{selectedOption?.early_cash_value_gbp_mwh === undefined ? "n/a" : `GBP ${selectedOption.early_cash_value_gbp_mwh.toFixed(3)}/MWh`}</strong></div>
                </div>
              </div>
              <div className="workspace-panel span-3">
                <div className="section-heading"><span className="eyebrow">{t("scenario.commercial_posture")}</span><strong>{t("panel.easington")}</strong></div>
                <div className="economics-grid wide">
                  <label>{t("economics.volume")}<input type="number" value={contract.delivery_quantity_mwh_per_day} onChange={(event) => updateContractNumber("delivery_quantity_mwh_per_day", event.target.value)} /></label>
                  <label>{t("economics.contract_price")}<input type="number" value={contract.contract_price_gbp_mwh} onChange={(event) => updateContractNumber("contract_price_gbp_mwh", event.target.value)} /></label>
                  <label>{t("economics.nbp_price")}<input type="number" value={contract.nbp_sale_price_gbp_mwh} onChange={(event) => updateContractNumber("nbp_sale_price_gbp_mwh", event.target.value)} /></label>
                  <label>{t("economics.physical_price")}<input type="number" value={contract.physical_exit_sale_price_gbp_mwh} onChange={(event) => updateContractNumber("physical_exit_sale_price_gbp_mwh", event.target.value)} /></label>
                  <label>{t("economics.delivery_tolerance")}<input type="number" value={contract.delivery_tolerance_pct} onChange={(event) => updateContractNumber("delivery_tolerance_pct", event.target.value)} /></label>
                  <label>{t("economics.nomination_tolerance")}<input type="number" value={contract.nomination_tolerance_pct} onChange={(event) => updateContractNumber("nomination_tolerance_pct", event.target.value)} /></label>
                  <label>{t("economics.cash_lag")}<input type="number" value={contract.screen_sale_cash_lag_days} onChange={(event) => updateContractNumber("screen_sale_cash_lag_days", event.target.value)} /></label>
                  <label>{t("economics.finance_rate")}<input type="number" value={contract.annual_financing_rate_pct} onChange={(event) => updateContractNumber("annual_financing_rate_pct", event.target.value)} /></label>
                </div>
                <div className="action-row"><button type="button" onClick={() => compareEasingtonOptions(contract)}>{t("economics.compare")}</button><button type="button" onClick={() => markEasingtonLivePnl(contract, [liveMark])}>{t("economics.live_pnl")}</button></div>
              </div>
            </div>
          )}

          {activeWorkspace === "strategy" && (
            <div className="workspace-grid strategy-page">
              <div className="workspace-panel span-2 strategy-panel">
                <h3>{t("panel.strategy_lab")}</h3>
                <div className="strategy-summary"><span>{t("strategy.window")}: 15:00-17:00</span><span>{t("strategy.bar")}: 5m</span><span>{t("strategy.mode")}: {strategyScenario.run_mode}</span></div>
                <button type="button" onClick={() => evaluateStrategyLab(strategyScenario)}>{t("strategy.evaluate")}</button>
                {strategyResult && (
                  <div className="strategy-result">
                    <div className="option-row"><span>{strategyResult.status}</span><strong>{strategyResult.candidate_action_for_review}</strong></div>
                    <div className="metric-grid three-column"><div><span>{t("strategy.day_ahead")}</span><strong>{strategyResult.day_ahead_average_gbp_mwh?.toFixed(2) ?? "n/a"}</strong></div><div><span>{t("strategy.intraday")}</span><strong>{strategyResult.intraday_average_gbp_mwh?.toFixed(2) ?? "n/a"}</strong></div><div><span>{t("strategy.spread")}</span><strong>{strategyResult.intraday_vs_day_ahead_spread_gbp_mwh?.toFixed(2) ?? "n/a"}</strong></div></div>
                  </div>
                )}
              </div>
              <div className="workspace-panel"><h3>{t("home.signal")}</h3><div className="net-pnl-card"><span>{t("home.strategy_process")}</span><strong>{firstStrategyTarget ? `${firstStrategyTarget.market_bucket} ${firstStrategyTarget.target_allocation_pct.toFixed(1)}%` : t("home.not_running")}</strong><small>{strategyResult?.candidate_action_for_review ?? t("home.signal_idle")}</small></div></div>
              <div className="workspace-panel span-3 analysis-panel">
                <h3>{t("panel.analysis")}</h3>
                <textarea value={analysisQuestion} onChange={(event) => setAnalysisQuestion(event.target.value)} rows={4} />
                <label className="checkbox-row"><input type="checkbox" checked={invokeDeepSeek} onChange={(event) => setInvokeDeepSeek(event.target.checked)} />{t("analysis.invoke_deepseek")}</label>
                <div className="action-row"><button type="button" onClick={() => askAnalysis(analysisPayload)}>{t("analysis.ask")}</button><button type="button" onClick={() => generatePortfolioReport(analysisPayload)}>{t("analysis.report")}</button></div>
                {analysisResult && <div className="analysis-result"><strong>{analysisResult.provider_id}: {analysisResult.provider_status}</strong><p>{i18n.language.startsWith("zh") ? analysisResult.answer_zh_cn : analysisResult.answer_en}</p></div>}
              </div>
            </div>
          )}

          {activeWorkspace === "sources" && (
            <div className="workspace-grid sources-page source-center">
              <div className="workspace-panel span-3 source-overview">
                <div className="section-heading">
                  <span className="eyebrow">{t("nav.sources")}</span>
                  <strong>{t("sources.title")}</strong>
                </div>
                <p>{t("sources.subtitle")}</p>
                <div className="metric-grid four-column source-kpi-grid">
                  <div><span>{t("sources.total_sources")}</span><strong>{sourceStats.total}</strong></div>
                  <div><span>{t("sources.active_sources")}</span><strong>{sourceStats.active}</strong></div>
                  <div><span>{t("sources.issue_sources")}</span><strong>{sourceStats.issues}</strong></div>
                  <div><span>{t("sources.runtime_records")}</span><strong>{sourceStats.records.toLocaleString()}</strong></div>
                </div>
              </div>

              <div className="workspace-panel source-category-rail">
                <h3>{t("sources.categories")}</h3>
                <div className="source-category-list">
                  {sourceCategories.map((category) => (
                    <button
                      key={`source-category-${category}`}
                      type="button"
                      className={sourceCategory === category ? "source-category active" : "source-category"}
                      onClick={() => {
                        setSourceCategory(category);
                        const nextSource = category === "all"
                          ? sources[0]
                          : sources.find((source) => source.category === category);
                        if (nextSource) selectSource(nextSource.source_id);
                      }}
                    >
                      <span>{sourceLabel("sources.category", category)}</span>
                      <strong>{category === "all" ? sources.length : sourceCategoryCounts.get(category) ?? 0}</strong>
                    </button>
                  ))}
                </div>
                <div className="source-category-summary">
                  <span>{t("sources.missing_credentials")}</span>
                  <strong>{sourceStats.missingCredentials}</strong>
                </div>
              </div>

              <div className="workspace-panel span-2 source-catalog-panel">
                <div className="panel-title-row">
                  <h3>{t("sources.registered_feeds")}</h3>
                  <span>{filteredSources.length} / {sources.length}</span>
                </div>
                <div className="source-health-grid">
                  {filteredSources.map((source) => (
                    <button
                      key={`source-card-${source.source_id}`}
                      type="button"
                      className={selectedSource?.source_id === source.source_id ? "source-health-card active" : "source-health-card"}
                      onClick={() => selectSource(source.source_id)}
                    >
                      <span className={`source-status source-status-${source.connectivity_status}`}>
                        {sourceLabel("sources.status", source.connectivity_status)}
                      </span>
                      <strong>{source.source_system}</strong>
                      <small>{source.description}</small>
                      <span className="source-card-meta">
                        {sourceLabel("sources.category", source.category)} / {source.live_record_count.toLocaleString()} {t("panel.records")}
                      </span>
                    </button>
                  ))}
                </div>
              </div>

              <div className="workspace-panel span-2 source-detail-panel">
                <div className="panel-title-row">
                  <h3>{selectedSource?.source_system ?? t("sources.no_source")}</h3>
                  {selectedSource && (
                    <span className={`source-status source-status-${selectedSource.connectivity_status}`}>
                      {sourceLabel("sources.status", selectedSource.connectivity_status)}
                    </span>
                  )}
                </div>
                {selectedSource && (
                  <>
                    <p>{selectedSource.description}</p>
                    <div className="metric-grid two-column source-detail-metrics">
                      <div><span>{t("sources.category_label")}</span><strong>{sourceLabel("sources.category", selectedSource.category)}</strong></div>
                      <div><span>{t("sources.entitlement")}</span><strong>{selectedSource.entitlement_scope}</strong></div>
                      <div><span>{t("sources.credential_state")}</span><strong>{sourceLabel("sources.credential", selectedSource.credential_state)}</strong></div>
                      <div><span>{t("sources.freshness")}</span><strong>{selectedSource.freshness_expectation_minutes ? `${selectedSource.freshness_expectation_minutes}m` : "n/a"}</strong></div>
                      <div><span>{t("sources.last_success")}</span><strong>{formatSourceTimestamp(selectedSource.last_success_at_utc)}</strong></div>
                      <div><span>{t("sources.last_failure")}</span><strong>{formatSourceTimestamp(selectedSource.last_failure_at_utc)}</strong></div>
                    </div>
                    <div className="source-datasets">
                      <span>{t("panel.datasets")}</span>
                      <div>{selectedSource.datasets.map((dataset) => <strong key={`${selectedSource.source_id}-${dataset}`}>{dataset}</strong>)}</div>
                    </div>
                    <div className="source-diagnostics">
                      <span>{t("sources.diagnostics")}</span>
                      <div>
                        {selectedSource.diagnostics.map((diagnostic) => (
                          <strong key={`${selectedSource.source_id}-${diagnostic}`}>{sourceLabel("sources.diagnostic", diagnostic)}</strong>
                        ))}
                      </div>
                    </div>
                    <p className="source-ingestion-note">
                      {t("sources.latest_ingestion")}: {selectedSource.last_ingestion_status ?? "n/a"}
                      {selectedSource.last_ingestion_message ? ` / ${selectedSource.last_ingestion_message}` : ""}
                    </p>
                  </>
                )}
              </div>

              <div className="workspace-panel source-credential-panel">
                <h3>{t("panel.credentials")}</h3>
                <p>
                  {selectedSource?.credential_provider_id
                    ? `${selectedSource.credential_provider_id}: ${sourceLabel("sources.credential", selectedSource.credential_state)}`
                    : t("credentials.not_required")}
                </p>
                <form className="credential-form source-credential-form" onSubmit={onCredentialSubmit}>
                  <select value={credentialProvider} onChange={(event) => setCredentialProvider(event.target.value)}>
                    {credentialProviders.map((provider) => <option key={provider.provider_id} value={provider.provider_id}>{provider.display_name}</option>)}
                  </select>
                  <input value={credentialLabel} onChange={(event) => setCredentialLabel(event.target.value)} placeholder={t("credentials.label")} />
                  <input type="password" autoComplete="current-password" value={credentialValue} disabled={!selectedCredentialProvider?.credential_required} onChange={(event) => setCredentialValue(event.target.value)} placeholder={selectedCredentialProvider?.credential_required ? t("credentials.api_key") : t("credentials.not_required")} />
                  <button type="submit" disabled={!selectedCredentialProvider?.credential_required || !credentialValue}>{t("credentials.save")}</button>
                </form>
                {selectedSourceCredentialProvider && (
                  <div className="credential-status-card">
                    <span>{selectedSourceCredentialProvider.display_name}</span>
                    <strong>{sourceLabel("sources.credential", selectedSourceCredentialProvider.status)}</strong>
                    <small>{selectedSourceCredentialProvider.last_test_status ?? t("sources.not_tested")}</small>
                  </div>
                )}
                {credentialMessage && <p>{credentialMessage}</p>}
              </div>

              <div className="workspace-panel span-3 source-runtime-panel">
                <div className="section-heading">
                  <span className="eyebrow">{t("data.runtime")}</span>
                  <strong>{t("panel.infrastructure")}</strong>
                </div>
                <div className="metric-grid six-column source-kpi-grid">
                  <div><span>{t("panel.flows")}</span><strong>{flows.filter((item) => item.source_system === "ENTSOG").length}</strong></div>
                  <div><span>{t("panel.capacity")}</span><strong>{capacity.filter((item) => item.source_system === "ENTSOG").length}</strong></div>
                  <div><span>{t("panel.tso_access")}</span><strong>{tsoAccess.length}</strong></div>
                  <div><span>{t("panel.storage")}</span><strong>{storage.filter((item) => item.source_system === "GIE").length}</strong></div>
                  <div><span>{t("panel.lng")}</span><strong>{lng.filter((item) => item.source_system === "GIE").length}</strong></div>
                  <div><span>{t("panel.tariffs")}</span><strong>{ukTariffs.length}</strong></div>
                </div>
                <div className="source-table-split">
                  <div className="data-table">
                    <div className="data-table-row header four"><span>{t("panel.point")}</span><span>{t("panel.direction")}</span><span>{t("panel.capacity_type")}</span><span>mcm/d</span></div>
                    {latestCapacityRows.map((row) => (
                      <div key={`capacity-row-${row.observation_id}`} className="data-table-row four">
                        <strong>{row.point_name}</strong>
                        <span>{row.direction}</span>
                        <span>{row.capacity_type}</span>
                        <span>{row.capacity_mcm_d.toFixed(2)}</span>
                      </div>
                    ))}
                    {latestCapacityRows.length === 0 && (
                      <div className="data-table-row four"><strong>n/a</strong><span>ENTSOG</span><span>{t("data.unavailable")}</span><span>n/a</span></div>
                    )}
                  </div>
                  <div className="data-table tariff-table">
                    <div className="data-table-row header four"><span>{t("panel.point")}</span><span>{t("panel.direction")}</span><span>{t("panel.product")}</span><span>{t("panel.tariff")}</span></div>
                    {ukTariffs.slice(0, 5).map((tariff) => (
                      <div key={`tariff-page-${tariff.tariff_id}`} className="data-table-row four">
                        <strong>{tariff.source_point_name}</strong>
                        <span>{tariff.direction}</span>
                        <span>{tariff.capacity_product}</span>
                        <span>{tariff.tariff_value.toFixed(4)} {tariff.currency}/MWh</span>
                      </div>
                    ))}
                    {ukTariffs.length === 0 && (
                      <div className="data-table-row four"><strong>n/a</strong><span>NTS</span><span>{t("data.unavailable")}</span><span>n/a</span></div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}

          {activeWorkspace === "glossary" && (
            <div className="workspace-grid glossary-page">
              <div className="workspace-panel glossary-index"><h3>{t("panel.glossary")}</h3><input value={glossaryQuery} onChange={(event) => setGlossaryQuery(event.target.value)} placeholder={t("glossary.search")} /><div className="glossary-list compact">{visibleGlossaryTerms.map((term) => <button key={`glossary-nav-${term.term_id}`} type="button" onClick={() => openGlossaryContext(term.term)}><strong>{term.term}</strong><span>{term.category}</span></button>)}</div></div>
              <div className="workspace-panel span-2 glossary-detail"><div className="glossary-controls"><label>{t("glossary.duration_start")}<input type="datetime-local" value={glossaryDurationStart} onChange={(event) => setGlossaryDurationStart(event.target.value)} /></label><label>{t("glossary.duration_end")}<input type="datetime-local" value={glossaryDurationEnd} onChange={(event) => setGlossaryDurationEnd(event.target.value)} /></label></div><div className="context-shortcuts">{glossaryShortcutTerms.map((term) => <button key={`page-shortcut-${term}`} type="button" onClick={() => openGlossaryContext(term)}>{term}</button>)}</div>{glossaryContext ? <div className="glossary-context"><div className="context-heading"><div><strong>{glossaryContext.term}</strong><span>{glossaryContext.context_type}</span></div><span>{glossaryContext.data_quality.runtime_db ? t("data.runtime") : t("data.partial")}</span></div><p>{glossaryContext.description}</p>{glossaryContext.metrics.length > 0 && <div className="metric-grid glossary-metrics">{glossaryContext.metrics.slice(0, 8).map((metric, index) => <div key={`page-glossary-metric-${index}`}><span>{formatContextValue(metric.label)}</span><strong>{formatContextValue(metric.value)} {formatContextValue(metric.unit)}</strong></div>)}</div>}</div> : <div className="glossary-context"><strong>{visibleGlossaryTerms[0]?.term ?? t("panel.glossary")}</strong><p>{visibleGlossaryTerms[0] ? (i18n.language.startsWith("zh") ? visibleGlossaryTerms[0].definition_zh_cn : visibleGlossaryTerms[0].definition_en) : t("status.loading")}</p></div>}</div>
            </div>
          )}

          {activeWorkspace === "runtime" && (
            <div className="workspace-grid runtime-page">
              <div className="workspace-panel"><h3>{t("panel.governance")}</h3>{meta && <div className="metric-grid"><div><span>{t("status.research_only")}</span><strong>{String(meta.research_only)}</strong></div><div><span>{t("status.human_review_required")}</span><strong>{String(meta.human_review_required)}</strong></div><div><span>{t("status.source")}</span><strong>{meta.source_references.join(", ")}</strong></div></div>}</div>
              <div className="workspace-panel span-2"><h3>{t("status.db")}</h3>{runtimeDb && <div className="metric-grid three-column"><div><span>{t("status.db")}</span><strong>{runtimeDb.connectivity.ok ? "ok" : "failed"}</strong></div><div><span>{t("status.alembic")}</span><strong>{runtimeDb.alembic_revision ?? "unavailable"}</strong></div><div><span>{t("status.missing_tables")}</span><strong>{runtimeDb.missing_tables.length}</strong></div></div>}</div>
            </div>
          )}

          {activeWorkspace === "settings" && (
            <div className="workspace-grid settings-page">
              <div className="workspace-panel settings-panel"><h3>{t("panel.settings")}</h3><label>{t("settings.language")}<select value={i18n.language} onChange={(event) => i18n.changeLanguage(event.target.value)}><option value="en">English</option><option value="zh-CN">{t("settings.chinese")}</option></select></label><label>{t("settings.appearance")}<select value={mode} onChange={(event) => setMode(event.target.value as typeof mode)}><option value="light">{t("theme.light")}</option><option value="dark">{t("theme.dark")}</option><option value="system">{t("theme.system")}</option></select></label></div>
              <div className="workspace-panel"><h3>{t("app.title")}</h3><div className="metric-grid"><div><span>{t("map.nodes")}</span><strong>{nodes.length}</strong></div><div><span>{t("map.edges")}</span><strong>{edges.length}</strong></div><div><span>{t("map.routes")}</span><strong>{routes.length}</strong></div></div></div>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

