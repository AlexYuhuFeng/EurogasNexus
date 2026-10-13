/**
 * Training qualification for research dataset snapshots.
 *
 * A materialized snapshot is not a training dataset. These tests pin the
 * boundary: materialization status is reported separately and never turns into
 * a readiness claim, blocked / all-missing / zero-coverage snapshots say
 * "training unavailable" with concrete reasons, an answer without quality
 * metadata says "not established" instead of ready, and adequately populated
 * data is only ever a statement about the training inputs.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  researchBuildSummary,
  researchTrainingQualification,
  researchTrainingQualificationKnown,
  researchTrainingReasonKey,
  researchTrainingStatusKey,
} from "../src/app/model/researchDataModel.ts";

function source(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

/** The quality report of the UAT snapshot: COMPLETE, blocked, 100% missing. */
const BLOCKED_QUALITY = {
  rows: 730,
  origins: 365,
  observed_values: 0,
  missing_values: 730,
  missing_percentage: 100,
  temporal_integrity: "TEMPORAL_APPROXIMATE",
  minimum_coverage: 0,
  coverage: 0,
  build_blocked: true,
  source_count: 472,
};

const ADEQUATE_QUALITY = {
  rows: 100,
  origins: 100,
  observed_values: 92,
  missing_values: 8,
  missing_percentage: 8,
  temporal_integrity: "TEMPORAL_VERIFIED",
  minimum_coverage: 0.5,
  coverage: 0.92,
  build_blocked: false,
  source_count: 3,
};

test("a build_blocked snapshot is training-unavailable with the blocker named", () => {
  const qualification = researchTrainingQualification({
    qualityReport: BLOCKED_QUALITY,
    leakageIssues: [
      { severity: "BLOCKER", code: "TEMPORAL_INSUFFICIENT_IN_STRICT_DATASET" },
    ],
  });
  assert.equal(qualification.status, "unavailable");
  assert.ok(qualification.reasons.includes("qualification_materialization_blocked"));
  assert.ok(qualification.reasons.includes("qualification_leakage_blockers"));
  assert.ok(qualification.reasons.includes("qualification_all_values_missing"));
  assert.ok(qualification.reasons.includes("qualification_zero_coverage"));
  // The materialization status is not what produced the verdict.
  assert.notEqual(qualification.status, "available");
});

test("all-missing records are unavailable even without an explicit blocker", () => {
  const allMissing = researchTrainingQualification({
    qualityReport: {
      rows: 12,
      observed_values: 0,
      missing_values: 12,
      coverage: 0,
      minimum_coverage: 0,
      build_blocked: false,
    },
    leakageIssues: [],
  });
  assert.equal(allMissing.status, "unavailable");
  assert.ok(allMissing.reasons.includes("qualification_all_values_missing"));
  assert.ok(allMissing.reasons.includes("qualification_zero_coverage"));

  // Rows whose values are all missing, expressed only through the counts.
  const byCounts = researchTrainingQualification({
    qualityReport: { rows: 5, observed_values: 0, missing_values: 5, coverage: 0 },
  });
  assert.equal(byCounts.status, "unavailable");
  assert.ok(byCounts.reasons.includes("qualification_all_values_missing"));
});

test("zero coverage from the list field alone is unavailable, never ready", () => {
  // The catalog row holds no quality report; its own coverage field is zero.
  const fromList = researchTrainingQualification({}, 0);
  assert.equal(fromList.status, "unavailable");
  assert.deepEqual(fromList.reasons, ["qualification_zero_coverage"]);
  assert.equal(researchTrainingQualificationKnown(fromList), true);

  // A non-zero list coverage proves nothing, so it must not become "available".
  const nonZeroList = researchTrainingQualification({}, 0.75);
  assert.equal(nonZeroList.status, "not_established");
  assert.deepEqual(nonZeroList.reasons, ["qualification_unknown_quality"]);
  assert.equal(researchTrainingQualificationKnown(nonZeroList), false);
});

test("absent quality metadata says not established, never ready by default", () => {
  for (const evidence of [
    {},
    { qualityReport: null, leakageIssues: null },
    { qualityReport: {}, leakageIssues: [] },
  ]) {
    const qualification = researchTrainingQualification(evidence);
    assert.equal(qualification.status, "not_established");
    assert.deepEqual(qualification.reasons, ["qualification_unknown_quality"]);
  }

  // A COMPLETE materialization with coverage reported as unknown is still unknown.
  const unknownCoverage = researchTrainingQualification({ qualityReport: {} }, null);
  assert.equal(unknownCoverage.status, "not_established");
});

test("materially adequate records are available, but only as training inputs", () => {
  const qualification = researchTrainingQualification({
    qualityReport: ADEQUATE_QUALITY,
    leakageIssues: [{ severity: "WARNING", code: "DUPLICATE_CONFLICTING_OBSERVATION" }],
  });
  assert.equal(qualification.status, "available");
  assert.deepEqual(qualification.reasons, []);
  assert.equal(researchTrainingQualificationKnown(qualification), true);

  // Coverage below the spec's declared minimum is not adequate.
  const belowMinimum = researchTrainingQualification({
    qualityReport: { ...ADEQUATE_QUALITY, coverage: 0.2, minimum_coverage: 0.5 },
  });
  assert.equal(belowMinimum.status, "unavailable");
  assert.ok(belowMinimum.reasons.includes("qualification_below_minimum_coverage"));

  // A BLOCKER-severity leakage issue outranks otherwise adequate coverage.
  const leakage = researchTrainingQualification({
    qualityReport: ADEQUATE_QUALITY,
    leakageIssues: [{ severity: "BLOCKER", code: "FUTURE_INFORMATION" }],
  });
  assert.equal(leakage.status, "unavailable");
  assert.deepEqual(leakage.reasons, ["qualification_leakage_blockers"]);
});

test("a partially populated quality report stays not established, never ready", () => {
  // The false positive this pins: coverage and an observed count alone used to
  // read "available" while the blocker flag, temporal metadata, declared minimum
  // and leakage array were all omitted. Missing evidence proves nothing.
  const partial = researchTrainingQualification({
    qualityReport: { coverage: 0.5, observed_values: 1 },
  });
  assert.equal(partial.status, "not_established");
  assert.deepEqual(partial.reasons, ["qualification_unknown_quality"]);
  assert.equal(researchTrainingQualificationKnown(partial), false);

  const declared = {
    rows: 100,
    observed_values: 92,
    missing_values: 8,
    temporal_integrity: "TEMPORAL_VERIFIED",
    minimum_coverage: 0.5,
    coverage: 0.92,
    build_blocked: false,
  };
  // The control: the same report with every field declared is a positive
  // observation even though 8 values are still missing.
  assert.equal(
    researchTrainingQualification({ qualityReport: declared, leakageIssues: [] }).status,
    "available",
  );

  const omissions: Array<[string, Record<string, unknown>]> = [
    ["build_blocked omitted", { ...declared, build_blocked: undefined }],
    ["temporal metadata omitted", { ...declared, temporal_integrity: undefined }],
    ["temporal metadata unrecognised", { ...declared, temporal_integrity: "TEMPORAL_LATER" }],
    ["minimum_coverage omitted", { ...declared, minimum_coverage: undefined }],
    ["coverage omitted", { ...declared, coverage: undefined }],
    ["coverage outside 0..1", { ...declared, coverage: 1.5 }],
    ["minimum outside 0..1", { ...declared, minimum_coverage: -0.2 }],
  ];
  for (const [label, report] of omissions) {
    const qualification = researchTrainingQualification({
      qualityReport: report,
      leakageIssues: [],
    });
    assert.equal(qualification.status, "not_established", label);
    assert.deepEqual(qualification.reasons, ["qualification_unknown_quality"], label);
  }

  // An omitted leakage array is missing evidence too, even over a complete report.
  const noLeakageArray = researchTrainingQualification({ qualityReport: declared });
  assert.equal(noLeakageArray.status, "not_established");
  assert.deepEqual(noLeakageArray.reasons, ["qualification_unknown_quality"]);
});

test("the build answer's own quality evidence carries the qualification", () => {
  const summary = researchBuildSummary({
    dataset_snapshot_id: "dataset-snapshot-abc123-spec",
    dataset_spec_id: "spec",
    dataset_spec_version: "spec@dataset-spec/v1@f00dbabe",
    row_count: 730,
    column_count: 14,
    coverage: 0,
    status: "COMPLETE",
    quality_report: BLOCKED_QUALITY,
    leakage_issues: [{ severity: "BLOCKER", code: "TEMPORAL_INSUFFICIENT_IN_STRICT_DATASET" }],
  });
  assert.equal(summary?.datasetSnapshotId, "dataset-snapshot-abc123-spec");
  assert.equal(summary?.trainingQualification.status, "unavailable");
  assert.ok(summary?.trainingQualification.reasons.includes("qualification_materialization_blocked"));

  // A build answer without a snapshot id is not a build reply at all.
  assert.equal(researchBuildSummary({ detail: { error: "dataset_build_invalid" } }), null);
});

test("every status and reason the model can produce has a translated key", () => {
  const en = JSON.parse(source("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(source("i18n/zh.json")) as Record<string, string>;
  const keys = [
    "research.training_qualification",
    "research.training_qualification_help",
    "research.training_qualification_scope",
    "research.training_available",
    "research.training_unavailable",
    "research.training_not_established",
    "research.qualification_unknown_quality",
    "research.qualification_materialization_blocked",
    "research.qualification_all_values_missing",
    "research.qualification_zero_coverage",
    "research.qualification_below_minimum_coverage",
    "research.qualification_leakage_blockers",
    "research.qualification_temporal_insufficient",
  ];
  const generated = [
    researchTrainingStatusKey("available"),
    researchTrainingStatusKey("unavailable"),
    researchTrainingStatusKey("not_established"),
    "qualification_unknown_quality",
    "qualification_materialization_blocked",
    "qualification_all_values_missing",
    "qualification_zero_coverage",
    "qualification_below_minimum_coverage",
    "qualification_leakage_blockers",
    "qualification_temporal_insufficient",
  ].map((entry) => (entry.startsWith("research.") ? entry : researchTrainingReasonKey(entry)));
  for (const key of [...keys, ...generated]) {
    assert.ok(en[key]?.trim(), `en ${key}`);
    assert.ok(zh[key]?.trim(), `zh ${key}`);
    assert.notEqual(en[key], zh[key], `${key} must be translated, not copied`);
  }
});

test("the workspace and catalog surface the qualification next to materialization", () => {
  const workspace = source("components/ResearchDataWorkspace.tsx");
  assert.match(workspace, /researchTrainingQualification\(/);
  assert.match(workspace, /researchTrainingStatusKey\(qualification\.status\)/);
  assert.match(workspace, /researchTrainingReasonKey\(reason\)/);
  assert.match(workspace, /buildState\.summary\.trainingQualification/);
  // The catalog column derives from the coverage field the list endpoint
  // actually returns, and that derivation can never claim availability.
  assert.match(workspace, /researchTrainingQualification\(\{\}, dataset\.coverage\)/);
  for (const coverage of [null, undefined, 0, 0.5, 1]) {
    assert.notEqual(
      researchTrainingQualification({}, coverage).status,
      "available",
      `list-level coverage ${String(coverage)} must not claim availability`,
    );
  }
});
