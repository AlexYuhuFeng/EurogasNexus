export function buildAnalysisPayload(
  analysisQuestion: string,
  invokeDeepSeek: boolean,
  language: string,
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
  // No selection field is sent, and none is invented on the analyst's behalf. The
  // analysis pipeline reads no term, asset, contract, strategy, section or portfolio
  // selection, so the platform refuses a non-empty one with
  // `422 analysis_selection_not_supported` rather than returning a report over the
  // whole snapshot as if it had been narrowed. The portfolio's own resources are
  // already the report's subject; naming them as a selection would restate the scope
  // as if it were a filter.
  const payload = {
    question: analysisQuestion,
    task: "PORTFOLIO_REPORT",
    provider_id: "DEEPSEEK",
    model: "deepseek-v4-flash",
    invoke_provider: invokeDeepSeek,
    language: language.startsWith("zh") ? "zh-CN" : "en",
  };
  const snapshotId = (analysisSnapshotId ?? "").trim();
  return snapshotId ? { ...payload, analysis_snapshot_id: snapshotId } : payload;
}
