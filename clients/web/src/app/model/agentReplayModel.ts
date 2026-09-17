/**
 * Read-only view model for the CR-15 governed research artifact chain.
 *
 * Every derivation here works on the persisted replay payload only: chain order,
 * present/missing state, artifact identity, lineage, entitlement state, fixture
 * and replay identity, timestamps and compact payload rows. Nothing models
 * execution, scheduling or nomination semantics, and no reasoning text is ever
 * invented: ``hidden_chain_of_thought`` is persistently null.
 */

import type {
  AgentArtifactChainSummaryDTO,
  AgentArtifactEnvelopeDTO,
  AgentArtifactType,
  AgentArtifactsDTO,
  AgentChallengeReportPayloadDTO,
  AgentReplayDTO,
  AgentResearchFindingPayloadDTO,
  AgentResearchPlanPayloadDTO,
  AgentReviewPackPayloadDTO,
  AgentStrategyIRPayloadDTO,
  AgentValidationPayloadDTO,
  ReviewDecisionDTO,
  ReviewDecisionInputDTO,
} from "@/api/client";

/** The persisted chain vocabulary, in the governed stage order. */
export const AGENT_ARTIFACT_TYPES: readonly AgentArtifactType[] = [
  "research_plan",
  "findings",
  "strategy_ir",
  "validation",
  "challenge_report",
  "review_pack",
] as const;

export type AgentReviewDecisionValue = "accepted" | "rejected" | "needs_attention";

export const AGENT_REVIEW_DECISIONS: readonly AgentReviewDecisionValue[] = [
  "accepted",
  "rejected",
  "needs_attention",
] as const;

/** Review artifact kind persisted for one agent review pack. */
export const AGENT_REVIEW_PACK_ENTITY_TYPE = "agent_review_pack";

export function isAgentArtifactType(value: string): value is AgentArtifactType {
  return (AGENT_ARTIFACT_TYPES as readonly string[]).includes(value);
}

export function isAgentReviewDecisionValue(value: string): value is AgentReviewDecisionValue {
  return (AGENT_REVIEW_DECISIONS as readonly string[]).includes(value);
}

/** One rendered chain position: order, presence, identity and its envelope. */
export interface AgentChainEntry {
  artifactType: AgentArtifactType;
  /** 1-based position in the persisted chain order. */
  position: number;
  present: boolean;
  operationId: string;
  stage: string;
  artifactId: string | null;
  artifactIds: string[];
  /** The chain lists the artifact but the read carried no envelope for it. */
  envelopeMissing: boolean;
  envelope: AgentArtifactEnvelopeDTO | null;
}

export interface AgentChainView {
  entries: AgentChainEntry[];
  order: AgentArtifactType[];
  present: AgentArtifactType[];
  missing: AgentArtifactType[];
  complete: boolean;
  chainHash: string;
  presentCount: number;
  missingCount: number;
  total: number;
}

function envelopeOf(
  artifacts: AgentArtifactsDTO,
  artifactType: AgentArtifactType,
): AgentArtifactEnvelopeDTO | undefined {
  const table = artifacts as Partial<Record<AgentArtifactType, AgentArtifactEnvelopeDTO>>;
  return table[artifactType];
}

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string" && item !== "");
}

/**
 * Derive the ordered chain view, including present/missing state.
 *
 * The server order wins, but a type the server omitted is appended instead of
 * dropped, and a chain that declares an artifact present without shipping its
 * envelope is reported as ``envelopeMissing`` so the surface never claims a body
 * it cannot show.
 */
export function agentChainView(replay: AgentReplayDTO): AgentChainView {
  const chain: Partial<AgentArtifactChainSummaryDTO> = replay.artifact_chain ?? {};
  const declaredOrder = stringList(chain.order).filter(isAgentArtifactType);
  const order: AgentArtifactType[] = [];
  for (const type of [...declaredOrder, ...AGENT_ARTIFACT_TYPES]) {
    if (!order.includes(type)) order.push(type);
  }

  const artifacts = (replay.artifacts ?? {}) as AgentArtifactsDTO;
  const declaredPresent = new Set(stringList(chain.present));
  const declaredMissing = new Set(stringList(chain.missing));

  const entries: AgentChainEntry[] = order.map((artifactType, index) => {
    const envelope = envelopeOf(artifacts, artifactType) ?? null;
    const hasEnvelope = envelope !== null;
    const present = hasEnvelope && envelope.present === true;
    const envelopeMissing = !hasEnvelope && declaredPresent.has(artifactType);
    return {
      artifactType,
      position: index + 1,
      present,
      operationId: envelope?.operation_id ?? "",
      stage: envelope?.stage ?? "",
      artifactId: envelope?.artifact_id ?? null,
      artifactIds: stringList(envelope?.artifact_ids),
      envelopeMissing,
      envelope,
    };
  });

  const present = entries
    .filter((entry) => entry.present && !declaredMissing.has(entry.artifactType))
    .map((entry) => entry.artifactType);
  const missing = entries
    .filter((entry) => !present.includes(entry.artifactType))
    .map((entry) => entry.artifactType);

  return {
    entries,
    order,
    present,
    missing,
    complete: missing.length === 0,
    chainHash: typeof chain.chain_hash === "string" ? chain.chain_hash : "",
    presentCount: present.length,
    missingCount: missing.length,
    total: entries.length,
  };
}

/** One formatted list value plus how many entries stayed unrendered. */
export interface AgentValueList {
  values: string[];
  remaining: number;
  total: number;
}

/** Format a bounded list of persisted values for compact rendering. */
export function agentValueList(value: unknown, max = 6): AgentValueList {
  const items = Array.isArray(value) ? value : value === null || value === undefined ? [] : [value];
  const rendered = items
    .map((item) => agentCompactText(item))
    .filter((item) => item !== "");
  const bounded = max > 0 ? rendered.slice(0, max) : rendered;
  return { values: bounded, remaining: rendered.length - bounded.length, total: rendered.length };
}

/** Format one persisted scalar. Objects and arrays are not guessed at. */
export function agentScalarText(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : "";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "bigint") return value.toString();
  return "";
}

/**
 * Format one persisted value compactly: scalars verbatim, arrays joined,
 * records as sorted ``key=value`` pairs. Unknown shapes render as nothing
 * rather than as invented text.
 */
export function agentCompactText(value: unknown): string {
  const scalar = agentScalarText(value);
  if (scalar !== "") return scalar;
  if (Array.isArray(value)) return agentValueList(value).values.join(", ");
  if (value !== null && typeof value === "object") {
    return agentFieldRows(value)
      .map((row) => `${row.key}=${row.value}`)
      .join(", ");
  }
  return "";
}

export interface AgentFieldRow {
  key: string;
  value: string;
}

/** Flatten a persisted record into sorted ``key``/``value`` rows. */
export function agentFieldRows(value: unknown): AgentFieldRow[] {
  if (value === null || value === undefined || typeof value !== "object" || Array.isArray(value)) {
    return [];
  }
  return Object.entries(value as Record<string, unknown>)
    .map(([key, item]) => {
      const list = agentValueList(item);
      const text = list.values.join(", ");
      return { key, value: text === "" ? agentScalarText(item) : text };
    })
    .filter((row) => row.value !== "")
    .sort((left, right) => left.key.localeCompare(right.key));
}

/** Explicit UTC timestamp of a persisted ISO value, or an empty string when unusable. */
export function formatAgentTimestamp(value: string | null | undefined): string {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "";
  return `${parsed.toISOString().slice(0, 19).replace("T", " ")} UTC`;
}

export function formatAgentCount(value: number): string {
  return Number.isFinite(value) ? value.toLocaleString() : "";
}

// --- artifact payload views -------------------------------------------------

export interface AgentPlanView {
  planId: string;
  objective: string;
  question: string;
  product: string;
  horizon: string;
  status: string;
  createdBy: string;
  createdAt: string;
  strategyGenerationAllowed: boolean;
  marketScope: AgentValueList;
  entities: AgentValueList;
  hypotheses: AgentValueList;
  stoppingConditions: AgentValueList;
  analyses: Array<{ analysisId: string; analysisType: string; inputSeries: AgentValueList; parameters: string }>;
  evidence: Array<{ seriesId: string; required: boolean; maxSourceAgeSeconds: string; temporalIntegrityMin: string; unit: string }>;
  dataQuality: AgentFieldRow[];
  statistical: AgentFieldRow[];
}

export function agentPlanView(payload: AgentResearchPlanPayloadDTO | null): AgentPlanView | null {
  if (!payload) return null;
  return {
    planId: agentScalarText(payload.research_plan_id),
    objective: agentScalarText(payload.objective),
    question: agentScalarText(payload.question),
    product: agentScalarText(payload.product),
    horizon: agentScalarText(payload.horizon),
    status: agentScalarText(payload.status),
    createdBy: agentScalarText(payload.created_by),
    createdAt: formatAgentTimestamp(payload.created_at),
    strategyGenerationAllowed: payload.strategy_generation_allowed === true,
    marketScope: agentValueList(payload.market_scope),
    entities: agentValueList(payload.entities),
    hypotheses: agentValueList(payload.hypotheses_to_test),
    stoppingConditions: agentValueList(payload.stopping_conditions),
    analyses: (Array.isArray(payload.analyses) ? payload.analyses : []).map((analysis) => ({
      analysisId: agentScalarText(analysis?.analysis_id),
      analysisType: agentScalarText(analysis?.analysis_type),
      inputSeries: agentValueList(analysis?.input_series),
      parameters: agentFieldRows(analysis?.parameters)
        .map((row) => `${row.key}=${row.value}`)
        .join(", "),
    })),
    evidence: (Array.isArray(payload.required_evidence) ? payload.required_evidence : []).map(
      (requirement) => ({
        seriesId: agentScalarText(requirement?.series_id),
        required: requirement?.required !== false,
        maxSourceAgeSeconds: agentScalarText(requirement?.max_source_age_seconds),
        temporalIntegrityMin: agentScalarText(requirement?.temporal_integrity_min),
        unit: agentScalarText(requirement?.unit),
      }),
    ),
    dataQuality: agentFieldRows(payload.data_quality_requirements),
    statistical: agentFieldRows(payload.statistical_requirements),
  };
}

export interface AgentFindingRow {
  findingId: string;
  question: string;
  statistic: string;
  value: string;
  unit: string;
  sample: string;
  period: string;
  methodology: string;
  qualityState: string;
  createdAt: string;
  evidence: AgentValueList;
  limitations: AgentValueList;
}

export function agentFindingRows(
  payload: AgentResearchFindingPayloadDTO[] | null,
): AgentFindingRow[] {
  if (!Array.isArray(payload)) return [];
  return payload.map((finding) => ({
    findingId: agentScalarText(finding?.finding_id),
    question: agentScalarText(finding?.question),
    statistic: agentScalarText(finding?.statistic),
    value: agentScalarText(finding?.value),
    unit: agentScalarText(finding?.unit),
    sample: agentScalarText(finding?.sample),
    period: agentScalarText(finding?.period),
    methodology: agentScalarText(finding?.methodology),
    qualityState: agentScalarText(finding?.quality_state),
    createdAt: formatAgentTimestamp(finding?.created_at),
    evidence: agentValueList(finding?.evidence),
    limitations: agentValueList(finding?.limitations),
  }));
}

export interface AgentStrategyIRView {
  schemaVersion: string;
  hypothesis: string;
  universe: string;
  components: Array<{ componentId: string; componentType: string; weight: string; conditions: string }>;
  parameters: Array<{ parameterId: string; parameterType: string; unit: string; defaultValue: string; bounds: string }>;
  sizing: string;
  riskControls: AgentFieldRow[];
  economicAssumptions: AgentFieldRow[];
  dataRequirements: AgentFieldRow[];
  evaluationWindows: AgentFieldRow[];
}

export function agentStrategyIRView(
  payload: AgentStrategyIRPayloadDTO | null,
): AgentStrategyIRView | null {
  if (!payload) return null;
  const universe = payload.universe ?? { origin_hub: "", destination_hub: "", product: "", currency: "" };
  const sizing = payload.sizing ?? { method: "", max_pct: 0 };
  return {
    schemaVersion: agentScalarText(payload.schema_version),
    hypothesis: agentScalarText(payload.hypothesis),
    universe: [
      agentScalarText(universe.origin_hub),
      agentScalarText(universe.destination_hub),
      agentScalarText(universe.product),
      agentScalarText(universe.currency),
    ]
      .filter((item) => item !== "")
      .join(" → "),
    components: (Array.isArray(payload.components) ? payload.components : []).map((component) => ({
      componentId: agentScalarText(component?.component_id),
      componentType: agentScalarText(component?.component_type),
      weight: agentScalarText(component?.weight),
      conditions: (Array.isArray(component?.conditions) ? component.conditions : [])
        .map((condition) =>
          [
            agentScalarText(condition?.feature_id),
            agentScalarText(condition?.operator),
            agentScalarText(condition?.value),
            agentScalarText(condition?.unit),
          ]
            .filter((item) => item !== "")
            .join(" "),
        )
        .join(", "),
    })),
    parameters: (Array.isArray(payload.parameters) ? payload.parameters : []).map((parameter) => ({
      parameterId: agentScalarText(parameter?.parameter_id),
      parameterType: agentScalarText(parameter?.parameter_type),
      unit: agentScalarText(parameter?.unit),
      defaultValue: agentScalarText(parameter?.default_value),
      bounds: [
        agentScalarText(parameter?.min_value),
        agentScalarText(parameter?.max_value),
      ]
        .filter((item) => item !== "")
        .join(" … "),
    })),
    sizing: [
      agentScalarText(sizing.method),
      agentScalarText(sizing.max_pct),
      agentScalarText(sizing.max_quantity_mwh_per_day),
    ]
      .filter((item) => item !== "")
      .join(" / "),
    riskControls: agentFieldRows(payload.risk_controls),
    economicAssumptions: agentFieldRows(payload.economic_assumptions),
    dataRequirements: agentFieldRows(payload.data_requirements),
    evaluationWindows: (Array.isArray(payload.evaluation_windows) ? payload.evaluation_windows : []).flatMap(
      (window) => agentFieldRows(window),
    ),
  };
}

export interface AgentValidationIssueRow {
  code: string;
  detail: string;
  field: string;
  evidence: string;
}

export interface AgentValidationView {
  planId: string;
  planStatus: string;
  planValidationSource: string;
  strategyValidationSource: string;
  strategyOk: boolean | null;
  featureCatalogId: string;
  planIssues: AgentValidationIssueRow[];
  strategyIssues: AgentValidationIssueRow[];
  runBlockers: AgentValueList;
  runWarnings: AgentValueList;
}

export function agentValidationView(payload: AgentValidationPayloadDTO | null): AgentValidationView | null {
  if (!payload) return null;
  const strategyValidation = payload.strategy_ir_validation ?? null;
  return {
    planId: agentScalarText(payload.plan_id),
    planStatus: agentScalarText(payload.plan_status),
    planValidationSource: agentScalarText(payload.plan_validation_source),
    strategyValidationSource: agentScalarText(payload.strategy_ir_validation_source),
    strategyOk: strategyValidation ? strategyValidation.ok === true : null,
    featureCatalogId: agentScalarText(payload.feature_catalog_id),
    planIssues: (Array.isArray(payload.plan_validation_issues) ? payload.plan_validation_issues : []).map(
      (issue) => ({
        code: agentScalarText(issue?.code),
        detail: agentScalarText(issue?.detail),
        field: "",
        evidence: agentScalarText(issue?.evidence),
      }),
    ),
    strategyIssues: (
      Array.isArray(strategyValidation?.issues) ? strategyValidation.issues : []
    ).map((issue) => ({
      code: agentScalarText(issue?.code),
      detail: agentScalarText(issue?.detail),
      field: agentScalarText(issue?.field),
      evidence: "",
    })),
    runBlockers: agentValueList(payload.run_blockers),
    runWarnings: agentValueList(payload.run_warnings),
  };
}

export interface AgentIssueDisplayRow {
  code: string;
  detail: string;
  evidence: string;
}

export function agentIssueLabelKey(code: string): string {
  const normalized = code.trim().toUpperCase();
  const known: Record<string, string> = {
    DATA_MISSING: "agents.issue.data_missing",
    SERIES_UNAVAILABLE: "agents.issue.series_unavailable",
    MISSING_SERIES: "agents.issue.series_unavailable",
    ENTITLEMENT_MISSING: "agents.issue.entitlement_missing",
    INSUFFICIENT_HISTORY: "agents.issue.insufficient_history",
    TEMPORAL_PROVENANCE_INSUFFICIENT: "agents.issue.temporal_provenance_insufficient",
    HUMAN_CONFIRMATION_REQUIRED: "agents.issue.human_confirmation_required",
    STRATEGY_GENERATION_NOT_REQUESTED: "agents.issue.strategy_generation_not_requested",
    BACKTEST_DEFERRED: "agents.issue.backtest_deferred",
  };
  return known[normalized] ?? "agents.issue.generic";
}

export function agentIssueRowFromText(value: string): AgentIssueDisplayRow {
  const raw = String(value ?? "").trim();
  const separator = raw.indexOf(":");
  if (separator < 0) {
    return { code: raw, detail: "", evidence: "" };
  }
  return {
    code: raw.slice(0, separator).trim(),
    detail: raw.slice(separator + 1).trim(),
    evidence: "",
  };
}

export function agentReplayIssueRows(
  replay: AgentReplayDTO,
  kind: "blocker" | "warning",
): AgentIssueDisplayRow[] {
  const raw = kind === "blocker" ? replay.blockers : replay.warnings;
  const validationEnvelope = replay.artifacts?.validation;
  const validation = validationEnvelope?.artifact_type === "validation"
    ? agentValidationView(validationEnvelope.payload)
    : null;
  const validationIssues = [
    ...(validation?.planIssues ?? []),
    ...(validation?.strategyIssues ?? []),
  ];

  return raw.map((value) => {
    const parsed = agentIssueRowFromText(value);
    const matched = validationIssues.find(
      (issue) => issue.code.trim().toUpperCase() === parsed.code.trim().toUpperCase(),
    );
    return {
      code: parsed.code,
      detail: matched?.detail || parsed.detail,
      evidence: matched?.evidence || matched?.field || "",
    };
  });
}

export interface AgentChallengeItemRow {
  challenge: string;
  severity: string;
  result: string;
  recommendedFollowUp: string;
  evidence: AgentFieldRow[];
}

export interface AgentChallengeView {
  reportId: string;
  overallResult: string;
  recommendedFollowUp: string;
  strategyVersionId: string;
  backtestRunId: string;
  createdAt: string;
  items: AgentChallengeItemRow[];
}

export function agentChallengeView(
  payload: AgentChallengeReportPayloadDTO | null,
): AgentChallengeView | null {
  if (!payload) return null;
  return {
    reportId: agentScalarText(payload.challenge_report_id),
    overallResult: agentScalarText(payload.overall_result),
    recommendedFollowUp: agentScalarText(payload.recommended_follow_up),
    strategyVersionId: agentScalarText(payload.strategy_version_id),
    backtestRunId: agentScalarText(payload.backtest_run_id),
    createdAt: formatAgentTimestamp(payload.created_at),
    items: (Array.isArray(payload.items) ? payload.items : []).map((item) => ({
      challenge: agentScalarText(item?.challenge),
      severity: agentScalarText(item?.severity),
      result: agentScalarText(item?.result),
      recommendedFollowUp: agentScalarText(item?.recommended_follow_up),
      evidence: agentFieldRows(item?.evidence),
    })),
  };
}

export interface AgentReviewPackView {
  reviewPackId: string;
  objective: string;
  status: string;
  createdAt: string;
  keyFindings: AgentValueList;
  warnings: AgentValueList;
  knownLimitations: AgentValueList;
  alternativeHypotheses: AgentValueList;
  dataProvenance: AgentValueList;
  backtest: AgentFieldRow[];
  robustness: AgentFieldRow[];
}

export function agentReviewPackView(payload: AgentReviewPackPayloadDTO | null): AgentReviewPackView | null {
  if (!payload) return null;
  return {
    reviewPackId: agentScalarText(payload.review_pack_id),
    objective: agentScalarText(payload.objective),
    status: agentScalarText(payload.status),
    createdAt: formatAgentTimestamp(payload.created_at),
    keyFindings: agentValueList(payload.key_findings),
    warnings: agentValueList(payload.warnings),
    knownLimitations: agentValueList(payload.known_limitations),
    alternativeHypotheses: agentValueList(payload.alternative_hypotheses),
    dataProvenance: agentValueList(payload.data_provenance),
    backtest: agentFieldRows(payload.backtest),
    robustness: agentFieldRows(payload.robustness),
  };
}

// --- human confirmation gate ------------------------------------------------

export interface AgentConfirmationDecision {
  decisionId: string;
  decision: string;
  actor: string;
  note: string;
  createdAtUtc: string;
}

export type AgentGateUnavailableReason = "no_review_pack" | "no_artifact_id" | "no_identity";

export interface AgentReviewGate {
  entityType: string;
  entityId: string;
  available: boolean;
  unavailableReason: AgentGateUnavailableReason | null;
  decisions: AgentConfirmationDecision[];
  /** Entitlement/policy boundary recorded with the chain artifacts. */
  policyBoundary: string;
  /** Principal that produced the reviewed artifacts, shown beside the reviewer. */
  producedBy: string;
}

function confirmationDecisions(payload: AgentReviewPackPayloadDTO | null): AgentConfirmationDecision[] {
  const decisions = payload?.human_confirmation?.decisions;
  if (!Array.isArray(decisions)) return [];
  return decisions.map((decision: ReviewDecisionDTO) => ({
    decisionId: agentScalarText(decision?.decision_id),
    decision: agentScalarText(decision?.decision),
    actor: agentScalarText(decision?.actor),
    note: agentScalarText(decision?.note),
    createdAtUtc: formatAgentTimestamp(decision?.created_at_utc),
  }));
}

/**
 * Resolve the review pack a human decision can be recorded against.
 *
 * The gate is only offered for a present review pack with a persisted artifact
 * id and a resolved reviewer identity; every other case carries the reason so
 * the surface can explain the refusal instead of rendering a dead control.
 */
export function agentReviewGate(
  replay: AgentReplayDTO | null,
  reviewerIdentity: string | null = null,
): AgentReviewGate {
  const chain = replay ? agentChainView(replay) : null;
  const entry = chain?.entries.find((item) => item.artifactType === "review_pack") ?? null;
  const envelope = entry?.envelope ?? null;
  const payload = envelope?.artifact_type === "review_pack" ? envelope.payload : null;
  const entityType =
    agentScalarText(replay?.review_entity_type) ||
    agentScalarText(payload?.human_confirmation?.entity_type) ||
    AGENT_REVIEW_PACK_ENTITY_TYPE;
  const entityId = agentScalarText(payload?.review_pack_id) || agentScalarText(entry?.artifactId);
  const reviewer = (reviewerIdentity ?? "").trim();

  let unavailableReason: AgentGateUnavailableReason | null = null;
  if (!entry || !entry.present) unavailableReason = "no_review_pack";
  else if (entityId === "") unavailableReason = "no_artifact_id";
  else if (reviewer === "") unavailableReason = "no_identity";

  return {
    entityType,
    entityId,
    available: unavailableReason === null,
    unavailableReason,
    decisions: confirmationDecisions(payload),
    policyBoundary: envelope?.rights.policy_boundary ?? "",
    producedBy: envelope?.rights.principal_id ?? "",
  };
}

export type AgentConfirmationState =
  | { status: "idle" }
  | { status: "submitting"; decision: AgentReviewDecisionValue }
  | { status: "recorded"; decision: AgentReviewDecisionValue; decisionId: string }
  | { status: "refused"; httpStatus: number; refusalKey: string };

/**
 * Build the review-decision body for one gate.
 *
 * The body names no actor: the platform records the authenticated identity as the actor
 * (W0-03 C13), so a client-supplied name could only ever be an unverified claim. The reviewer
 * identity still decides whether the gate is *available* - that is a UI question about who may
 * confirm - but it is not what the decision is filed under.
 *
 * Returns null when the gate is unavailable or the server reported an entity kind outside the
 * controlled vocabulary this surface may post, so an unknown kind can never be invented
 * client-side.
 */
export function agentReviewDecisionInput(
  gate: AgentReviewGate,
  decision: AgentReviewDecisionValue,
  note: string,
): ReviewDecisionInputDTO | null {
  if (!gate.available || gate.entityId === "") return null;
  if (gate.entityType !== AGENT_REVIEW_PACK_ENTITY_TYPE) return null;
  const trimmedNote = note.trim();
  return {
    entity_type: AGENT_REVIEW_PACK_ENTITY_TYPE,
    entity_id: gate.entityId,
    decision,
    note: trimmedNote === "" ? null : trimmedNote,
  };
}

export type AgentConfirmationEvent =
  | { type: "submit"; decision: AgentReviewDecisionValue }
  | { type: "recorded"; decision: AgentReviewDecisionValue; decisionId: string | null }
  | { type: "refused"; httpStatus: number };

/**
 * Localised explanation key for one refused review-decision mutation.
 *
 * 422 is the controlled-vocabulary refusal (unknown review artifact kind) and
 * 401/403 is the identity refusal (missing or insufficiently privileged
 * reviewer); anything else stays a generic transport failure.
 */
export function agentConfirmationRefusalKey(httpStatus: number): string {
  if (httpStatus === 422) return "agents.gate.refusal_unknown_kind";
  if (httpStatus === 401 || httpStatus === 403) return "agents.gate.refusal_identity";
  return "agents.gate.refusal_failed";
}

/**
 * Pure confirmation state machine: one in-flight decision at a time, a refusal
 * never leaves the control stuck, and a new submit clears an earlier outcome.
 */
export function nextAgentConfirmationState(
  state: AgentConfirmationState,
  event: AgentConfirmationEvent,
): AgentConfirmationState {
  if (event.type === "submit") {
    if (state.status === "submitting") return state;
    return { status: "submitting", decision: event.decision };
  }
  if (state.status !== "submitting") return state;
  if (event.type === "recorded") {
    return {
      status: "recorded",
      decision: event.decision,
      decisionId: (event.decisionId ?? "").trim(),
    };
  }
  return {
    status: "refused",
    httpStatus: event.httpStatus,
    refusalKey: agentConfirmationRefusalKey(event.httpStatus),
  };
}

/** True while a confirmation is in flight; the gate is disabled then. */
export function agentConfirmationBusy(state: AgentConfirmationState): boolean {
  return state.status === "submitting";
}

/** Recorded/refused notice for the gate, or null while idle or in flight. */
export function agentConfirmationNotice(
  state: AgentConfirmationState,
): { tone: "recorded" | "refused"; key: string; decisionId: string } | null {
  if (state.status === "recorded") {
    return { tone: "recorded", key: "agents.gate.recorded", decisionId: state.decisionId };
  }
  if (state.status === "refused") {
    return { tone: "refused", key: state.refusalKey, decisionId: "" };
  }
  return null;
}
