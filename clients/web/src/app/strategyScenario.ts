import type { StrategyPriceObservationDTO } from "@/api/client";
import type { ContractDraft } from "./defaultContractDraft";
import {
  isGasPriceObservation,
  marketObservationHub,
  marketObservationTenor,
  marketPriceGbpMwh,
  newestObservation,
} from "./marketPriceNormalization";
import type { FxRateLike, MarketObservationLike } from "./marketPriceNormalization";

type MarketLike = MarketObservationLike & {
  observation_id: string;
  period_end_utc: string;
  source_system?: string;
  source_reference?: string;
};

type LiveMarkLike = {
  venue: string;
  hub: string;
  product: string;
  bid_gbp_mwh: number | null;
  ask_gbp_mwh: number | null;
  last_gbp_mwh: number | null;
  mark_time_utc?: string;
  source_system: string;
};

type PortfolioResourceLike = {
  resource_id?: string;
  resource_name?: string;
  available_quantity_mwh_per_day?: number;
  contract_cost_gbp_mwh?: number | null;
  tolerance_risk_allowance_gbp_mwh?: number | null;
  delivery_tolerance_pct?: number | null;
  nomination_tolerance_pct?: number | null;
  required_tso_access?: string[];
  accessible_tsos?: string[] | null;
};

function observationHaystack(observation: MarketLike): string {
  return [
    observation.market_venue,
    observation.product,
    observation.source_system ?? "",
    observation.source_reference ?? "",
    marketObservationTenor(observation),
  ].join(" ").toUpperCase();
}

function latestPositiveObservation(
  markets: MarketLike[],
  fxRates: FxRateLike[],
  predicate: (observation: MarketLike) => boolean,
): MarketLike | null {
  return newestObservation(markets.filter((observation) => {
    if (!isGasPriceObservation(observation) || !predicate(observation)) return false;
    const converted = marketPriceGbpMwh(observation, fxRates);
    return converted !== null && converted > 0;
  }));
}

function strategyObservation(
  observation: MarketLike,
  priceName: string,
  fxRates: FxRateLike[],
): StrategyPriceObservationDTO | null {
  const convertedPrice = marketPriceGbpMwh(observation, fxRates);
  if (convertedPrice === null || convertedPrice <= 0) return null;
  return {
    observation_id: observation.observation_id,
    source_system: observation.source_system ?? "market-observation",
    venue: observation.market_venue,
    hub: marketObservationHub(observation),
    product: observation.product,
    price_name: priceName,
    price_gbp_mwh: convertedPrice,
    observed_at_utc: observation.observed_at_utc ?? observation.period_start_utc ?? "",
    delivery_start_utc: observation.period_start_utc ?? observation.observed_at_utc ?? "",
    delivery_end_utc: observation.period_end_utc,
    bar_minutes: marketObservationTenor(observation).includes("within") ? 5 : null,
    source_reference: observation.source_reference ?? observation.observation_id,
  };
}

function positiveLiveMark(liveMark: LiveMarkLike): number | null {
  const candidates = [liveMark.last_gbp_mwh, liveMark.bid_gbp_mwh, liveMark.ask_gbp_mwh];
  return candidates.find((value): value is number => (
    typeof value === "number" && Number.isFinite(value) && value > 0
  )) ?? null;
}

export function buildStrategyScenario(
  contract: ContractDraft,
  liveMark: LiveMarkLike,
  markets: MarketLike[],
  portfolioResources: PortfolioResourceLike[],
  fxRates: FxRateLike[],
) {
  const nbpMarkets = markets.filter((observation) => marketObservationHub(observation).toUpperCase() === "NBP");
  const sapRow = latestPositiveObservation(
    nbpMarkets,
    fxRates,
    (observation) => observationHaystack(observation).includes("SAP"),
  );
  const icisRow = latestPositiveObservation(
    nbpMarkets,
    fxRates,
    (observation) => observationHaystack(observation).includes("ICIS"),
  );
  const fallbackDayAheadRow = latestPositiveObservation(
    nbpMarkets,
    fxRates,
    (observation) => {
      const tenor = marketObservationTenor(observation);
      return tenor.includes("day-ahead") || tenor.includes("day ahead");
    },
  );
  const ocmRow = latestPositiveObservation(
    nbpMarkets,
    fxRates,
    (observation) => {
      const tenor = marketObservationTenor(observation);
      const haystack = observationHaystack(observation);
      return (tenor.includes("within") || tenor.includes("intraday")) && haystack.includes("OCM");
    },
  );

  const dayAheadObservations = [
    sapRow ? strategyObservation(sapRow, "SAP", fxRates) : null,
    icisRow ? strategyObservation(icisRow, "ICIS_HEREN_DAY_AHEAD", fxRates) : null,
  ].filter((observation): observation is StrategyPriceObservationDTO => observation !== null);
  if (dayAheadObservations.length === 0 && fallbackDayAheadRow) {
    const fallback = strategyObservation(fallbackDayAheadRow, "NBP_DAY_AHEAD", fxRates);
    if (fallback) dayAheadObservations.push(fallback);
  }

  const manualOcmPrice = positiveLiveMark(liveMark);
  const persistedOcmObservation = ocmRow
    ? strategyObservation(ocmRow, "ICE_OCM", fxRates)
    : null;
  const referenceDelivery = persistedOcmObservation ?? dayAheadObservations[0] ?? null;
  const manualOcmObservation: StrategyPriceObservationDTO | null = manualOcmPrice === null
    ? null
    : {
        observation_id: "operator-ocm-reference",
        source_system: liveMark.source_system,
        venue: liveMark.venue,
        hub: liveMark.hub,
        product: liveMark.product,
        price_name: "ICE_OCM",
        price_gbp_mwh: manualOcmPrice,
        observed_at_utc: liveMark.mark_time_utc ?? new Date().toISOString(),
        delivery_start_utc: referenceDelivery?.delivery_start_utc ?? new Date().toISOString(),
        delivery_end_utc: referenceDelivery?.delivery_end_utc ?? new Date().toISOString(),
        bar_minutes: 5,
        source_reference: liveMark.source_system,
      };
  const intradayObservation = manualOcmObservation ?? persistedOcmObservation;
  const resource = portfolioResources[0];
  const dayAheadNames = dayAheadObservations.map((observation) => observation.price_name);

  return {
    strategy_id: "nbp-sap-icis-ocm-window",
    strategy_name: "NBP SAP/ICIS day-ahead versus ICE OCM window",
    run_mode: "SHADOW_RUN",
    resource_contexts: [
      {
        resource_id: resource?.resource_id ?? "resource-pool-unavailable",
        resource_name: resource?.resource_name ?? "Resource pool unavailable",
        available_quantity_mwh_per_day: resource?.available_quantity_mwh_per_day ?? 0,
        all_in_cost_gbp_mwh:
          (resource?.contract_cost_gbp_mwh ?? 0) +
          (resource?.tolerance_risk_allowance_gbp_mwh ?? 0),
        delivery_tolerance_pct: resource?.delivery_tolerance_pct ?? null,
        nomination_tolerance_pct: resource?.nomination_tolerance_pct ?? null,
        booked_entry_capacity_mwh_per_day: contract.owned_entry_capacity_mwh_per_day,
        balancing_allowance_gbp_mwh: resource?.tolerance_risk_allowance_gbp_mwh ?? 0,
        required_tso_access: resource?.required_tso_access ?? [],
        company_accessible_tsos: resource?.accessible_tsos ?? null,
      },
    ],
    price_observations: [
      ...dayAheadObservations,
      ...(intradayObservation ? [intradayObservation] : []),
    ],
    components: [
      {
        component_id: "sap-icis-ocm-1500-1700",
        component_type: "OCM_VS_DAY_AHEAD",
        weight: 1,
        day_ahead_price_names: dayAheadNames.length > 0 ? dayAheadNames : ["SAP", "ICIS_HEREN_DAY_AHEAD"],
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
      max_single_market_volume_mwh_per_day:
        (portfolioResources[0]?.available_quantity_mwh_per_day ?? 0) * 0.6,
      min_expected_margin_gbp_mwh: 0,
      require_tso_access: true,
    },
    existing_shadow_pnl_gbp: 0,
  };
}
