import type { RouteRecommendationRequestDTO } from "@/api/client";

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
  capacity_status?: string | null;
  route_cost_gbp_mwh?: number | null;
  route_cost_currency?: string | null;
  route_cost_unit?: string | null;
  route_cost_source_refs?: string[] | null;
  tariff_applicability_date?: string | null;
  source_refs?: string[] | null;
};

type UpstreamContractLike = {
  gas_year?: string | null;
};

function uniqueStrings(values: ReadonlyArray<string | null | undefined>): string[] {
  return [
    ...new Set(
      values.filter((value): value is string => typeof value === "string" && value.trim().length > 0),
    ),
  ];
}

/**
 * Compose the route-comparison request from the backend-owned resource-pool read.
 *
 * Identity rules:
 * - `sale_price_gbp_mwh` and `route_cost_gbp_mwh` are already the backend's
 *   normalized GBP/MWh values. They are sent with that explicit GBP/MWh
 *   identity; the builder never defaults missing metadata to EUR and never asks
 *   the backend to convert an already-GBP value a second time.
 * - An absent/unknown route cost stays `null` with null cost metadata. It is
 *   never replaced by `0`; only an explicit `route_cost_gbp_mwh: 0` is a known
 *   zero. The backend refuses a candidate it cannot price.
 * - `capacity_status` is forwarded exactly as the backend reported it, so an
 *   explicit `NOT_REQUIRED` is not lost. A missing state is sent as `UNKNOWN`,
 *   never promoted to `NOT_REQUIRED`.
 * - The caller's current canonical gas day is the request's
 *   `tariff_applicability_date` and the item's identity, so a gas-day change
 *   cannot reuse a prior recommendation.
 * - The source option's tariff date and references travel with the candidate as
 *   provenance only. The backend marks caller references `unverified_input:`;
 *   they establish no entitlement and feed no arithmetic.
 *
 * `gasDay` is optional to keep existing four-argument callers working; omitting
 * it means "tariff applicability not assessed" (the backend discloses that).
 */
export function buildRouteRecommendationRequest(
  portfolioResources: PortfolioResourceLike[],
  saleOptions: SaleOptionLike[],
  totalPoolVolume: number,
  upstreamContracts: UpstreamContractLike[],
  gasDay?: string | null,
): RouteRecommendationRequestDTO {
  const tariffApplicabilityDate = gasDay?.trim() || null;
  return {
    request_id: "web-db-backed-route-allocation",
    source_point_id: portfolioResources[0]?.location_point_name ?? "RESOURCE_POOL",
    target_point_id: saleOptions[0]?.target_point_name ?? null,
    required_quantity_mwh_per_day: totalPoolVolume,
    gas_year: upstreamContracts[0]?.gas_year ?? "2025+",
    capacity_product: "ANNUAL",
    firmness: "FIRM",
    company_accessible_tsos: portfolioResources[0]?.accessible_tsos ?? null,
    tariff_applicability_date: tariffApplicabilityDate,
    candidates: saleOptions.map((option) => {
      // The backend's resource-pool contract owns these fields: a `*_gbp_mwh`
      // value is GBP/MWh by definition. A known zero is preserved; an unknown
      // cost is null and its metadata is null rather than an invented currency.
      const manualCost = option.route_cost_gbp_mwh ?? null;
      const costKnown = manualCost !== null;
      // The backend vocabulary is upper-case; a missing state is UNKNOWN, never
      // promoted to the explicit NOT_REQUIRED that permits an uncapped sale.
      const capacityStatus = (option.capacity_status?.trim() || "UNKNOWN").toUpperCase();
      return {
        route_id: option.option_id,
        route_name: option.label,
        destination_market: option.target_point_name,
        sale_price: option.sale_price_gbp_mwh,
        price_currency: "GBP",
        price_unit: "GBP/MWh",
        required_tso_access: option.required_tso_access ?? [],
        available_capacity_mwh_per_day: option.capacity_limit_mwh_per_day ?? null,
        capacity_status: capacityStatus,
        manual_cost: manualCost,
        cost_currency: costKnown ? "GBP" : null,
        cost_unit: costKnown ? "GBP/MWh" : null,
        tariff_applicability_date: option.tariff_applicability_date?.trim() || null,
        source_refs: uniqueStrings([
          ...(option.route_cost_source_refs ?? []),
          ...(option.source_refs ?? []),
        ]),
      };
    }),
  };
}
