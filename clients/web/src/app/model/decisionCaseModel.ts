/**
 * Decision Case presentation model (Architecture V2 Wave 6, client side).
 *
 * A Decision Case collects objective, context, assumptions, alternatives and
 * evidence and ends in a human Decision Record. These helpers keep the surface
 * honest: they name the states and outcomes, decide whether an action is
 * available from the payload the backend returned, and never infer a decision the
 * backend has not recorded.
 */

import type {
  DecisionCaseDTO,
  DecisionCaseEvidenceInputDTO,
  DecisionCaseSummaryDTO,
} from "@/api/client";

export const DECISION_OUTCOMES = ["accepted", "rejected", "needs_attention"] as const;
export type DecisionOutcomeId = (typeof DECISION_OUTCOMES)[number];

export const DECISION_EVIDENCE_KINDS: DecisionCaseEvidenceInputDTO["kind"][] = [
  "MARKET_CONTEXT",
  "PORTFOLIO_SNAPSHOT",
  "SCENARIO",
  "OPTIMIZATION",
  "ROUTE_RECOMMENDATION",
  "BACKTEST",
  "STRATEGY_RUN",
  "RESEARCH_DATASET",
  "AGENT_RUN",
  "AI_ANALYSIS",
  "REVIEW_CONTEXT",
  "MANUAL",
];

export const DECISION_CASE_VIEWS = ["open", "decided"] as const;
export type DecisionCaseViewId = (typeof DECISION_CASE_VIEWS)[number];

/** Label key for a case status, so EN and zh-CN share one vocabulary. */
export function caseStatusLabelKey(status: string): string {
  const normalized = (status ?? "").trim().toUpperCase();
  return `decision_case.status.${normalized || "UNKNOWN"}`;
}

export function outcomeLabelKey(outcome: string): string {
  return `decision_case.outcome.${(outcome ?? "").trim().toLowerCase()}`;
}

export function evidenceKindLabelKey(kind: string): string {
  return `decision_case.evidence.${(kind ?? "").trim().toUpperCase()}`;
}

/**
 * Blocker codes the backend may return with a refusal. An unknown code still gets
 * a stable key, so a surface never renders a raw identifier at a user.
 */
export function blockerLabelKey(blocker: string): string {
  const normalized = (blocker ?? "").trim().toLowerCase().replace(/[^a-z0-9_]/g, "_");
  return `decision_case.blocker.${normalized || "unknown"}`;
}

/**
 * A decision may be offered only when the backend says the case is decidable: the
 * client must not enable a button whose call it knows will be refused.
 */
export function canRecordDecision(caseDto: DecisionCaseDTO | null | undefined): boolean {
  if (!caseDto) return false;
  return caseDto.decidable === true && caseDto.status !== "DECIDED";
}

/** Reopening applies to a decided case only, and keeps its history. */
export function canReopen(caseDto: DecisionCaseDTO | null | undefined): boolean {
  if (!caseDto) return false;
  return caseDto.status === "DECIDED" || caseDto.status === "REOPENED";
}

export function isReproducible(caseDto: DecisionCaseDTO | null | undefined): boolean {
  return Boolean(caseDto?.reproducible);
}

/** Compact counts for the case header, taken from the payload, never recomputed. */
export function caseCounts(caseDto: DecisionCaseDTO | null | undefined): {
  evidence: number;
  alternatives: number;
  assumptions: number;
  records: number;
} {
  return {
    evidence: caseDto?.evidence.length ?? 0,
    alternatives: caseDto?.alternatives.length ?? 0,
    assumptions: caseDto?.assumptions.length ?? 0,
    records: caseDto?.records.length ?? 0,
  };
}

/** Split a list payload into the two views the panel offers. */
export function splitCases(cases: readonly DecisionCaseSummaryDTO[]): {
  open: DecisionCaseSummaryDTO[];
  decided: DecisionCaseSummaryDTO[];
} {
  const open: DecisionCaseSummaryDTO[] = [];
  const decided: DecisionCaseSummaryDTO[] = [];
  for (const row of cases) {
    if (row.status === "DECIDED" || row.status === "REOPENED") decided.push(row);
    else open.push(row);
  }
  return { open, decided };
}

/**
 * The evidence reference a new attachment should default to for a given kind, so a
 * user is not asked to type an identifier the Active Context already carries.
 */
export function suggestedEvidenceRef(
  kind: DecisionCaseEvidenceInputDTO["kind"],
  context: {
    routeId?: string | null;
    strategyRunId?: string | null;
    snapshotId?: string | null;
    /** The last governed AI analysis run this identity completed, if any. */
    analysisId?: string | null;
  },
): string {
  if (kind === "ROUTE_RECOMMENDATION" && context.routeId) return context.routeId;
  if (kind === "STRATEGY_RUN" && context.strategyRunId) return context.strategyRunId;
  // The Decision Case chain cites AI findings and challenges, so the run the user just
  // completed is offered by reference instead of asking them to copy an identifier.
  if (kind === "AI_ANALYSIS" && context.analysisId) return context.analysisId;
  return "";
}

/** A case is "decided" once a record exists; the payload is the only source. */
export function isDecided(caseDto: DecisionCaseDTO | null | undefined): boolean {
  return (caseDto?.records.length ?? 0) > 0;
}
