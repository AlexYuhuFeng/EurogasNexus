import { useMemo } from "react";
import type { PortfolioResourceDTO } from "@/api/client";
import { buildAnalysisPayload } from "@/app/index";

/**
 * The deterministic question the portfolio report is generated from.
 *
 * The review surface used to let a user type a question and switch the provider on, which
 * made a second AI entry point beside the canonical five actions (Architecture V2 Wave 7):
 * an AI-drafted artefact is the `draft` action's job, and the report itself is the backend's
 * deterministic run. What remains here is that run's input.
 */
const REPORT_QUESTION = "Summarize current portfolio PnL, route, market, and strategy status.";

export function useReviewAnalysis(language: string, portfolioResources: PortfolioResourceDTO[]) {
  const analysisPayload = useMemo(
    () => buildAnalysisPayload(REPORT_QUESTION, false, language, portfolioResources),
    [language, portfolioResources],
  );

  return { analysisPayload };
}
