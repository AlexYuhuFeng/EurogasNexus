/**
 * A new deal changes the position on an open screen within a second (small-desk plan section 5):
 * on a position page the price, trade and book notices re-read at most every `LADDER_LIVE_MS`
 * (5 s under a busy price tape), and a `deals` notice bypasses that throttle
 * (app/hooks/useLive.ts `createLiveRereader`, `immediateTopics`).
 */
import assert from "node:assert/strict";
import test from "node:test";

import { loadApiStore } from "./support/apiStoreHarness.ts";

type UseLiveModule = typeof import("../src/app/hooks/useLive.ts");

function fakeTimers(now: () => number) {
  const timers: { fn: () => void; at: number }[] = [];
  return {
    timers,
    api: {
      set: (fn: () => void, ms: number) => {
        const timer = { fn, at: now() + ms };
        timers.push(timer);
        return timer;
      },
      clear: (handle: unknown) => {
        const index = timers.indexOf(handle as (typeof timers)[number]);
        if (index >= 0) timers.splice(index, 1);
      },
    },
  };
}

test("a deal notice re-reads at once while price notices wait out the ladder's interval", async () => {
  const { createLiveRereader, DEAL_LIVE_MS, DEAL_TOPICS } = await (await loadApiStore()).load<UseLiveModule>("/src/app/hooks/useLive.ts");
  const LADDER_LIVE_MS = 5_000;
  assert.ok(DEAL_LIVE_MS < 1_000, "the deal path stays inside the one-second target");
  let clock = 0;
  const reads: number[] = [];
  const { timers, api } = fakeTimers(() => clock);
  const rereader = createLiveRereader(() => reads.push(clock), LADDER_LIVE_MS, DEAL_TOPICS, DEAL_LIVE_MS, () => clock, api);

  rereader.notice("prices");
  assert.deepEqual(reads, [0], "the first price notice reads at once");
  clock = 200;
  rereader.notice("prices"); // a busy tape: the next price read waits for 5 s
  assert.equal(reads.length, 1);
  clock = 300;
  rereader.notice("deals");
  assert.deepEqual(reads, [0, 300], "a captured deal re-reads at once, past the price throttle");
  clock = 350;
  rereader.notice("deals"); // the rest of an import's burst: once, within DEAL_LIVE_MS
  rereader.notice("deals");
  const dealTimer = timers.find((timer) => timer.at === 300 + DEAL_LIVE_MS);
  assert.ok(dealTimer, "one trailing read for the burst of deals");
  clock = dealTimer.at;
  timers.splice(timers.indexOf(dealTimer), 1);
  dealTimer.fn();
  assert.deepEqual(reads, [0, 300, 300 + DEAL_LIVE_MS]);
  assert.ok(reads.at(-1)! - 300 < 1_000);
  // The prices keep their own interval.
  const priceTimer = timers.find((timer) => timer.at === LADDER_LIVE_MS);
  assert.ok(priceTimer, "the price read still waits for the ladder's interval");
  clock = LADDER_LIVE_MS;
  priceTimer.fn();
  assert.equal(reads.at(-1), LADDER_LIVE_MS);
  rereader.cancel();
});

test("without immediate topics every notice shares one throttle (pages that show no position)", async () => {
  const { createLiveRereader } = await (await loadApiStore()).load<UseLiveModule>("/src/app/hooks/useLive.ts");
  let clock = 0;
  const reads: number[] = [];
  const { api } = fakeTimers(() => clock);
  const rereader = createLiveRereader(() => reads.push(clock), 5_000, [], 250, () => clock, api);
  rereader.notice("prices");
  clock = 300;
  rereader.notice("deals");
  assert.deepEqual(reads, [0]);
  rereader.cancel();
});
