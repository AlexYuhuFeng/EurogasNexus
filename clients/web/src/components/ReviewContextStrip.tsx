/**
 * Review context strip (Architecture V2 Wave 5, surface half).
 *
 * The review surface resolves evidence per review entity, so it reads its own projection
 * when it opens instead of making every session pay for that work. This strip shows what
 * that read actually returned: one as-of, one time basis, and per-slice freshness - so a
 * reviewer can see whether the evidence behind a decision was retrieved, withheld or
 * stale before treating the decision as reviewed.
 */

import type { ReviewContextProjectionDTO } from "@/api/client";
import {
  REVIEW_CONTEXT_SLICE_LABEL_KEYS,
  degradedReviewSlices,
  reviewAsOf,
  reviewEvidenceCoverage,
  reviewReadings,
  reviewTimeBasis,
} from "@/app/model/reviewContextModel";
import { ProjectionContextStrip } from "@/components/ProjectionContextStrip";

type Translate = (key: string, options?: Record<string, unknown>) => string;

interface ReviewContextStripProps {
  projection: ReviewContextProjectionDTO | null;
  t: Translate;
}

export function ReviewContextStrip({ projection, t }: ReviewContextStripProps) {
  if (!projection) return null;

  const coverage = reviewEvidenceCoverage(projection);

  return (
    <ProjectionContextStrip
      namespace="review_context"
      className="review-context-strip"
      readings={reviewReadings(projection)}
      degraded={degradedReviewSlices(projection)}
      labelKeys={REVIEW_CONTEXT_SLICE_LABEL_KEYS}
      asOf={reviewAsOf(projection)}
      basis={reviewTimeBasis(projection)}
      t={t}
    >
      {coverage && (
        <span className="projection-slice-count">
          {t("review_context.evidence_coverage", {
            resolved: coverage.resolved,
            requested: coverage.requested,
          })}
        </span>
      )}
    </ProjectionContextStrip>
  );
}
