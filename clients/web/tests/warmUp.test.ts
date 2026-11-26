import assert from "node:assert/strict";
import test from "node:test";

import { runWarmUp, startWarmUp, stopWarmUp, warmUpStepsFor, type WarmUpStep } from "../src/app/data/warmUp.ts";

// After sign-in the heavy reads of the user's tabs are asked for one at a time while idle, so the
// server's warm views hold them when a tab is first opened (application/warm_views.py).

const noWait = async () => undefined;

function steps(log: string[], fail = new Set<string>()): WarmUpStep[] {
  const step = (id: string, permissions: string[]): WarmUpStep => ({
    id,
    permissions,
    read: async () => {
      log.push(`start:${id}`);
      await new Promise((resolve) => setTimeout(resolve, 1));
      log.push(`end:${id}`);
      if (fail.has(id)) throw new Error("500");
    },
  });
  return [step("today", ["market.read"]), step("ladder", ["portfolio.read"]), step("any", [])];
}

test("only the reads of tasks the identity can use are asked for", () => {
  const all = steps([]);
  assert.deepEqual(warmUpStepsFor(["market.read"], all).map((s) => s.id), ["today", "any"]);
  assert.deepEqual(warmUpStepsFor(["portfolio.read", "market.read"], all).map((s) => s.id), ["today", "ladder", "any"]);
  assert.deepEqual(warmUpStepsFor(undefined, all).map((s) => s.id), ["any"]);
});

test("reads run one at a time, in order, and a failure is skipped", async () => {
  const log: string[] = [];
  const answered = await runWarmUp(steps(log, new Set(["today"])), new AbortController().signal, noWait);
  assert.equal(answered, 2);
  assert.deepEqual(log, ["start:today", "end:today", "start:ladder", "end:ladder", "start:any", "end:any"]);
});

test("an abort (sign-out) stops before the next read", async () => {
  const log: string[] = [];
  const controller = new AbortController();
  const idle = async () => {
    if (log.length >= 2) controller.abort();
  };
  await runWarmUp(steps(log), controller.signal, idle);
  assert.deepEqual(log, ["start:today", "end:today"]);
});

test("once per principal; another principal stops the first one's run", async () => {
  const log: string[] = [];
  let release: () => void = () => undefined;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  const first = startWarmUp("alice", ["market.read"], steps(log), () => gate);
  assert.ok(first);
  assert.equal(startWarmUp("alice", ["market.read"], steps(log), noWait), null);
  const second = startWarmUp("bob", ["portfolio.read"], steps(log), noWait);
  release();
  assert.equal(await first, 0); // alice's run was stopped before it read anything
  assert.equal(await second, 2); // bob: ladder and any
  assert.ok(!log.includes("start:today"));
  stopWarmUp();
  assert.equal(startWarmUp(null, [], steps(log), noWait), null);
});
