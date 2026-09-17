/**
 * Analysis Snapshot recording tests (Architecture V2 Wave 4, client half).
 *
 * The platform could record a snapshot; nothing in the product did, so a user could only cite a
 * snapshot somebody else had recorded. These tests pin the rule for recording one from the
 * context the user is standing in, and the wiring that makes a recorded reference the citation
 * the next run carries:
 *
 * - only the Active Context keys the backend accepts are ever sent, so a dimension the platform
 *   cannot express is omitted here rather than silently dropped into a descriptor;
 * - a snapshot is persisted evidence, so the runtime database is a precondition, and freezing
 *   nothing is refused instead of recorded;
 * - the list is re-read from the backend after a write rather than appended optimistically.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  SNAPSHOT_CONTEXT_KEYS,
  analysisSnapshotReadiness,
  analysisSnapshotRequest,
  snapshotContextFrom,
  snapshotContextValues,
} from "../src/app/model/analysisSnapshotModel.ts";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

const CONTEXT = {
  workspace: "review",
  task: "review",
  gas_day: "2026-02-01",
  product: "WithinDay",
  hub: "NBP",
  strategy_run_id: "run-7",
};

const AS_OF = "2026-02-01T09:00:00.000Z";

test("only the context keys the backend accepts are sent", () => {
  // Organisation and a decision case are declared unsupported dimensions. A snapshot that
  // carried them would be refused by the route; omitting them here is the narrowing, and the
  // refusal (not silence) is what tells a caller a dimension is missing.
  const narrowed = snapshotContextFrom({
    ...CONTEXT,
    organization: "acme",
    decision_case: "case-1",
  });

  assert.equal("organization" in narrowed, false);
  assert.equal("decision_case" in narrowed, false);
  assert.deepEqual(Object.keys(narrowed).sort(), [
    "gas_day",
    "hub",
    "product",
    "strategy_run_id",
    "task",
    "workspace",
  ]);
  for (const key of Object.keys(narrowed)) {
    assert.ok((SNAPSHOT_CONTEXT_KEYS as readonly string[]).includes(key), key);
  }
});

test("the request carries the frozen context and the instant the caller froze it", () => {
  const request = analysisSnapshotRequest(CONTEXT, AS_OF);

  assert.equal(request.as_of_utc, AS_OF);
  assert.deepEqual(request.active_context, {
    workspace: "review",
    task: "review",
    gas_day: "2026-02-01",
    product: "WithinDay",
    hub: "NBP",
    strategy_run_id: "run-7",
  });
  // Declaration order, so two snapshots of the same context hash the same way.
  assert.deepEqual(
    Object.keys(request.active_context),
    [...SNAPSHOT_CONTEXT_KEYS].filter((key) => key in request.active_context),
  );
});

test("empty and whitespace-only context entries are not sent as values", () => {
  assert.deepEqual(snapshotContextValues({ gas_day: "  ", hub: null, task: "review" }), [
    ["task", "review"],
  ]);
  assert.deepEqual(analysisSnapshotRequest({ hub: "" }, AS_OF).active_context, {});
});

test("recording needs a runtime database, something to freeze, and no run in flight", () => {
  const ready = analysisSnapshotReadiness({
    context: CONTEXT,
    runtimeDbReady: true,
    recording: false,
  });
  assert.deepEqual(ready, { canRecord: true, blockerKeys: [], firstBlockerKey: null });

  // A snapshot is persisted evidence: the route refuses the write without a store.
  const noStore = analysisSnapshotReadiness({
    context: CONTEXT,
    runtimeDbReady: false,
    recording: false,
  });
  assert.deepEqual(noStore.blockerKeys, ["review.snapshot.blocker.runtime_db"]);
  assert.equal(noStore.firstBlockerKey, "review.snapshot.blocker.runtime_db");

  // Freezing nothing names no version set, so it is refused here rather than recorded.
  const empty = analysisSnapshotReadiness({
    context: { gas_day: "  ", task: null },
    runtimeDbReady: true,
    recording: false,
  });
  assert.deepEqual(empty.blockerKeys, ["review.snapshot.blocker.empty_context"]);

  const inFlight = analysisSnapshotReadiness({
    context: CONTEXT,
    runtimeDbReady: true,
    recording: true,
  });
  assert.deepEqual(inFlight.blockerKeys, ["review.snapshot.blocker.in_flight"]);

  // A real precondition is reported first, and several are all reported.
  assert.deepEqual(
    analysisSnapshotReadiness({ context: {}, runtimeDbReady: false, recording: true }).blockerKeys,
    [
      "review.snapshot.blocker.runtime_db",
      "review.snapshot.blocker.empty_context",
      "review.snapshot.blocker.in_flight",
    ],
  );
});

test("the store records through the platform and reads the list back", () => {
  const store = readWebSource("stores/api.ts");
  const client = readWebSource("api/client.ts");

  assert.match(
    client,
    /createAnalysisSnapshot: \(\s*body: \{ as_of_utc: string; active_context: Record<string, string> \},\s*options\?: ApiRequestOptions,\s*\) => post<AnalysisSnapshotDTO>\("\/analysis-snapshots", body, options\)/s,
  );
  assert.match(
    store,
    /recordAnalysisSnapshot: async \(context, runtimeDbReady\) => \{[\s\S]*?const readiness = analysisSnapshotReadiness\(\{ context: snapshotContextFrom\(context\), runtimeDbReady, recording: false \}\);[\s\S]*?if \(!readiness\.canRecord\) return readiness\.firstBlockerKey;/s,
  );
  assert.match(store, /api\.createAnalysisSnapshot\(\s*analysisSnapshotRequest\(snapshotContextFrom\(context\), new Date\(\)\.toISOString\(\)\),\s*\)/s);
  // The recorded reference becomes the next citation, and the list is re-read rather than
  // appended to: the record the deployment holds is the evidence.
  assert.match(store, /set\(\{ reviewSnapshotId: recorded, snapshotMessage: "recorded" \}\);/);
  assert.match(store, /await get\(\)\.fetchAnalysisSnapshots\(\);/);
  assert.match(store, /if \(!isIdentityGateOpen\(get\(\)\.authState\)\) return null;/);
});

test("the surface offers the step beside the reference it creates", () => {
  const review = readWebSource("components/ReviewWorkspace.tsx");
  const decision = readWebSource("components/DecisionWorkspace.tsx");

  assert.match(review, /t\("review\.snapshot\.record"\)/);
  assert.match(review, /disabled=\{!snapshotReadiness\.canRecord\}/);
  assert.match(review, /t\(snapshotReadiness\.firstBlockerKey\)/);
  assert.match(review, /onClick=\{onRecordSnapshot\}/);
  // Recording is a bounded step next to the picker, not the workspace's primary action: the
  // review task's primary slot stays empty because its act is the three-outcome decision.
  assert.equal(review.includes("primaryAction"), false);
  assert.match(review, /\{snapshotMessage === "recorded" && \(/);

  // The context it freezes is the Active Context the shell already holds.
  assert.match(
    decision,
    /snapshotReadiness=\{analysisSnapshotReadiness\(\{\s*context: snapshotContextFrom\(\{\s*workspace: "review",\s*task,\s*gas_day: traderContext\.gasDay,\s*product: traderContext\.deliveryProduct,\s*hub: traderContext\.hubId,\s*strategy_run_id: selection\.strategyRunId \?\? "",\s*\}\),/s,
  );
  assert.match(decision, /void api\.recordAnalysisSnapshot\(/);
  assert.match(decision, /onSelectSnapshot=\{api\.setReviewSnapshotId\}/);
});

test("every new snapshot string exists in both locales, and says something different", () => {
  const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>;

  for (const key of [
    "review.snapshot.record",
    "review.snapshot.record_hint",
    "review.snapshot.recorded",
    "review.snapshot.blocker.runtime_db",
    "review.snapshot.blocker.empty_context",
    "review.snapshot.blocker.in_flight",
  ]) {
    assert.ok(en[key], `en is missing ${key}`);
    assert.ok(zh[key], `zh is missing ${key}`);
    assert.notEqual(en[key], zh[key], `${key} is not translated`);
    assert.equal(en[key].includes("?"), false, `${key} carries a placeholder`);
    assert.equal(zh[key].includes("\ufffd"), false, `${key} carries a replacement character`);
  }
});
