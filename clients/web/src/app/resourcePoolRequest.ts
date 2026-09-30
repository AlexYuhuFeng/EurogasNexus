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

export function buildResourcePoolOptimizationRequest(
  contract: ContractDraft,
  portfolioResources: PortfolioResourceDTO[],
  saleOptions: PortfolioSaleOptionDTO[],
  upstreamContracts: ReadonlyArray<FinancingRateSource>,
): PortfolioOptimizationRequestDTO {
  return {
    portfolio_id: "web-resource-pool",
    resources: portfolioResources,
    sale_options: saleOptions,
    // The one draft value this request consumes, resolved by the same rule the Scenario
    // panel displays (saved upstream contract rate first, draft as fallback).
    annual_financing_rate_pct: resolvePoolFinancingRate(contract, upstreamContracts).pct,
    objective: "MAX_DAILY_PNL",
  };
}
