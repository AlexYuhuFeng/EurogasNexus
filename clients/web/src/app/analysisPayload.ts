type PortfolioResourceLike = {
  resource_id: string;
};

export function buildAnalysisPayload(
  analysisQuestion: string,
  invokeDeepSeek: boolean,
  language: string,
  portfolioResources: PortfolioResourceLike[],
) {
  return {
    question: analysisQuestion,
    task: "PORTFOLIO_REPORT",
    provider_id: "DEEPSEEK",
    model: "deepseek-chat",
    invoke_provider: invokeDeepSeek,
    selected_terms: ["TTF", "NBP", "ICE OCM"],
    selected_assets: ["TTF", "NBP", "BBL"],
    selected_contracts: portfolioResources.map((resource) => resource.resource_id),
    language: language.startsWith("zh") ? "zh-CN" : "en",
  };
}
