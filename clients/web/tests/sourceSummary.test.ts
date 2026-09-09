import assert from "node:assert/strict";
import test from "node:test";
import {
  buildSourceStats,
  buildSourceSummary,
} from "../src/app/workspaceDerivedData.ts";

function stats(total: number, active: number, issues = 0) {
  return { total, active, issues };
}

test("source summary is checking while the initial empty load is in flight", () => {
  const summary = buildSourceSummary(stats(0, 0), { loading: true, dataStatus: "unavailable" });
  assert.equal(summary.viewState, "checking");
  assert.equal(summary.showCounts, false);
});

test("source endpoint failure wins over retained ready rows", () => {
  const failed = buildSourceSummary(stats(3, 3), {
    loading: false,
    sourceError: "source endpoint timed out",
    dataStatus: "runtime",
  });
  assert.equal(failed.viewState, "unavailable");
  assert.equal(failed.showCounts, false);
  const unavailable = buildSourceSummary(stats(3, 3), {
      loading: false,
      dataStatus: "unavailable",
  });
  assert.equal(unavailable.viewState, "unavailable");
  assert.equal(unavailable.showCounts, false);
});

test("completed empty source data is unknown, not ready", () => {
  const summary = buildSourceSummary(stats(0, 0), { loading: false, dataStatus: "runtime" });
  assert.equal(summary.viewState, "unknown");
  assert.equal(summary.showCounts, false);
});

test("populated but partially workflow-ready sources are explicitly partial", () => {
  const partial = buildSourceSummary(stats(3, 2), { loading: false, dataStatus: "runtime" });
  assert.equal(partial.viewState, "partial");
  assert.equal(partial.showCounts, true);
  assert.equal(partial.total, 3);
  assert.equal(partial.active, 2);
  assert.equal(partial.issues, 0);
  assert.equal(
    buildSourceSummary(stats(3, 3, 1), { loading: false, dataStatus: "runtime" }).viewState,
    "partial",
  );
  assert.equal(
    buildSourceSummary(stats(3, 3), { loading: false, dataStatus: "partial" }).viewState,
    "partial",
  );
});

test("ready requires populated all-workflow-ready source data", () => {
  const runtime = buildSourceSummary(stats(3, 3), { loading: false, dataStatus: "runtime" });
  assert.equal(runtime.viewState, "ready");
  assert.equal(runtime.showCounts, true);
  assert.equal(
    buildSourceSummary(stats(3, 3), { loading: false, dataStatus: "delayed" }).viewState,
    "ready",
  );
});

test("loading retained rows remain checking until the refresh settles", () => {
  const summary = buildSourceSummary(stats(3, 3), { loading: true, dataStatus: "runtime" });
  assert.equal(summary.viewState, "checking");
  assert.equal(summary.showCounts, false);
});

test("unknown data status fails closed without inferring readiness", () => {
  const summary = buildSourceSummary(stats(3, 3), { loading: false, dataStatus: "mystery" });
  assert.equal(summary.viewState, "unknown");
  assert.equal(summary.showCounts, false);
});

test("existing source statistics semantics remain unchanged for unknown source statuses", () => {
  const sourceStats = buildSourceStats([
    {
      connectivity_status: "mystery",
      credential_state: "configured",
      live_record_count: 4,
    },
  ]);

  assert.deepEqual(sourceStats, {
    total: 1,
    active: 0,
    issues: 0,
    records: 4,
    missingCredentials: 0,
  });
  assert.equal(
    buildSourceSummary(sourceStats, { loading: false, dataStatus: "runtime" }).viewState,
    "partial",
  );
});
