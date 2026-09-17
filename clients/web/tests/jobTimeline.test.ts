/**
 * Architecture V2 Wave 8 - job timeline tests.
 *
 * The activity surface must read the lifecycle honestly: active work first, states
 * as the backend recorded them, cancellation only where it would be accepted, and
 * failure codes explained through the taxonomy rather than printed raw.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  JOB_STATUS_BADGE_VARIANT,
  TERMINAL_JOB_STATES,
  jobCanCancel,
  jobDurationLabel,
  jobIsActive,
  jobKindLabelKey,
  jobProgressPercent,
  jobRetryable,
  jobStatusLabelKey,
  jobTimelineOrder,
  jobTimelineSummary,
} from "../src/app/model/jobTimelineModel.ts";
import { statusBadgeClass } from "../src/components/ui/statusBadgeClass.ts";
import type { JobDTO } from "../src/api/client.ts";

function readWebSource(relativePath: string): string {
  return readFileSync(new URL(`../src/${relativePath}`, import.meta.url), "utf8");
}

function job(overrides: Partial<JobDTO> = {}): JobDTO {
  return {
    job_id: "job-1",
    kind: "DATASET_BUILD",
    job_version: "job/v1",
    status: "RUNNING",
    principal: "analyst.one",
    scope_refs: [],
    snapshot_id: "",
    input_hash: "abc",
    progress: 0.4,
    created_at_utc: "2026-09-16T06:00:00+00:00",
    started_at_utc: "2026-09-16T06:00:00+00:00",
    finished_at_utc: null,
    duration_seconds: null,
    output_refs: [],
    error_code: "",
    error_message: "",
    retryable: false,
    cancellable: true,
    correlation_id: "corr-1",
    provenance: [],
    ...overrides,
  };
}

test("active work is distinguished from finished work", () => {
  assert.deepEqual([...TERMINAL_JOB_STATES], ["SUCCEEDED", "FAILED", "CANCELLED", "EXPIRED"]);
  for (const status of TERMINAL_JOB_STATES) {
    assert.equal(jobIsActive(job({ status })), false, status);
  }
  for (const status of ["QUEUED", "RUNNING", "WAITING_FOR_INPUT"] as const) {
    assert.equal(jobIsActive(job({ status })), true, status);
  }
});

test("cancellation and retry follow the payload, not the surface's hope", () => {
  assert.equal(jobCanCancel(job()), true);
  assert.equal(jobCanCancel(job({ cancellable: false })), false);
  assert.equal(jobCanCancel(job({ status: "SUCCEEDED", cancellable: true })), false);
  assert.equal(jobCanCancel(job({ status: "FAILED", cancellable: false })), false);

  assert.equal(jobRetryable(job({ status: "FAILED", retryable: true })), true);
  assert.equal(jobRetryable(job({ status: "SUCCEEDED", retryable: true })), false);
  assert.equal(jobRetryable(job({ status: "FAILED", retryable: false })), false);
});

test("progress and duration are formatted without inventing values", () => {
  assert.equal(jobProgressPercent(job({ progress: 0.42 })), 42);
  assert.equal(jobProgressPercent(job({ progress: 1.4 })), 100);
  assert.equal(jobProgressPercent(job({ progress: -1 })), 0);
  assert.equal(jobProgressPercent(job({ progress: Number.NaN })), 0);

  assert.equal(jobDurationLabel(job({ duration_seconds: null })), null);
  assert.equal(jobDurationLabel(job({ duration_seconds: 12 })), "12s");
  assert.equal(jobDurationLabel(job({ duration_seconds: 90 })), "1m 30s");
  assert.equal(jobDurationLabel(job({ duration_seconds: 7200 })), "2h 0m");
});

test("the timeline keeps active work above finished work, newest first", () => {
  const ordered = jobTimelineOrder([
    job({ job_id: "old-finished", status: "SUCCEEDED", created_at_utc: "2026-09-16T05:00:00+00:00" }),
    job({ job_id: "new-finished", status: "FAILED", created_at_utc: "2026-09-16T07:00:00+00:00" }),
    job({ job_id: "old-active", status: "RUNNING", created_at_utc: "2026-09-16T04:00:00+00:00" }),
    job({ job_id: "new-active", status: "QUEUED", created_at_utc: "2026-09-16T06:00:00+00:00" }),
  ]);

  assert.deepEqual(
    ordered.map((row) => row.job_id),
    ["new-active", "old-active", "new-finished", "old-finished"],
  );

  const summary = jobTimelineSummary(ordered);
  assert.deepEqual(summary, { active: 2, failed: 1, succeeded: 1, cancelled: 0 });

  const withCancelled = jobTimelineSummary([
    job({ status: "CANCELLED" }),
    job({ status: "EXPIRED" }),
  ]);
  assert.deepEqual(withCancelled, { active: 0, failed: 0, succeeded: 0, cancelled: 2 });
});

test("labels are stable keys and the badge uses the shared primitive", () => {
  assert.equal(jobKindLabelKey("dataset_build"), "job.kind.DATASET_BUILD");
  assert.equal(jobKindLabelKey(""), "job.kind.UNKNOWN");
  assert.equal(jobStatusLabelKey("waiting_for_input"), "job.status.WAITING_FOR_INPUT");
  assert.equal(jobStatusLabelKey(""), "job.status.UNKNOWN");

  assert.equal(JOB_STATUS_BADGE_VARIANT, "job-state");
  assert.equal(
    statusBadgeClass("job-state", "SUCCEEDED"),
    "job-state job-state-succeeded",
  );
  assert.equal(statusBadgeClass("job-state", "FAILED"), "job-state job-state-failed");
  assert.equal(statusBadgeClass("job-state", "WAITING_FOR_INPUT"), "job-state job-state-waiting_for_input");
  // The existing variants are unchanged.
  assert.equal(statusBadgeClass("source", "active"), "source-status source-status-active");
  assert.equal(statusBadgeClass("runtime-readiness-state", "ready"), "runtime-readiness-state ready");
});

test("the panel is mounted on the administration surface and is honest about failures", () => {
  const panel = readWebSource("components/JobTimeline.tsx");
  const runtime = readWebSource("components/RuntimeWorkspace.tsx");

  assert.match(runtime, /import \{ JobTimeline \} from "@\/components\/JobTimeline"/);
  assert.match(runtime, /<JobTimeline t=\{t\} \/>/);

  assert.match(panel, /api\.jobs\(\{ limit: String\(TIMELINE_LIMIT\) \}\)/);
  assert.match(panel, /api\.cancelJob\(jobId\)/);
  assert.match(panel, /jobCanCancel\(job\)/);
  assert.match(panel, /describeApiError\(\{ error: job\.error_code \}\)/);
  assert.match(panel, /role="alert"/);
  assert.match(panel, /t\("job\.title"\)/);

  const code = panel
    .split("\n")
    .filter((line) => {
      const trimmed = line.trim();
      return !trimmed.startsWith("*") && !trimmed.startsWith("//") && !trimmed.startsWith("/*");
    })
    .join("\n");
  for (const banned of ["order", "nomination", "settle", "execute", "trade"]) {
    assert.equal(new RegExp(`\\b${banned}\\b`, "i").test(code), false, banned);
  }
});

test("the job vocabulary exists in both locales", () => {
  const en = JSON.parse(readWebSource("i18n/en.json")) as Record<string, string>;
  const zh = JSON.parse(readWebSource("i18n/zh.json")) as Record<string, string>;

  const kinds = ["INGESTION", "DATASET_BUILD", "OPTIMISATION", "BACKTEST", "REPORT", "AGENT_RUN", "SNAPSHOT", "UNKNOWN"];
  const statuses = ["QUEUED", "RUNNING", "WAITING_FOR_INPUT", "SUCCEEDED", "FAILED", "CANCELLED", "EXPIRED", "UNKNOWN"];
  const keys = [
    "job.title",
    "job.subtitle",
    "job.refresh",
    "job.cancel",
    "job.outputs",
    "job.empty",
    ...kinds.map((kind) => jobKindLabelKey(kind)),
    ...statuses.map((status) => jobStatusLabelKey(status)),
  ];
  for (const key of keys) {
    assert.ok(en[key]?.trim(), key);
    assert.ok(zh[key]?.trim(), key);
    assert.notEqual(en[key], zh[key], key);
  }
  assert.equal(Object.keys(en).length, Object.keys(zh).length);
});
