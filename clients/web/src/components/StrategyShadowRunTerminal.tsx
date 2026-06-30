import type {
  MarketObsDTO,
  PortfolioResourceDTO,
  StrategyLabRequestDTO,
  StrategyLabResultDTO,
  StrategyPriceObservationDTO,
} from "@/api/client";

type Translate = (key: string) => string;

interface StrategyShadowRunTerminalProps {
  strategyScenario: StrategyLabRequestDTO;
  strategyResult: StrategyLabResultDTO | null;
  portfolioResources: PortfolioResourceDTO[];
  marketObservations: MarketObsDTO[];
  loading: boolean;
  t: Translate;
  onEvaluate: () => void;
}

function formatMoney(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return value.toFixed(2);
}

function formatQuantity(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return `${Math.round(value).toLocaleString()} MWh/d`;
}

function riskValue(riskControl: Record<string, unknown> | undefined, key: string): string {
  const value = riskControl?.[key];
  if (typeof value === "number" && Number.isFinite(value)) return value.toLocaleString();
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (typeof value === "string" && value.trim()) return value;
  return "n/a";
}

function tapePriceFromMarketObservation(item: MarketObsDTO): StrategyPriceObservationDTO {
  return {
    observation_id: item.observation_id,
    source_system: item.source_system ?? "market-observation",
    venue: item.market_venue,
    hub: item.market_venue,
    product: item.product,
    price_name: item.product,
    price_gbp_mwh: item.price,
    observed_at_utc: item.observed_at_utc ?? item.period_start_utc,
    delivery_start_utc: item.period_start_utc,
    delivery_end_utc: item.period_end_utc,
    source_reference: item.source_reference,
  };
}

export function StrategyShadowRunTerminal({
  strategyScenario,
  strategyResult,
  portfolioResources,
  marketObservations,
  loading,
  t,
  onEvaluate,
}: StrategyShadowRunTerminalProps) {
  const priceTape =
    strategyScenario.price_observations.length > 0
      ? strategyScenario.price_observations
      : marketObservations.slice(0, 8).map(tapePriceFromMarketObservation);
  const source_refs = strategyResult?.source_refs.length
    ? strategyResult.source_refs
    : priceTape
        .map((item) => item.source_reference ?? item.source_system)
        .filter((item): item is string => Boolean(item));
  const warningStack = [
    ...(strategyResult?.missing_inputs ?? []),
    ...(strategyResult?.warnings ?? []),
    ...(!strategyResult?.human_review_required ? [] : ["HUMAN_REVIEW_REQUIRED"]),
  ];
  const firstResource = portfolioResources[0] ?? strategyScenario.resource_contexts[0];
  const candidateAction =
    strategyResult?.candidate_action_for_review ?? t("strategy.awaiting_shadow_run");

  return (
    <div className="workspace-grid strategy-page strategy-shadow-run-terminal">
      <section className="workspace-panel span-2 strategy-command-deck">
        <div className="section-heading">
          <span className="eyebrow">{t("strategy.shadow_terminal")}</span>
          <strong>{strategyScenario.strategy_name}</strong>
        </div>
        <p className="panel-copy">{t("strategy.description")}</p>
        <div className="strategy-summary">
          <span>{t("strategy.window")}: 15:00-17:00</span>
          <span>{t("strategy.bar")}: 5m</span>
          <span>{t("strategy.mode")}: {strategyScenario.run_mode}</span>
          <span>{t("strategy.no_execution")}</span>
        </div>
        <div className="strategy-command-actions">
          <button type="button" disabled={loading} onClick={onEvaluate}>
            {t("strategy.evaluate")}
          </button>
          <span className="status-badge">{t("strategy.paper_state")}</span>
        </div>
      </section>

      <section className="workspace-panel strategy-paper-state">
        <h3>{t("strategy.paper_state")}</h3>
        <div className="strategy-candidate-action">
          <span>{strategyResult?.status ?? t("home.not_running")}</span>
          <strong>{candidateAction}</strong>
          <small>{strategyResult?.human_review_required ? t("review.title") : t("strategy.no_execution")}</small>
        </div>
        <div className="metric-grid">
          <div><span>{t("strategy.day_ahead")}</span><strong>{formatMoney(strategyResult?.day_ahead_average_gbp_mwh)}</strong></div>
          <div><span>{t("strategy.intraday")}</span><strong>{formatMoney(strategyResult?.intraday_average_gbp_mwh)}</strong></div>
          <div><span>{t("strategy.spread")}</span><strong>{formatMoney(strategyResult?.intraday_vs_day_ahead_spread_gbp_mwh)}</strong></div>
        </div>
      </section>

      <section className="workspace-panel strategy-risk-stack">
        <h3>{t("strategy.risk_controls")}</h3>
        <div className="metric-grid">
          <div><span>Max OCM</span><strong>{riskValue(strategyScenario.risk_control, "max_ocm_allocation_pct")}%</strong></div>
          <div><span>Min day-ahead</span><strong>{riskValue(strategyScenario.risk_control, "min_day_ahead_allocation_pct")}%</strong></div>
          <div><span>Max market</span><strong>{riskValue(strategyScenario.risk_control, "max_single_market_volume_mwh_per_day")}</strong></div>
          <div><span>TSO access</span><strong>{riskValue(strategyScenario.risk_control, "require_tso_access")}</strong></div>
        </div>
      </section>

      <section className="workspace-panel span-2 strategy-market-tape">
        <div className="panel-title-row">
          <h3>{t("strategy.market_tape")}</h3>
          <span>{priceTape.length} {t("panel.records")}</span>
        </div>
        <div className="strategy-tape-grid">
          {priceTape.map((price) => (
            <div key={`strategy-tape-${price.observation_id}`} className="strategy-tape-card">
              <span>{price.venue} / {price.hub}</span>
              <strong>{formatMoney(price.price_gbp_mwh)} GBP/MWh</strong>
              <small>{price.price_name} · {price.source_system}</small>
            </div>
          ))}
          {priceTape.length === 0 && <p className="panel-copy">{t("data.unavailable")}</p>}
        </div>
      </section>

      <section className="workspace-panel strategy-resource-stack">
        <h3>{t("home.resource_pool")}</h3>
        <div className="net-pnl-card">
          <span>{firstResource?.resource_name ?? t("data.unavailable")}</span>
          <strong>{formatQuantity(firstResource?.available_quantity_mwh_per_day)}</strong>
          <small>{portfolioResources.length} {t("home.resources")}</small>
        </div>
      </section>

      <section className="workspace-panel span-2 strategy-allocation-ladder">
        <h3>{t("strategy.allocation_targets")}</h3>
        <div className="data-table">
          <div className="data-table-row header four"><span>Bucket</span><span>Target</span><span>Quantity</span><span>Reference</span></div>
          {strategyResult?.allocation_targets.map((target) => (
            <div key={`shadow-target-${target.market_bucket}`} className="data-table-row four">
              <strong>{target.market_bucket}</strong>
              <span>{target.target_allocation_pct.toFixed(1)}%</span>
              <span>{formatQuantity(target.target_quantity_mwh_per_day)}</span>
              <span>{formatMoney(target.reference_price_gbp_mwh)}</span>
            </div>
          ))}
          {!strategyResult && (
            <div className="data-table-row four"><strong>{t("home.not_running")}</strong><span>n/a</span><span>n/a</span><span>{t("strategy.no_execution")}</span></div>
          )}
        </div>
      </section>

      <section className="workspace-panel strategy-source-evidence">
        <h3>{t("strategy.source_evidence")}</h3>
        <div className="source-chip-list">
          {source_refs.slice(0, 8).map((source) => <span key={`strategy-source-${source}`}>{source}</span>)}
          {source_refs.length === 0 && <span>{t("data.partial")}</span>}
        </div>
      </section>

      <section className="workspace-panel strategy-warning-stack">
        <h3>{t("strategy.warning_stack")}</h3>
        <div className="review-warning-list">
          {warningStack.length > 0
            ? warningStack.slice(0, 8).map((warning) => <span key={`strategy-warning-${warning}`}>{warning}</span>)
            : <span>{t("review.no_warnings")}</span>}
        </div>
      </section>
    </div>
  );
}
