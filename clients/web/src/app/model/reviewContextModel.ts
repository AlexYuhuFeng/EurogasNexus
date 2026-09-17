/**
 * Review context presentation model (Architecture V2 Wave 5, client half).
 *
 * The review surface needs three things the workspace batch deliberately does not carry:
 * the decisions of the current review target, the evidence each decision was taken on,
 * and the monitoring posture. Resolving evidence is per-entity work, so it belongs on the
 * surface's own open path rather than on every session's load.
 *
 * The rules this model keeps:
 *
 * - evidence a resolver could not produce stays explicitly unavailable with its reason;
 *   the client never renders it as an empty artifact;
 * - the decisions slice is the anchor: a payload whose decisions the backend did not
 *   serve is not usable, and the surface keeps what it already had;
 * - one as-of and one time basis cover all three slices, so a decision and the evidence
 *   it cites can never be read on different clocks.
 */

import type {
  MonitoringSummaryDTO,
  ReviewContextProjectionDTO,
  ReviewDecisionDTO,
  ReviewEvidenceEntryDTO,
} from "@/api/client";
import {
  degradedReadings,
  projectionSliceIsAvailable,
  projectionSlicePayload,
  projectionSliceRows,
  projectionSliceReadings,
  type SliceReading,
} from "./projectionModel.ts";

export type { SliceReading };

export type ReviewSliceKey = keyof ReviewContextProjectionDTO["slices"];

export const REVIEW_CONTEXT_SLICE_ORDER: ReviewSliceKey[] = [
  "decisions",
  "evidence",
  "monitoring",
];

/** Translation keys for the slice labels the surface renders. */
export const REVIEW_CONTEXT_SLICE_LABEL_KEYS: Readonly<Record<ReviewSliceKey, string>> = {
  decisions: "review_context.slice.decisions",
  evidence: "review_context.slice.evidence",
  monitoring: "review_context.slice.monitoring",
};

interface DecisionsPayload {
  latest_decision?: ReviewDecisionDTO | null;
  needs_attention_count?: number;
  decided_entities?: Array<{ entity_type?: string; entity_id?: string }>;
}

interface EvidencePayload {
  requested_entity_count?: number;
  resolved_entity_count?: number;
  supported_entity_types?: string[];
}

/** One row per slice, in reading order, for the surface's status strip. */
export function reviewReadings(
  projection: ReviewContextProjectionDTO | null | undefined,
): SliceReading[] {
  return projectionSliceReadings(projection?.slices, REVIEW_CONTEXT_SLICE_ORDER);
}

/** Slices that are stale, missing or unavailable. */
export function degradedReviewSlices(
  projection: ReviewContextProjectionDTO | null | undefined,
): SliceReading[] {
  return degradedReadings(reviewReadings(projection));
}

export function reviewDecisions(
  projection: ReviewContextProjectionDTO | null | undefined,
): ReviewDecisionDTO[] {
  return projectionSliceRows<
    ReviewDecisionDTO,
    ReviewContextProjectionDTO["slices"],
    ReviewSliceKey
  >(projection?.slices, "decisions");
}

export function reviewEvidence(
  projection: ReviewContextProjectionDTO | null | undefined,
): ReviewEvidenceEntryDTO[] {
  return projectionSliceRows<
    ReviewEvidenceEntryDTO,
    ReviewContextProjectionDTO["slices"],
    ReviewSliceKey
  >(projection?.slices, "evidence");
}

/** The monitoring posture the projection measured, or `null` when it did not serve it. */
export function reviewMonitoring(
  projection: ReviewContextProjectionDTO | null | undefined,
): MonitoringSummaryDTO | null {
  return projectionSlicePayload<
    MonitoringSummaryDTO,
    ReviewContextProjectionDTO["slices"],
    ReviewSliceKey
  >(projection?.slices, "monitoring");
}

/** The newest decision of the review target, as the payload reports it. */
export function reviewLatestDecision(
  projection: ReviewContextProjectionDTO | null | undefined,
): ReviewDecisionDTO | null {
  const payload = projectionSlicePayload<
    DecisionsPayload,
    ReviewContextProjectionDTO["slices"],
    ReviewSliceKey
  >(projection?.slices, "decisions");
  return payload?.latest_decision ?? null;
}

/** How many decisions the payload counted as needing attention, or `null` if unreported. */
export function reviewNeedsAttentionCount(
  projection: ReviewContextProjectionDTO | null | undefined,
): number | null {
  const payload = projectionSlicePayload<
    DecisionsPayload,
    ReviewContextProjectionDTO["slices"],
    ReviewSliceKey
  >(projection?.slices, "decisions");
  const count = payload?.needs_attention_count;
  return typeof count === "number" ? count : null;
}

/**
 * How much of the requested evidence the backend could resolve.
 *
 * `requested > resolved` is the honest signal that some evidence is unavailable, and the
 * per-entry `unavailable_reason` says which and why.
 */
export function reviewEvidenceCoverage(
  projection: ReviewContextProjectionDTO | null | undefined,
): { requested: number; resolved: number } | null {
  const payload = projectionSlicePayload<
    EvidencePayload,
    ReviewContextProjectionDTO["slices"],
    ReviewSliceKey
  >(projection?.slices, "evidence");
  const requested = payload?.requested_entity_count;
  const resolved = payload?.resolved_entity_count;
  if (typeof requested !== "number" || typeof resolved !== "number") return null;
  return { requested, resolved };
}

/** The evidence entry for one entity, or `null` when the payload does not carry one. */
export function reviewEvidenceFor(
  projection: ReviewContextProjectionDTO | null | undefined,
  entityType: string,
  entityId: string,
): ReviewEvidenceEntryDTO | null {
  return (
    reviewEvidence(projection).find(
      (entry) => entry.entity_type === entityType && entry.entity_id === entityId,
    ) ?? null
  );
}

/** The single as-of instant the whole payload shares. */
export function reviewAsOf(
  projection: ReviewContextProjectionDTO | null | undefined,
): string | null {
  return projection?.as_of_utc ?? null;
}

/** The declared time basis, as the backend stated it. */
export function reviewTimeBasis(
  projection: ReviewContextProjectionDTO | null | undefined,
): Record<string, unknown> | null {
  return projection?.time_basis ?? null;
}

/**
 * Whether the payload may be used as the review surface's coherent source. An absent
 * payload, or one whose decisions slice the backend did not serve, leaves the surface
 * with the decisions it already had rather than an empty review.
 */
export function reviewIsUsable(
  projection: ReviewContextProjectionDTO | null | undefined,
): boolean {
  if (!projection) return false;
  return projectionSliceIsAvailable(projection.slices, "decisions");
}
