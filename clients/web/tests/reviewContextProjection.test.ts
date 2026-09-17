/**
 * Architecture V2 Wave 5 - review projection consumption tests.
 *
 * The review surface resolves evidence per review entity, so it reads its own projection
 * when it opens instead of making every session pay for that work. These tests pin what
 * makes that safe: unresolved evidence stays explicitly unavailable with its reason, the
 * decisions slice is the anchor, the on-demand read is gated and coalesced, and the
 * surface says what the read actually returned.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  REVIEW_CONTEXT_SLICE_LABEL_KEYS,
  REVIEW_CONTEXT_SLICE_ORDER,
  degradedReviewSlices,
  reviewAsOf,
  reviewDecisions,
  reviewEvidence,
  reviewEvidenceCoverage,
  reviewEvidenceFor,
  reviewIsUsable,
  reviewLatestDecision,
  reviewMonitoring,
  reviewNeedsAttentionCount,
  reviewReadings,
  reviewTimeBasis,
} from "../src/app/model/reviewContextModel.ts";
import type {
  ProjectionSliceDTO,
  ReviewContextProjectionDTO,
} from "../src/api/client.ts";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

/** A slice fixture; only the fields a case asserts on are overridden. */
function slice(overrides: Record<string, unknown> = {}): ProjectionSliceDTO<never> {
  return {
    available: true,
    source_references: ["runtime-postgresql"],
    row_count: 0,
    rows: null,
    payload: null,
    freshness: {
      state: "FRESH",
      basis: "gas-day",
      evaluated_at_utc: "2026-09-16T06:00:00+00:00",
      last_observed_at_utc: "2026-09-16T05:58:00+00:00",
      expected_within_minutes: null,
      expectation_source: null,
      measured: null,
      derived_from: null,
    },
    entitlement: null,
    context_filter: null,
    limits: null,
    warnings: [],
    notes: [],
    ...overrides,
  } as unknown as ProjectionSliceDTO<never>;
}

const DECISION = {
  decision_id: "decision-1",
  entity_type: "intraday_opportunity",
  entity_id: "opportunity-1",
  actor: "analyst@example",
  decision: "needs_attention",
  note: "spread looks stale",
  created_at_utc: "2026-09-16T05:30:00+00:00",
};

function projection(
  overrides: Partial<
    Record<keyof ReviewContextProjectionDTO["slices"], ProjectionSliceDTO<never>>
  > = {},
): ReviewContextProjectionDTO {
  return {
    projection: "review-context",
    projection_version: "review-context/v1",
    as_of_utc: "2026-09-16T06:00:00+00:00",
    time_basis: { basis_id: "EU-CAM-UTC-2025", gas_day: "2026-09-16" },
    active_context: { gas_day: "2026-09-16" },
    review_target: { entity_type: "intraday_opportunity", entity_id: "opportunity-1" },
    slices: {
      decisions: slice({
        row_count: 1,
        rows: [DECISION],
        payload: {
          latest_decision: DECISION,
          needs_attention_count: 1,
          decided_entities: [
            { entity_type: "intraday_opportunity", entity_id: "opportunity-1" },
          ],
        },
      }),
      evidence: slice({
        row_count: 2,
        rows: [
          {
            entity_type: "intraday_opportunity",
            entity_id: "opportunity-1",
            available: true,
            resolver: "intraday_opportunity",
            artifact: { opportunity_id: "opportunity-1" },
            unavailable_reason: null,
            warnings: [],
          },
          {
            entity_type: "strategy_run",
            entity_id: "run-1",
            available: false,
            resolver: "strategy_run",
            artifact: null,
            unavailable_reason: "ENTITLEMENT_DENIED",
            warnings: ["ENTITLEMENT_DENIED"],
          },
        ],
        payload: {
          requested_entity_count: 2,
          resolved_entity_count: 1,
          supported_entity_types: ["intraday_opportunity", "strategy_run"],
        },
      }),
      monitoring: slice({
        payload: {
          open_count: 3,
          acknowledged_count: 1,
          critical_count: 0,
          warning_count: 2,
          info_count: 1,
          llm_pending_count: 0,
          simulated_count: 0,
        },
      }),
      ...overrides,
    },
    warnings: [],
    research_only: true,
    human_review_required: true,
  } as unknown as ReviewContextProjectionDTO;
}

test("the review payload carries decisions, evidence and monitoring on one as-of", () => {
  const payload = projection();

  assert.equal(reviewAsOf(payload), "2026-09-16T06:00:00+00:00");
  assert.equal(reviewTimeBasis(payload)?.gas_day, "2026-09-16");

  assert.equal(reviewDecisions(payload).length, 1);
  assert.equal(reviewLatestDecision(payload)?.decision_id, "decision-1");
  assert.equal(reviewNeedsAttentionCount(payload), 1);
  assert.equal(reviewEvidence(payload).length, 2);
  assert.equal(reviewMonitoring(payload)?.open_count, 3);
  assert.equal(reviewIsUsable(payload), true);

  assert.deepEqual(
    reviewReadings(payload).map((reading) => reading.key),
    REVIEW_CONTEXT_SLICE_ORDER,
  );
});

test("evidence a resolver could not produce stays unavailable with its reason", () => {
  const payload = projection();
  const entries = reviewEvidence(payload);

  const withheld = entries.find((entry) => entry.entity_id === "run-1");
  assert.equal(withheld?.available, false);
  assert.equal(withheld?.unavailable_reason, "ENTITLEMENT_DENIED");
  // The client never renders an unavailable artifact as an empty one.
  assert.equal(withheld?.artifact, null);

  const resolved = reviewEvidenceFor(payload, "intraday_opportunity", "opportunity-1");
  assert.equal(resolved?.available, true);
  assert.equal(resolved?.artifact?.opportunity_id, "opportunity-1");

  // Coverage is the honest summary: two asked for, one resolved.
  assert.deepEqual(reviewEvidenceCoverage(payload), { requested: 2, resolved: 1 });

  // An entity the payload does not carry is absent, not a fabricated entry.
  assert.equal(reviewEvidenceFor(payload, "strategy_run", "run-absent"), null);
});

test("the decisions slice is the anchor, so a missing review is not an empty one", () => {
  const payload = projection({
    decisions: slice({ available: false, rows: null, payload: null }),
    evidence: slice({ available: false, rows: null, payload: null }),
  });

  assert.equal(reviewIsUsable(payload), false);
  assert.deepEqual(reviewDecisions(payload), []);
  assert.equal(reviewLatestDecision(payload), null);
  assert.equal(reviewNeedsAttentionCount(payload), null);
  assert.deepEqual(
    degradedReviewSlices(payload).map((reading) => reading.key),
    ["decisions", "evidence"],
  );

  // The monitoring slice has no rows: it reports its payload, and a missing payload is
  // null rather than a zeroed summary.
  assert.equal(reviewMonitoring(projection({ monitoring: slice({ available: false }) })), null);
  assert.equal(reviewIsUsable(null), false);
  assert.equal(reviewIsUsable(undefined), false);
  assert.deepEqual(reviewReadings(null), []);
  assert.equal(reviewAsOf(null), null);
});

test("the review lane is on demand, gated, coalesced and retryable", () => {
  const store = readWebSource("stores/api.ts");
  const coordinator = readWebSource("stores/workspaceLoading.ts");

  // On demand: the review read is its own action, not part of the workspace batch.
  const loaders = /const WORKSPACE_LOADERS[\s\S]*?\n\];/.exec(store)?.[0] ?? "";
  assert.equal(loaders.includes("api.reviewContext"), false);
  assert.match(store, /fetchReviewContext: async \(\) => \{/);
  assert.match(
    store,
    /const refresh = readRefreshCoordinator\.review\.tryStart\(\);/,
  );
  assert.match(store, /isIdentityGateOpen\(get\(\)\.authState\)\) return;/);
  // Retryable through the same bounded control as the other projection reads.
  assert.match(store, /\["reviewContext", \(options\) => api\.reviewContext\(undefined, options\)\]/);
  assert.match(store, /reviewContext: \(state, payload\) => \{/);
  // The lane exists and an identity or workspace reset cancels it.
  assert.match(coordinator, /readonly review = new ReadRefreshLane\(\);/);
  assert.match(coordinator, /this\.review\.cancel\(\);/);
});

test("the review surface reads the projection when it opens and never fetches itself", () => {
  const workspace = readWebSource("components/DecisionWorkspace.tsx");
  const strip = readWebSource("components/ReviewContextStrip.tsx");

  assert.match(workspace, /if \(task !== "review"\) return;/);
  assert.match(workspace, /void api\.fetchReviewContext\(\);/);
  assert.match(workspace, /<ReviewContextStrip projection=\{api\.reviewContext\} t=\{t\} \/>/);

  // The strip renders the backend's reading; it does not fetch or recompute.
  assert.match(strip, /reviewReadings\(projection\)/);
  assert.match(strip, /degradedReviewSlices\(projection\)/);
  assert.match(strip, /reviewEvidenceCoverage\(projection\)/);
  for (const banned of ["useEffect", "api.", "fetch(", "Date.now"]) {
    assert.equal(strip.includes(banned), false, banned);
  }

  const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>;
  const keys = [
    "review_context.title",
    "review_context.as_of",
    "review_context.as_of_unknown",
    "review_context.time_basis",
    "review_context.all_fresh",
    "review_context.degraded",
    "review_context.rows",
    "review_context.restricted",
    "review_context.evidence_coverage",
    ...REVIEW_CONTEXT_SLICE_ORDER.map((key) => REVIEW_CONTEXT_SLICE_LABEL_KEYS[key]),
    ...["FRESH", "STALE", "MISSING", "UNKNOWN", "UNAVAILABLE"].map(
      (state) => `review_context.freshness.${state}`,
    ),
  ];
  for (const key of keys) {
    assert.ok(en[key]?.trim(), `en ${key}`);
    assert.ok(zh[key]?.trim(), `zh ${key}`);
    assert.notEqual(en[key], zh[key], key);
  }
  assert.equal(Object.keys(en).length, Object.keys(zh).length);
});
