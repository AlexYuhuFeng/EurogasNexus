import { useMemo, useState } from "react";
import type { PortfolioResourceDTO } from "@/api/client";
import { buildAnalysisPayload } from "@/app/index";

const DEFAULT_ANALYSIS_QUESTION =
  "Summarize current portfolio PnL, route, market, and strategy status.";

export function useReviewAnalysis(language: string, portfolioResources: PortfolioResourceDTO[]) {
  const [analysisQuestion, setAnalysisQuestion] = useState(DEFAULT_ANALYSIS_QUESTION);
  const [invokeDeepSeek, setInvokeDeepSeek] = useState(false);
  const analysisPayload = useMemo(
    () => buildAnalysisPayload(analysisQuestion, invokeDeepSeek, language, portfolioResources),
    [analysisQuestion, invokeDeepSeek, language, portfolioResources],
  );

  return {
    analysisQuestion,
    invokeDeepSeek,
    analysisPayload,
    setAnalysisQuestion,
    setInvokeDeepSeek,
  };
}
