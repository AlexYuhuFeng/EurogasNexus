/**
 * Background work in the notification centre: when the client polls, what it lists, how a step,
 * a failure and a result read, and the drawer section and trigger mark as they render. The store
 * is driven through the shared harness, with the HTTP boundary mocked.
 */
import assert from "node:assert/strict";
import test, { after } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "node:fs";

import type { JobDTO } from "../src/api/client.ts";
import {
  JOB_NOTICE_LIMIT,
  JOB_NOTICE_TTL_MS,
  JOB_POLL_FAST_MS,
  JOB_POLL_SLOW_MS,
  jobActivity,
  jobCanRetry,
  jobFailureText,
  jobPollDelay,
  jobResultHref,
  jobResultRef,
  jobStepText,
  newlyFinishedJobs,
  visibleJobNotices,
  type StartedJob,
} from "../src/app/jobs/backgroundJobsModel.ts";
import { closeApiStoreHarness, loadApiStore, settle } from "./support/apiStoreHarness.ts";

after(closeApiStoreHarness);

const NOW = Date.parse("2026-11-26T10:00:00Z");
const ago = (seconds: number) => new Date(NOW - seconds * 1000).toISOString();

function job(id: string, overrides: Partial<JobDTO> = {}): JobDTO {
  return {
    job_id: id, kind: "DATASET_BUILD", job_version: "job/v1", status: "RUNNING", principal: "analyst",
    scope_refs: [], snapshot_id: "", input_hash: "h", progress: 0.5, created_at_utc: ago(20),
    started_at_utc: ago(20), finished_at_utc: null, duration_seconds: null, output_refs: [],
    error_code: "", error_message: "", retryable: false, cancellable: true, correlation_id: null,
    provenance: ["research-datasets", "background-job"], step: 4, step_total: 6,
    step_label: "dataset.compute", ...overrides,
  };
}

const finished = (id: string, overrides: Partial<JobDTO> = {}) =>
  job(id, { status: "SUCCEEDED", progress: 1, finished_at_utc: ago(5), duration_seconds: 41, cancellable: false, ...overrides });

const started = (id: string, overrides: Partial<StartedJob> = {}): StartedJob => ({
  job_id: id, return_to: "/research?task=datasets", title: "TTF month-ahead next-day",
  retry: { action: "dataset-build", body: { dataset_spec: { dataset_spec_id: "s" } } },
  started_at_ms: NOW - 20_000, ...overrides,
});

/** A translator that echoes keys and options, and knows a few catalogued texts. */
const KNOWN: Record<string, string> = {
  "errors.JOB_INTERRUPTED.message": "The server restarted.",
  "errors.JOB_INTERRUPTED.action": "Start it again.",
  "errors.JOB_FAILED.message": "The background job did not complete.",
  "errors.JOB_FAILED.action": "Review and retry.",
  "jobs.step.dataset.compute": "Building the rows",
  "jobs.step.working": "Working",
};
const t = (key: string, options?: Record<string, unknown>) => {
  const base = KNOWN[key] ?? key;
  return options ? `${base}:${Object.entries(options).map(([k, v]) => `${k}=${v}`).join("|")}` : base;
};

/* ------------------------------------------------------------------ the model */

test("the client polls only while a job is active, fast at first and then calmly", () => {
  assert.equal(jobPollDelay([], NOW), null);
  assert.equal(jobPollDelay([finished("a")], NOW), null);
  assert.equal(jobPollDelay([job("a")], NOW), JOB_POLL_FAST_MS);
  assert.equal(jobPollDelay([job("a", { started_at_utc: ago(300) })], NOW), JOB_POLL_SLOW_MS);
  assert.equal(jobPollDelay([job("q", { status: "QUEUED", started_at_utc: null, created_at_utc: ago(2) })], NOW), JOB_POLL_FAST_MS);
});

test("the centre lists background jobs and jobs started here, active first, until dismissed or a day old", () => {
  const requestScoped = finished("request", { provenance: ["research-datasets"] });
  const startedHereRequestScoped = finished("mine", { provenance: [] });
  const old = finished("old", { finished_at_utc: new Date(NOW - JOB_NOTICE_TTL_MS - 1000).toISOString() });
  const running = job("running", { created_at_utc: ago(30) });
  const recent = finished("recent", { created_at_utc: ago(10) });
  const gone = finished("gone");
  const listed = visibleJobNotices(
    [recent, requestScoped, startedHereRequestScoped, old, running, gone],
    { mine: started("mine") },
    new Set(["gone"]),
    NOW,
  );
  assert.deepEqual(listed.map((row) => row.job_id), ["running", "recent", "mine"]);
  const many = Array.from({ length: JOB_NOTICE_LIMIT + 3 }, (_, index) => job(`j${index}`));
  assert.equal(visibleJobNotices(many, {}, new Set(), NOW).length, JOB_NOTICE_LIMIT);
});

test("a step reads as step x of n with its translated label; a queued job says it waits", () => {
  assert.equal(jobStepText(job("a"), t), "jobs.step_of:step=4|total=6|label=Building the rows");
  assert.equal(
    jobStepText(job("a", { step_label: "dataset.unknown_step" }), t),
    "jobs.step_of:step=4|total=6|label=Working",
  );
  assert.equal(jobStepText(job("a", { step: null, step_total: null, progress: 0.25 }), t), "jobs.percent:percent=25");
  assert.equal(jobStepText(job("a", { status: "QUEUED" }), t), "jobs.queued");
});

test("a failure reads as the catalogued text for its code, else the server's reason", () => {
  assert.deepEqual(jobFailureText({ error_code: "JOB_INTERRUPTED", error_message: "raw" }, t), {
    message: "The server restarted.",
    action: "Start it again.",
  });
  assert.deepEqual(jobFailureText({ error_code: "dataset_snapshot_conflict", error_message: "Already exists." }, t), {
    message: "Already exists.",
    action: null,
  });
  assert.deepEqual(jobFailureText({ error_code: "", error_message: "" }, t), {
    message: "The background job did not complete.",
    action: "Review and retry.",
  });
});

test("the result is the job's stored output, opened on the page that started it", () => {
  const done = finished("d", { output_refs: ["dataset_snapshot:snap-1", "dataset_snapshot_reused:true"] });
  assert.deepEqual(jobResultRef(done), { kind: "dataset_snapshot", id: "snap-1" });
  assert.deepEqual(jobResultRef(finished("r", { output_refs: ["dataset_snapshot_reused:true"] })), null);
  assert.equal(jobResultHref(done, started("d")), "/research?task=datasets&job=d");
  assert.equal(jobResultHref(done, undefined), null);
  // A stored entry can never send the user to another site.
  assert.equal(jobResultHref(done, started("d", { return_to: "//evil.example/x" })), null);
  assert.equal(jobResultHref(done, started("d", { return_to: "https://evil.example" })), null);
});

test("retry is offered for a failed or stopped job this browser can re-send", () => {
  const failed = job("f", { status: "FAILED", retryable: true });
  assert.equal(jobCanRetry(failed, started("f")), true);
  assert.equal(jobCanRetry(failed, undefined), false);
  assert.equal(jobCanRetry(job("f", { status: "FAILED", retryable: false }), started("f")), false);
  assert.equal(jobCanRetry(job("c", { status: "CANCELLED" }), started("c")), true);
  assert.equal(jobCanRetry(finished("s"), started("s")), false);
});

test("the trigger mark counts running jobs with their progress, and unseen finished ones", () => {
  const notices = [job("a", { progress: 0.5 }), job("b", { progress: 0 }), finished("c"), job("d", { status: "FAILED" })];
  assert.deepEqual(jobActivity(notices, new Set(["c"])), { running: 2, percent: 25, unseenFinished: 1, unseenFailed: 1 });
  assert.deepEqual(jobActivity([], new Set()), { running: 0, percent: null, unseenFinished: 0, unseenFailed: 0 });
  assert.deepEqual(newlyFinishedJobs([job("a"), finished("c")], [finished("a"), finished("c")]).map((row) => row.job_id), ["a"]);
});

/* ------------------------------------------------------------------ the store */

interface StoreLike {
  getState: () => {
    jobs: JobDTO[];
    started: Record<string, StartedJob>;
    dismissed: string[];
    justFinished: JobDTO[];
    bindIdentity: (id: string | null) => void;
    refresh: () => Promise<void>;
    startDatasetBuild: (spec: Record<string, unknown>, options?: Record<string, unknown>) => Promise<JobDTO>;
    startResearchRun: (body: Record<string, unknown>, options?: Record<string, unknown>) => Promise<JobDTO>;
    retry: (id: string) => Promise<JobDTO | null>;
    cancel: (id: string) => Promise<void>;
    dismiss: (id: string) => void;
    clearFinished: () => void;
    stop: () => void;
  };
}

test("starting a build records it, follows it until it finishes, and stops asking", async () => {
  const harness = await loadApiStore();
  const { useBackgroundJobsStore: store } = await harness.load<{ useBackgroundJobsStore: StoreLike }>(
    "/src/stores/backgroundJobs.ts?test=start",
  );
  let listed: JobDTO[] = [];
  harness.answer("jobs", () => ({ data: listed, meta: {} }));
  harness.answer("startDatasetBuild", () => ({ data: job("new", { status: "QUEUED", step: 0, started_at_utc: null, created_at_utc: new Date().toISOString() }), meta: {} }));
  store.getState().bindIdentity("principal-a");
  await settle();

  const queued = await store.getState().startDatasetBuild({ dataset_spec_id: "s" }, { returnTo: "/research?task=datasets", title: "My build" });
  assert.equal(queued.job_id, "new");
  assert.equal(store.getState().started.new.return_to, "/research?task=datasets");
  assert.deepEqual(store.getState().started.new.retry, {
    action: "dataset-build",
    body: { dataset_spec: { dataset_spec_id: "s" }, snapshot_id: null },
  });
  const startCall = harness.calls.find((call) => call.method === "startDatasetBuild");
  assert.deepEqual(startCall?.args, [{ dataset_spec_id: "s" }, null]);

  listed = [finished("new", { output_refs: ["dataset_snapshot:snap-1"] })];
  await store.getState().refresh();
  assert.equal(store.getState().jobs[0].status, "SUCCEEDED");
  assert.deepEqual(store.getState().justFinished.map((row) => row.job_id), ["new"]);
  const readsAfterFinish = harness.calls.filter((call) => call.method === "jobs").length;
  await new Promise((resolve) => setTimeout(resolve, JOB_POLL_FAST_MS + 200));
  assert.equal(harness.calls.filter((call) => call.method === "jobs").length, readsAfterFinish, "no polling with nothing running");
  store.getState().stop();
});

test("retry re-sends the stored request as a new job and dismisses the failed one", async () => {
  const harness = await loadApiStore();
  const { useBackgroundJobsStore: store } = await harness.load<{ useBackgroundJobsStore: StoreLike }>(
    "/src/stores/backgroundJobs.ts?test=retry",
  );
  harness.answer("jobs", () => ({ data: [], meta: {} }));
  let next = "first";
  harness.answer("startDatasetBuild", () => ({ data: job(next, { status: "QUEUED" }), meta: {} }));
  store.getState().bindIdentity("principal-b");
  await settle();
  await store.getState().startDatasetBuild({ dataset_spec_id: "s" }, { snapshotId: "snap-x", title: "Build" });
  next = "second";
  const again = await store.getState().retry("first");
  assert.equal(again?.job_id, "second");
  assert.ok(store.getState().dismissed.includes("first"));
  const starts = harness.calls.filter((call) => call.method === "startDatasetBuild");
  assert.deepEqual(starts.map((call) => call.args), [[{ dataset_spec_id: "s" }, "snap-x"], [{ dataset_spec_id: "s" }, "snap-x"]]);
  assert.equal(await store.getState().retry("unknown"), null);
  store.getState().stop();
});

test("a research run starts in the background and its retry re-sends the same request", async () => {
  const harness = await loadApiStore();
  const { useBackgroundJobsStore: store } = await harness.load<{ useBackgroundJobsStore: StoreLike }>(
    "/src/stores/backgroundJobs.ts?test=research",
  );
  harness.answer("jobs", () => ({ data: [], meta: {} }));
  let next = "run-1";
  harness.answer("startResearchRun", () => ({ data: job(next, { kind: "AGENT_RUN", status: "QUEUED" }), meta: {} }));
  store.getState().bindIdentity("principal-r");
  await settle();
  const body = { objective: "Is the NBP premium over TTF persistent today?", agent_profile: "STRATEGY_RESEARCHER" };
  await store.getState().startResearchRun(body, { returnTo: "/research?task=agents", title: "NBP premium" });
  assert.deepEqual(store.getState().started["run-1"].retry, { action: "research-run", body });
  next = "run-2";
  const again = await store.getState().retry("run-1");
  assert.equal(again?.job_id, "run-2");
  const starts = harness.calls.filter((call) => call.method === "startResearchRun");
  assert.deepEqual(starts.map((call) => call.args), [[body], [body]]);
  store.getState().stop();
});

test("another user's jobs are not carried over when the identity changes", async () => {
  const harness = await loadApiStore();
  const { useBackgroundJobsStore: store } = await harness.load<{ useBackgroundJobsStore: StoreLike }>(
    "/src/stores/backgroundJobs.ts?test=identity",
  );
  harness.answer("jobs", () => ({ data: [finished("theirs")], meta: {} }));
  store.getState().bindIdentity("principal-c");
  await settle();
  assert.equal(store.getState().jobs.length, 1);
  harness.answer("jobs", () => ({ data: [], meta: {} }));
  store.getState().bindIdentity("principal-d");
  assert.equal(store.getState().jobs.length, 0);
  store.getState().bindIdentity(null);
  store.getState().stop();
});

/* ------------------------------------------------------------------ the views */

async function views() {
  const { load } = await loadApiStore();
  return load<{
    JobNotificationsView: React.ComponentType<Record<string, unknown>>;
    JobActivityIndicatorView: React.ComponentType<Record<string, unknown>>;
  }>("/src/components/JobNotifications.tsx");
}

const noop = () => undefined;

test("the drawer section shows a running step, an open result, and a failure with retry and dismiss", async () => {
  const { JobNotificationsView } = await views();
  const html = renderToStaticMarkup(
    React.createElement(JobNotificationsView, {
      notices: [
        job("run"),
        finished("done", { output_refs: ["dataset_snapshot:snap-1"] }),
        job("fail", { status: "FAILED", error_code: "JOB_INTERRUPTED", retryable: true, cancellable: false }),
      ],
      started: { done: started("done"), fail: started("fail", { title: "Failed build" }) },
      busyJobId: null, t,
      onOpenResult: noop, onRetry: noop, onCancel: noop, onDismiss: noop, onClearFinished: noop,
    }),
  );
  assert.match(html, /role="progressbar"[^>]*aria-valuenow="50"/);
  assert.match(html, /jobs\.step_of:step=4\|total=6\|label=Building the rows/);
  assert.match(html, /jobs\.leave_hint/);
  assert.match(html, /href="\/research\?task=datasets&amp;job=done"[^>]*>jobs\.open_result/);
  assert.match(html, /The server restarted\. Start it again\./);
  assert.match(html, /jobs\.retry/);
  assert.match(html, /aria-label="jobs\.dismiss_label:name=Failed build"/);
  assert.match(html, /jobs\.clear_finished/);
  assert.match(html, /jobs\.cancel/);
  // The finished job is named by the title it was started with.
  assert.match(html, /TTF month-ahead next-day/);
});

test("the drawer section renders nothing with no background work", async () => {
  const { JobNotificationsView } = await views();
  const html = renderToStaticMarkup(
    React.createElement(JobNotificationsView, {
      notices: [], started: {}, busyJobId: null, t,
      onOpenResult: noop, onRetry: noop, onCancel: noop, onDismiss: noop, onClearFinished: noop,
    }),
  );
  assert.equal(html, "");
});

test("the trigger mark shows running work, a finished dot, or only the live region", async () => {
  const { JobActivityIndicatorView } = await views();
  const running = renderToStaticMarkup(
    React.createElement(JobActivityIndicatorView, {
      activity: { running: 1, percent: 40, unseenFinished: 0, unseenFailed: 0 }, announcement: "", t,
    }),
  );
  assert.match(running, /class="job-activity is-running"/);
  assert.match(running, /jobs\.indicator\.running:count=1\|percent=40/);
  const failed = renderToStaticMarkup(
    React.createElement(JobActivityIndicatorView, {
      activity: { running: 0, percent: null, unseenFinished: 1, unseenFailed: 1 }, announcement: "Build did not finish.", t,
    }),
  );
  assert.match(failed, /job-activity is-finished has-failed/);
  assert.match(failed, /role="status" aria-live="polite">Build did not finish\./);
  const idle = renderToStaticMarkup(
    React.createElement(JobActivityIndicatorView, {
      activity: { running: 0, percent: null, unseenFinished: 0, unseenFailed: 0 }, announcement: "", t,
    }),
  );
  assert.doesNotMatch(idle, /job-activity/);
});

test("every new jobs text exists in both locales, translated", () => {
  const en = JSON.parse(readFileSync(new URL("../src/i18n/en.json", import.meta.url), "utf8").replace(/^﻿/, ""));
  const zh = JSON.parse(readFileSync(new URL("../src/i18n/zh.json", import.meta.url), "utf8").replace(/^﻿/, ""));
  const keys = Object.keys(en).filter((key) => key.startsWith("jobs."));
  assert.ok(keys.length >= 25);
  for (const key of keys) {
    assert.ok(zh[key], `zh is missing ${key}`);
    assert.notEqual(zh[key], en[key], `zh copies en for ${key}`);
  }
  for (const step of ["resolve", "read_prices", "read_fundamentals", "compute", "write_files", "save_snapshot"]) {
    assert.ok(en[`jobs.step.dataset.${step}`], `the server's step dataset.${step} has no text`);
  }
  for (const step of ["plan", "analyse", "hypothesis", "backtest", "review"]) {
    assert.ok(en[`jobs.step.research.${step}`], `the server's step research.${step} has no text`);
  }
});

test("the stylesheet holds the motion back under reduced motion", () => {
  const css = readFileSync(new URL("../src/components/job-notifications.css", import.meta.url), "utf8");
  const animated = css.indexOf("animation:");
  const guard = css.indexOf("@media (prefers-reduced-motion: no-preference)");
  assert.ok(guard >= 0 && animated > guard, "the spin runs only when motion is welcome");
});
