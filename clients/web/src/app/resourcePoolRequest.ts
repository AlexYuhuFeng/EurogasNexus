import type {
  PortfolioOptimizationRequestDTO,
  PortfolioResourceDTO,
  PortfolioSaleOptionDTO,
} from "@/api/client";
import type { ContractDraft } from "./defaultContractDraft";
import {
  resolvePoolFinancingRate,
  type FinancingRateSource,
} from "./model/scenarioInputProvenance.ts";

/**
 * Compose the pool-optimisation request, or refuse when its one draft input is unknown.
 *
 * The annual financing rate is the only draft term either Decision action consumes. A blank
 * draft rate with no saved contract rate is *unknown*, and the request is refused (`null`)
 * rather than sent with an invented `0`: returning a 0 there would compute an early-cash term
 * from a rate nobody recorded while presenting it as the operator's assumption. Callers treat
 * null as "the action has no valid input".
 */
export function buildResourcePoolOptimizationRequest(
  contract: ContractDraft,
  portfolioResources: PortfolioResourceDTO[],
  saleOptions: PortfolioSaleOptionDTO[],
  upstreamContracts: ReadonlyArray<FinancingRateSource>,
): PortfolioOptimizationRequestDTO | null {
  const financingRate = resolvePoolFinancingRate(contract, upstreamContracts);
  if (financingRate.pct === null) return null;
  return {
    portfolio_id: "web-resource-pool",
    resources: portfolioResources,
    sale_options: saleOptions,
    // The one draft value this request consumes, resolved by the same rule the Scenario
    // panel displays (saved upstream contract rate first, draft as fallback).
    annual_financing_rate_pct: financingRate.pct,
    objective: "MAX_DAILY_PNL",
  };
}
