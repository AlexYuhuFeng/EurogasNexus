import type {
  PortfolioOptimizationRequestDTO,
  PortfolioResourceDTO,
  PortfolioSaleOptionDTO,
} from "@/api/client";
import type { ContractDraft } from "./defaultContractDraft";

type UpstreamContractLike = {
  annual_financing_rate_pct?: number | null;
};

export function buildResourcePoolOptimizationRequest(
  contract: ContractDraft,
  portfolioResources: PortfolioResourceDTO[],
  saleOptions: PortfolioSaleOptionDTO[],
  upstreamContracts: UpstreamContractLike[],
): PortfolioOptimizationRequestDTO {
  return {
    portfolio_id: "web-resource-pool",
    resources: portfolioResources,
    sale_options: saleOptions,
    annual_financing_rate_pct: upstreamContracts[0]?.annual_financing_rate_pct ?? contract.annual_financing_rate_pct,
    objective: "MAX_DAILY_PNL",
  };
}
