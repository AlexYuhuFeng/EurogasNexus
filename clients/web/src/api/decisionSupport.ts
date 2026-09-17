/**
 * Decision-support markers of a response (Architecture V2 Wave 7/8 boundary).
 *
 * Every public response carries `research_only` and `human_review_required`. The first
 * is a **retained compatibility field** (`docs/architecture/TERMINOLOGY.md`), so the
 * wire keeps it while new application modules must not start depending on its name.
 *
 * This module is the single place that reads it. It has no imports on purpose: the API
 * layer owns the wire vocabulary, and keeping it dependency-free lets every consumer -
 * including modules a Node test loads directly - import it without pulling the HTTP
 * client and its host boundary along.
 *
 * The read fails closed: a caller passes every response it composed its output from
 * (the body and the envelope, typically), and either one reporting a marker is enough.
 * A missing field therefore never reads as "reviewed and clear".
 */

export interface DecisionSupportSource {
  readonly research_only?: boolean;
  readonly human_review_required?: boolean;
}

export interface DecisionSupportMarkers {
  readonly researchOnly: boolean;
  readonly humanReviewRequired: boolean;
}

export function decisionSupportMarkers(
  ...responses: Array<DecisionSupportSource | null | undefined>
): DecisionSupportMarkers {
  return {
    researchOnly: responses.some((response) => Boolean(response?.research_only)),
    humanReviewRequired: responses.some((response) => Boolean(response?.human_review_required)),
  };
}
