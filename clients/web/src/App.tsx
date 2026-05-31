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

export default function App() {
  const { t, i18n } = useTranslation();
  const { mode, setMode } = useThemeStore();
  const {
    nodes,
    edges,
    sources,
    markets,
    fxRates,
    flows,
    storage,
    lng,
    routes,
    routeCandidates,
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
  const [glossaryQuery, setGlossaryQuery] = useState("");
  const [analysisQuestion, setAnalysisQuestion] = useState("Summarize current portfolio PnL, route, market, and strategy status.");
  const [invokeDeepSeek, setInvokeDeepSeek] = useState(false);
  const selectedCredentialProvider = useMemo(
    () => credentialProviders.find((provider) => provider.provider_id === credentialProvider),
    [credentialProvider, credentialProviders],
  );
  const [contract, setContract] = useState({
    contract_id: "demo-easington-contract",
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
          observation_id: "operator-sap-demo",
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
          observation_id: "operator-icis-demo",
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
          observation_id: "operator-ocm-demo",
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

  return (
    <div className="app">
      <header className="app-header">
        <div>
          <h1>{t("app.title")}</h1>
          <p>{t("app.subtitle")}</p>
        </div>
        <div className="header-controls">
          <span className={`status-badge status-${dataStatus}`}>{t(`data.${dataStatus}`)}</span>
          <select value={i18n.language} onChange={(event) => i18n.changeLanguage(event.target.value)}>
            <option value="en">English</option>
            <option value="zh-CN">中文</option>
          </select>
          <select value={mode} onChange={(event) => setMode(event.target.value as typeof mode)}>
            <option value="light">{t("theme.light")}</option>
            <option value="dark">{t("theme.dark")}</option>
            <option value="system">{t("theme.system")}</option>
          </select>
        </div>
      </header>

      <nav className="app-nav">
        {["network", "market", "scenario", "strategy", "review", "sources", "glossary", "runtime", "settings"].map(
          (item) => (
            <button key={item} className="nav-btn">
              {t(`nav.${item}`)}
            </button>
          ),
        )}
      </nav>

      <main className="app-main">
        <section className="map-container" id="map">
          <div className="map-toolbar">
            <input
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
              placeholder={t("map.search")}
            />
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
              <span>{[...(strategyResult?.warnings ?? []), ...(meta?.warnings ?? [])][0] ?? t("home.warning_clear")}</span>
            </div>
          </div>
        </section>

        <aside className="sidebar">
          {error && <div className="panel alert">{error}</div>}
          {loading && <div className="panel">{t("status.loading")}</div>}

          <div className="panel">
            <h3>{t("panel.routes")}</h3>
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

          <div className="panel route-economics">
            <h3>{t("panel.easington")}</h3>
            <div className="economics-grid">
              <label>{t("economics.volume")}<input type="number" value={contract.delivery_quantity_mwh_per_day} onChange={(event) => updateContractNumber("delivery_quantity_mwh_per_day", event.target.value)} /></label>
              <label>{t("economics.contract_price")}<input type="number" value={contract.contract_price_gbp_mwh} onChange={(event) => updateContractNumber("contract_price_gbp_mwh", event.target.value)} /></label>
              <label>{t("economics.nbp_price")}<input type="number" value={contract.nbp_sale_price_gbp_mwh} onChange={(event) => updateContractNumber("nbp_sale_price_gbp_mwh", event.target.value)} /></label>
              <label>{t("economics.physical_price")}<input type="number" value={contract.physical_exit_sale_price_gbp_mwh} onChange={(event) => updateContractNumber("physical_exit_sale_price_gbp_mwh", event.target.value)} /></label>
              <label>{t("economics.delivery_tolerance")}<input type="number" value={contract.delivery_tolerance_pct} onChange={(event) => updateContractNumber("delivery_tolerance_pct", event.target.value)} /></label>
              <label>{t("economics.nomination_tolerance")}<input type="number" value={contract.nomination_tolerance_pct} onChange={(event) => updateContractNumber("nomination_tolerance_pct", event.target.value)} /></label>
              <label>{t("economics.cash_lag")}<input type="number" value={contract.screen_sale_cash_lag_days} onChange={(event) => updateContractNumber("screen_sale_cash_lag_days", event.target.value)} /></label>
              <label>{t("economics.finance_rate")}<input type="number" value={contract.annual_financing_rate_pct} onChange={(event) => updateContractNumber("annual_financing_rate_pct", event.target.value)} /></label>
            </div>
            <div className="action-row">
              <button type="button" onClick={() => compareEasingtonOptions(contract)}>{t("economics.compare")}</button>
              <button type="button" onClick={() => markEasingtonLivePnl(contract, [liveMark])}>{t("economics.live_pnl")}</button>
            </div>
            <div className="live-mark-row">
              <span>{liveMark.venue}</span>
              <label>{t("economics.bid")}<input type="number" value={liveMark.bid_gbp_mwh ?? ""} onChange={(event) => updateLiveMarkNumber("bid_gbp_mwh", event.target.value)} /></label>
              <label>{t("economics.ask")}<input type="number" value={liveMark.ask_gbp_mwh ?? ""} onChange={(event) => updateLiveMarkNumber("ask_gbp_mwh", event.target.value)} /></label>
            </div>
            {(livePnl ?? routeOptions)?.options.map((option) => (
              <div key={option.option_id} className="option-row">
                <div>
                  <strong>{option.label}</strong>
                  <span>{option.business_model}</span>
                </div>
                <div>
                  <strong>GBP {Math.round(option.net_pnl_gbp_per_day).toLocaleString()}/d</strong>
                  <span>{option.net_margin_gbp_mwh.toFixed(4)} GBP/MWh</span>
                </div>
              </div>
            ))}
            {livePnl?.live_marks.map((mark) => (
              <div key={`${mark.option_id}-${mark.venue}`} className="option-row live">
                <span>{mark.venue} {mark.product}: {mark.signal.suggested_action}</span>
                <strong>GBP {Math.round(mark.live_net_pnl_gbp_per_day ?? 0).toLocaleString()}/d</strong>
              </div>
            ))}
          </div>

          <div className="panel">
            <h3>{t("panel.market")}</h3>
            <div className="metric-grid">
              {fxRates.slice(0, 2).map((fx) => (
                <div key={fx.pair}>
                  <span>ECB {fx.pair}</span>
                  <strong>{fx.rate}</strong>
                </div>
              ))}
              {markets.slice(0, 3).map((market) => (
                <div key={market.observation_id}>
                  <span>{market.market_venue} {market.product}</span>
                  <strong>{market.price} {market.currency}</strong>
                </div>
              ))}
            </div>
          </div>

          <div className="panel strategy-panel">
            <h3>{t("panel.strategy_lab")}</h3>
            <p>{t("strategy.description")}</p>
            <div className="strategy-summary">
              <span>{t("strategy.window")}: 15:00-17:00</span>
              <span>{t("strategy.bar")}: 5m</span>
              <span>{t("strategy.mode")}: {strategyScenario.run_mode}</span>
            </div>
            <button type="button" onClick={() => evaluateStrategyLab(strategyScenario)}>
              {t("strategy.evaluate")}
            </button>
            {strategyResult && (
              <div className="strategy-result">
                <div className="option-row">
                  <span>{strategyResult.status}</span>
                  <strong>{strategyResult.candidate_action_for_review}</strong>
                </div>
                <div className="metric-grid">
                  <div>
                    <span>{t("strategy.day_ahead")}</span>
                    <strong>{strategyResult.day_ahead_average_gbp_mwh?.toFixed(2) ?? "n/a"}</strong>
                  </div>
                  <div>
                    <span>{t("strategy.intraday")}</span>
                    <strong>{strategyResult.intraday_average_gbp_mwh?.toFixed(2) ?? "n/a"}</strong>
                  </div>
                  <div>
                    <span>{t("strategy.spread")}</span>
                    <strong>{strategyResult.intraday_vs_day_ahead_spread_gbp_mwh?.toFixed(2) ?? "n/a"}</strong>
                  </div>
                </div>
                {strategyResult.allocation_targets.map((target) => (
                  <div key={target.market_bucket} className="option-row live">
                    <span>{target.market_bucket}: {target.target_allocation_pct.toFixed(1)}%</span>
                    <strong>{Math.round(target.target_quantity_mwh_per_day).toLocaleString()} MWh/d</strong>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="panel">
            <h3>{t("panel.sources")}</h3>
            <p>{sources.length} {t("panel.sources_registered")}</p>
            <ul className="source-list">
              {sources.slice(0, 5).map((source) => (
                <li key={source.source_id}>
                  {source.source_system}: {source.status}
                  {source.live_record_count > 0 ? ` (${source.live_record_count})` : ""}
                </li>
              ))}
            </ul>
          </div>

          <div className="panel">
            <h3>{t("panel.infrastructure")}</h3>
            <div className="metric-grid">
              <div>
                <span>{t("panel.flows")}</span>
                <strong>{flows.filter((item) => item.source_system === "ENTSOG").length}</strong>
              </div>
              <div>
                <span>{t("panel.storage")}</span>
                <strong>{storage.filter((item) => item.source_system === "GIE").length}</strong>
              </div>
              <div>
                <span>{t("panel.lng")}</span>
                <strong>{lng.filter((item) => item.source_system === "GIE").length}</strong>
              </div>
            </div>
          </div>

          <div className="panel glossary-panel">
            <h3>{t("panel.glossary")}</h3>
            <input
              value={glossaryQuery}
              onChange={(event) => setGlossaryQuery(event.target.value)}
              placeholder={t("glossary.search")}
            />
            <div className="glossary-list">
              {visibleGlossaryTerms.map((term) => (
                <div key={term.term_id} className="glossary-row">
                  <div>
                    <strong>{term.term}</strong>
                    <span>{t("glossary.category")}: {term.category}</span>
                  </div>
                  <p>{i18n.language.startsWith("zh") ? term.definition_zh_cn : term.definition_en}</p>
                  <button type="button" onClick={() => fetchGlossaryContext(term.term)}>
                    {t("glossary.context")}
                  </button>
                  {term.related_terms.length > 0 && (
                    <span>{t("glossary.related")}: {term.related_terms.slice(0, 4).join(", ")}</span>
                  )}
                </div>
              ))}
            </div>
            {glossaryContext && (
              <div className="glossary-context">
                <strong>{glossaryContext.term}: {glossaryContext.context_type}</strong>
                <p>{glossaryContext.description}</p>
                {glossaryContext.capacity_usage && (
                  <span>
                    {t("glossary.capacity_usage")}: {String(glossaryContext.capacity_usage.usage_pct ?? "n/a")}%
                  </span>
                )}
                {glossaryContext.related_prices.slice(0, 3).map((price, index) => (
                  <span key={`${glossaryContext.term}-price-${index}`}>
                    {String(price.market_venue ?? price.source_system ?? "price")}: {String(price.price ?? "n/a")}
                  </span>
                ))}
              </div>
            )}
          </div>

          <div className="panel analysis-panel">
            <h3>{t("panel.analysis")}</h3>
            <textarea
              value={analysisQuestion}
              onChange={(event) => setAnalysisQuestion(event.target.value)}
              rows={4}
            />
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={invokeDeepSeek}
                onChange={(event) => setInvokeDeepSeek(event.target.checked)}
              />
              {t("analysis.invoke_deepseek")}
            </label>
            <div className="action-row">
              <button type="button" onClick={() => askAnalysis(analysisPayload)}>
                {t("analysis.ask")}
              </button>
              <button type="button" onClick={() => generatePortfolioReport(analysisPayload)}>
                {t("analysis.report")}
              </button>
            </div>
            {analysisResult && (
              <div className="analysis-result">
                <strong>{analysisResult.provider_id}: {analysisResult.provider_status}</strong>
                <p>{i18n.language.startsWith("zh") ? analysisResult.answer_zh_cn : analysisResult.answer_en}</p>
                {analysisResult.sections.map((section) => (
                  <div key={section.section_id} className="analysis-section">
                    <strong>{section.title}</strong>
                    <span>{section.content}</span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="panel">
            <h3>{t("panel.credentials")}</h3>
            <form className="credential-form" onSubmit={onCredentialSubmit}>
              <select value={credentialProvider} onChange={(event) => setCredentialProvider(event.target.value)}>
                {credentialProviders.map((provider) => (
                  <option key={provider.provider_id} value={provider.provider_id}>
                    {provider.display_name}
                  </option>
                ))}
              </select>
              <input
                value={credentialLabel}
                onChange={(event) => setCredentialLabel(event.target.value)}
                placeholder={t("credentials.label")}
              />
              <input
                type="password"
                value={credentialValue}
                disabled={!selectedCredentialProvider?.credential_required}
                onChange={(event) => setCredentialValue(event.target.value)}
                placeholder={
                  selectedCredentialProvider?.credential_required
                    ? t("credentials.api_key")
                    : t("credentials.not_required")
                }
              />
              <button type="submit" disabled={!selectedCredentialProvider?.credential_required || !credentialValue}>
                {t("credentials.save")}
              </button>
            </form>
            {credentialMessage && <p>{credentialMessage}</p>}
            <ul className="source-list">
              {credentialProviders.map((provider) => (
                <li key={provider.provider_id}>
                  {provider.display_name}: {provider.configured ? provider.redacted_preview : provider.status}
                </li>
              ))}
            </ul>
          </div>

          <div className="panel settings-panel">
            <h3>{t("panel.settings")}</h3>
            <label>
              {t("settings.language")}
              <select value={i18n.language} onChange={(event) => i18n.changeLanguage(event.target.value)}>
                <option value="en">English</option>
                <option value="zh-CN">中文</option>
              </select>
            </label>
            <label>
              {t("settings.appearance")}
              <select value={mode} onChange={(event) => setMode(event.target.value as typeof mode)}>
                <option value="light">{t("theme.light")}</option>
                <option value="dark">{t("theme.dark")}</option>
                <option value="system">{t("theme.system")}</option>
              </select>
            </label>
          </div>

          <div className="panel">
            <h3>{t("panel.governance")}</h3>
            {meta && (
              <>
                <p>{t("status.research_only")}: {String(meta.research_only)}</p>
                <p>{t("status.human_review_required")}: {String(meta.human_review_required)}</p>
                <p>{t("status.source")}: {meta.source_references.join(", ")}</p>
              </>
            )}
            {runtimeDb && (
              <>
                <p>{t("status.db")}: {runtimeDb.connectivity.ok ? "ok" : "failed"}</p>
                <p>{t("status.alembic")}: {runtimeDb.alembic_revision ?? "unavailable"}</p>
                <p>{t("status.missing_tables")}: {runtimeDb.missing_tables.length}</p>
              </>
            )}
          </div>
        </aside>
      </main>
    </div>
  );
}
