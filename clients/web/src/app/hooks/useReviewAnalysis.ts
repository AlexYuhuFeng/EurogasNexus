import { useMemo } from "react";
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

export function useReviewAnalysis(
  language: string,
  /**
   * The reproducibility reference the next report run cites (Architecture V2 Wave 4), chosen
   * from the snapshots the deployment recorded. Null cites nothing.
   */
  analysisSnapshotId: string | null = null,
) {
  // The portfolio's resource list is not an input: the report covers the whole entitled
  // snapshot, and the platform refuses the selection field the list used to fill.
  const analysisPayload = useMemo(
    () =>
      buildAnalysisPayload(
        REPORT_QUESTION,
        false,
        language,
        analysisSnapshotId,
      ),
    [language, analysisSnapshotId],
  );

  return { analysisPayload };
}
