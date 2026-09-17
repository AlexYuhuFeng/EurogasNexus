import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import type {
  AgentArtifactEnvelopeDTO,
  AgentArtifactType,
  AgentReplayDTO,
} from "../src/api/client.ts";
import {
  AGENT_ARTIFACT_TYPES,
  AGENT_REVIEW_PACK_ENTITY_TYPE,
  agentChainView,
  agentChallengeView,
  agentConfirmationBusy,
  agentConfirmationNotice,
  agentConfirmationRefusalKey,
  agentFieldRows,
  agentFindingRows,
  agentPlanView,
  agentReviewDecisionInput,
  agentReviewGate,
  agentStrategyIRView,
  agentValidationView,
  agentValueList,
  agentIssueLabelKey,
  agentIssueRowFromText,
  agentReplayIssueRows,
  formatAgentTimestamp,
  nextAgentConfirmationState,
  type AgentConfirmationState,
} from "../src/app/model/agentReplayModel.ts";

const RUN_ID = "agent-run-cr15ui001proof";
const REVIEW_PACK_ID = "review-pack-cr15ui001";

const OPERATION_IDS: Record<AgentArtifactType, string> = {
  research_plan: "agent.research.plan",
  findings: "agent.research.findings",
  strategy_ir: "agent.research.strategy_ir",
  validation: "agent.research.validation",
  challenge_report: "agent.research.challenge",
  review_pack: "agent.research.review_pack",
};

const STAGES: Record<AgentArtifactType, string> = {
  research_plan: "PLAN_DRAFTED",
  findings: "DATA_ANALYSIS",
  strategy_ir: "STRATEGY_SPEC_DRAFTED",
  validation: "PLAN_VALIDATED",
  challenge_report: "CHALLENGED",
  review_pack: "READY_FOR_HUMAN_REVIEW",
};

function artifactEnvelope(
  artifactType: AgentArtifactType,
  payload: unknown,
  present: boolean,
): AgentArtifactEnvelopeDTO {
  const artifactId = present ? `${artifactType}-id` : null;
  return {
    artifact_type: artifactType,
    operation_id: OPERATION_IDS[artifactType],
    stage: STAGES[artifactType],
    present,
    artifact_id: artifactId,
    artifact_ids: artifactId ? [artifactId] : [],
    agent_run_id: RUN_ID,
    fixture: {
      fixture_id: "fixture-0123456789abcdef0123",
      fixture_kind: "PERSISTED_RUN_INPUTS",
      evidence_refs: ["series:nbp.da.d1@2026-01-01"],
      tool_invocation_ids: ["invocation-1"],
      deterministic_model: { model_provider: "DETERMINISTIC", model_id: "deterministic-planner" },
    },
    replay_identity: {
      replay_id: `replay-${artifactType}-hash`,
      content_hash: `sha256:${artifactType}-hash`,
      deterministic: true,
    },
    lineage: {
      upstream_artifact_ids: ["research_plan-id"],
      producing_invocation_ids: ["invocation-1"],
      source_families: ["market"],
      series_ids: ["nbp.da.d1"],
      snapshot_ids: ["snapshot-1"],
      source_references: ["source:ice"],
      evidence_dependencies: ["evidence:1"],
    },
    rights: {
      entitlement_state: "GRANTED",
      entitlement_states: ["GRANTED"],
      principal_id: "dev.analyst",
      evaluated_invocation_ids: ["invocation-1"],
      policy_boundary: "CapabilityRuntime",
    },
    timestamps: {
      created_at: "2026-02-01T10:00:00+00:00",
      run_started_at: "2026-02-01T09:59:00+00:00",
      run_completed_at: "2026-02-01T10:05:00+00:00",
    },
    payload: present ? payload : null,
    hidden_chain_of_thought: null,
  } as AgentArtifactEnvelopeDTO;
}

function planPayload() {
  return {
    research_plan_id: "plan-cr15ui001",
    agent_run_id: RUN_ID,
    objective: "Establish whether the NBP day-ahead spread widened",
    question: "Did the NBP day-ahead spread widen over the window",
    market_scope: ["NBP", "TTF"],
    entities: ["hub.nbp"],
    product: "DAY_AHEAD",
    horizon: "D1",
    hypotheses_to_test: ["spread widens after storage withdrawal"],
    required_evidence: [
      {
        series_id: "nbp.da.d1",
        required: true,
        max_source_age_seconds: 900,
        temporal_integrity_min: "TEMPORAL_APPROXIMATE",
        unit: "GBP/MWh",
      },
    ],
    analyses: [
      {
        analysis_id: "analysis.spread",
        analysis_type: "descriptive",
        input_series: ["nbp.da.d1"],
        parameters: { window_days: 14 },
      },
    ],
    data_quality_requirements: { min_history_days: 14 },
    statistical_requirements: { min_sample: 30 },
    strategy_generation_allowed: true,
    stopping_conditions: ["evidence missing"],
    status: "VALIDATED",
    created_by: "agent",
    created_at: "2026-02-01T09:59:30+00:00",
  };
}

function findingPayload() {
  return {
    finding_id: "finding-1",
    research_plan_id: "plan-cr15ui001",
    agent_run_id: RUN_ID,
    question: "Did the spread widen",
    statistic: "mean_spread",
    value: "1.42",
    unit: "GBP/MWh",
    sample: "30",
    period: "P14D",
    methodology: "point-in-time descriptive statistic",
    evidence: ["snapshot-1"],
    limitations: ["approximate temporal integrity"],
    quality_state: "VERIFIED",
    created_at: "2026-02-01T10:01:00+00:00",
  };
}

function strategyIrPayload() {
  return {
    schema_version: "strategy-ir/1",
    hypothesis: "widen the day-ahead spread capture when storage withdrawals rise",
    universe: {
      origin_hub: "NBP",
      destination_hub: "TTF",
      product: "DAY_AHEAD",
      currency: "GBP",
    },
    components: [
      {
        component_id: "component-1",
        component_type: "SPREAD_CAPTURE",
        weight: 1,
        conditions: [{ feature_id: "feature.nbp.da.level", operator: "GT", value: 1.2, unit: "GBP/MWh" }],
      },
    ],
    parameters: [
      {
        parameter_id: "param.window_days",
        parameter_type: "INTEGER",
        unit: "days",
        default_value: 14,
        min_value: 7,
        max_value: 30,
      },
    ],
    sizing: { method: "RESOURCE_PERCENTAGE", max_pct: 20, max_quantity_mwh_per_day: 5000 },
    risk_controls: { max_ocm_allocation_pct: 80 },
    economic_assumptions: { transaction_cost_policy: "EXPLICIT_ZERO_UNMODELED" },
    data_requirements: { series_ids: ["nbp.da.d1"], require_fx: true },
    evaluation_windows: [{ start: "2026-01-01", end: "2026-01-15" }],
  };
}

function validationPayload() {
  return {
    plan_id: "plan-cr15ui001",
    plan_status: "VALIDATED",
    plan_validation_issues: [
      { code: "MISSING_SERIES", detail: "series not registered", evidence: "nbp.da.d1" },
    ],
    plan_validation_source: "persisted:agent_research_plans.validation_issues",
    strategy_ir_validation: {
      ok: false,
      issues: [{ code: "UNKNOWN_FEATURE", detail: "feature missing", field: "components.0" }],
    },
    strategy_ir_validation_source: "recomputed:validate_strategy_ir",
    feature_catalog_id: "agent-research-features/v1",
    run_blockers: ["EVIDENCE_INCOMPLETE"],
    run_warnings: ["FX_AS_OF_APPROXIMATED"],
  };
}

function challengePayload() {
  return {
    challenge_report_id: "challenge-1",
    agent_run_id: RUN_ID,
    strategy_version_id: "strategy-version-1",
    backtest_run_id: "backtest-1",
    items: [
      {
        challenge: "small sample",
        severity: "medium",
        evidence: { sample_size: 30 },
        result: "NEEDS_FOLLOW_UP",
        recommended_follow_up: "extend the window",
      },
    ],
    overall_result: "NEEDS_FOLLOW_UP",
    recommended_follow_up: "extend the window",
    created_at: "2026-02-01T10:03:00+00:00",
  };
}

function reviewPackPayload(decisions: Array<Record<string, unknown>> = []) {
  return {
    review_pack_id: REVIEW_PACK_ID,
    agent_run_id: RUN_ID,
    objective: "Establish whether the NBP day-ahead spread widened",
    research_plan: { research_plan_id: "plan-cr15ui001" },
    key_findings: [{ finding_id: "finding-1", statistic: "mean_spread" }],
    strategy_specification: strategyIrPayload(),
    backtest: { run_id: "backtest-1", status: "COMPLETED" },
    robustness: { parameter_variants: 3 },
    challenge_report: { challenge_report_id: "challenge-1" },
    data_provenance: ["snapshot-1"],
    warnings: ["FX_AS_OF_APPROXIMATED"],
    known_limitations: ["approximate temporal integrity"],
    alternative_hypotheses: ["spread narrows"],
    status: "READY_FOR_HUMAN_REVIEW",
    created_at: "2026-02-01T10:04:00+00:00",
    human_confirmation: {
      entity_type: AGENT_REVIEW_PACK_ENTITY_TYPE,
      entity_id: REVIEW_PACK_ID,
      decisions,
    },
  };
}

function replayFixture(options: {
  present?: AgentArtifactType[];
  order?: string[];
  declarations?: { present?: string[]; missing?: string[] };
  decisions?: Array<Record<string, unknown>>;
  omitEnvelope?: AgentArtifactType[];
} = {}): AgentReplayDTO {
  const present = options.present ?? [...AGENT_ARTIFACT_TYPES];
  const payloadFor: Record<AgentArtifactType, unknown> = {
    research_plan: planPayload(),
    findings: [findingPayload()],
    strategy_ir: strategyIrPayload(),
    validation: validationPayload(),
    challenge_report: challengePayload(),
    review_pack: reviewPackPayload(options.decisions ?? []),
  };
  const artifacts = {} as AgentReplayDTO["artifacts"];
  for (const artifactType of AGENT_ARTIFACT_TYPES) {
    if ((options.omitEnvelope ?? []).includes(artifactType)) continue;
    const isPresent = present.includes(artifactType);
    artifacts[artifactType] = artifactEnvelope(
      artifactType,
      payloadFor[artifactType],
      isPresent,
    );
  }
  const declaredPresent =
    options.declarations?.present ??
    AGENT_ARTIFACT_TYPES.filter((artifactType) => present.includes(artifactType));
  const declaredMissing =
    options.declarations?.missing ??
    AGENT_ARTIFACT_TYPES.filter((artifactType) => !present.includes(artifactType));
  return {
    agent_run_id: RUN_ID,
    principal_id: "dev.analyst",
    user_objective: "Establish whether the NBP day-ahead spread widened",
    agent_profile: "STRATEGY_RESEARCHER",
    model_provider: "DETERMINISTIC",
    model_id: "deterministic-planner",
    status: "COMPLETED",
    current_stage: "READY_FOR_HUMAN_REVIEW",
    artifacts_created: ["research_plan", "review_pack"],
    created_at: "2026-02-01T09:59:00+00:00",
    completed_at: "2026-02-01T10:05:00+00:00",
    research_plan_id: "plan-cr15ui001",
    evidence_dependencies: ["evidence:1"],
    warnings: ["FX_AS_OF_APPROXIMATED"],
    blockers: [],
    final_output_reference: REVIEW_PACK_ID,
    started_at: "2026-02-01T09:59:00+00:00",
    review_entity_type: AGENT_REVIEW_PACK_ENTITY_TYPE,
    fixture: {
      fixture_id: "fixture-0123456789abcdef0123",
      fixture_kind: "PERSISTED_RUN_INPUTS",
      evidence_refs: ["series:nbp.da.d1@2026-01-01"],
      tool_invocation_ids: ["invocation-1"],
      deterministic_model: { model_provider: "DETERMINISTIC", model_id: "deterministic-planner" },
    },
    artifact_chain: {
      order: options.order ?? [...AGENT_ARTIFACT_TYPES],
      present: declaredPresent,
      missing: declaredMissing,
      complete: declaredMissing.length === 0,
      artifact_ids: {},
      chain_hash: "sha256:chainhash",
    },
    artifacts,
    tool_invocations: [{ invocation_id: "invocation-1" }],
    hidden_chain_of_thought: null,
  } as AgentReplayDTO;
}

function readWebFile(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

test("the chain view keeps the persisted server order and reports present state", () => {
  const chain = agentChainView(replayFixture());

  assert.deepEqual(
    chain.order,
    [...AGENT_ARTIFACT_TYPES],
  );
  assert.equal(chain.complete, true);
  assert.equal(chain.presentCount, 6);
  assert.equal(chain.missingCount, 0);
  assert.deepEqual(chain.missing, []);
  assert.equal(chain.chainHash, "sha256:chainhash");
  assert.deepEqual(
    chain.entries.map((entry) => [entry.position, entry.artifactType, entry.operationId, entry.stage]),
    [
      [1, "research_plan", "agent.research.plan", "PLAN_DRAFTED"],
      [2, "findings", "agent.research.findings", "DATA_ANALYSIS"],
      [3, "strategy_ir", "agent.research.strategy_ir", "STRATEGY_SPEC_DRAFTED"],
      [4, "validation", "agent.research.validation", "PLAN_VALIDATED"],
      [5, "challenge_report", "agent.research.challenge", "CHALLENGED"],
      [6, "review_pack", "agent.research.review_pack", "READY_FOR_HUMAN_REVIEW"],
    ],
  );
  for (const entry of chain.entries) {
    assert.equal(entry.present, true);
    assert.equal(entry.envelopeMissing, false);
    assert.equal(entry.envelope?.hidden_chain_of_thought, null);
    assert.equal(entry.envelope?.fixture.fixture_kind, "PERSISTED_RUN_INPUTS");
    assert.equal(entry.envelope?.rights.policy_boundary, "CapabilityRuntime");
  }
});

test("a partially persisted run derives missing artifacts instead of failing", () => {
  const partial = replayFixture({ present: ["research_plan", "validation"] });
  const chain = agentChainView(partial);

  assert.equal(chain.complete, false);
  assert.equal(chain.presentCount, 2);
  assert.equal(chain.missingCount, 4);
  assert.deepEqual(chain.missing, [
    "findings",
    "strategy_ir",
    "challenge_report",
    "review_pack",
  ]);

  const reviewPack = chain.entries.find((entry) => entry.artifactType === "review_pack");
  assert.equal(reviewPack?.present, false);
  assert.equal(reviewPack?.artifactId, null);
  assert.equal(reviewPack?.envelope?.payload, null);
  assert.deepEqual(reviewPack?.envelope?.artifact_ids, []);

  const plan = chain.entries.find((entry) => entry.artifactType === "research_plan");
  assert.equal(plan?.present, true);
  assert.equal(plan?.artifactId, "research_plan-id");
});

test("an order that omits a type still renders that artifact", () => {
  const chain = agentChainView(replayFixture({ order: ["research_plan", "review_pack"] }));

  assert.equal(chain.entries.length, 6);
  assert.deepEqual(
    chain.entries.map((entry) => entry.artifactType),
    ["research_plan", "review_pack", "findings", "strategy_ir", "validation", "challenge_report"],
  );
  assert.deepEqual(chain.order.slice(0, 2), ["research_plan", "review_pack"]);
});

test("a chain that declares an artifact present without a body never claims a payload", () => {
  const chain = agentChainView(
    replayFixture({
      present: ["research_plan", "validation"],
      declarations: { present: ["research_plan", "validation", "findings"], missing: ["strategy_ir"] },
      omitEnvelope: ["findings"],
    }),
  );

  const findings = chain.entries.find((entry) => entry.artifactType === "findings");
  assert.equal(findings?.envelopeMissing, true);
  assert.equal(findings?.present, false);
  assert.equal(findings?.envelope, null);
  assert.ok(chain.missing.includes("findings"));
});

test("agent issue presentation preserves raw codes and attaches persisted evidence context", () => {
  const replay = replayFixture();
  // The fixture intentionally carries the older MISSING_SERIES validation
  // vocabulary. Replay presentation must enrich historical persisted runs too,
  // rather than only matching the current SERIES_UNAVAILABLE spelling.
  replay.blockers = ["MISSING_SERIES"];
  replay.warnings = ["BACKTEST_DEFERRED: no period/frozen version evidence"];

  const blockers = agentReplayIssueRows(replay, "blocker");
  assert.equal(blockers[0]?.code, "MISSING_SERIES");
  assert.equal(blockers[0]?.detail, "series not registered");
  assert.equal(blockers[0]?.evidence, "nbp.da.d1");
  assert.equal(agentIssueLabelKey("MISSING_SERIES"), "agents.issue.series_unavailable");
  assert.equal(agentIssueLabelKey("SERIES_UNAVAILABLE"), "agents.issue.series_unavailable");

  const warning = agentIssueRowFromText(replay.warnings[0] ?? "");
  assert.equal(warning.code, "BACKTEST_DEFERRED");
  assert.equal(warning.detail, "no period/frozen version evidence");
  assert.equal(agentIssueLabelKey("UNKNOWN_CODE"), "agents.issue.generic");
});

test("artifact payloads render compact rows without inventing values", () => {
  const plan = agentPlanView(planPayload());
  assert.equal(plan?.status, "VALIDATED");
  assert.equal(plan?.strategyGenerationAllowed, true);
  assert.deepEqual(plan?.marketScope.values, ["NBP", "TTF"]);
  assert.equal(plan?.analyses[0]?.analysisId, "analysis.spread");
  assert.equal(plan?.analyses[0]?.parameters, "window_days=14");
  assert.equal(plan?.evidence[0]?.seriesId, "nbp.da.d1");
  assert.equal(plan?.evidence[0]?.maxSourceAgeSeconds, "900");
  assert.deepEqual(plan?.dataQuality, [{ key: "min_history_days", value: "14" }]);
  assert.equal(agentPlanView(null), null);

  const findings = agentFindingRows([findingPayload()]);
  assert.equal(findings.length, 1);
  assert.equal(findings[0]?.value, "1.42");
  assert.equal(findings[0]?.qualityState, "VERIFIED");
  assert.deepEqual(findings[0]?.evidence.values, ["snapshot-1"]);
  assert.deepEqual(agentFindingRows(null), []);

  const strategy = agentStrategyIRView(strategyIrPayload());
  assert.equal(strategy?.universe, "NBP → TTF → DAY_AHEAD → GBP");
  assert.equal(strategy?.components[0]?.conditions, "feature.nbp.da.level GT 1.2 GBP/MWh");
  assert.equal(strategy?.parameters[0]?.bounds, "7 … 30");
  assert.deepEqual(strategy?.dataRequirements, [
    { key: "require_fx", value: "true" },
    { key: "series_ids", value: "nbp.da.d1" },
  ]);
  assert.equal(agentStrategyIRView(null), null);

  const validation = agentValidationView(validationPayload());
  assert.equal(validation?.planValidationSource, "persisted:agent_research_plans.validation_issues");
  assert.equal(validation?.strategyValidationSource, "recomputed:validate_strategy_ir");
  assert.deepEqual(validation?.planIssues.map((issue) => issue.code), ["MISSING_SERIES"]);
  assert.deepEqual(validation?.strategyIssues.map((issue) => issue.code), ["UNKNOWN_FEATURE"]);
  assert.equal(validation?.strategyOk, false);
  assert.deepEqual(validation?.runWarnings.values, ["FX_AS_OF_APPROXIMATED"]);
  assert.equal(agentValidationView(null), null);

  const challenge = agentChallengeView(challengePayload());
  assert.equal(challenge?.overallResult, "NEEDS_FOLLOW_UP");
  assert.deepEqual(challenge?.items.map((item) => item.severity), ["medium"]);
  assert.deepEqual(challenge?.items[0]?.evidence, [{ key: "sample_size", value: "30" }]);
  assert.equal(agentChallengeView(null), null);
});

test("bounded value lists and field rows never invent text", () => {
  assert.deepEqual(agentValueList(["a", "b", "c"], 2), { values: ["a", "b"], remaining: 1, total: 3 });
  assert.deepEqual(agentValueList(null), { values: [], remaining: 0, total: 0 });
  assert.deepEqual(agentValueList([{ k: 1 }]), { values: ["k=1"], remaining: 0, total: 1 });
  assert.deepEqual(agentValueList([{ nested: { deep: true } }]).values, ["nested=deep=true"]);
  assert.deepEqual(agentFieldRows({ b: 1, a: "x", c: null }), [
    { key: "a", value: "x" },
    { key: "b", value: "1" },
  ]);
  assert.deepEqual(agentFieldRows(null), []);
  assert.equal(agentValueList([1, 2]).values.join(", "), "1, 2");
});

test("timestamps render only when usable and always name the UTC basis", () => {
  assert.equal(formatAgentTimestamp(null), "");
  assert.equal(formatAgentTimestamp("not-a-timestamp"), "");
  assert.equal(
    formatAgentTimestamp("2026-02-01T10:04:00+00:00"),
    "2026-02-01 10:04:00 UTC",
  );
});

test("the review gate is offered only for a present review pack with an id and a reviewer", () => {
  const full = agentReviewGate(replayFixture(), "dev.analyst");
  assert.equal(full.available, true);
  assert.equal(full.unavailableReason, null);
  assert.equal(full.entityType, AGENT_REVIEW_PACK_ENTITY_TYPE);
  assert.equal(full.entityId, REVIEW_PACK_ID);
  assert.equal(full.producedBy, "dev.analyst");
  assert.equal(full.policyBoundary, "CapabilityRuntime");
  assert.deepEqual(full.decisions, []);

  const withoutPack = agentReviewGate(
    replayFixture({ present: ["research_plan", "validation"] }),
    "dev.analyst",
  );
  assert.equal(withoutPack.available, false);
  assert.equal(withoutPack.unavailableReason, "no_review_pack");
  assert.equal(withoutPack.entityId, "");

  const withoutIdentity = agentReviewGate(replayFixture(), null);
  assert.equal(withoutIdentity.available, false);
  assert.equal(withoutIdentity.unavailableReason, "no_identity");

  assert.equal(agentReviewGate(null, "dev.analyst").unavailableReason, "no_review_pack");

  const recorded = agentReviewGate(
    replayFixture({
      decisions: [
        {
          decision_id: "review-1",
          entity_type: AGENT_REVIEW_PACK_ENTITY_TYPE,
          entity_id: REVIEW_PACK_ID,
          actor: "dev.reviewer",
          decision: "accepted",
          note: "evidence complete",
          created_at_utc: "2026-02-01T11:00:00+00:00",
        },
      ],
    }),
    "dev.analyst",
  );
  assert.equal(recorded.decisions.length, 1);
  assert.equal(recorded.decisions[0]?.actor, "dev.reviewer");
  assert.equal(recorded.decisions[0]?.decision, "accepted");
  assert.equal(recorded.decisions[0]?.note, "evidence complete");
  assert.notEqual(recorded.decisions[0]?.createdAtUtc, "");
});

test("the posted review decision never invents an entity kind or an actor", () => {
  const gate = agentReviewGate(replayFixture(), "dev.analyst");
  const body = agentReviewDecisionInput(gate, "accepted", "  ");
  // No actor: the platform records the authenticated identity (W0-03 C13), so the client sends
  // no name it could only be repeating as an unverified claim.
  assert.deepEqual(body, {
    entity_type: AGENT_REVIEW_PACK_ENTITY_TYPE,
    entity_id: REVIEW_PACK_ID,
    decision: "accepted",
    note: null,
  });
  assert.equal("actor" in (body ?? {}), false);
  assert.equal(
    agentReviewDecisionInput(gate, "needs_attention", " check ")?.note,
    "check",
  );

  const unavailable = agentReviewGate(replayFixture({ present: ["research_plan"] }), "dev.analyst");
  assert.equal(agentReviewDecisionInput(unavailable, "accepted", ""), null);

  const foreignKind = { ...gate, entityType: "generated_report" };
  assert.equal(agentReviewDecisionInput(foreignKind, "accepted", ""), null);
});

test("confirmation transitions hold one in-flight decision and explain refusals", () => {
  let state: AgentConfirmationState = { status: "idle" };
  assert.equal(agentConfirmationBusy(state), false);
  assert.equal(agentConfirmationNotice(state), null);

  state = nextAgentConfirmationState(state, { type: "submit", decision: "accepted" });
  assert.deepEqual(state, { status: "submitting", decision: "accepted" });
  assert.equal(agentConfirmationBusy(state), true);

  const held = nextAgentConfirmationState(state, { type: "submit", decision: "rejected" });
  assert.deepEqual(held, state);

  state = nextAgentConfirmationState(state, {
    type: "recorded",
    decision: "accepted",
    decisionId: "review-9",
  });
  assert.deepEqual(state, { status: "recorded", decision: "accepted", decisionId: "review-9" });
  assert.equal(agentConfirmationBusy(state), false);
  assert.deepEqual(agentConfirmationNotice(state), {
    tone: "recorded",
    key: "agents.gate.recorded",
    decisionId: "review-9",
  });

  const refused = nextAgentConfirmationState(
    nextAgentConfirmationState(state, { type: "submit", decision: "rejected" }),
    { type: "refused", httpStatus: 422 },
  );
  assert.deepEqual(refused, {
    status: "refused",
    httpStatus: 422,
    refusalKey: "agents.gate.refusal_unknown_kind",
  });
  assert.deepEqual(agentConfirmationNotice(refused), {
    tone: "refused",
    key: "agents.gate.refusal_unknown_kind",
    decisionId: "",
  });

  assert.equal(agentConfirmationRefusalKey(422), "agents.gate.refusal_unknown_kind");
  assert.equal(agentConfirmationRefusalKey(403), "agents.gate.refusal_identity");
  assert.equal(agentConfirmationRefusalKey(401), "agents.gate.refusal_identity");
  assert.equal(agentConfirmationRefusalKey(500), "agents.gate.refusal_failed");
  assert.equal(agentConfirmationRefusalKey(0), "agents.gate.refusal_failed");

  const idle = nextAgentConfirmationState({ status: "idle" }, { type: "refused", httpStatus: 403 });
  assert.deepEqual(idle, { status: "idle" });
});

test("the agents surface renders objectives, explicit UTC timestamps, and contextual issues without clipping", () => {
  const workspace = readWebFile("components/AgentsWorkspace.tsx");
  const css = readWebFile("styles/app.css");

  assert.match(workspace, /t\("agents\.objective"\).*objective\.trim\(\)/s);
  assert.match(workspace, /formatAgentTimestamp\(run\.created_at\)/);
  assert.match(workspace, /formatAgentTimestamp\(selectedRun\.started_at\)/);
  assert.match(workspace, /agentReplayIssueRows\(selectedRun, "blocker"\)/);
  assert.match(workspace, /<AgentIssueList rows=\{selectedBlockers\} t=\{t\} \/>/);
  assert.match(workspace, /className="agents-run-objective"/);
  assert.match(workspace, /className="agents-run-model"/);

  assert.match(css, /\.agents-page \.agents-run-objective,[\s\S]*?white-space: normal;/);
  assert.match(css, /\.agents-replay-panel \{[\s\S]*?border: 0;/);
  assert.match(css, /\.agents-issue-list/);
});

test("the agents surface renders the chain and the gate through shared primitives", () => {
  const workspace = readWebFile("components/AgentsWorkspace.tsx");
  const chain = readWebFile("components/agents/AgentArtifactChain.tsx");
  const gate = readWebFile("components/agents/AgentReviewGate.tsx");

  for (const primitive of ["MetricStrip", "PanelHeader", "WorkspaceHeader"]) {
    assert.match(workspace, new RegExp(`<${primitive}`));
  }
  assert.match(workspace, /from "@\/components\/ui"/);
  for (const primitive of ["MetricStrip", "PanelHeader", "StatusBadge"]) {
    assert.match(chain, new RegExp(`<${primitive}`));
  }
  assert.match(chain, /from "@\/components\/ui"/);
  for (const primitive of ["PanelHeader", "StatusBadge"]) {
    assert.match(gate, new RegExp(`<${primitive}`));
  }
  assert.match(gate, /from "@\/components\/ui"/);
  assert.doesNotMatch(chain, /<button[\s\S]*?role="tab"/);
  assert.doesNotMatch(gate, /<button[\s\S]*?role="tab"/);

  // Already-verified agent behaviour stays mounted.
  assert.match(workspace, /api\.runAgentResearch/);
  assert.match(workspace, /api\.agentRuns\(\)/);
  assert.match(workspace, /api\.agentReplay\(/);
  assert.match(workspace, /t\("agents\.no_runs"\)/);
  assert.match(workspace, /t\("agents\.capability"\)/);
  assert.match(workspace, /<AgentArtifactChain replay=\{selectedRun\} t=\{t\} \/>/);
  assert.match(workspace, /<AgentReviewGate/);
});

test("the gate records through the existing review endpoint and disables in flight", () => {
  const workspace = readWebFile("components/AgentsWorkspace.tsx");
  const gate = readWebFile("components/agents/AgentReviewGate.tsx");
  const model = readWebFile("app/model/agentReplayModel.ts");
  const client = readWebFile("api/client.ts");

  assert.match(workspace, /api\.recordReviewDecisionOutcome\(body\)/);
  assert.match(workspace, /agentReviewDecisionInput\(gate, decision, note\)/);
  // The reviewer identity still decides whether the gate is available; it is simply no longer
  // sent as the actor, because the platform records the authenticated identity.
  assert.match(workspace, /agentReviewGate\(selectedRun, reviewerIdentity\)/);
  assert.match(workspace, /api\.agentReplay\(selectedRun\.agent_run_id\)/);
  assert.doesNotMatch(workspace, /"\/review/);
  assert.match(client, /recordReviewDecisionOutcome: \(body: ReviewDecisionInputDTO\) =>[\s\S]*?apiOutcome\(\(\) => post<ReviewDecisionDTO>\("\/review\/decisions", body\)\)/);
  assert.match(client, /"agent_review_pack"/);
  assert.match(client, /recordReviewDecision: \(body: ReviewDecisionInputDTO\) =>/);

  assert.match(gate, /const disabled = !gate\.available \|\| busy/);
  assert.match(gate, /disabled=\{disabled\}/);
  assert.match(gate, /AGENT_REVIEW_DECISIONS\.map/);
  assert.match(gate, /agentConfirmationNotice\(state\)/);
  assert.match(gate, /\{t\(notice\.key\)\}/);
  assert.match(gate, /t\(UNAVAILABLE_KEYS\[gate\.unavailableReason\]\)/);

  for (const key of [
    "agents.gate.refusal_unknown_kind",
    "agents.gate.refusal_identity",
    "agents.gate.refusal_failed",
  ]) {
    assert.match(model, new RegExp(`"${key.replace(/\./g, "\\.")}"`));
  }
  assert.match(model, /if \(httpStatus === 422\) return "agents\.gate\.refusal_unknown_kind"/);
  assert.match(model, /if \(httpStatus === 401 \|\| httpStatus === 403\) return "agents\.gate\.refusal_identity"/);
});

test("hidden reasoning is only ever rendered as an explicit not-applicable statement", () => {
  const chain = readWebFile("components/agents/AgentArtifactChain.tsx");
  const workspace = readWebFile("components/AgentsWorkspace.tsx");

  assert.match(chain, /t\("agents\.hidden_cot_none"\)/);
  assert.doesNotMatch(chain, /hidden_chain_of_thought\s*\./);
  assert.doesNotMatch(workspace, /hidden_chain_of_thought/);
  assert.doesNotMatch(workspace + chain, /reasoning_steps|thought_process|scratchpad/i);
});

test("every new agent string exists in both locales without placeholder characters", () => {
  const en = JSON.parse(readWebFile("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(readWebFile("i18n/zh.json")) as Record<string, string>;
  const added = [
    "agents.issue.data_missing",
    "agents.issue.series_unavailable",
    "agents.issue.entitlement_missing",
    "agents.issue.insufficient_history",
    "agents.issue.temporal_provenance_insufficient",
    "agents.issue.human_confirmation_required",
    "agents.issue.strategy_generation_not_requested",
    "agents.issue.backtest_deferred",
    "agents.issue.generic",
    "agents.issue.affected_evidence",
    "agents.issue.unknown_code",
    "agents.chain",
    "agents.chain_help",
    "agents.chain_progress",
    "agents.chain_missing",
    "agents.chain_state",
    "agents.chain_complete",
    "agents.chain_incomplete",
    "agents.artifact.research_plan",
    "agents.artifact.findings",
    "agents.artifact.strategy_ir",
    "agents.artifact.validation",
    "agents.artifact.challenge_report",
    "agents.artifact.review_pack",
    "agents.artifact_present",
    "agents.artifact_missing",
    "agents.artifact_absent",
    "agents.operation_id",
    "agents.stage",
    "agents.artifact_id",
    "agents.artifact_ids",
    "agents.replay_id",
    "agents.content_hash",
    "agents.deterministic",
    "agents.fixture_id",
    "agents.fixture_kind",
    "agents.fixture_model",
    "agents.lineage.upstream",
    "agents.lineage.invocations",
    "agents.lineage.source_families",
    "agents.lineage.series",
    "agents.lineage.snapshots",
    "agents.lineage.source_refs",
    "agents.lineage.evidence_deps",
    "agents.rights.state",
    "agents.rights.states",
    "agents.rights.principal",
    "agents.rights.boundary",
    "agents.rights.evaluated",
    "agents.created_at",
    "agents.run_started_at",
    "agents.run_completed_at",
    "agents.payload",
    "agents.payload_absent",
    "agents.value_absent",
    "agents.more_values",
    "agents.hidden_cot_none",
    "agents.plan.objective",
    "agents.plan.status",
    "agents.plan.analyses",
    "agents.plan.required_evidence",
    "agents.findings.count",
    "agents.findings.statistic",
    "agents.strategy_ir.hypothesis",
    "agents.strategy_ir.risk_controls",
    "agents.validation.plan_issues",
    "agents.validation.strategy_issues",
    "agents.challenge.overall_result",
    "agents.challenge.items",
    "agents.review_pack.status",
    "agents.review_pack.key_findings",
    "agents.gate.title",
    "agents.gate.help",
    "agents.gate.accepted",
    "agents.gate.rejected",
    "agents.gate.needs_attention",
    "agents.gate.in_flight",
    "agents.gate.recorded",
    "agents.gate.refusal_unknown_kind",
    "agents.gate.refusal_identity",
    "agents.gate.refusal_failed",
    "agents.gate.boundary",
    "agents.gate.no_decisions",
  ];
  for (const key of added) {
    assert.ok(typeof en[key] === "string" && en[key] !== "", `en missing ${key}`);
    assert.ok(typeof zh[key] === "string" && zh[key] !== "", `zh missing ${key}`);
    assert.notEqual(en[key], zh[key], `untranslated ${key}`);
    assert.doesNotMatch(en[key], /\?|\ufffd/, `placeholder in en ${key}`);
    assert.doesNotMatch(zh[key], /\?|\ufffd/, `placeholder in zh ${key}`);
  }
});
