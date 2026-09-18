/**
 * Analysis Snapshot citation on the client (Architecture V2 Wave 4, client half).
 *
 * The platform has accepted and carried a reproducibility reference since Wave 4, but no
 * client surface ever sent one - the Web client could not even list the snapshots a
 * deployment recorded. These tests pin the client half of that contract:
 *
 * - the picker offers the deployment's own references and never invents one;
 * - citing nothing leaves the report payload exactly as it was;
 * - the citation shown to the user comes from the response, not from the picker, so a run
 *   that cited nothing shows nothing and a refused reference never reaches a result;
 * - an empty list is explained by what the deployment said, not assumed to mean "none".
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { buildAnalysisPayload } from "../src/app/analysisPayload.ts";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

test("citing nothing leaves the report payload exactly as it was", () => {
  const payload = buildAnalysisPayload("Summarize", false, "en");

  assert.equal("analysis_snapshot_id" in payload, false);
  assert.deepEqual(buildAnalysisPayload("Summarize", false, "en", null), payload);
  assert.deepEqual(buildAnalysisPayload("Summarize", false, "en", ""), payload);
  assert.deepEqual(buildAnalysisPayload("Summarize", false, "en", "   "), payload);
});

test("a chosen reference is sent as the citation and changes nothing else", () => {
  const base = buildAnalysisPayload("Summarize", false, "en");
  const cited = buildAnalysisPayload("Summarize", false, "en", "asnap-2026-02-01");

  assert.equal(cited.analysis_snapshot_id, "asnap-2026-02-01");
  // The citation is an added reference, not a second request: every other input is identical,
  // and the question stays the deterministic one the surface composes.
  assert.deepEqual({ ...cited, analysis_snapshot_id: undefined }, {
    ...base,
    analysis_snapshot_id: undefined,
  });
  assert.equal(cited.question, base.question);
  assert.equal(cited.task, "PORTFOLIO_REPORT");
  assert.equal(cited.invoke_provider, false);
});

test("the report run sends no selection, not even the portfolio's resources", () => {
  // The pipeline reads no selection and the platform refuses a non-empty one
  // (`422 analysis_selection_not_supported`), so the payload carries none: naming the
  // portfolio's resources would describe a filter that was never applied.
  const payload = buildAnalysisPayload("Summarize", false, "en");
  assert.deepEqual(Object.keys(payload).sort(), [
    "invoke_provider",
    "language",
    "model",
    "provider_id",
    "question",
    "task",
  ]);

  // The resource list is not even an input any more, so it cannot reach the payload.
  const module = readWebSource("app/analysisPayload.ts");
  assert.equal(/portfolioResources|resource_id|selected_/.test(module), false);
});

test("the client reads the deployment's references from the platform surface", () => {
  const client = readWebSource("api/client.ts");

  // The list is the only source of a selectable reference: no id is composed on the client.
  assert.match(
    client,
    /analysisSnapshots: \(params\?: \{ limit\?: number \}, options\?: ApiRequestOptions\) =>\s*get<AnalysisSnapshotDTO\[\]>\(\s*"\/analysis-snapshots",/s,
  );
  assert.match(client, /export interface AnalysisSnapshotDTO \{/);
  assert.match(client, /snapshot_id: string;\n  as_of_utc: string;\n  gas_day: string;/);

  // The result may carry the citation, and its absence is a real state rather than a null.
  assert.match(client, /analysis_snapshot_id\?: string;/);
});

test("the picker offers what the deployment recorded and explains an empty list", () => {
  const review = readWebSource("components/ReviewWorkspace.tsx");

  assert.match(review, /analysisSnapshots\.map\(\(snapshot\) => \(/);
  assert.match(review, /value=\{snapshot\.snapshot_id\}/);
  assert.match(review, /onChange=\{\(event\) => onSelectSnapshot\(event\.target\.value \|\| null\)\}/);
  // Citing nothing is the default and is offered first.
  assert.match(review, /<option value="">\{t\("review\.snapshot\.none"\)\}<\/option>/);
  // An empty list is explained by the deployment's own answer, not from a client guess.
  assert.match(review, /analysisSnapshots\.length === 0/);
  assert.match(review, /analysisSnapshotSource === "runtime-db-not-configured"/);
  assert.match(review, /t\("review\.snapshot\.not_configured"\)/);
  assert.match(review, /t\("review\.snapshot\.empty"\)/);
  // The citation is rendered from the response.
  assert.match(review, /\{analysisResult\.analysis_snapshot_id && \(/);
  assert.match(review, /t\("review\.report_citation"\)/);
});

test("the read is task-scoped and gated, and the selection reaches the run", () => {
  const store = readWebSource("stores/api.ts");
  const decision = readWebSource("components/DecisionWorkspace.tsx");
  const controller = readWebSource("app/hooks/useAppController.ts");

  // Task-scoped: the reference list is only read when the review task opens.
  assert.match(decision, /if \(task !== "review"\) return;\s*void api\.fetchReviewContext\(\);\s*\/\/[\s\S]*?void api\.fetchAnalysisSnapshots\(\);/s);
  // Gated like every other read, and bounded rather than unbounded.
  assert.match(
    store,
    /fetchAnalysisSnapshots: async \(\) => \{\s*if \(logoutInProgress\) return;\s*if \(!isIdentityGateOpen\(get\(\)\.authState\)\) return;/s,
  );
  assert.match(store, /api\.analysisSnapshots\(\{ limit: SNAPSHOT_PICKER_LIMIT \}\)/);
  // The header/panel wiring carries the selection into the payload the report run uses.
  assert.match(controller, /useReviewAnalysis\(i18n\.language, api\.reviewSnapshotId\)/);
  assert.match(decision, /onGenerateReport=\{\(\) => api\.generatePortfolioReport\(review\.analysisPayload\)\}/);
  assert.match(decision, /reviewSnapshotId=\{api\.reviewSnapshotId\}/);
  assert.match(decision, /onSelectSnapshot=\{api\.setReviewSnapshotId\}/);

  // A failed read leaves the picker empty and says so rather than keeping a stale reference.
  assert.match(
    store,
    /set\(\{ analysisSnapshots: \[\], analysisSnapshotSource: null, error: String\(e\) \}\);/,
  );
});

test("every snapshot string exists in both locales, and says something different", () => {
  const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>;

  for (const key of [
    "review.snapshot.label",
    "review.snapshot.none",
    "review.snapshot.help",
    "review.snapshot.empty",
    "review.snapshot.not_configured",
    "review.report_citation",
  ]) {
    assert.ok(en[key], `en is missing ${key}`);
    assert.ok(zh[key], `zh is missing ${key}`);
    assert.notEqual(en[key], zh[key], `${key} is not translated`);
    assert.equal(en[key].includes("?"), false, `${key} carries a placeholder`);
    assert.equal(zh[key].includes("\ufffd"), false, `${key} carries a replacement character`);
  }
});
