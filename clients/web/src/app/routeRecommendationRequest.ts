type PortfolioResourceLike = {
  location_point_name?: string | null;
  accessible_tsos?: string[] | null;
};

type SaleOptionLike = {
  option_id: string;
  label: string;
  target_point_name: string;
  sale_price_gbp_mwh: number;
  sale_price_currency?: string | null;
  sale_price_unit?: string | null;
  required_tso_access?: string[];
  capacity_limit_mwh_per_day?: number | null;
  route_cost_gbp_mwh?: number | null;
  route_cost_currency?: string | null;
  route_cost_unit?: string | null;
};

type UpstreamContractLike = {
  gas_year?: string | null;
};

export function buildRouteRecommendationRequest(
  portfolioResources: PortfolioResourceLike[],
  saleOptions: SaleOptionLike[],
  totalPoolVolume: number,
  upstreamContracts: UpstreamContractLike[],
) {
  return {
    request_id: "web-db-backed-route-allocation",
    source_point_id: portfolioResources[0]?.location_point_name ?? "RESOURCE_POOL",
    target_point_id: saleOptions[0]?.target_point_name ?? null,
    required_quantity_mwh_per_day: totalPoolVolume,
    gas_year: upstreamContracts[0]?.gas_year ?? "2025+",
    capacity_product: "ANNUAL",
    firmness: "FIRM",
    company_accessible_tsos: portfolioResources[0]?.accessible_tsos ?? null,
    candidates: saleOptions.map((option) => ({
      route_id: option.option_id,
      route_name: option.label,
      destination_market: option.target_point_name,
      sale_price: option.sale_price_gbp_mwh,
      price_currency: option.sale_price_currency ?? "EUR",
      price_unit: option.sale_price_unit ?? "EUR/MWh",
      required_tso_access: option.required_tso_access ?? [],
      available_capacity_mwh_per_day: option.capacity_limit_mwh_per_day ?? null,
      manual_cost: option.route_cost_gbp_mwh ?? 0,
      cost_currency: option.route_cost_currency ?? "EUR",
      cost_unit: option.route_cost_unit ?? "EUR/MWh",
    })),
  };
}
