import type { ContractDraft } from "./defaultContractDraft";

type MarketLike = {
  market_venue: string;
  price: number;
};

type LiveMarkLike = {
  venue: string;
  hub: string;
  product: string;
  bid_gbp_mwh: number | null;
  ask_gbp_mwh: number | null;
  last_gbp_mwh: number | null;
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

export function buildStrategyScenario(
  contract: ContractDraft,
  liveMark: LiveMarkLike,
  markets: MarketLike[],
  portfolioResources: PortfolioResourceLike[],
) {
  const deliveryStart = "2026-01-16T00:00:00Z";
  const deliveryEnd = "2026-01-17T00:00:00Z";
  const ocmMid = liveMark.last_gbp_mwh ?? liveMark.bid_gbp_mwh ?? liveMark.ask_gbp_mwh ?? 0;
  const resource = portfolioResources[0];
  const nbpPrice = markets.find((market) => market.market_venue === "NBP")?.price ?? 0;
  return {
    strategy_id: "nbp-sap-icis-ocm-window",
    strategy_name: "NBP SAP/ICIS day-ahead versus ICE OCM window",
    run_mode: "SHADOW_RUN",
    resource_contexts: [
      {
        resource_id: resource?.resource_id ?? "resource-pool-unavailable",
        resource_name: resource?.resource_name ?? "Resource pool unavailable",
        available_quantity_mwh_per_day: resource?.available_quantity_mwh_per_day ?? 0,
        all_in_cost_gbp_mwh: (resource?.contract_cost_gbp_mwh ?? 0) + (resource?.tolerance_risk_allowance_gbp_mwh ?? 0),
        delivery_tolerance_pct: resource?.delivery_tolerance_pct ?? null,
        nomination_tolerance_pct: resource?.nomination_tolerance_pct ?? null,
        booked_entry_capacity_mwh_per_day: contract.owned_entry_capacity_mwh_per_day,
        balancing_allowance_gbp_mwh: resource?.tolerance_risk_allowance_gbp_mwh ?? 0,
        required_tso_access: resource?.required_tso_access ?? [],
        company_accessible_tsos: resource?.accessible_tsos ?? null,
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
        price_gbp_mwh: Math.max(nbpPrice - 0.4, 0),
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
        price_gbp_mwh: nbpPrice,
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
      max_single_market_volume_mwh_per_day: (portfolioResources[0]?.available_quantity_mwh_per_day ?? 0) * 0.6,
      min_expected_margin_gbp_mwh: 0,
      require_tso_access: true,
    },
    existing_shadow_pnl_gbp: 0,
  };
}
