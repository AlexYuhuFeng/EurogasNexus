import type { ContractDraft } from "./defaultContractDraft";

type ResourcePoolResource = {
  available_quantity_mwh_per_day: number;
};

type ResourcePoolSaleOption = Record<string, unknown>;

type UpstreamContractLike = {
  annual_financing_rate_pct?: number | null;
};

export function buildResourcePoolOptimizationRequest(
  contract: ContractDraft,
  portfolioResources: ResourcePoolResource[],
  saleOptions: ResourcePoolSaleOption[],
  upstreamContracts: UpstreamContractLike[],
) {
  return {
    portfolio_id: "web-resource-pool",
    resources: portfolioResources,
    sale_options: saleOptions,
    annual_financing_rate_pct: upstreamContracts[0]?.annual_financing_rate_pct ?? contract.annual_financing_rate_pct,
    objective: "MAX_DAILY_PNL",
    research_only: true,
  };
}
