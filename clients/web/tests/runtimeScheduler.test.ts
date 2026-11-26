/**
 * P1-C: the Runtime page's scheduler row reads the scheduler's heartbeat.
 *
 * The demo showed "no heartbeat, 0/42 scheduled": no scheduler process ran there, and the
 * row counted schedules in the source list, which only a scheduler scan fills. The row now
 * says the scheduler is not running, and otherwise reports its own count and its age.
 */

import assert from "node:assert/strict";
import test from "node:test";

import { schedulerReadiness } from "../src/app/model/runtimeScheduler.ts";

const t = (key: string, options?: Record<string, unknown>) =>
  options ? `${key}${JSON.stringify(options)}` : key;
const quiet = { scheduled: 0, registered: 45, stale: 0, failed: 0 };

test("no heartbeat: not running, whatever the source list says", () => {
  const row = schedulerReadiness({ state: "UNKNOWN", detail_code: "no_heartbeat", registered_sources: 45 }, quiet, t);
  assert.equal(row.state, "blocked");
  assert.equal(row.value, "runtime.scheduler_not_running");
  assert.equal(row.detail, "runtime.scheduler_no_heartbeat_detail");
});

test("a live heartbeat reports the scheduler's own count, not the source rows", () => {
  const row = schedulerReadiness(
    {
      state: "AVAILABLE",
      last_heartbeat_at_utc: "2026-11-26T12:00:00Z",
      age_seconds: 20,
      sources_scheduled: 10,
      registered_sources: 45,
    },
    quiet,
    t,
  );
  assert.equal(row.state, "ready");
  assert.equal(row.value, "10/45 runtime.scheduled_sources");
  assert.match(row.detail, /runtime\.dep_detail\.heartbeat_age/);
});

test("a stopped scheduler is blocked and says so", () => {
  const row = schedulerReadiness(
    {
      state: "UNAVAILABLE",
      last_heartbeat_at_utc: "2026-11-26T10:00:00Z",
      age_seconds: 7200,
      sources_scheduled: 10,
      registered_sources: 45,
    },
    quiet,
    t,
  );
  assert.equal(row.state, "blocked");
  assert.match(row.detail, /runtime\.scheduler_stopped_detail/);
  assert.match(row.detail, /count\\":120/);
});

test("stale sources under a live scheduler are partial", () => {
  const row = schedulerReadiness(
    { state: "AVAILABLE", last_heartbeat_at_utc: "x", age_seconds: 5, sources_scheduled: 10, registered_sources: 45 },
    { scheduled: 10, registered: 45, stale: 2, failed: 0 },
    t,
  );
  assert.equal(row.state, "partial");
});

test("before the dependencies load, the source list is used as before", () => {
  const row = schedulerReadiness(undefined, quiet, t);
  assert.equal(row.state, "blocked");
  assert.equal(row.detail, "runtime.scheduler_blocked_detail");
});
