type PortfolioResourceLike = {
  resource_id: string;
};

export function buildAnalysisPayload(
  analysisQuestion: string,
  invokeDeepSeek: boolean,
  language: string,
  portfolioResources: PortfolioResourceLike[],
  /**
   * The Analysis Snapshot this run cites as its reproducibility reference
   * (Architecture V2 Wave 4), or null/absent to cite nothing.
   *
   * The reference is only ever sent when the caller picked one the deployment recorded:
   * citing nothing leaves the payload exactly as it was, and the backend refuses an
   * unverifiable reference rather than storing a citation nobody can resolve.
   */
  analysisSnapshotId?: string | null,
) {
  const payload = {
    question: analysisQuestion,
    task: "PORTFOLIO_REPORT",
    provider_id: "DEEPSEEK",
    model: "deepseek-v4-flash",
    invoke_provider: invokeDeepSeek,
    selected_terms: ["TTF", "NBP", "ICE OCM"],
    selected_assets: ["TTF", "NBP", "BBL"],
    selected_contracts: portfolioResources.map((resource) => resource.resource_id),
    language: language.startsWith("zh") ? "zh-CN" : "en",
  };
  const snapshotId = (analysisSnapshotId ?? "").trim();
  return snapshotId ? { ...payload, analysis_snapshot_id: snapshotId } : payload;
}
