import type {
  FxRateDTO,
  MarketObsDTO,
  PortfolioResourceDTO,
  StrategyLabRequestDTO,
  StrategyLabResultDTO,
  StrategyPriceObservationDTO,
} from "@/api/client";
import {
  StrategyBasisExposureLadder,
  StrategyContractPnlAttribution,
  StrategyPnlCurvePanel,
  StrategyPriceBasisBoard,
} from "@/components/strategy/StrategyShadowRunSections";
import type {
  PriceBasisId,
  StrategyBasisExposureRow,
  StrategyContractPnlRow,
  StrategyPnlCurveRow,
  StrategyPriceBasisRow,
} from "@/components/strategy/StrategyShadowRunSections";
import { useMemo, useState } from "react";

type Translate = (key: string) => string;

interface StrategyShadowRunTerminalProps {
  strategyScenario: StrategyLabRequestDTO;
  strategyResult: StrategyLabResultDTO | null;
  portfolioResources: PortfolioResourceDTO[];
  marketObservations: MarketObsDTO[];
  fxRates: FxRateDTO[];
  language: string;
  loading: boolean;
  t: Translate;
  onEvaluate: () => void;
}

const PRICE_BASIS_ORDER: PriceBasisId[] = [
  "WITHIN_DAY",
  "DAY_AHEAD",
  "MONTHLY",
  "ICIS_ASSESSMENT",
  "ICE_OCM_MARK",
  "EEX_CURVE",
  "FX",
];

const STALE_HOURS_BY_BASIS: Record<PriceBasisId, number> = {
  WITHIN_DAY: 2,
  DAY_AHEAD: 36,
  MONTHLY: 120,
  ICIS_ASSESSMENT: 72,
  ICE_OCM_MARK: 2,
  EEX_CURVE: 24,
  FX: 72,
};

function formatMoney(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return value.toFixed(2);
}

function formatQuantity(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  return `${Math.round(value).toLocaleString()} MWh/d`;
}

function formatSignedMoney(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
  const sign = value > 0 ? "+" : "";
  return `${sign}${Math.round(value).toLocaleString()}`;
}

function formatTimestamp(value: string | null | undefined, language: string): string {
  if (!value) return "n/a";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "n/a";
  return new Intl.DateTimeFormat(language.startsWith("zh") ? "zh-CN" : "en-GB", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
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

function sourceHaystack(price: StrategyPriceObservationDTO): string {
  return [
    price.source_system,
    price.venue,
    price.hub,
    price.product,
    price.price_name,
    price.source_reference ?? "",
  ].join(" ").toUpperCase();
}

function classifyPriceBasis(price: StrategyPriceObservationDTO): PriceBasisId {
  const haystack = sourceHaystack(price);
  if (haystack.includes("ICIS")) return "ICIS_ASSESSMENT";
  if (haystack.includes("ICE_OCM") || haystack.includes("ICE OCM")) return "ICE_OCM_MARK";
  if (haystack.includes("EEX") || haystack.includes("CURVE") || haystack.includes("FUTURE")) {
    return "EEX_CURVE";
  }
  if (haystack.includes("MONTH") || haystack.includes("M+")) return "MONTHLY";
  if (haystack.includes("WITHIN") || haystack.includes("INTRADAY")) return "WITHIN_DAY";
  return "DAY_AHEAD";
}

function priceMatchesBasis(price: StrategyPriceObservationDTO, basis: PriceBasisId): boolean {
  const haystack = sourceHaystack(price);
  if (basis === "FX") return false;
  if (classifyPriceBasis(price) === basis) return true;
  if (basis === "WITHIN_DAY") return haystack.includes("WITHIN") || haystack.includes("INTRADAY");
  if (basis === "DAY_AHEAD") return haystack.includes("DAY-AHEAD") || haystack.includes("DAY AHEAD") || haystack.includes("SAP");
  if (basis === "MONTHLY") return haystack.includes("MONTH") || haystack.includes("M+");
  if (basis === "ICIS_ASSESSMENT") return haystack.includes("ICIS") || haystack.includes("HEREN");
  if (basis === "ICE_OCM_MARK") return haystack.includes("ICE_OCM") || haystack.includes("ICE OCM") || haystack.includes("OCM");
  return haystack.includes("EEX") || haystack.includes("CURVE") || haystack.includes("FUTURE");
}

function isSimulatedSource(sourceSystem: string | null | undefined): boolean {
  return Boolean(sourceSystem?.toUpperCase().includes("_SIM"));
}

function observedAtMs(value: string | null | undefined): number {
  if (!value) return 0;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function isStaleObservation(
  observedAtUtc: string | null | undefined,
  maxAgeHours: number,
  nowMs = Date.now(),
): boolean {
  const observedMs = observedAtMs(observedAtUtc);
  if (observedMs <= 0) return true;
  return nowMs - observedMs > maxAgeHours * 60 * 60 * 1000;
}

function latestPriceObservation(
  observations: StrategyPriceObservationDTO[],
): StrategyPriceObservationDTO | null {
  return observations.reduce<StrategyPriceObservationDTO | null>((latest, observation) => {
    if (!latest) return observation;
    return observedAtMs(observation.observed_at_utc) > observedAtMs(latest.observed_at_utc)
      ? observation
      : latest;
  }, null);
}

function average(values: number[]): number | null {
  if (values.length === 0) return null;
  return values.reduce((total, value) => total + value, 0) / values.length;
}

function uniqueStrings(values: Array<string | null | undefined>): string[] {
  return Array.from(new Set(values.filter((value): value is string => Boolean(value))));
}

function basisLabelKey(basis: PriceBasisId): string {
  return `strategy.basis.${basis.toLowerCase()}`;
}

export function StrategyShadowRunTerminal({
  strategyScenario,
  strategyResult,
  portfolioResources,
  marketObservations,
  fxRates,
  language,
  loading,
  t,
  onEvaluate,
}: StrategyShadowRunTerminalProps) {
  const [activeBasis, setActiveBasis] = useState<PriceBasisId>("WITHIN_DAY");
  const combinedPriceTape = useMemo(() => {
    const observed = [
      ...strategyScenario.price_observations,
      ...marketObservations.map(tapePriceFromMarketObservation),
    ];
    const seen = new Set<string>();
    return observed.filter((price) => {
      const key = `${price.observation_id}:${price.source_system}:${price.price_name}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
  }, [strategyScenario.price_observations, marketObservations]);
  const priceTape = combinedPriceTape.slice(0, 12);
  const resourcePoolRows = useMemo(() => {
    if (portfolioResources.length > 0) {
      return portfolioResources.map((resource) => ({
        resourceId: resource.resource_id,
        resourceName: resource.resource_name,
        quantityMwhPerDay: resource.available_quantity_mwh_per_day,
        costGbpMwh:
          resource.contract_cost_gbp_mwh +
          (resource.variable_cost_gbp_mwh ?? 0) +
          (resource.tolerance_risk_allowance_gbp_mwh ?? 0),
      }));
    }
    return strategyScenario.resource_contexts.map((resource) => ({
      resourceId: resource.resource_id,
      resourceName: resource.resource_name,
      quantityMwhPerDay: resource.available_quantity_mwh_per_day,
      costGbpMwh:
        resource.all_in_cost_gbp_mwh + (resource.balancing_allowance_gbp_mwh ?? 0),
    }));
  }, [portfolioResources, strategyScenario.resource_contexts]);
  const totalPoolQuantityMwhPerDay = resourcePoolRows.reduce(
    (total, resource) => total + resource.quantityMwhPerDay,
    0,
  );
  const weightedPoolCostGbpMwh =
    totalPoolQuantityMwhPerDay > 0
      ? resourcePoolRows.reduce(
          (total, resource) =>
            total + resource.quantityMwhPerDay * resource.costGbpMwh,
          0,
        ) / totalPoolQuantityMwhPerDay
      : null;
  const nowMs = Date.now();
  const priceBasisRows = useMemo<StrategyPriceBasisRow[]>(() => (
    PRICE_BASIS_ORDER.map((basis) => {
      if (basis === "FX") {
        const latestFx = fxRates.reduce<FxRateDTO | null>((latest, rate) => {
          if (!latest) return rate;
          return observedAtMs(rate.observed_at_utc) > observedAtMs(latest.observed_at_utc)
            ? rate
            : latest;
        }, null);
        return {
          basis,
          latestPrice: latestFx?.rate ?? null,
          observationCount: fxRates.length,
          sourceSystems: uniqueStrings(fxRates.map((rate) => rate.source_system)),
          simulatedCount: fxRates.filter((rate) => isSimulatedSource(rate.source_system)).length,
          staleCount: fxRates.filter((rate) =>
            isStaleObservation(rate.observed_at_utc, STALE_HOURS_BY_BASIS.FX, nowMs),
          ).length,
          latestObservedAtUtc: latestFx?.observed_at_utc ?? null,
        };
      }
      const observations = combinedPriceTape.filter((price) => priceMatchesBasis(price, basis));
      const latest = latestPriceObservation(observations);
      const observedPrices = observations
        .map((price) => price.price_gbp_mwh)
        .filter((value) => Number.isFinite(value));
      return {
        basis,
        latestPrice: latest?.price_gbp_mwh ?? average(observedPrices),
        observationCount: observations.length,
        sourceSystems: uniqueStrings(observations.map((price) => price.source_system)),
        simulatedCount: observations.filter((price) => isSimulatedSource(price.source_system)).length,
        staleCount: observations.filter((price) =>
          isStaleObservation(price.observed_at_utc, STALE_HOURS_BY_BASIS[basis], nowMs),
        ).length,
        latestObservedAtUtc: latest?.observed_at_utc ?? null,
      };
    })
  ), [combinedPriceTape, fxRates, nowMs]);
  const pnlCurveRows = useMemo<StrategyPnlCurveRow[]>(() => (
    priceBasisRows
      .filter((row) => row.basis !== "FX")
      .map((row) => {
        const margin =
          row.latestPrice !== null && weightedPoolCostGbpMwh !== null
            ? row.latestPrice - weightedPoolCostGbpMwh
            : null;
        return {
          basis: row.basis,
          latestPrice: row.latestPrice,
          marginGbpMwh: margin,
          pnlGbpPerDay:
            margin !== null && totalPoolQuantityMwhPerDay > 0
              ? margin * totalPoolQuantityMwhPerDay
              : null,
          poolQuantityMwhPerDay: totalPoolQuantityMwhPerDay,
          weightedPoolCostGbpMwh,
          sourceSystems: row.sourceSystems,
          simulatedCount: row.simulatedCount,
          staleCount: row.staleCount,
        };
      })
  ), [priceBasisRows, totalPoolQuantityMwhPerDay, weightedPoolCostGbpMwh]);
  const basisExposureRows = useMemo<StrategyBasisExposureRow[]>(() => (
    pnlCurveRows.map((row) => ({
      basis: row.basis,
      latestPrice: row.latestPrice,
      basisMarginVsPoolCost: row.marginGbpMwh,
      poolPnlAtRiskGbpPerDay: row.pnlGbpPerDay,
      poolQuantityMwhPerDay: row.poolQuantityMwhPerDay,
      weightedPoolCostGbpMwh: row.weightedPoolCostGbpMwh,
      observationCount:
        priceBasisRows.find((basisRow) => basisRow.basis === row.basis)?.observationCount ?? 0,
      sourceSystems: row.sourceSystems,
      simulatedCount: row.simulatedCount,
      staleCount: row.staleCount,
    }))
  ), [pnlCurveRows, priceBasisRows]);
  const activeBasisRow =
    priceBasisRows.find((row) => row.basis === activeBasis) ?? priceBasisRows[0];
  const activePnlRow =
    activeBasis === "FX" ? null : pnlCurveRows.find((row) => row.basis === activeBasis) ?? null;
  const contractPnlRows = useMemo<StrategyContractPnlRow[]>(() => {
    const activeSalePrice = activePnlRow?.latestPrice ?? null;
    return resourcePoolRows.map((resource) => {
      const marginGbpMwh =
        activeSalePrice !== null ? activeSalePrice - resource.costGbpMwh : null;
      return {
        ...resource,
        marginGbpMwh,
        dailyPnlGbp:
          marginGbpMwh !== null
            ? marginGbpMwh * resource.quantityMwhPerDay
            : null,
      };
    });
  }, [activePnlRow, resourcePoolRows]);
  const hasSelectedContractPnl = contractPnlRows.some((row) => row.dailyPnlGbp !== null);
  const selectedContractPnlGbpPerDay = hasSelectedContractPnl
    ? contractPnlRows.reduce((total, row) => total + (row.dailyPnlGbp ?? 0), 0)
    : null;
  const simulatedBasisCount = priceBasisRows.filter((row) => row.simulatedCount > 0).length;
  const staleBasisCount = priceBasisRows.filter((row) => row.staleCount > 0).length;
  const unavailableBasisCount = priceBasisRows.filter((row) => row.observationCount === 0).length;
  const maxAbsPnl = Math.max(
    ...pnlCurveRows
      .map((row) => Math.abs(row.pnlGbpPerDay ?? 0))
      .filter((value) => Number.isFinite(value)),
    1,
  );
  const dataQualityFlags = priceBasisRows.flatMap((row) => {
    const label = t(basisLabelKey(row.basis));
    const flags: string[] = [];
    if (row.observationCount === 0) flags.push(`${t("data.unavailable")}: ${label}`);
    if (row.simulatedCount > 0) flags.push(`${t("strategy.simulated_data")}: ${label}`);
    if (row.staleCount > 0) flags.push(`${t("strategy.stale_data")}: ${label}`);
    return flags;
  });
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

      <StrategyPriceBasisBoard
        rows={priceBasisRows}
        activeBasis={activeBasis}
        simulatedBasisCount={simulatedBasisCount}
        staleBasisCount={staleBasisCount}
        unavailableBasisCount={unavailableBasisCount}
        language={language}
        t={t}
        onSelectBasis={setActiveBasis}
      />

      <section className="workspace-panel span-2 strategy-pnl-scenario-comparison">
        <div className="panel-title-row">
          <h3>{t("strategy.selected_price_basis")}</h3>
          <span>{activeBasisRow ? t(basisLabelKey(activeBasisRow.basis)) : t("data.unavailable")}</span>
        </div>
        <div className="metric-grid">
          <div>
            <span>{t("strategy.latest_price")}</span>
            <strong>{formatMoney(activeBasisRow?.latestPrice)} {activeBasis === "FX" ? "" : "GBP/MWh"}</strong>
          </div>
          <div>
            <span>{t("strategy.weighted_pool_cost")}</span>
            <strong>{formatMoney(weightedPoolCostGbpMwh)} GBP/MWh</strong>
          </div>
          <div>
            <span>{t("strategy.spread")}</span>
            <strong>{formatMoney(activePnlRow?.marginGbpMwh)} GBP/MWh</strong>
          </div>
          <div>
            <span>{t("strategy.pool_volume")}</span>
            <strong>{formatQuantity(totalPoolQuantityMwhPerDay)}</strong>
          </div>
          <div>
            <span>{t("strategy.contract_pnl_attribution")}</span>
            <strong>{formatSignedMoney(selectedContractPnlGbpPerDay)} GBP/d</strong>
          </div>
          <div>
            <span>{t("strategy.observations")}</span>
            <strong>{activeBasisRow?.observationCount ?? 0}</strong>
          </div>
        </div>
        <StrategyContractPnlAttribution rows={contractPnlRows} t={t} />
      </section>

      <StrategyBasisExposureLadder rows={basisExposureRows} t={t} />

      <StrategyPnlCurvePanel
        rows={pnlCurveRows}
        maxAbsPnl={maxAbsPnl}
        weightedPoolCostGbpMwh={weightedPoolCostGbpMwh}
        totalPoolQuantityMwhPerDay={totalPoolQuantityMwhPerDay}
        t={t}
      />

      <section className="workspace-panel strategy-data-quality-flags">
        <h3>{t("strategy.data_quality")}</h3>
        <div className="review-warning-list">
          {dataQualityFlags.length > 0
            ? dataQualityFlags.slice(0, 10).map((flag) => <span key={`strategy-quality-${flag}`}>{flag}</span>)
            : <span>{t("review.no_warnings")}</span>}
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
              <small>{price.price_name} / {price.source_system}</small>
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
