/**
 * Architecture V2 Wave 6 - Decision Case product surface tests.
 *
 * The panel's job is to be honest: it offers a decision only when the backend says
 * the case is decidable, shows the blockers it was refused on, keeps the actor with
 * the backend, and never implies that a decision record authorises execution.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  DECISION_EVIDENCE_KINDS,
  DECISION_OUTCOMES,
  blockerLabelKey,
  canRecordDecision,
  canReopen,
  caseCounts,
  caseStatusLabelKey,
  evidenceKindLabelKey,
  isDecided,
  isReproducible,
  outcomeLabelKey,
  splitCases,
  suggestedEvidenceRef,
} from "../src/app/model/decisionCaseModel.ts";
import type { DecisionCaseDTO, DecisionCaseSummaryDTO } from "../src/api/client.ts";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

function caseDto(overrides: Partial<DecisionCaseDTO> = {}): DecisionCaseDTO {
  return {
    case_id: "case-1",
    objective: "Decide where tomorrow's NBP resource should go.",
    status: "OPEN",
    created_by: "analyst.one",
    created_at_utc: "2026-09-16T06:00:00+00:00",
    gas_day: "2026-09-16",
    delivery_product: "day-ahead",
    hub_id: "NBP",
    portfolio_ref: "",
    snapshot_id: "snap-1",
    reproducible: true,
    assumptions: [],
    alternatives: [],
    evidence: [
      { kind: "ROUTE_RECOMMENDATION", ref: "route-rec-1", label: "", as_of_utc: "", snapshot_id: "snap-1" },
    ],
    ai_findings: [],
    warnings: [],
    records: [],
    decidable: true,
    blockers: [],
    ...overrides,
  };
}

function summary(overrides: Partial<DecisionCaseSummaryDTO> = {}): DecisionCaseSummaryDTO {
  return {
    case_id: "case-1",
    objective: "Objective",
    status: "OPEN",
    gas_day: "2026-09-16",
    delivery_product: "day-ahead",
    hub_id: "NBP",
    evidence_count: 1,
    alternative_count: 0,
    assumption_count: 0,
    record_count: 0,
    reproducible: true,
    last_record: null,
    ...overrides,
  };
}

test("a decision is offered only when the backend says the case is decidable", () => {
  assert.equal(canRecordDecision(caseDto()), true);
  assert.equal(
    canRecordDecision(caseDto({ decidable: false, blockers: ["evidence_required"] })),
    false,
  );
  assert.equal(canRecordDecision(caseDto({ status: "DECIDED" })), false);
  assert.equal(canRecordDecision(null), false);

  assert.equal(canReopen(caseDto({ status: "DECIDED" })), true);
  assert.equal(canReopen(caseDto({ status: "OPEN" })), false);
  assert.equal(canReopen(null), false);
});

test("reproducibility and decidedness come from the payload, never a guess", () => {
  assert.equal(isReproducible(caseDto()), true);
  assert.equal(isReproducible(caseDto({ reproducible: false, snapshot_id: "" })), false);
  assert.equal(isReproducible(null), false);

  assert.equal(isDecided(caseDto()), false);
  assert.equal(
    isDecided(
      caseDto({
        status: "DECIDED",
        records: [
          {
            outcome: "accepted",
            actor: "reviewer.one",
            note: "",
            evidence_refs: ["route-rec-1"],
            recorded_at_utc: "2026-09-16T07:00:00+00:00",
          },
        ],
      }),
    ),
    true,
  );
});

test("counts come from the payload and the list splits by recorded state", () => {
  const counts = caseCounts(caseDto());
  assert.deepEqual(counts, { evidence: 1, alternatives: 0, assumptions: 0, records: 0 });

  const grouped = splitCases([
    summary({ case_id: "a", status: "DRAFT" }),
    summary({ case_id: "b", status: "OPEN" }),
    summary({ case_id: "c", status: "DECIDED", record_count: 1 }),
    summary({ case_id: "d", status: "REOPENED", record_count: 2 }),
  ]);
  assert.deepEqual(grouped.open.map((row) => row.case_id), ["a", "b"]);
  assert.deepEqual(grouped.decided.map((row) => row.case_id), ["c", "d"]);
});

test("labels are stable keys, and an unknown blocker still gets one", () => {
  assert.equal(caseStatusLabelKey("decided"), "decision_case.status.DECIDED");
  assert.equal(caseStatusLabelKey(""), "decision_case.status.UNKNOWN");
  assert.equal(outcomeLabelKey("needs_attention"), "decision_case.outcome.needs_attention");
  assert.equal(
    evidenceKindLabelKey("route_recommendation"),
    "decision_case.evidence.ROUTE_RECOMMENDATION",
  );
  assert.equal(blockerLabelKey("evidence_required"), "decision_case.blocker.evidence_required");
  assert.equal(blockerLabelKey(""), "decision_case.blocker.unknown");
  assert.equal(blockerLabelKey("Something odd!"), "decision_case.blocker.something_odd_");

  assert.deepEqual([...DECISION_OUTCOMES], ["accepted", "rejected", "needs_attention"]);
  assert.ok(DECISION_EVIDENCE_KINDS.includes("ROUTE_RECOMMENDATION"));
  // The Decision Case chain names an "AI Findings/Challenge" stage, so an AI interpretation
  // run is citable evidence alongside the deterministic artefacts.
  assert.ok(DECISION_EVIDENCE_KINDS.includes("AI_ANALYSIS"));
  assert.equal(DECISION_EVIDENCE_KINDS.length, 12);
  // Every kind has copy in both locales: a selector must never render a raw identifier.
  const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>;
  for (const kind of DECISION_EVIDENCE_KINDS) {
    const key = evidenceKindLabelKey(kind);
    assert.ok(en[key]?.trim(), `en ${key}`);
    assert.ok(zh[key]?.trim(), `zh ${key}`);
    assert.notEqual(en[key], zh[key], key);
  }
});

test("the Active Context supplies identifiers instead of asking the user to type them", () => {
  assert.equal(
    suggestedEvidenceRef("ROUTE_RECOMMENDATION", { routeId: "route-9" }),
    "route-9",
  );
  assert.equal(suggestedEvidenceRef("STRATEGY_RUN", { strategyRunId: "run-3" }), "run-3");
  // The run the user just completed is offered by reference, never typed in.
  assert.equal(
    suggestedEvidenceRef("AI_ANALYSIS", { analysisId: "analysis-7" }),
    "analysis-7",
  );
  assert.equal(suggestedEvidenceRef("AI_ANALYSIS", { analysisId: null }), "");
  assert.equal(suggestedEvidenceRef("ROUTE_RECOMMENDATION", { routeId: null }), "");
  assert.equal(suggestedEvidenceRef("MANUAL", { routeId: "route-9" }), "");
});

test("the panel keeps the actor on the backend and explains refusals", () => {
  const panel = readWebSource("components/DecisionCasePanel.tsx");
  // Comments state the rules; only the executable lines are checked for payloads.
  const code = panel
    .split("\n")
    .filter((line) => {
      const trimmed = line.trim();
      return !trimmed.startsWith("*") && !trimmed.startsWith("//") && !trimmed.startsWith("/*");
    })
    .join("\n");

  // The actor is never sent: the backend records the authenticated identity.
  assert.equal(code.includes("actor:"), false);
  assert.match(panel, /api\.createDecisionCase\(/);
  assert.match(panel, /api\.attachDecisionCaseEvidence\(/);
  // The decision goes through the `apiOutcome` variant of the route, so a 409 `case_not_decidable`
  // arrives as a governed answer with its blockers instead of as a thrown transport failure.
  assert.match(panel, /api\.recordDecisionCaseDecisionOutcome\(/);
  assert.match(panel, /result\.ok/);
  assert.match(panel, /api\.reopenDecisionCase\(/);

  // Availability and blockers come from the payload.
  assert.match(panel, /canRecordDecision\(selected\)/);
  assert.match(panel, /selected\.blockers\.length > 0/);
  assert.match(panel, /blockerLabelKey\(blocker\)/);

  // Failures are explained through the product error taxonomy, not a raw status: the
  // panel hands the whole failure to `describeFailure` (which reassembles the envelope)
  // and renders resolved text through `presentError`, so no raw `errors.…` key is shown.
  assert.match(panel, /describeFailure\(error\)/);
  assert.match(panel, /presentError\(t, describeFailure\(error\)\)/);
  assert.equal(/describeApiError\(/.test(panel), false);
  assert.match(panel, /role="alert"/);

  // The no-execution boundary is stated, not implied.
  assert.match(panel, /decision_case\.boundary/);
  for (const banned of ["order", "nomination", "settle", "execute", "trade"]) {
    assert.equal(new RegExp(`\\b${banned}\\b`, "i").test(code), false, banned);
  }
});

test("the panel is mounted on the review task and its vocabulary is bilingual", () => {
  const workspace = readWebSource("components/DecisionWorkspace.tsx");
  assert.match(workspace, /import \{ DecisionCasePanel \} from "@\/components\/DecisionCasePanel"/);
  assert.match(workspace, /task === "review" && \(\s*<DecisionCasePanel/);
  assert.match(workspace, /gasDay=\{traderContext\.gasDay\}/);

  const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>;

  const keys = [
    "decision_case.title",
    "decision_case.subtitle",
    "decision_case.objective",
    "decision_case.create",
    "decision_case.empty",
    "decision_case.attach",
    "decision_case.reopen",
    "decision_case.boundary",
    "decision_case.not_reproducible",
    ...DECISION_OUTCOMES.map((outcome) => outcomeLabelKey(outcome)),
    ...DECISION_EVIDENCE_KINDS.map((kind) => evidenceKindLabelKey(kind)),
    ...[
      "DRAFT",
      "OPEN",
      "UNDER_REVIEW",
      "DECIDED",
      "REOPENED",
      "RETIRED",
      "UNKNOWN",
    ].map((status) => caseStatusLabelKey(status)),
    ...[
      "evidence_required",
      "snapshot_recommended",
      "decided_case_requires_record",
      "unknown",
    ].map((blocker) => blockerLabelKey(blocker)),
  ];
  for (const key of keys) {
    assert.ok(en[key]?.trim(), key);
    assert.ok(zh[key]?.trim(), key);
    assert.notEqual(en[key], zh[key], key);
  }
  assert.equal(Object.keys(en).length, Object.keys(zh).length);
});
